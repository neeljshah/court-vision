"""
tests/test_prop_calibration.py

Sanity tests for the prop calibration + bias-correction + conformal interval pipeline.
Tests mock the prediction path so they run without NBA API or model files.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


class TestPropCalibrationHelpers(unittest.TestCase):
    """Unit tests for _apply_stack_meta, _apply_calibration, _load_bias, _build_prop_interval."""

    def setUp(self):
        # Clear module-level caches before each test to avoid state bleed
        import src.prediction.player_props as pp
        pp._stack_meta_cache = None
        pp._calibration_cache = {}
        pp._conformal_cache = {}
        pp._bias_cache = None

    def test_stack_meta_applies_coef_and_intercept(self):
        """Ridge meta: stacked = coef * base + intercept."""
        import src.prediction.player_props as pp

        fake_meta = {
            "pts": {"coef": 0.9, "intercept": 1.5},
        }
        with patch.object(pp, "_load_stack_meta", return_value=fake_meta):
            result = pp._apply_stack_meta(20.0, "pts")
        self.assertAlmostEqual(result, 0.9 * 20.0 + 1.5, places=4)

    def test_stack_meta_passthrough_when_stat_missing(self):
        """If stat not in meta, return base value unchanged."""
        import src.prediction.player_props as pp

        with patch.object(pp, "_load_stack_meta", return_value={}):
            result = pp._apply_stack_meta(15.0, "pts")
        self.assertEqual(result, 15.0)

    def test_bias_correction_shifts_value(self):
        """bias_corrected = calibrated - median_bias (positive bias means overpredict)."""
        import src.prediction.player_props as pp

        pp._bias_cache = {"pts": {"median_bias": 0.4, "mae": 4.7, "n": 21835}}
        bias = pp._load_bias("pts")
        self.assertAlmostEqual(bias, 0.4, places=4)

        # Correction: subtract median_bias
        base = 22.0
        corrected = base - bias
        self.assertAlmostEqual(corrected, 21.6, places=4)

    def test_bias_zero_when_missing(self):
        """If no bias summary, _load_bias returns 0.0."""
        import src.prediction.player_props as pp

        pp._bias_cache = {}
        self.assertEqual(pp._load_bias("pts"), 0.0)

    def test_conformal_interval_from_file(self):
        """_build_prop_interval uses q80 from conformal_{stat}.json."""
        import src.prediction.player_props as pp

        pp._conformal_cache = {"pts": {"q80": 7.0, "q95": 12.0}}
        low, high = pp._build_prop_interval(20.0, "pts")
        self.assertAlmostEqual(low, max(20.0 - 7.0, 0.0), places=2)
        self.assertAlmostEqual(high, 20.0 + 7.0, places=2)

    def test_conformal_interval_fallback_when_no_file(self):
        """_build_prop_interval falls back to ±1.28σ when no conformal file."""
        import src.prediction.player_props as pp

        pp._conformal_cache = {"pts": {}}  # empty entry simulates missing q80
        low, high = pp._build_prop_interval(20.0, "pts")
        # Should still produce low <= point <= high
        self.assertLessEqual(low, 20.0)
        self.assertGreaterEqual(high, 20.0)

    def test_low_lte_point_lte_high(self):
        """For any realistic point estimate, low <= point <= high must hold."""
        import src.prediction.player_props as pp

        for stat, point in [("pts", 22.5), ("reb", 8.0), ("ast", 5.0),
                             ("fg3m", 2.5), ("stl", 1.0), ("blk", 0.5), ("tov", 2.0)]:
            pp._conformal_cache = {}  # force fallback path
            low, high = pp._build_prop_interval(point, stat)
            self.assertLessEqual(low, point,
                                 f"{stat}: low={low} > point={point}")
            self.assertGreaterEqual(high, point,
                                    f"{stat}: high={high} < point={point}")


class TestPredictPropsReturnShape(unittest.TestCase):
    """Integration test: predict_props returns correct shape with all keys."""

    def _make_mock_feats(self):
        """Minimal feature dict sufficient for _predict_with_models to run."""
        feats: dict = {"player_id": 99999, "team": "GSW"}
        defaults = {
            "season_pts": 20.0, "season_reb": 5.0, "season_ast": 4.0,
            "season_min": 32.0, "season_fg3m": 2.0, "season_stl": 1.0,
            "season_blk": 0.5, "season_tov": 2.0,
            "pts_bayes": 20.0, "reb_bayes": 5.0, "ast_bayes": 4.0,
            "fg3m_bayes": 2.0, "stl_bayes": 1.0, "blk_bayes": 0.5,
            "tov_bayes": 2.0,
            "pts_roll": 20.0, "reb_roll": 5.0, "ast_roll": 4.0,
            "stl_roll": 1.0, "blk_roll": 0.5,
            "min_roll": 32.0, "n_games_form": 10,
        }
        feats.update(defaults)
        return feats

    @patch("src.prediction.player_props._build_player_features")
    @patch("src.prediction.player_props._compute_blowout_prob", return_value=0.1)
    def test_predict_props_returns_props_dict(self, mock_blowout, mock_feats):
        """predict_props should return a 'props' dict with all 7 stats."""
        import src.prediction.player_props as pp

        mock_feats.return_value = self._make_mock_feats()
        pp._bias_cache = {s: {"median_bias": 0.0} for s in pp._PROP_STATS}
        pp._calibration_cache = {s: None for s in pp._PROP_STATS}
        pp._conformal_cache = {s: {} for s in pp._PROP_STATS}
        pp._stack_meta_cache = {}

        result = pp.predict_props("LeBron James", "GSW", season="2024-25", n_games=5)

        self.assertIn("props", result, "predict_props must return a 'props' key")
        props = result["props"]
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            self.assertIn(stat, props, f"props dict must contain '{stat}'")
            self.assertIn("point", props[stat])
            self.assertIn("low", props[stat])
            self.assertIn("high", props[stat])
            self.assertIn("mean", props[stat])
            self.assertIn("components", props[stat])

    @patch("src.prediction.player_props._build_player_features")
    @patch("src.prediction.player_props._compute_blowout_prob", return_value=0.1)
    def test_bias_corrected_differs_from_base_when_bias_nonzero(
        self, mock_blowout, mock_feats
    ):
        """bias_corrected must differ from base when median_bias != 0."""
        import src.prediction.player_props as pp

        mock_feats.return_value = self._make_mock_feats()
        # Force non-zero bias for pts
        pp._bias_cache = {"pts": {"median_bias": 2.0}}
        pp._calibration_cache = {s: None for s in pp._PROP_STATS}
        pp._conformal_cache = {s: {} for s in pp._PROP_STATS}
        pp._stack_meta_cache = {}

        result = pp.predict_props("LeBron James", "GSW", season="2024-25", n_games=5)
        comps = result["props"]["pts"]["components"]

        # bias_corrected = calibrated - 2.0 → must differ from calibrated
        self.assertNotAlmostEqual(
            comps["bias_corrected"], comps["calibrated"], places=1,
            msg="bias_corrected should differ from calibrated when bias=2.0",
        )

    @patch("src.prediction.player_props._build_player_features")
    @patch("src.prediction.player_props._compute_blowout_prob", return_value=0.1)
    def test_low_lte_point_lte_high_in_predict_props(self, mock_blowout, mock_feats):
        """predict_props intervals must satisfy low <= point <= high for all stats."""
        import src.prediction.player_props as pp

        mock_feats.return_value = self._make_mock_feats()
        pp._bias_cache = {s: {"median_bias": 0.0} for s in pp._PROP_STATS}
        pp._calibration_cache = {s: None for s in pp._PROP_STATS}
        pp._conformal_cache = {s: {} for s in pp._PROP_STATS}
        pp._stack_meta_cache = {}

        result = pp.predict_props("LeBron James", "GSW", season="2024-25", n_games=5)
        for stat in pp._PROP_STATS:
            p = result["props"][stat]
            self.assertLessEqual(
                p["low"], p["point"],
                f"{stat}: low={p['low']} > point={p['point']}",
            )
            self.assertGreaterEqual(
                p["high"], p["point"],
                f"{stat}: high={p['high']} < point={p['point']}",
            )

    @patch("src.prediction.player_props._build_player_features")
    @patch("src.prediction.player_props._compute_blowout_prob", return_value=0.1)
    def test_backward_compat_scalar_fields(self, mock_blowout, mock_feats):
        """Scalar stat fields must still be present for backward compatibility."""
        import src.prediction.player_props as pp

        mock_feats.return_value = self._make_mock_feats()
        pp._bias_cache = {s: {"median_bias": 0.0} for s in pp._PROP_STATS}
        pp._calibration_cache = {s: None for s in pp._PROP_STATS}
        pp._conformal_cache = {s: {} for s in pp._PROP_STATS}
        pp._stack_meta_cache = {}

        result = pp.predict_props("LeBron James", "GSW", season="2024-25", n_games=5)
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            self.assertIn(stat, result, f"Scalar field '{stat}' missing from result")
            self.assertIsInstance(result[stat], float)


if __name__ == "__main__":
    unittest.main()
