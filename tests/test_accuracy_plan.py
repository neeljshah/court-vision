"""
test_accuracy_plan.py — Tests for Pre-Season Accuracy Maximization Plan (Blocks A-E).

All tests are offline (no video, no NBA API calls required).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_tracking_df(n: int = 200, n_players: int = 4, seed: int = 42) -> pd.DataFrame:
    """Minimal synthetic tracking DataFrame for feature tests."""
    rng = np.random.default_rng(seed)
    frames = np.tile(np.arange(n), n_players)
    player_ids = np.repeat(np.arange(1, n_players + 1), n)
    df = pd.DataFrame({
        "frame":            frames,
        "player_id":        player_ids,
        "game_id":          "TEST_GAME",
        "velocity":         rng.uniform(0.5, 8.0, n * n_players),
        "acceleration":     rng.uniform(-2.0, 3.0, n * n_players),
        "dist_traveled_150": rng.uniform(5.0, 80.0, n * n_players),
        "nearest_opponent": rng.uniform(10.0, 200.0, n * n_players),
        "off_ball_distance": rng.uniform(20.0, 300.0, n * n_players),
        "paint_count_own":  rng.integers(0, 3, n * n_players),
        "paint_count_opp":  rng.integers(0, 3, n * n_players),
        "team":             np.tile(["green", "white"] * (n_players // 2), n),
        "ball_possession":  rng.integers(0, 2, n * n_players),
        "event":            np.where(rng.random(n * n_players) < 0.05, "shot", "none"),
        "court_zone":       np.random.choice(["paint", "3pt_arc", "mid_range"], n * n_players),
    })
    return df


# ── A-1: Acceleration features ────────────────────────────────────────────────

class TestAccelerationFeatures:
    def test_acceleration_mean_30_numeric(self):
        from src.features.advanced_features import add_acceleration_features
        df = _make_tracking_df()
        out = add_acceleration_features(df)
        assert "acceleration_mean_30" in out.columns
        assert pd.api.types.is_float_dtype(out["acceleration_mean_30"])

    def test_no_nan_on_full_data(self):
        from src.features.advanced_features import add_acceleration_features
        df = _make_tracking_df()
        out = add_acceleration_features(df)
        # Non-null acceleration input → no NaN in rolling mean
        assert out["acceleration_mean_30"].isna().sum() == 0

    def test_no_op_when_acceleration_absent(self):
        from src.features.advanced_features import add_acceleration_features
        df = _make_tracking_df().drop(columns=["acceleration"])
        out = add_acceleration_features(df)
        assert "acceleration_mean_30" not in out.columns

    def test_velocity_std_produced(self):
        from src.features.advanced_features import add_acceleration_features
        df = _make_tracking_df()
        out = add_acceleration_features(df, windows=[30, 90])
        assert "velocity_std_30" in out.columns
        assert "velocity_std_90" in out.columns


# ── A-2: Fatigue index ────────────────────────────────────────────────────────

class TestFatigueFeatures:
    def test_fatigue_in_bounds(self):
        from src.features.advanced_features import add_fatigue_features
        df = _make_tracking_df()
        out = add_fatigue_features(df)
        assert "fatigue_index" in out.columns
        valid = out["fatigue_index"].dropna()
        assert (valid >= 0.3).all(), "fatigue_index below 0.3"
        assert (valid <= 2.5).all(), "fatigue_index above 2.5"

    def test_no_op_when_dist_absent(self):
        from src.features.advanced_features import add_fatigue_features
        df = _make_tracking_df().drop(columns=["dist_traveled_150"])
        out = add_fatigue_features(df)
        assert "fatigue_index" not in out.columns


# ── A-3: Defender features ────────────────────────────────────────────────────

class TestDefenderFeatures:
    def test_contested_fraction_in_bounds(self):
        from src.features.advanced_features import add_defender_features
        df = _make_tracking_df()
        out = add_defender_features(df)
        assert "contested_fraction_90" in out.columns
        valid = out["contested_fraction_90"].dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 1.0).all()

    def test_defender_dist_mean_produced(self):
        from src.features.advanced_features import add_defender_features
        df = _make_tracking_df()
        out = add_defender_features(df)
        for col in ("defender_dist_mean_30", "defender_dist_mean_90", "defender_dist_min_90"):
            assert col in out.columns

    def test_no_op_when_nearest_opponent_absent(self):
        from src.features.advanced_features import add_defender_features
        df = _make_tracking_df().drop(columns=["nearest_opponent"])
        out = add_defender_features(df)
        assert "contested_fraction_90" not in out.columns


# ── A-7: ELO features ─────────────────────────────────────────────────────────

class TestEloFeatures:
    def test_returns_expected_keys(self):
        from src.features.advanced_features import get_elo_features
        result = get_elo_features("GSW", "BOS")
        assert "home_elo" in result
        assert "away_elo" in result
        assert "elo_differential" in result

    def test_fallback_when_no_file(self, tmp_path, monkeypatch):
        import src.features.advanced_features as af
        monkeypatch.setattr(af, "_ELO_PATH", str(tmp_path / "nonexistent.json"))
        result = af.get_elo_features("GSW", "BOS")
        assert result["home_elo"] == 1500.0
        assert result["away_elo"] == 1500.0
        assert result["elo_differential"] == 0.0

    def test_differential_is_home_minus_away(self, tmp_path, monkeypatch):
        import json
        import src.features.advanced_features as af
        elo_file = tmp_path / "elo_ratings.json"
        elo_file.write_text(json.dumps({"GSW": 1600.0, "BOS": 1500.0}))
        monkeypatch.setattr(af, "_ELO_PATH", str(elo_file))
        result = af.get_elo_features("GSW", "BOS")
        assert result["home_elo"] == 1600.0
        assert result["away_elo"] == 1500.0
        assert abs(result["elo_differential"] - 100.0) < 0.1


# ── B-1: Defender adjustment ──────────────────────────────────────────────────

class TestDefenderAdjustment:
    def test_tight_defense_reduces_fg_pct(self):
        from src.prediction.possession_outcome_model import _defender_adjustment
        assert _defender_adjustment(0.0) < 1.0, "0ft defender should reduce fg_pct"

    def test_wide_open_increases_fg_pct(self):
        from src.prediction.possession_outcome_model import _defender_adjustment
        assert _defender_adjustment(15.0) > 1.0, "15ft defender should increase fg_pct"

    def test_none_returns_one(self):
        from src.prediction.possession_outcome_model import _defender_adjustment
        assert _defender_adjustment(None) == 1.0

    def test_output_in_bounds(self):
        from src.prediction.possession_outcome_model import _defender_adjustment
        for d in (0.0, 2.0, 5.0, 8.0, 15.0, 30.0):
            v = _defender_adjustment(d)
            assert 0.75 <= v <= 1.10, f"Out of bounds for d={d}: {v}"


# ── B-1 + E-3: predict_outcome extended ──────────────────────────────────────

class TestPredictOutcomeExtended:
    def test_tight_defense_blowout_lowers_efficiency(self):
        from src.prediction.possession_outcome_model import predict_outcome
        # Tight defense + blowout → lower fg_pct_est
        result_contested = predict_outcome(
            2544, "drive", "paint",
            defender_dist_ft=2.0, score_diff=-15, period=4
        )
        result_open = predict_outcome(
            2544, "drive", "paint",
            defender_dist_ft=None, score_diff=0, period=2
        )
        assert result_contested["fg_pct_est"] < result_open["fg_pct_est"], (
            "Tight defense + blowout should lower fg_pct_est vs open+normal"
        )

    def test_returns_all_keys(self):
        from src.prediction.possession_outcome_model import predict_outcome
        result = predict_outcome(2544, "drive", "paint")
        for key in ("shot_prob", "tov_prob", "fta_prob", "fg_pct_est"):
            assert key in result
            assert 0.0 <= result[key] <= 1.0, f"{key}={result[key]} out of [0,1]"

    def test_no_crash_on_bad_inputs(self):
        from src.prediction.possession_outcome_model import predict_outcome
        result = predict_outcome(
            -1, "unknown", "unknown",
            defender_dist_ft="bad", spacing_advantage=None
        )
        assert isinstance(result, dict)


# ── D-7: Conformal predictor ──────────────────────────────────────────────────

class TestConformalPredictor:
    def test_interval_width_positive(self):
        from src.prediction.conformal_props import ConformalPredictor
        rng = np.random.default_rng(0)
        y_cal = rng.uniform(10, 40, 100)
        y_hat = y_cal + rng.normal(0, 3, 100)
        cp = ConformalPredictor()
        cp.calibrate(y_cal, y_hat)
        width = cp.interval_width(coverage=0.80)
        assert width > 0.0, "Interval width must be positive"

    def test_higher_coverage_wider_interval(self):
        from src.prediction.conformal_props import ConformalPredictor
        rng = np.random.default_rng(1)
        y_cal = rng.uniform(5, 50, 200)
        y_hat = y_cal + rng.normal(0, 4, 200)
        cp = ConformalPredictor()
        cp.calibrate(y_cal, y_hat)
        w80 = cp.interval_width(coverage=0.80)
        w50 = cp.interval_width(coverage=0.50)
        assert w80 > w50, "80% interval must be wider than 50% interval"

    def test_interval_contains_point_prediction(self):
        from src.prediction.conformal_props import ConformalPredictor
        cp = ConformalPredictor()
        cp.calibrate(np.array([20.0, 25.0, 30.0]), np.array([19.0, 26.0, 29.0]))
        lo, hi = cp.predict_interval(22.5, coverage=0.80)
        assert lo <= 22.5 <= hi, "Point prediction must be inside its own interval"

    def test_uncalibrated_returns_wide_fallback(self):
        from src.prediction.conformal_props import ConformalPredictor
        cp = ConformalPredictor()
        lo, hi = cp.predict_interval(20.0, coverage=0.80)
        assert hi - lo == pytest.approx(10.0, abs=0.1), "Uncalibrated width should be 10.0 (fallback)"


# ── D-1: Quantile props smoke test ────────────────────────────────────────────

class TestQuantilePropsSmoke:
    def test_predict_proba_over_in_bounds(self):
        from src.prediction.quantile_props import QuantilePropsModel
        rng = np.random.default_rng(42)
        n, f = 200, 10
        X = rng.standard_normal((n, f))
        y = rng.uniform(5, 40, n)

        qm = QuantilePropsModel()
        qm.train(X[:150], y[:150], stat="pts")
        prob = qm.predict_proba_over(X[150:], line=20.0)
        assert 0.0 <= prob <= 1.0, f"predict_proba_over returned {prob} outside [0,1]"

    def test_high_line_gives_lower_prob(self):
        from src.prediction.quantile_props import QuantilePropsModel
        rng = np.random.default_rng(7)
        X = rng.standard_normal((300, 5))
        y = rng.uniform(0, 30, 300)

        qm = QuantilePropsModel()
        qm.train(X[:200], y[:200], stat="pts")
        prob_low  = qm.predict_proba_over(X[200:], line=5.0)
        prob_high = qm.predict_proba_over(X[200:], line=25.0)
        assert prob_low >= prob_high, "P(stat > 5) should be >= P(stat > 25)"

    def test_save_load_roundtrip(self, tmp_path):
        from src.prediction.quantile_props import QuantilePropsModel
        rng = np.random.default_rng(3)
        X = rng.standard_normal((100, 5))
        y = rng.uniform(10, 35, 100)
        qm = QuantilePropsModel()
        qm.train(X, y, stat="reb")
        path = str(tmp_path / "qm_reb.pkl")
        qm.save(path)
        qm2 = QuantilePropsModel.load(path)
        p1 = qm.predict_proba_over(X[:10], line=20.0)
        p2 = qm2.predict_proba_over(X[:10], line=20.0)
        assert abs(p1 - p2) < 1e-6, "Loaded model should produce same output"


# ── A-12: compute_regression_weight ───────────────────────────────────────────

class TestRegressionWeight:
    def test_zero_games_returns_zero(self):
        from src.features.advanced_features import compute_regression_weight
        assert compute_regression_weight(0) == pytest.approx(0.0)

    def test_fifty_games_returns_one(self):
        from src.features.advanced_features import compute_regression_weight
        assert compute_regression_weight(50) == pytest.approx(1.0)

    def test_intermediate_values(self):
        from src.features.advanced_features import compute_regression_weight
        w25 = compute_regression_weight(25)
        assert 0.0 < w25 < 1.0
        assert w25 == pytest.approx(0.5)

    def test_over_fifty_capped_at_one(self):
        from src.features.advanced_features import compute_regression_weight
        assert compute_regression_weight(100) == pytest.approx(1.0)
