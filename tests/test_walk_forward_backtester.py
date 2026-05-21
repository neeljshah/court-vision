"""
test_walk_forward_backtester.py — Tests for the walk-forward cross-validation harness.

Verifies:
- Folds are strictly chronological (max train date < min test date for each fold).
- Aggregate metrics are finite.
- platt_calibration_check returns a finite post-calibration Brier that is
  <= pre-calibration Brier on well-behaved synthetic data.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression, Ridge

from src.prediction.walk_forward_backtester import (
    platt_calibration_check,
    run_walk_forward,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)


def _make_regression_dataset(
    n: int = 200,
    n_features: int = 5,
    noise: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X, y, dates) with a clean linear signal and Gaussian noise.

    Rows are ordered chronologically by date.
    """
    dates = pd.date_range("2022-01-01", periods=n, freq="D").values
    X = RNG.standard_normal((n, n_features))
    coef = RNG.standard_normal(n_features)
    y = X @ coef + RNG.normal(0, noise, n)
    return X, y, dates


def _make_calibration_dataset(
    n: int = 500,
    noise: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (probs, outcomes) where probs are well-behaved probabilities.

    Probs are drawn from Beta(2,2) (spread around 0.5) and outcomes are
    sampled from Bernoulli(prob).  Slight miscalibration is injected by
    squashing probs toward the centre so Platt scaling has something to fix.
    """
    raw = RNG.beta(2, 2, n)
    # Mild miscalibration: scale raw probs so they're slightly over-confident
    miscalibrated = np.clip(raw * 1.3 - 0.15, 0.01, 0.99)
    outcomes = RNG.binomial(1, raw, n)  # true probabilities stay `raw`
    return miscalibrated, outcomes


# ---------------------------------------------------------------------------
# Tests — run_walk_forward
# ---------------------------------------------------------------------------


def test_folds_are_chronological() -> None:
    """Max train date must be strictly less than min test date for every fold."""
    X, y, dates = _make_regression_dataset(n=200)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=5)

    for fold in result["folds"]:
        assert fold["max_train_date"] < fold["min_test_date"], (
            f"Fold {fold['fold']}: leakage detected — "
            f"max_train_date={fold['max_train_date']} >= "
            f"min_test_date={fold['min_test_date']}"
        )


def test_correct_number_of_folds() -> None:
    """run_walk_forward must return exactly n_folds fold entries."""
    X, y, dates = _make_regression_dataset(n=120)
    for n_folds in (3, 5, 7):
        result = run_walk_forward(LinearRegression, X, y, dates, n_folds=n_folds)
        assert len(result["folds"]) == n_folds, (
            f"Expected {n_folds} folds, got {len(result['folds'])}"
        )


def test_aggregate_metrics_are_finite() -> None:
    """Aggregate R² and MAE must be finite floats."""
    X, y, dates = _make_regression_dataset(n=200)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=5)

    agg = result["aggregate"]
    assert "r2" in agg and "mae" in agg, "aggregate must contain 'r2' and 'mae' keys"
    assert math.isfinite(agg["r2"]),  f"Aggregate R² is not finite: {agg['r2']}"
    assert math.isfinite(agg["mae"]), f"Aggregate MAE is not finite: {agg['mae']}"
    assert agg["mae"] >= 0.0, f"MAE must be non-negative, got {agg['mae']}"


def test_per_fold_metrics_are_finite() -> None:
    """Each per-fold R² and MAE must be finite."""
    X, y, dates = _make_regression_dataset(n=200)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=5)

    for fold in result["folds"]:
        assert math.isfinite(fold["r2"]),  f"Fold {fold['fold']} R² not finite"
        assert math.isfinite(fold["mae"]), f"Fold {fold['fold']} MAE not finite"
        assert fold["mae"] >= 0.0, f"Fold {fold['fold']} MAE negative"


def test_train_size_expands_monotonically() -> None:
    """With an expanding window, each successive fold must have a larger train set."""
    X, y, dates = _make_regression_dataset(n=200)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=5)

    train_sizes = [f["train_size"] for f in result["folds"]]
    for i in range(1, len(train_sizes)):
        assert train_sizes[i] > train_sizes[i - 1], (
            f"Train size did not expand: fold {i-1}={train_sizes[i-1]}, "
            f"fold {i}={train_sizes[i]}"
        )


def test_no_data_overlap_between_folds() -> None:
    """Test windows across folds must not overlap."""
    X, y, dates = _make_regression_dataset(n=200)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=5)

    # min_test_date must strictly increase across folds
    min_test_dates = [f["min_test_date"] for f in result["folds"]]
    for i in range(1, len(min_test_dates)):
        assert min_test_dates[i] > min_test_dates[i - 1], (
            "Test fold windows overlap or are not ordered chronologically"
        )


def test_custom_model_factory() -> None:
    """run_walk_forward works with any sklearn-compatible model factory."""
    X, y, dates = _make_regression_dataset(n=200)

    def ridge_factory() -> Ridge:
        return Ridge(alpha=1.0)

    result = run_walk_forward(ridge_factory, X, y, dates, n_folds=4)
    assert len(result["folds"]) == 4
    assert math.isfinite(result["aggregate"]["r2"])


def test_result_keys() -> None:
    """Return dict must contain 'folds' (list) and 'aggregate' (dict with r2, mae)."""
    X, y, dates = _make_regression_dataset(n=100)
    result = run_walk_forward(LinearRegression, X, y, dates, n_folds=3)

    assert "folds" in result, "Missing 'folds' key"
    assert "aggregate" in result, "Missing 'aggregate' key"
    assert isinstance(result["folds"], list)
    assert isinstance(result["aggregate"], dict)
    assert set(result["aggregate"].keys()) >= {"r2", "mae"}


def test_too_small_dataset_raises() -> None:
    """run_walk_forward must raise ValueError when dataset is too small."""
    X = np.ones((4, 2))
    y = np.ones(4)
    dates = pd.date_range("2024-01-01", periods=4, freq="D").values

    with pytest.raises(ValueError, match="too small"):
        run_walk_forward(LinearRegression, X, y, dates, n_folds=5)


# ---------------------------------------------------------------------------
# Tests — platt_calibration_check
# ---------------------------------------------------------------------------


def test_platt_calibration_returns_finite_brier() -> None:
    """Both Brier scores returned by platt_calibration_check must be finite."""
    probs, outcomes = _make_calibration_dataset(n=500)
    result = platt_calibration_check(probs, outcomes)

    assert "brier_before" in result and "brier_after" in result, (
        "Result must contain 'brier_before' and 'brier_after'"
    )
    assert math.isfinite(result["brier_before"]), (
        f"brier_before is not finite: {result['brier_before']}"
    )
    assert math.isfinite(result["brier_after"]), (
        f"brier_after is not finite: {result['brier_after']}"
    )


def test_platt_calibration_brier_non_negative() -> None:
    """Brier scores must be in [0, 1]."""
    probs, outcomes = _make_calibration_dataset(n=500)
    result = platt_calibration_check(probs, outcomes)

    assert 0.0 <= result["brier_before"] <= 1.0, (
        f"brier_before out of range: {result['brier_before']}"
    )
    assert 0.0 <= result["brier_after"] <= 1.0, (
        f"brier_after out of range: {result['brier_after']}"
    )


def test_platt_calibration_improves_on_well_behaved_data() -> None:
    """Post-calibration Brier must be <= pre-calibration Brier on synthetic data.

    We construct a dataset where probs are systematically miscalibrated
    (offset by a constant), so Platt scaling can only improve or maintain
    the Brier score.
    """
    rng = np.random.default_rng(0)
    n = 800
    true_probs = rng.beta(3, 3, n)           # spread, centred around 0.5
    outcomes = rng.binomial(1, true_probs, n)
    # Miscalibrate: shift all probs up by 0.15 (clipped to [0.01, 0.99])
    miscalibrated = np.clip(true_probs + 0.15, 0.01, 0.99)

    result = platt_calibration_check(miscalibrated, outcomes)

    assert result["brier_after"] <= result["brier_before"], (
        f"Calibration made things worse: "
        f"brier_before={result['brier_before']:.4f}, "
        f"brier_after={result['brier_after']:.4f}"
    )


def test_platt_calibration_result_keys() -> None:
    """platt_calibration_check must return expected keys."""
    probs, outcomes = _make_calibration_dataset(n=200)
    result = platt_calibration_check(probs, outcomes)

    expected_keys = {"brier_before", "brier_after", "calibrated_probs", "improved"}
    assert expected_keys.issubset(result.keys()), (
        f"Missing keys: {expected_keys - result.keys()}"
    )
    assert len(result["calibrated_probs"]) == len(probs), (
        "calibrated_probs length must match input length"
    )


def test_platt_improved_flag() -> None:
    """'improved' flag must be True iff brier_after <= brier_before."""
    probs, outcomes = _make_calibration_dataset(n=400)
    result = platt_calibration_check(probs, outcomes)

    expected_improved = result["brier_after"] <= result["brier_before"]
    assert result["improved"] == expected_improved, (
        f"'improved' flag ({result['improved']}) does not match "
        f"brier_after ({result['brier_after']:.4f}) <= "
        f"brier_before ({result['brier_before']:.4f})"
    )
