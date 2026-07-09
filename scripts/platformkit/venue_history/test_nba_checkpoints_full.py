"""Tests for scripts.platformkit.venue_history.nba_checkpoints_full.
Offline, synthetic fixtures only -- monkeypatches the ESPN-fetch boundary
(_espn_events_for_date / fetch_states_for_event), no network. The PM archive's
home/away labels are systematically INVERTED (measured: 0 as-is / 1603
flipped); the end-to-end test exercises the flipped path as the norm."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.venue_history import nba_checkpoints_full as ncf


def _pm_doc(date, home, away, outcome_home_win=1, prices=None):
    return {
        "date": date, "event_slug": f"nba-{date}-{home}-{away}".lower().replace(" ", "-"),
        "market_slug": f"nba-{date}-{home}-{away}".lower().replace(" ", "-"),
        "sport": "nba", "home": home, "away": away,
        "outcome_home_win": outcome_home_win, "closed": True,
        "prices": prices or [],
    }


def _write_docs(path: Path, fname: str, docs) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / fname).write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")


# -- pure helpers ------------------------------------------------------------

def test_resolve_teams_full_names() -> None:
    doc = _pm_doc("2024-10-22", "Knicks", "Celtics")
    assert ncf.resolve_teams(doc) == ("BOS", "NYK")


def test_resolve_teams_unmatched_returns_none() -> None:
    doc = _pm_doc("2024-10-22", "BIG3 Team", "Celtics")
    assert ncf.resolve_teams(doc) is None


def test_pm_candles_flip_reorients_prob() -> None:
    doc = _pm_doc("2024-10-22", "Knicks", "Celtics",
                   prices=[{"ts": "2024-10-22T23:36:00Z", "prob_home": 0.6}])
    assert ncf.pm_candles(doc) == [{"ts": "2024-10-22T23:36:00Z", "prob": 0.6, "traded": True}]
    flipped = ncf.pm_candles(doc, flip=True)
    assert abs(flipped[0]["prob"] - 0.4) < 1e-12
    assert flipped[0]["traded"] is True


def test_resolve_event_orientation(monkeypatch) -> None:
    """ESPN has NYK@BOS. Doc-as-is (away=NYK, home=BOS) -> not flipped;
    doc-inverted (away=BOS, home=NYK) -> flipped=True. Both-ways on one
    date -> AMBIGUOUS. Absent -> None."""
    monkeypatch.setattr(ncf, "_espn_events_for_date", lambda d: {("NYK", "BOS"): "401704627"})
    assert ncf.resolve_event_id_by_teams("2024-10-22", "NYK", "BOS") == ("401704627", False, 0)
    assert ncf.resolve_event_id_by_teams("2024-10-22", "BOS", "NYK") == ("401704627", True, 0)
    both = {("NYK", "BOS"): "1", ("BOS", "NYK"): "2"}
    monkeypatch.setattr(ncf, "_espn_events_for_date", lambda d: both)
    assert ncf.resolve_event_id_by_teams("2024-10-22", "NYK", "BOS") == ncf.AMBIGUOUS
    monkeypatch.setattr(ncf, "_espn_events_for_date", lambda d: {})
    assert ncf.resolve_event_id_by_teams("2024-10-22", "NYK", "BOS") is None


def test_season_label() -> None:
    assert ncf.season_label("2024-10-22") == "2024-25"
    assert ncf.season_label("2025-04-30") == "2024-25"
    assert ncf.season_label("2025-10-21") == "2025-26"
    assert ncf.season_label("bad") == "unknown"


def test_load_pm_docs_dedupes_and_skips_bad_lines(tmp_path: Path) -> None:
    doc = _pm_doc("2024-10-22", "Knicks", "Celtics")
    _write_docs(tmp_path, "a.jsonl", [doc])
    (tmp_path / "b.jsonl").write_text(json.dumps(doc) + "\nnot json\n", encoding="utf-8")
    docs = ncf.load_pm_docs(tmp_path)
    assert len(docs) == 1  # duplicate event_slug + malformed line both dropped


# -- end-to-end build (network boundary monkeypatched) -----------------------

def test_build_checkpoints_flipped_end_to_end_no_leak(tmp_path: Path, monkeypatch) -> None:
    """Doc labels home=Knicks/away=Celtics but the REAL game is NYK@BOS
    (the archive norm): prob and outcome must be flipped to the real home
    side, and the as-of join must never take a future state."""
    _write_docs(tmp_path, "2024-10-22_nba-games.jsonl", [
        _pm_doc("2024-10-22", "Knicks", "Celtics", outcome_home_win=0, prices=[
            {"ts": 150, "prob_home": 0.60}, {"ts": 250, "prob_home": 0.65}]),
    ])
    states = [
        {"ts": 100, "period": 1, "game_clock_s": 600.0, "score_home": 0, "score_away": 0, "margin": 0},
        {"ts": 200, "period": 1, "game_clock_s": 300.0, "score_home": 2, "score_away": 0, "margin": 2},
    ]
    # ESPN truth: NYK away at BOS home -> doc orientation (away=BOS, home=NYK) is flipped
    monkeypatch.setattr(ncf, "_espn_events_for_date", lambda d: {("NYK", "BOS"): "401704627"})
    monkeypatch.setattr(ncf, "fetch_states_for_event", lambda eid: states)

    df, counters = ncf.build_checkpoints(tmp_path)
    assert counters["games_total"] == 1
    assert counters["games_joined"] == 1
    assert counters["games_flipped"] == 1
    assert len(df) == 2
    # candle ts=150 gets state ts=100 (margin 0), never the ts=200 future state
    row150 = df[df["ts"] == 150].iloc[0]
    assert row150["margin"] == 0
    # prob flipped to real home: 1-0.60=0.40 ; outcome flipped: 1-0=1
    assert abs(row150["market_prob"] - 0.40) < 1e-12
    assert (df["outcome_home_win"] == 1).all()
    assert (df["venue"] == "polymarket").all()
    assert (df["traded"] == True).all()  # noqa: E712
    for col in ("game_id", "ts", "period", "score_home", "score_away", "margin", "outcome_home_win"):
        assert str(df[col].dtype) == "int64", f"{col} is {df[col].dtype}"


def test_build_checkpoints_counts_exclusions(tmp_path: Path, monkeypatch) -> None:
    _write_docs(tmp_path, "d.jsonl", [
        _pm_doc("2024-10-22", "BIG3 Team", "Celtics"),           # unmatched name
        _pm_doc("2024-10-23", "Knicks", "Lakers", outcome_home_win=None),  # unresolved outcome
        _pm_doc("2024-10-24", "Knicks", "Celtics"),              # no ESPN match
        _pm_doc("2024-10-25", "Heat", "Magic"),                  # ambiguous both-ways
    ])
    def fake_idx(d):
        if d in ("20241024", "20241025", "20241026"):
            return {("MIA", "ORL"): "1", ("ORL", "MIA"): "2"}
        return {}
    monkeypatch.setattr(ncf, "_espn_events_for_date", fake_idx)
    df, counters = ncf.build_checkpoints(tmp_path)
    assert df.empty
    assert counters["unmatched_team_name"] == 1
    assert counters["unresolved_outcome"] == 1
    assert counters["no_espn_event_match"] == 1
    assert counters["ambiguous_orientation"] == 1
    assert counters["games_joined"] == 0


def test_build_checkpoints_dedupes_same_game_two_docs(tmp_path: Path, monkeypatch) -> None:
    """The archive lists a few games under two adjacent dates; only ONE doc
    per real game may survive -- the exact-date (delta 0) one wins, and the
    shifted as-is rematch artifact (which would carry a WRONG outcome) is
    dropped."""
    _write_docs(tmp_path, "d.jsonl", [
        _pm_doc("2026-01-29", "Heat", "Bulls", outcome_home_win=0,   # real MIA@CHI Jan29, flipped, delta 0
                prices=[{"ts": 150, "prob_home": 0.6}]),
        _pm_doc("2026-01-30", "Bulls", "Heat", outcome_home_win=1,   # same event via delta -1, as-is artifact
                prices=[{"ts": 150, "prob_home": 0.4}]),
    ])
    idx = {"20260129": {("MIA", "CHI"): "401850920"}}
    monkeypatch.setattr(ncf, "_espn_events_for_date", lambda d: idx.get(d, {}))
    states = [{"ts": 100, "period": 1, "game_clock_s": 600.0,
               "score_home": 0, "score_away": 0, "margin": 0}]
    monkeypatch.setattr(ncf, "fetch_states_for_event", lambda eid: states)

    df, counters = ncf.build_checkpoints(tmp_path)
    assert counters["games_joined"] == 1
    assert counters["duplicate_game_doc"] == 1
    assert df["game_id"].nunique() == 1
    assert df["market_ticker"].nunique() == 1
    # the kept doc is the delta-0 flipped one: outcome 1-0=1, prob 1-0.6=0.4
    assert (df["outcome_home_win"] == 1).all()
    assert abs(df.iloc[0]["market_prob"] - 0.4) < 1e-12


def test_games_per_season(tmp_path: Path) -> None:
    df = pd.DataFrame({"game_id": [1, 2, 3], "game_date": ["2024-10-22", "2025-04-01", "2025-11-01"]})
    assert ncf.games_per_season(df) == {"2024-25": 2, "2025-26": 1}
    assert ncf.games_per_season(pd.DataFrame()) == {}
