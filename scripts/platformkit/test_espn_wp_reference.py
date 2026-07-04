"""Per-file test for scripts.platformkit.espn_wp_reference -- covers the NBA route
added wave-22 lane 5 (additive alongside the existing MLB/WNBA routes) plus the
pure extract_latest/build_asof_series/get_outcome helpers on an NBA-shaped fixture.

No network: fetch_summary is not called here -- these test the pure functions
that operate on an already-fetched summary dict, and the SUPPORTED_SPORTS/
UNSUPPORTED_SPORTS route table itself.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_espn_wp_reference.py -q
"""
from __future__ import annotations

from scripts.platformkit.espn_wp_reference import (
    SUPPORTED_SPORTS,
    UNSUPPORTED_SPORTS,
    build_asof_series,
    extract_latest,
    get_outcome,
)


def _nba_fixture() -> dict:
    return {
        "winprobability": [
            {"homeWinPercentage": 0.542, "tiePercentage": 0.0, "playId": "4018110264"},
            {"homeWinPercentage": 0.601, "tiePercentage": 0.0, "playId": "4018110265"},
        ],
        "plays": [
            {"id": "4018110264", "wallclock": "2026-04-10T23:05:01Z",
             "homeScore": 2, "awayScore": 0},
            {"id": "4018110265", "wallclock": "2026-04-10T23:05:20Z",
             "homeScore": 4, "awayScore": 0},
        ],
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "winner": True},
            {"homeAway": "away", "winner": False},
        ]}]},
        "meta": {"lastUpdatedAt": "2026-04-10T23:05:20Z"},
    }


def test_nba_is_supported_route():
    assert SUPPORTED_SPORTS.get("nba") == "basketball/nba"
    assert "nba" not in UNSUPPORTED_SPORTS


def test_existing_routes_untouched():
    assert SUPPORTED_SPORTS.get("mlb") == "baseball/mlb"
    assert SUPPORTED_SPORTS.get("wnba") == "basketball/wnba"
    assert "soccer" in UNSUPPORTED_SPORTS
    assert "tennis" in UNSUPPORTED_SPORTS


def test_extract_latest_nba_fixture():
    rec = extract_latest("nba", "401811026", _nba_fixture())
    assert rec is not None
    assert rec["sport"] == "nba"
    assert rec["event_id"] == "401811026"
    assert rec["n_wp_points"] == 2
    assert rec["espn_wp_home"] == 0.601
    assert rec["last_play_id"] == "4018110265"


def test_build_asof_series_nba_fixture():
    rows = build_asof_series(_nba_fixture())
    assert len(rows) == 2
    assert rows[0]["wallclock"] <= rows[1]["wallclock"]
    assert rows[-1]["home_win_pct"] == 0.601
    assert rows[-1]["home_score"] == 4


def test_get_outcome_nba_fixture():
    outcome = get_outcome(_nba_fixture())
    assert outcome == {"home_win": True, "completed": True}


def test_extract_latest_missing_wp_returns_none():
    assert extract_latest("nba", "x", {"winprobability": []}) is None
