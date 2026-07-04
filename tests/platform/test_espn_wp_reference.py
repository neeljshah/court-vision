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
