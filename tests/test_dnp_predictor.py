"""
Tests for src/prediction/dnp_predictor.py — DNP probability predictor.
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.dnp_predictor import _parse_min, predict_dnp, FEAT_COLS


# ── _parse_min ───────────────────────────────────────────────────────────────

class TestParseMin:
    def test_colon_format(self):
        result = _parse_min("32:15")
        assert abs(result - 32.25) < 0.01

    def test_zero_string(self):
        assert _parse_min("0") == 0.0

    def test_zero_colon(self):
        assert _parse_min("0:00") == 0.0

    def test_float_string(self):
        result = _parse_min("28.5")
        assert abs(result - 28.5) < 0.01

    def test_none_returns_none(self):
        assert _parse_min(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_min("") is None

    def test_none_string_returns_zero(self):
        assert _parse_min("None") == 0.0

    def test_integer_input(self):
        result = _parse_min(25)
        assert abs(result - 25.0) < 0.01


# ── predict_dnp ──────────────────────────────────────────────────────────────

class TestPredictDnp:
    def test_returns_float(self):
        result = predict_dnp("LeBron James")
        assert isinstance(result, float)

    def test_result_in_unit_interval(self):
        result = predict_dnp("Stephen Curry")
        assert 0.0 <= result <= 1.0

    def test_unknown_player_returns_low_probability(self):
        # Unknown players should return a low base rate (0.05 or 0.0)
        result = predict_dnp("Fake Player XYZ99999")
        assert result <= 0.1

    def test_no_model_returns_zero(self, monkeypatch, tmp_path):
        """Graceful fallback when model file doesn't exist."""
        monkeypatch.setattr(
            "src.prediction.dnp_predictor._MODEL_PATH",
            str(tmp_path / "nonexistent.pkl"),
        )
        # Clear the module-level cache so it re-checks model existence
        import src.prediction.dnp_predictor as dnp_mod
        monkeypatch.setattr(dnp_mod, "_dnp_cache", {})
        result = predict_dnp("LeBron James")
        assert result == 0.0

    def test_feat_cols_length(self):
        assert len(FEAT_COLS) == 5


# ── FEAT_COLS contract ───────────────────────────────────────────────────────

class TestFeatCols:
    def test_expected_features_present(self):
        expected = {
            "recent_min_avg", "min_trend", "games_in_last_7",
            "season_gp_pct", "age_flag",
        }
        assert set(FEAT_COLS) == expected
