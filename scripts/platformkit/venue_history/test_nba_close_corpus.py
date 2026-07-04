"""Tests for scripts.platformkit.venue_history.nba_close_corpus (+ nba_close_corpus_kalshi).
Offline, synthetic fixtures only -- no dependency on real disk corpora."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.platformkit.venue_history import nba_close_corpus as ncc
from scripts.platformkit.venue_history import nba_close_corpus_kalshi as nck


def _sched(rows):
    """rows: list of (date_str, home, away, home_win) -> a ScheduleIndex."""
    idx = {}
    for date_str, home, away, hw in rows:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        ch, ca = ncc.canonical("nba", home), ncc.canonical("nba", away)
        gid = f"g_{date_str}_{home}_{away}"
        idx.setdefault(frozenset([ch, ca]), []).append((d, gid, home, away, hw))
    return ncc.ScheduleIndex(idx)


def _comm(rows):
    """rows: list of (commence_iso, home, away) -> a CommenceIndex."""
    idx = {}
    for iso, home, away in rows:
        ct = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        key = frozenset([ncc.canonical("nba", home), ncc.canonical("nba", away)])
        idx.setdefault(key, []).append((ct, home, away))
    return ncc.CommenceIndex(idx, len(rows))


def test_schedule_index_exact_and_near_date_match() -> None:
    sched = _sched([("2024-12-25", "NYK", "SAS", 1.0)])
    # exact date
    m = sched.match("2024-12-25", "Spurs", "Knicks")  # order-agnostic, full names
    assert m is not None and m[2] == "NYK" and m[3] == "SAS"
    # +/-1 day tolerance (late UTC tip logged a day off)
    m2 = sched.match("2024-12-26", "Spurs", "Knicks")
    assert m2 is not None
    # no match at all -> None, never a guess
    assert sched.match("2024-12-25", "Lakers", "Celtics") is None


def test_schedule_index_ambiguous_same_pair_twice_same_window_is_excluded() -> None:
    # Two games between the same pair land within the +/-1 day window of a
    # THIRD probe date that exactly matches neither -> ambiguous -> None.
    sched = _sched([
        ("2024-12-24", "NYK", "SAS", 1.0),
        ("2024-12-26", "NYK", "SAS", 0.0),
    ])
    assert sched.match("2024-12-25", "NYK", "SAS") is None
    # exact-date hits are unambiguous even with another candidate nearby
    assert sched.match("2024-12-24", "NYK", "SAS") is not None


def test_commence_index_nearest_within_tolerance() -> None:
    comm = _comm([("2024-11-16T00:30:00Z", "Atlanta Hawks", "Washington Wizards")])
    m = comm.match("2024-11-15", "Hawks", "Wizards")
    assert m == datetime(2024, 11, 16, 0, 30, tzinfo=timezone.utc)
    assert comm.match("2024-11-15", "Lakers", "Celtics") is None


def test_last_tick_before_picks_latest_strictly_before_cutoff() -> None:
    cutoff = datetime(2024, 11, 16, 0, 30, tzinfo=timezone.utc)
    prices = [
        {"ts": "2024-11-16T00:00:00Z", "prob_home": 0.5},
        {"ts": "2024-11-16T00:29:00Z", "prob_home": 0.6},
        {"ts": "2024-11-16T00:30:00Z", "prob_home": 0.9},  # AT cutoff -- excluded (strict <)
        {"ts": "2024-11-16T00:31:00Z", "prob_home": 0.95},  # after -- excluded
    ]
    tick = ncc._last_tick_before(prices, cutoff, "prob_home")
    assert tick is not None
    ts, p = tick
    assert ts == datetime(2024, 11, 16, 0, 29, tzinfo=timezone.utc)
    assert p == 0.6


def test_build_from_polymarket_flips_prob_when_pm_home_label_is_backwards(tmp_path: Path) -> None:
    """The CRITICAL DATA FIX: PM's 'home' field is outcome[0] (market listing
    order), not necessarily the true venue home team. Here PM lists SAS as
    outcome[0]/'home' but games.parquet says NYK is the real home team --
    close_prob_home must be flipped (1 - p) to represent P(NYK wins)."""
    pm_dir = tmp_path / "pm_nba"
    pm_dir.mkdir()
    doc = {
        "date": "2024-12-25", "event_slug": "nba-dailies-2024-12-25",
        "market_slug": "nba-sas-nyk-2024-12-25", "sport": "nba",
        "home": "Spurs", "away": "Knicks", "outcome_home_win": 0,
        "closed": True, "token_home": "T0", "n_prices": 2,
        "prices": [
            {"ts": "2024-12-25T16:00:00Z", "prob_home": 0.30},  # P(Spurs win) = 0.30
            {"ts": "2024-12-25T21:59:00Z", "prob_home": 0.35},  # last tick before tip
        ],
    }
    (pm_dir / "2024-12-25_nba-dailies-2024-12-25.jsonl").write_text(
        json.dumps(doc) + "\n", encoding="utf-8")

    sched = _sched([("2024-12-25", "NYK", "SAS", 1.0)])
    comm = _comm([("2024-12-25T22:00:00Z", "New York Knicks", "San Antonio Spurs")])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm, exclusions)
    assert len(rows) == 1
    r = rows[0]
    assert r["home_team"] == "NYK" and r["away_team"] == "SAS"
    # P(Spurs win)=0.35 at close -> P(NYK wins) = 1 - 0.35 = 0.65 (flipped)
    assert r["close_prob_home"] == 0.65
    assert r["home_win"] == 1.0
    assert r["validation_only"] is True
    assert sum(exclusions.values()) == 0


def test_build_from_polymarket_no_flip_when_pm_home_matches_real_home(tmp_path: Path) -> None:
    pm_dir = tmp_path / "pm_nba2"
    pm_dir.mkdir()
    doc = {
        "date": "2024-11-15", "event_slug": "nba-games", "market_slug": "nba-bos-mia-2024-11-15",
        "sport": "nba", "home": "Celtics", "away": "Heat", "outcome_home_win": 1,
        "closed": True, "token_home": "T1", "n_prices": 1,
        "prices": [{"ts": "2024-11-15T23:00:00Z", "prob_home": 0.7}],
    }
    (pm_dir / "2024-11-15_nba-games.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    sched = _sched([("2024-11-15", "BOS", "MIA", 1.0)])
    comm = _comm([("2024-11-16T00:00:00Z", "Boston Celtics", "Miami Heat")])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm, exclusions)
    assert len(rows) == 1
    assert rows[0]["close_prob_home"] == 0.7  # no flip needed


def test_build_from_polymarket_dedups_identical_repeated_docs(tmp_path: Path) -> None:
    """PM files carry benign byte-identical duplicate lines -- must count once."""
    pm_dir = tmp_path / "pm_dedup"
    pm_dir.mkdir()
    doc = {
        "date": "2024-11-15", "event_slug": "nba-games", "market_slug": "nba-bos-mia-2024-11-15",
        "sport": "nba", "home": "Celtics", "away": "Heat", "outcome_home_win": 1,
        "closed": True, "token_home": "T1", "n_prices": 1,
        "prices": [{"ts": "2024-11-15T23:00:00Z", "prob_home": 0.7}],
    }
    line = json.dumps(doc) + "\n"
    (pm_dir / "2024-11-15_nba-games.jsonl").write_text(line + line, encoding="utf-8")
    sched = _sched([("2024-11-15", "BOS", "MIA", 1.0)])
    comm = _comm([("2024-11-16T00:00:00Z", "Boston Celtics", "Miami Heat")])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm, exclusions)
    assert len(rows) == 1  # not 2


def test_build_from_polymarket_excludes_and_counts_honestly(tmp_path: Path) -> None:
    pm_dir = tmp_path / "pm_excl"
    pm_dir.mkdir()
    # 1) no schedule match at all
    doc_a = {"date": "2024-11-15", "market_slug": "a", "home": "Lakers", "away": "Celtics",
             "prices": [{"ts": "2024-11-15T23:00:00Z", "prob_home": 0.5}]}
    # 2) schedule matches but no commence_time reference available
    doc_b = {"date": "2024-11-15", "market_slug": "b", "home": "Bulls", "away": "Wizards",
             "prices": [{"ts": "2024-11-15T23:00:00Z", "prob_home": 0.5}]}
    (pm_dir / "day.jsonl").write_text(
        json.dumps(doc_a) + "\n" + json.dumps(doc_b) + "\n", encoding="utf-8")
    sched = _sched([("2024-11-15", "CHI", "WAS", 1.0)])  # only doc_b's pair is scheduled
    comm = _comm([])  # no commence_time reference at all
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm, exclusions)
    assert rows == []
    assert exclusions["no_schedule_match"] == 1  # doc_a
    assert exclusions["no_commence_time_reference"] == 1  # doc_b


def test_build_from_polymarket_falls_back_to_extra_commence_index(tmp_path: Path) -> None:
    """Primary comm has no match for this game (simulates the pre-2024-11-15
    odds_api gap); comm_extra (e.g. ESPN backfill) supplies the tipoff time
    instead. Primary is tried first and wins when both have a match --
    covered by test_build_from_polymarket_no_flip_when_pm_home_matches_real_home
    which never even builds an extra index (default None)."""
    pm_dir = tmp_path / "pm_fallback"
    pm_dir.mkdir()
    doc = {
        "date": "2023-02-23", "market_slug": "nba-ind-bos-2023-02-23",
        "home": "Pacers", "away": "Celtics",
        "prices": [{"ts": "2023-02-23T23:00:00Z", "prob_home": 0.4}],
    }
    (pm_dir / "day.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    sched = _sched([("2023-02-23", "IND", "BOS", 0.0)])
    comm_primary = _comm([])  # odds_api has no 2023 coverage -- no match
    comm_extra = _comm([("2023-02-23T23:30:00Z", "Indiana Pacers", "Boston Celtics")])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm_primary, exclusions,
                                      comm_extra=comm_extra)
    assert len(rows) == 1
    assert rows[0]["close_prob_home"] == 0.4
    assert sum(exclusions.values()) == 0


def test_build_from_polymarket_no_extra_index_stays_honest_exclusion(tmp_path: Path) -> None:
    """Without comm_extra, a game outside the primary index's coverage is
    STILL excluded -- confirms the fallback is additive, never a silent
    behavior change for callers that don't pass it (e.g. Kalshi builder)."""
    pm_dir = tmp_path / "pm_no_fallback"
    pm_dir.mkdir()
    doc = {
        "date": "2023-02-23", "market_slug": "nba-ind-bos-2023-02-23",
        "home": "Pacers", "away": "Celtics",
        "prices": [{"ts": "2023-02-23T23:00:00Z", "prob_home": 0.4}],
    }
    (pm_dir / "day.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    sched = _sched([("2023-02-23", "IND", "BOS", 0.0)])
    comm_primary = _comm([])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = ncc._build_from_polymarket(pm_dir, "test_corpus", sched, comm_primary, exclusions)
    assert rows == []
    assert exclusions["no_commence_time_reference"] == 1


def test_kalshi_tail_split_unique_match_resolves(tmp_path: Path) -> None:
    sched = _sched([("2026-04-26", "BOS", "PHI", 1.0)])
    m = nck.match_tail_to_schedule("PHIBOS", "2026-04-26", sched)
    assert m is not None
    game_id, real_home, real_away, home_win = m
    assert real_home == "BOS" and real_away == "PHI"


def test_kalshi_tail_split_no_match_is_honest_none() -> None:
    sched = _sched([("2026-04-26", "BOS", "PHI", 1.0)])
    assert nck.match_tail_to_schedule("XXXYYY", "2026-04-26", sched) is None


def test_build_from_kalshi_end_to_end_with_flip(tmp_path: Path) -> None:
    kal_dir = tmp_path / "kalshi_nba"
    kal_dir.mkdir()
    # PHI-side ticker: prob = P(PHI wins). Real home is BOS -> must flip.
    doc = {
        "ticker": "KXNBAGAME-26APR26BOSPHI-PHI", "event_ticker": "KXNBAGAME-26APR26BOSPHI",
        "series_ticker": "KXNBAGAME", "sport": "nba", "close_time": "2026-04-27T01:37:43Z",
        "result": "no", "candles": [
            {"ts": "2026-04-26T22:00:00Z", "prob": 0.30, "traded": False},
            {"ts": "2026-04-26T23:59:00Z", "prob": 0.32, "traded": False},
        ],
    }
    (kal_dir / "KXNBAGAME-26APR26BOSPHI-PHI.jsonl").write_text(
        json.dumps(doc) + "\n", encoding="utf-8")
    sched = _sched([("2026-04-26", "BOS", "PHI", 1.0)])
    comm = _comm([("2026-04-27T00:00:00Z", "Boston Celtics", "Philadelphia 76ers")])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = nck.build_from_kalshi(kal_dir, sched, comm, exclusions)
    assert len(rows) == 1
    r = rows[0]
    assert r["home_team"] == "BOS" and r["away_team"] == "PHI"
    assert r["close_prob_home"] == 0.68  # 1 - 0.32 (PHI-side prob flipped to home)
    assert r["venue"] == "kalshi"
    assert sum(exclusions.values()) == 0


def test_build_from_kalshi_unparseable_ticker_is_excluded(tmp_path: Path) -> None:
    kal_dir = tmp_path / "kalshi_bad"
    kal_dir.mkdir()
    doc = {"ticker": "NOT-A-VALID-TICKER", "candles": []}
    (kal_dir / "bad.jsonl").write_text(json.dumps(doc) + "\n", encoding="utf-8")
    sched = _sched([])
    comm = _comm([])
    exclusions = {"malformed_doc": 0, "no_schedule_match": 0,
                  "no_commence_time_reference": 0, "no_tick_before_tipoff": 0,
                  "kalshi_unparseable_ticker": 0}
    rows = nck.build_from_kalshi(kal_dir, sched, comm, exclusions)
    assert rows == []
    assert exclusions["kalshi_unparseable_ticker"] == 1


def test_build_corpus_end_to_end_writes_parquet_and_reports_honestly(tmp_path: Path) -> None:
    """Full build_corpus() wiring: PM(2023 pilot)+PM(2024plus)+Kalshi against
    injected indices, writes a real parquet, honest counts."""
    pm23 = tmp_path / "pm23"
    pm24 = tmp_path / "pm24"
    kal = tmp_path / "kal"
    pm23.mkdir(); pm24.mkdir(); kal.mkdir()

    doc24 = {
        "date": "2024-11-15", "market_slug": "nba-bos-mia-2024-11-15",
        "home": "Celtics", "away": "Heat",
        "prices": [{"ts": "2024-11-15T23:00:00Z", "prob_home": 0.7}],
    }
    (pm24 / "day.jsonl").write_text(json.dumps(doc24) + "\n", encoding="utf-8")

    import scripts.platformkit.venue_history.nba_close_corpus as m
    orig_23, orig_24, orig_k = m.PM_NBA_2023, m.PM_NBA_2024PLUS, m.KALSHI_NBA
    m.PM_NBA_2023, m.PM_NBA_2024PLUS, m.KALSHI_NBA = pm23, pm24, kal
    try:
        sched = _sched([("2024-11-15", "BOS", "MIA", 1.0)])
        comm = _comm([("2024-11-16T00:00:00Z", "Boston Celtics", "Miami Heat")])
        out_path = tmp_path / "out.parquet"
        rep = m.build_corpus(out_path=out_path, schedule_index=sched, commence_index=comm,
                             commence_index_extra=_comm([]))  # hermetic: no real ESPN cache hit
    finally:
        m.PM_NBA_2023, m.PM_NBA_2024PLUS, m.KALSHI_NBA = orig_23, orig_24, orig_k

    assert rep["n_games_written"] == 1
    assert out_path.exists()
    import pandas as pd
    df = pd.read_parquet(out_path)
    assert len(df) == 1
    assert df.iloc[0]["validation_only"] == True  # noqa: E712
    assert df.iloc[0]["close_prob_home"] == 0.7
