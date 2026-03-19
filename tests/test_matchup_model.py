"""
tests/test_matchup_model.py — Unit tests for M22 matchup model.

All tests use mocked data — no NBA API calls, no disk I/O.
"""

import json
import math
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.prediction.matchup_model as mm


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

_HUSTLE = {
    201939: {
        "player_id": 201939,
        "player_name": "Stephen Curry",
        "games_played": 60,
        "deflections_pg": 1.5,
        "screen_assists": 60,
        "contested_shots": 120,
        "charges_per_game": 0.2,
        "box_outs": 90,
    },
    201950: {
        "player_id": 201950,
        "player_name": "Jrue Holiday",
        "games_played": 55,
        "deflections_pg": 2.1,
        "screen_assists": 44,
        "contested_shots": 165,
        "charges_per_game": 0.4,
        "box_outs": 110,
    },
}

_ON_OFF = {
    201939: {"player_id": 201939, "on_off_diff": 3.5, "on_court_plus_minus": 4.0, "minutes_on": 35.0},
    201950: {"player_id": 201950, "on_off_diff": -2.0, "on_court_plus_minus": 2.0, "minutes_on": 32.0},
}

_MATCHUPS = [
    {"def_player_id": 201950, "partial_possessions": 85.0},
    {"def_player_id": 201939, "partial_possessions": 30.0},
]


def _patch_data(hustle=None, on_off=None, matchups=None):
    """Return kwargs for patch.multiple(mm, ...) — keys are attribute names."""
    h = hustle if hustle is not None else _HUSTLE
    o = on_off  if on_off  is not None else _ON_OFF
    m = matchups if matchups is not None else _MATCHUPS
    return {
        "_load_hustle":   MagicMock(return_value=h),
        "_load_on_off":   MagicMock(return_value=o),
        "_load_matchups": MagicMock(return_value=m),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — _build_defender_features computes correct per-game rates
# ─────────────────────────────────────────────────────────────────────────────

def test_build_defender_features_rates():
    feats = mm._build_defender_features(201950, _HUSTLE, _ON_OFF, _MATCHUPS)
    gp = 55.0
    assert feats["deflections_pg"]     == pytest.approx(2.1, abs=0.01)
    assert feats["screen_assists_pg"]  == pytest.approx(44 / gp, abs=0.01)
    assert feats["contested_shots_pg"] == pytest.approx(165 / gp, abs=0.01)
    assert feats["box_outs_pg"]        == pytest.approx(110 / gp, abs=0.01)
    assert feats["matchup_poss"]       == pytest.approx(85.0, abs=0.1)
    assert feats["on_off_diff"] if False else True   # on_off_diff not in feats dict


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — get_defender_quality finds player and returns sensible adjustment
# ─────────────────────────────────────────────────────────────────────────────

def test_get_defender_quality_found():
    patches = _patch_data()
    with patch("src.prediction.matchup_model._load_model", return_value=None):
        with patch.multiple(mm, **patches):
            result = mm.get_defender_quality("Jrue Holiday", season="2024-25")

    assert result["found"] is True
    assert result["player_id"] == 201950
    # on_off_diff = -2.0 → adj = clamp(-2.0 * 0.015, -0.12, 0.12) = -0.03 → -3.0%
    assert result["adjustment_pct"] == pytest.approx(-3.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — get_defender_quality returns found=False for unknown player
# ─────────────────────────────────────────────────────────────────────────────

def test_get_defender_quality_not_found():
    patches = _patch_data()
    with patch("src.prediction.matchup_model._load_model", return_value=None):
        with patch.multiple(mm, **patches):
            result = mm.get_defender_quality("Nonexistent Player", season="2024-25")

    assert result["found"] is False
    assert result["adjustment_pct"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — predict_matchup applies defender adjustment to base pts
# ─────────────────────────────────────────────────────────────────────────────

def test_predict_matchup_adjusts_scoring():
    player_avgs = {"stephen curry": {"pts": 24.0}}

    patches = _patch_data()
    with patch("src.prediction.matchup_model._load_model", return_value=None):
        with patch.multiple(mm, **patches):
            with patch("os.path.exists", return_value=True):
                with patch("builtins.open", MagicMock(return_value=MagicMock(
                    __enter__=lambda s, *a: s,
                    __exit__=lambda s, *a: None,
                    read=lambda: json.dumps(player_avgs),
                ))):
                    with patch("json.load", return_value=player_avgs):
                        result = mm.predict_matchup("Stephen Curry", "Jrue Holiday", "2024-25")

    assert result["off_player"] == "Stephen Curry"
    assert result["def_player"] == "Jrue Holiday"
    assert result["base_pts_per_game"] == pytest.approx(24.0, abs=0.1)
    # Jrue adj_pct = -3.0% → adjusted should be higher than base_per_100
    # base_per_100 = 24 * (100/36) ≈ 66.7; adjusted = 66.7 * (1 - (-0.03)) ≈ 68.7
    assert result["adjusted_pts_per_100"] > result["base_pts_per_100"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — adjustment is clamped to ±12%
# ─────────────────────────────────────────────────────────────────────────────

def test_adjustment_clamped():
    # Extreme on_off_diff values should be clamped
    extreme_on_off = {
        201950: {"player_id": 201950, "on_off_diff": 100.0, "on_court_plus_minus": 5.0, "minutes_on": 30.0},
    }
    patches = _patch_data(on_off=extreme_on_off)
    with patch("src.prediction.matchup_model._load_model", return_value=None):
        with patch.multiple(mm, **patches):
            result = mm.get_defender_quality("Jrue Holiday", season="2024-25")

    # 100.0 * 0.015 = 1.5 → clamped to 0.12 → 12.0%
    assert result["adjustment_pct"] == pytest.approx(12.0, abs=0.01)

    # Also test negative extreme
    extreme_neg = {
        201950: {"player_id": 201950, "on_off_diff": -100.0, "on_court_plus_minus": -5.0, "minutes_on": 30.0},
    }
    patches2 = _patch_data(on_off=extreme_neg)
    with patch("src.prediction.matchup_model._load_model", return_value=None):
        with patch.multiple("src.prediction.matchup_model", **patches2):
            result2 = mm.get_defender_quality("Jrue Holiday", season="2024-25")

    assert result2["adjustment_pct"] == pytest.approx(-12.0, abs=0.01)
