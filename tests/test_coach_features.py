"""
tests/test_coach_features.py — Unit tests for src/features/coach_features.py
"""
import json
import os
import sys
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.features.coach_features import (
    get_coach_features,
    get_head_coach,
    _team_season_coach,
    _COACH_TENURE,
    _load_coach_lookup,
    _default_coach_features,
)


# ── Tenure-map tests ───────────────────────────────────────────────────────────

def test_known_coaches_mapped():
    """Spot-check that canonical coaches appear in the tenure map."""
    assert "Steve Kerr" in _COACH_TENURE
    assert "Erik Spoelstra" in _COACH_TENURE
    assert "Tom Thibodeau" in _COACH_TENURE
    assert len(_COACH_TENURE) >= 15


def test_team_season_map_populated():
    """_team_season_coach should map every team in _COACH_TENURE to seasons."""
    assert len(_team_season_coach) > 0
    # GSW → 2024-25 → Steve Kerr
    assert _team_season_coach.get("GSW", {}).get("2024-25") == "Steve Kerr"
    # NYK → 2024-25 → Tom Thibodeau
    assert _team_season_coach.get("NYK", {}).get("2024-25") == "Tom Thibodeau"


def test_get_head_coach_known_team():
    """get_head_coach should return a non-empty string for known teams."""
    # Use team_id=1610612744 (GSW) — even without API it falls back
    coach = get_head_coach(1610612744, "2024-25", "2025-01-15")
    assert isinstance(coach, str)
    assert len(coach) > 0


def test_get_head_coach_unknown_team():
    """Unknown team_id returns 'Unknown Coach'."""
    coach = get_head_coach(9999999, "2024-25", "2025-01-15")
    assert coach == "Unknown Coach"


# ── get_coach_features tests ───────────────────────────────────────────────────

def test_coach_features_returns_dict():
    """get_coach_features always returns a dict."""
    feats = get_coach_features("GSW", "BOS", "2024-25", "2025-01-15")
    assert isinstance(feats, dict)


def test_coach_features_all_keys_present():
    """All 22+ expected keys are in the output."""
    feats = get_coach_features("LAL", "GSW", "2024-25", "2025-02-01")
    expected_prefixes = [
        "home_coach_avg_pace", "home_coach_avg_oe", "home_coach_avg_de",
        "home_coach_3pa_rate", "home_coach_fta_rate", "home_coach_to_pct",
        "home_coach_rotation_depth_avg", "home_coach_late_close_win_pct",
        "home_coach_b2b_win_pct", "home_coach_games_coached",
        "away_coach_avg_pace", "away_coach_avg_oe", "away_coach_avg_de",
        "home_coach_pace_diff", "home_coach_3pa_diff",
        "home_coach_name", "away_coach_name",
    ]
    for key in expected_prefixes:
        assert key in feats, f"Missing key: {key}"


def test_coach_features_numeric_ranges():
    """Feature values should be in sensible NBA ranges."""
    feats = get_coach_features("MIA", "NYK", "2024-25", "2025-03-01")
    assert 85.0 <= feats["home_coach_avg_pace"] <= 115.0
    assert 0.20 <= feats["home_coach_3pa_rate"] <= 0.60
    assert 0.0  <= feats["home_coach_late_close_win_pct"] <= 1.0
    assert 0.0  <= feats["home_coach_b2b_win_pct"] <= 1.0


def test_coach_features_delta_computed():
    """Pace and 3PA deltas are correctly derived from home - away."""
    feats = get_coach_features("GSW", "MIA", "2024-25", "2025-01-10")
    expected_diff = round(feats["home_coach_avg_pace"] - feats["away_coach_avg_pace"], 3)
    assert abs(feats["home_coach_pace_diff"] - expected_diff) < 1e-3


def test_default_features_for_unknown_coach():
    """Unknown teams still return complete default feature dict."""
    feats = get_coach_features("XYZ", "ABC", "2024-25", "2025-01-01")
    defaults = _default_coach_features("home_coach")
    for k in defaults:
        assert k in feats


def test_coach_history_cache_loadable(tmp_path):
    """If coach_history.json exists, _load_coach_lookup parses it."""
    fake = [
        {"coach": "Test Coach", "coach_avg_pace": 98.5, "coach_3pa_rate": 0.41,
         "coach_games_coached": 100, "coach_avg_oe": 112.0, "coach_avg_de": 110.0,
         "coach_fta_rate": 0.25, "coach_to_pct": 0.13,
         "coach_rotation_depth_avg": 8.5, "coach_late_close_win_pct": 0.52,
         "coach_b2b_win_pct": 0.45, "coach_win_pct": 0.61}
    ]
    cache_file = tmp_path / "coach_history.json"
    cache_file.write_text(json.dumps(fake))
    # Patch module path
    import src.features.coach_features as cf
    orig = cf._COACH_HIST
    cf._COACH_HIST = str(cache_file)
    cf._coach_lookup = None  # reset
    lookup = cf._load_coach_lookup()
    assert "Test Coach" in lookup
    assert lookup["Test Coach"]["coach_avg_pace"] == 98.5
    cf._COACH_HIST = orig
    cf._coach_lookup = None
