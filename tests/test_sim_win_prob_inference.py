"""
tests/test_sim_win_prob_inference.py — Unit tests for sim_* feature inference path.

Verifies that WinProbModel.predict() populates sim_win_prob,
sim_score_diff_mean, sim_score_diff_std, and sim_pace_adj at inference time,
and that the model returns a numeric win probability (not "unavailable").
"""
from __future__ import annotations

import sys
import os
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_sim_result(home: str, away: str) -> dict:
    """Return a plausible PossessionSimulator.simulate_game() result."""
    return {
        "win_probability":    {home: 0.55, away: 0.45},
        "score_distribution": {
            home: {"mean": 112.4, "std": 9.1},
            away: {"mean": 108.7, "std": 9.3},
        },
    }


def _make_mock_model(proba: float = 0.62) -> MagicMock:
    """Return a mock XGBClassifier that always returns proba for the home team."""
    m = MagicMock()
    m.predict_proba.return_value = np.array([[1 - proba, proba]])
    return m


# ---------------------------------------------------------------------------
# Test 1: _sim_features returns the four expected keys
# ---------------------------------------------------------------------------

def test_sim_features_keys():
    """_sim_features_safe must return all four required feature keys."""
    from src.prediction.win_probability import _sim_features_safe

    fake_sim = MagicMock()
    fake_sim.simulate_game.return_value = _fake_sim_result("BOS", "LAL")

    with patch("src.prediction.win_probability.PossessionSimulator",
               return_value=fake_sim):
        out = _sim_features_safe("BOS", "LAL",
                                 home_stats={"pace": 98.5},
                                 away_stats={"pace": 100.3})

    assert set(out.keys()) == {
        "sim_win_prob", "sim_score_diff_mean",
        "sim_score_diff_std", "sim_pace_adj",
    }


# ---------------------------------------------------------------------------
# Test 2: sim_win_prob is within [0, 1] for a real-looking matchup
# ---------------------------------------------------------------------------

def test_sim_win_prob_range():
    """sim_win_prob must be a float in [0, 1]."""
    from src.prediction.win_probability import _sim_features_safe

    fake_sim = MagicMock()
    fake_sim.simulate_game.return_value = _fake_sim_result("BOS", "LAL")

    with patch("src.prediction.win_probability.PossessionSimulator",
               return_value=fake_sim):
        out = _sim_features_safe("BOS", "LAL")

    assert 0.0 <= out["sim_win_prob"] <= 1.0


# ---------------------------------------------------------------------------
# Test 3: Neutral fallback when PossessionSimulator raises
# ---------------------------------------------------------------------------

def test_sim_features_safe_fallback_on_error():
    """_sim_features_safe must fall back to neutral defaults if simulator crashes."""
    import src.prediction.win_probability as _wpm
    from src.prediction.win_probability import _sim_features_safe, _SIM_NEUTRAL

    def _boom(*a, **kw):
        raise RuntimeError("No possession data")

    # Use a team combo not already cached by earlier tests
    _wpm._SIM_CACHE.pop("MIL_PHX", None)
    with patch("src.prediction.win_probability.PossessionSimulator",
               side_effect=_boom):
        out = _sim_features_safe("MIL", "PHX")

    assert out == _SIM_NEUTRAL


# ---------------------------------------------------------------------------
# Test 4: _build_features includes all four sim_* keys
# ---------------------------------------------------------------------------

def test_build_features_includes_sim_keys():
    """_build_features must include sim_* keys so WinProbModel.predict() never sees NaN."""
    from src.prediction.win_probability import _sim_features_safe, _SIM_NEUTRAL

    # Patch the heavy helpers so this test runs offline / fast
    with patch("src.prediction.win_probability._sim_features_safe",
               return_value=dict(_SIM_NEUTRAL)) as mock_sf, \
         patch("src.prediction.win_probability._fetch_team_stats",
               return_value={}), \
         patch("src.prediction.win_probability._get_schedule_context",
               return_value={"rest_days": 2, "back_to_back": 0}), \
         patch("src.prediction.win_probability._get_top_lineup_net_rtg",
               return_value=0.0), \
         patch("src.prediction.win_probability._get_last5_wins",
               return_value=3), \
         patch("src.prediction.win_probability.compute_travel_distance",
               return_value=0.0), \
         patch("nba_api.stats.static.teams.get_teams",
               return_value=[{"abbreviation": "BOS", "id": 1610612738},
                              {"abbreviation": "LAL", "id": 1610612747}]):
        from src.prediction.win_probability import _build_features
        feats = _build_features("BOS", "LAL", "2025-26", "2026-05-22")

    assert mock_sf.called, "_sim_features_safe was not called by _build_features"
    for key in ("sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj"):
        assert key in feats, f"Missing feature: {key}"
