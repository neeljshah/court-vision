"""test_espn_wp_reference.py -- extractor + as-of join tests for the ESPN
win-probability EXTERNAL REFERENCE ingest (scripts.platformkit.espn_wp_reference).

NO network: all summary payloads are synthetic dicts shaped like the real
site.api.espn.com summary?event={id} response (verified live 2026-07-03).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.espn_wp_reference import (
    SUPPORTED_SPORTS, UNSUPPORTED_SPORTS, extract_latest, build_asof_series,
    get_outcome, capture_one, append_snapshot,
)


def _summary(wp, plays, home_winner=True, completed=True):
    return {
        "winprobability": wp,
        "plays": plays,
        "meta": {"lastUpdatedAt": "2026-06-19T21:15:00Z"},
        "header": {"competitions": [{
            "competitors": [
                {"homeAway": "home", "winner": home_winner if completed else None},
                {"homeAway": "away", "winner": (not home_winner) if completed else None},
            ]
        }]},
    }


def test_extract_latest_returns_last_point():
    wp = [{"homeWinPercentage": 0.6, "playId": "p1"},
          {"homeWinPercentage": 0.75, "playId": "p2"}]
    summary = _summary(wp, [])
    rec = extract_latest("mlb", "999", summary)
    assert rec is not None
    assert rec["espn_wp_home"] == 0.75
    assert rec["n_wp_points"] == 2
    assert rec["last_play_id"] == "p2"
    assert rec["event_id"] == "999"


def test_extract_latest_none_when_empty():
    summary = _summary([], [])
    assert extract_latest("mlb", "999", summary) is None


def test_build_asof_series_joins_by_playid_and_sorts():
    wp = [{"homeWinPercentage": 0.7, "playId": "p2"},
          {"homeWinPercentage": 0.6, "playId": "p1"}]
    plays = [
        {"id": "p1", "wallclock": "2026-06-19T18:20:00Z", "homeScore": 0, "awayScore": 0},
        {"id": "p2", "wallclock": "2026-06-19T18:25:00Z", "homeScore": 1, "awayScore": 0},
    ]
    series = build_asof_series(_summary(wp, plays))
    assert [r["play_id"] for r in series] == ["p1", "p2"]
    assert series[0]["wallclock"] < series[1]["wallclock"]


def test_build_asof_series_drops_unmatched_playid():
    wp = [{"homeWinPercentage": 0.7, "playId": "orphan"},
          {"homeWinPercentage": 0.6, "playId": "p1"}]
    plays = [{"id": "p1", "wallclock": "2026-06-19T18:20:00Z", "homeScore": 0, "awayScore": 0}]
    series = build_asof_series(_summary(wp, plays))
    assert len(series) == 1
    assert series[0]["play_id"] == "p1"


def test_build_asof_series_empty_when_no_plays_or_wp():
    assert build_asof_series(_summary([], [])) == []
    assert build_asof_series({"winprobability": [{"homeWinPercentage": 0.5, "playId": "p1"}]}) == []


def test_get_outcome_home_win():
    outcome = get_outcome(_summary([], [], home_winner=True, completed=True))
    assert outcome == {"home_win": True, "completed": True}


def test_get_outcome_none_when_incomplete():
    assert get_outcome(_summary([], [], completed=False)) is None


def test_get_outcome_none_when_no_competitions():
    assert get_outcome({"header": {"competitions": []}}) is None


def test_unsupported_sports_recorded_with_reason():
    assert "soccer" in UNSUPPORTED_SPORTS
    assert "tennis" in UNSUPPORTED_SPORTS
    assert SUPPORTED_SPORTS["mlb"] == "baseball/mlb"
    assert SUPPORTED_SPORTS["wnba"] == "basketball/wnba"
    assert set(SUPPORTED_SPORTS) & set(UNSUPPORTED_SPORTS) == set()


def test_capture_one_skips_unsupported_sport_without_network():
    # No network call should be attempted for a sport in UNSUPPORTED_SPORTS.
    assert capture_one("soccer", "401879301") is None
    assert capture_one("tennis", "12345") is None


def test_append_snapshot_writes_jsonl(tmp_path, monkeypatch):
    import scripts.platformkit.espn_wp_reference as mod
    monkeypatch.setattr(mod, "_REPO", tmp_path)
    record = {"event_id": "1", "sport": "mlb", "ts": "t", "espn_wp_home": 0.5,
              "n_wp_points": 1, "last_play_id": "p1"}
    path = append_snapshot("mlb", "1", record)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == record


def test_wallclock_join_never_uses_future_wp_point():
    """Property: a WP point's play wallclock must never be AFTER the tick ts it's
    matched to. This mirrors the nearest-prior join used in the measurement
    script (_nearest_prior in espn_wp_backfill_measure)."""
    from scripts.platformkit.espn_wp_backfill_measure import _nearest_prior
    series = [
        {"wallclock": "2026-06-19T18:20:00Z", "home_win_pct": 0.5},
        {"wallclock": "2026-06-19T18:30:00Z", "home_win_pct": 0.6},
        {"wallclock": "2026-06-19T18:40:00Z", "home_win_pct": 0.7},
    ]
    tick_ts = "2026-06-19T18:35:00Z"
    point = _nearest_prior(series, tick_ts)
    assert point is not None
    assert point["wallclock"] <= tick_ts
    assert point["home_win_pct"] == 0.6  # not the 18:40 (future) point


def test_wallclock_join_none_when_all_points_are_future():
    from scripts.platformkit.espn_wp_backfill_measure import _nearest_prior
    series = [{"wallclock": "2026-06-19T19:00:00Z", "home_win_pct": 0.9}]
    assert _nearest_prior(series, "2026-06-19T18:00:00Z") is None


def test_parse_ticker_extracts_date_and_team_suffix():
    from scripts.platformkit.espn_wp_backfill_measure import parse_ticker
    result = parse_ticker("KXMLBGAME-26JUL011310TEXCLE")
    assert result == ("20260701", "TEXCLE")


def test_parse_ticker_none_for_numeric_event_id():
    from scripts.platformkit.espn_wp_backfill_measure import parse_ticker
    assert parse_ticker("401815820") is None


def test_brier_matches_hand_computation():
    from scripts.platformkit.espn_wp_backfill_measure import _brier
    preds = [0.8, 0.3]
    outcomes = [1, 0]
    expected = ((0.8 - 1) ** 2 + (0.3 - 0) ** 2) / 2
    assert _brier(preds, outcomes) == pytest.approx(expected)


def test_brier_none_on_empty():
    from scripts.platformkit.espn_wp_backfill_measure import _brier
    assert _brier([], []) is None


def test_measure_mlb_insufficient_when_dirs_missing(tmp_path, monkeypatch):
    import scripts.platformkit.espn_wp_backfill_measure as mod
    monkeypatch.setattr(mod, "_REPO", tmp_path)
    result = mod.measure_mlb()
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_measure_mlb_skips_ticks_with_none_model_or_market_prob(tmp_path, monkeypatch):
    # LANE 5 regression: a tick with model_prob/market_prob == None (first-tick
    # placeholder rows on newly-resolved games) must be SKIPPED, never poison the
    # whole aggregate to NaN via float(None-default nan).
    import scripts.platformkit.espn_wp_backfill_measure as mod
    monkeypatch.setattr(mod, "_REPO", tmp_path)
    monkeypatch.setattr(mod, "_MIN_OVERLAP", 1)

    wp_dir = tmp_path / "data" / "domains" / "mlb" / "espn_wp"
    wp_dir.mkdir(parents=True)
    grade_dir = tmp_path / "data" / "cache" / "ingame_grade" / "mlb"
    grade_dir.mkdir(parents=True)

    series = [{"wallclock": "2026-07-04T04:05:00Z", "home_win_pct": 0.5}]
    (wp_dir / "999_series.json").write_text(json.dumps({
        "event_id": "999", "capture_name": "999", "series": series,
        "outcome": {"home_win": True, "completed": True},
    }), encoding="utf-8")

    ticks = [
        {"ts": "2026-07-04T04:05:18Z", "model_prob": None, "market_prob": None},
        {"ts": "2026-07-04T04:06:18Z", "model_prob": 0.6, "market_prob": 0.55},
    ]
    with (grade_dir / "999.jsonl").open("w", encoding="utf-8") as f:
        for t in ticks:
            f.write(json.dumps(t) + "\n")

    result = mod.measure_mlb()
    assert result["verdict"] == "MEASURED"
    assert result["n_overlap_ticks"] == 1  # the None-prob tick was skipped, not counted
    assert result["brier_our_model"] == pytest.approx((0.6 - 1) ** 2)
    assert result["brier_venue"] == pytest.approx((0.55 - 1) ** 2)


# --------------------------------------------------------------------------------------- #
# LANE 5: fuzzy alias-fallback resolver. 36 (this corpus: 28) espn_wp backfill games missed
# strict suffix-concat resolution on abbreviation-spelling mismatches (our ticker's "AZ" vs
# ESPN's "ARI", "CWS" vs ESPN's "CHW", etc.) -- reuses team_resolver.canonical(), no new
# alias map invented. Network-free: scoreboard payloads are injected fixtures shaped like
# the real site.api.espn.com scoreboard response (trimmed to the fields these functions read).
# --------------------------------------------------------------------------------------- #
def _scoreboard(events):
    """events: list of (event_id, away_abbr, home_abbr)."""
    return {"events": [
        {"id": eid, "competitions": [{"competitors": [
            {"homeAway": "away", "team": {"abbreviation": away}},
            {"homeAway": "home", "team": {"abbreviation": home}},
        ]}]}
        for eid, away, home in events
    ]}


def test_split_team_suffix_unambiguous_two_and_three_char_codes():
    from scripts.platformkit.espn_wp_backfill_measure import _split_team_suffix
    # "AZSTL" -> away=AZ (2), home=STL (3): the only split where both halves are known
    # MLB codes/aliases (team_resolver's own map, not reinvented here).
    assert _split_team_suffix("mlb", "AZSTL") == [("AZ", "STL")]
    assert _split_team_suffix("mlb", "SFAZ") == [("SF", "AZ")]
    assert _split_team_suffix("mlb", "CWSDET") == [("CWS", "DET")]


def test_split_team_suffix_no_split_for_unknown_codes():
    from scripts.platformkit.espn_wp_backfill_measure import _split_team_suffix
    assert _split_team_suffix("mlb", "ZZZQQQ") == []


def test_resolve_event_id_fuzzy_matches_az_vs_ari_abbreviation_gap():
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    board = _scoreboard([("401815875", "ARI", "STL"), ("401815876", "CLE", "CHW")])
    assert resolve_event_id_fuzzy("mlb", "20260623", "AZSTL", scoreboard=board) == "401815875"


def test_resolve_event_id_fuzzy_matches_cws_vs_chw_abbreviation_gap():
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    board = _scoreboard([("401815812", "CHW", "DET"), ("401815813", "CIN", "NYY")])
    assert resolve_event_id_fuzzy("mlb", "20260619", "CWSDET", scoreboard=board) == "401815812"


def test_resolve_event_id_fuzzy_none_when_no_event_matches():
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    board = _scoreboard([("1", "BOS", "NYY")])
    assert resolve_event_id_fuzzy("mlb", "20260619", "AZSTL", scoreboard=board) is None


def test_resolve_event_id_fuzzy_refuses_ambiguous_suffix_split():
    """A suffix that splits into 2+ valid (away,home) code pairs must return None --
    never guess which split is the real one, even if the scoreboard would otherwise
    resolve one of them. Construct a suffix with two synthetic valid splits by
    monkeypatching the known-code set indirectly via a suffix that is genuinely
    ambiguous under the REAL alias map: "SDSD" splits as ("SD","SD") only (single valid
    split) so instead we assert the *mechanism* directly against _split_team_suffix
    returning 2+ candidates -- covered by patching team_resolver's alias table so two
    real prefixes of the probe string both qualify as known codes."""
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    import scripts.platformkit.espn_wp_backfill_measure as mod

    def _fake_split(sport, team_suffix):
        return [("SD", "SFO"), ("SDG", "FO")]  # 2 candidates -> ambiguous by construction

    orig = mod._split_team_suffix
    mod._split_team_suffix = _fake_split
    try:
        board = _scoreboard([("1", "SD", "SFO")])
        assert resolve_event_id_fuzzy("mlb", "20260619", "SDSFO", scoreboard=board) is None
    finally:
        mod._split_team_suffix = orig


def test_resolve_event_id_fuzzy_refuses_when_two_events_share_canonical_pair():
    # a genuinely ambiguous SCOREBOARD (two events canonicalizing to the same pair,
    # e.g. a doubleheader listed twice) must also refuse rather than pick one.
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    board = _scoreboard([("401815875", "ARI", "STL"), ("999999999", "AZ", "STL")])
    assert resolve_event_id_fuzzy("mlb", "20260623", "AZSTL", scoreboard=board) is None


def test_resolve_event_id_unsupported_sport_is_none():
    from scripts.platformkit.espn_wp_backfill_measure import resolve_event_id_fuzzy
    assert resolve_event_id_fuzzy("soccer", "20260619", "ARGAUT", scoreboard={}) is None


def test_resolve_event_id_falls_back_to_fuzzy_on_strict_miss(monkeypatch):
    # end-to-end: resolve_event_id tries strict concat first (misses on AZ vs ARI), then
    # falls back to the fuzzy pass using the SAME fetched payload (no second network call).
    import scripts.platformkit.espn_wp_backfill_measure as mod
    board = _scoreboard([("401815875", "ARI", "STL")])
    calls = {"n": 0}

    def _fake_fetch(sport, yyyymmdd):
        calls["n"] += 1
        return board

    monkeypatch.setattr(mod, "_fetch_scoreboard", _fake_fetch)
    result = mod.resolve_event_id("mlb", "20260623", "AZSTL")
    assert result == "401815875"
    assert calls["n"] == 1  # exactly one scoreboard fetch, reused for both passes
