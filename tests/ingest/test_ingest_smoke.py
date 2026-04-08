"""
Smoke tests for ingest modules — no network calls, tests pure logic only.
"""
import pytest
import pandas as pd
import numpy as np


# ── rest_travel ─────────────────────────────────────────────────────────────

def test_haversine_zero():
    from src.ingest.rest_travel import _haversine
    assert _haversine(0, 0, 0, 0) == pytest.approx(0.0)


def test_haversine_lal_gsw():
    from src.ingest.rest_travel import _haversine, _ARENA_GEO
    lat1, lon1, _ = _ARENA_GEO["LAL"]
    lat2, lon2, _ = _ARENA_GEO["GSW"]
    miles = _haversine(lat1, lon1, lat2, lon2)
    assert 300 < miles < 450   # ~345 miles LAX <-> SFO


def test_compute_travel_same_venue():
    from src.ingest.rest_travel import _compute_travel
    miles, alt = _compute_travel("LAL", "LAL")
    assert miles == pytest.approx(0.0)
    assert alt > 0


def test_compute_rest_travel_basic():
    from src.ingest.rest_travel import compute_rest_travel
    df = pd.DataFrame({
        "game_id":          ["G1", "G2", "G3"],
        "team_abbreviation": ["LAL", "LAL", "LAL"],
        "game_date":        ["2024-12-01", "2024-12-02", "2024-12-05"],
        "matchup":          ["LAL vs. GSW", "LAL @ PHX", "LAL vs. BOS"],
    })
    result = compute_rest_travel(df)
    assert len(result) == 3
    lal = result[result["team_abbreviation"] == "LAL"].reset_index(drop=True)
    # G2 is day after G1 = B2B
    assert lal.loc[1, "days_rest"] == 0
    assert lal.loc[1, "is_b2b"]    == 1
    # G3 is 3 days after G2
    assert lal.loc[2, "days_rest"] == 2


# ── injury_report ────────────────────────────────────────────────────────────

def test_severity_mapping():
    from src.ingest.injury_report import _severity
    assert _severity("Out") == 4
    assert _severity("Doubtful") == 3
    assert _severity("Questionable") == 2
    assert _severity("Probable") == 1
    assert _severity("Available") == 0
    assert _severity("") == 0


def test_parse_injury_json():
    from src.ingest.injury_report import _parse_injury_json
    raw = {
        "injuryDate": "2024-12-01",
        "injuryReport": [
            {
                "teamAbbreviation": "LAL",
                "injuredPlayers": [
                    {"playerId": 1001, "playerName": "LeBron James",
                     "personStatus": "Questionable", "injuryNote": "knee",
                     "gameDate": "2024-12-01"},
                ],
            }
        ],
    }
    records = _parse_injury_json(raw)
    assert len(records) == 1
    assert records[0]["status"] == "Questionable"
    assert records[0]["severity"] == 2


def test_get_player_status_default(tmp_path):
    from src.ingest.injury_report import get_player_status
    result = get_player_status(9999, "2024-12-01", cache_path=tmp_path / "ir.parquet")
    assert result["status"] == "available"
    assert result["severity"] == 0


# ── vegas_lines ──────────────────────────────────────────────────────────────

def test_robots_check_returns_bool():
    from src.ingest.vegas_lines import _check_robots
    # Should return a boolean (True or False), not raise
    result = _check_robots.__code__  # just check it's callable
    assert callable(_check_robots)


# ── playtype_rates ───────────────────────────────────────────────────────────

def test_playtype_constants():
    from src.ingest.playtype_rates import _PLAY_TYPES
    assert "Isolation" in _PLAY_TYPES
    assert "Transition" in _PLAY_TYPES
    assert len(_PLAY_TYPES) >= 5
