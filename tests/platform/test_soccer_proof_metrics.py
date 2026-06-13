"""Tests for scripts.platformkit.proof_soccer.proof_metrics (soccer O/U-2.5 proof).

Known-value tests — all pure functions, no src.* or domains.* imports needed.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.platformkit.proof_soccer.proof_metrics import (
    _devig2,
    brier,
    clv_sign_invariants,
    ece,
    isotonic_calibrate,
    reliability_slope,
)


# ---------------------------------------------------------------------------
# brier
# ---------------------------------------------------------------------------


def test_brier_perfect_forecast_is_zero():
    """A forecast where probs == outcomes has Brier score 0.0."""
    outcomes = np.array([1.0, 0.0, 1.0, 0.0])
    probs = outcomes.copy()
    assert brier(probs, outcomes) == 0.0


def test_brier_constant_half_balanced():
    """Constant-0.5 forecast over balanced outcomes gives Brier ≈ 0.25."""
    rng = np.random.default_rng(42)
    n = 10_000
    outcomes = rng.integers(0, 2, size=n).astype(float)
    probs = np.full(n, 0.5)
    score = brier(probs, outcomes)
    assert abs(score - 0.25) < 0.01


# ---------------------------------------------------------------------------
# _devig2
# ---------------------------------------------------------------------------


def test_devig2_symmetric_odds():
    """Equal odds 2.0/2.0 → (0.5, 0.5)."""
    pa, pb = _devig2(2.0, 2.0)
    assert pa == pytest.approx(0.5)
    assert pb == pytest.approx(0.5)


def test_devig2_sums_to_one():
    """Output probabilities always sum to 1.0."""
    pa, pb = _devig2(1.8, 2.1)
    assert pa + pb == pytest.approx(1.0)


def test_devig2_price_le_one_returns_half():
    """Prices <= 1.0 are invalid; function returns (0.5, 0.5) as a safe fallback."""
    pa, pb = _devig2(0.9, 2.0)
    assert pa == pytest.approx(0.5)
    assert pb == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# clv_sign_invariants
# ---------------------------------------------------------------------------


def test_clv_invariant_a_open_equals_close():
    """When open == close, inv_a_ok is True and max_close_vs_itself < 1e-9."""
    prices = np.array([1.9, 2.0, 1.85, 2.05])
    result = clv_sign_invariants(
        open_a=prices,
        open_b=prices,
        close_a=prices,
        close_b=prices,
    )
    assert result["inv_a_ok"] is True
    assert result["max_close_vs_itself"] < 1e-9


def test_clv_invariant_b_anti_symmetry():
    """inv_b_ok is True and anti_sym_gap ≈ 0 on a small synthetic open/close array."""
    rng = np.random.default_rng(7)
    n = 50
    open_a = rng.uniform(1.7, 2.3, size=n)
    open_b = rng.uniform(1.7, 2.3, size=n)
    # Close prices differ slightly from open
    close_a = open_a + rng.uniform(-0.1, 0.1, size=n)
    close_b = open_b + rng.uniform(-0.1, 0.1, size=n)
    # Clamp to valid decimal odds range
    close_a = np.clip(close_a, 1.01, 10.0)
    close_b = np.clip(close_b, 1.01, 10.0)

    result = clv_sign_invariants(open_a, open_b, close_a, close_b)
    assert result["inv_b_ok"] is True
    assert result["anti_sym_gap"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# isotonic_calibrate
# ---------------------------------------------------------------------------


def test_isotonic_calibrate_shape_and_range():
    """Calibrated probs are in [0, 1] and have the right shape."""
    rng = np.random.default_rng(0)
    n_train, n_eval = 200, 50
    train_p = rng.uniform(0.2, 0.8, size=n_train)
    train_y = (rng.uniform(size=n_train) < train_p).astype(float)
    eval_p = rng.uniform(0.2, 0.8, size=n_eval)

    cal_p = isotonic_calibrate(train_p, train_y, eval_p)
    assert cal_p.shape == (n_eval,)
    assert float(cal_p.min()) >= 0.0
    assert float(cal_p.max()) <= 1.0


def test_isotonic_calibrate_monotone_train():
    """On a strictly monotone train mapping the calibrated values preserve ordering."""
    train_p = np.linspace(0.1, 0.9, 50)
    train_y = train_p.copy()  # perfectly calibrated monotone mapping
    eval_p = np.array([0.2, 0.4, 0.6, 0.8])

    cal_p = isotonic_calibrate(train_p, train_y, eval_p)
    assert cal_p.shape == (4,)
    # Calibrated values should be non-decreasing (isotonic)
    assert all(cal_p[i] <= cal_p[i + 1] for i in range(len(cal_p) - 1))


# ---------------------------------------------------------------------------
# ece
# ---------------------------------------------------------------------------


def test_ece_perfectly_calibrated_near_zero():
    """ECE of a perfectly calibrated synthetic set is approximately 0."""
    rng = np.random.default_rng(1)
    n = 2000
    probs = rng.uniform(0.1, 0.9, size=n)
    # outcomes drawn from the stated probability → perfectly calibrated in expectation
    outcomes = (rng.uniform(size=n) < probs).astype(float)
    score = ece(probs, outcomes)
    # With 2000 samples the ECE of a truly calibrated forecast should be well under 0.05
    assert score < 0.05


# ---------------------------------------------------------------------------
# reliability_slope
# ---------------------------------------------------------------------------


def test_reliability_slope_perfectly_calibrated_near_one():
    """Slope of a well-calibrated model is ≈ 1.0 (loose tolerance ±0.4)."""
    rng = np.random.default_rng(2)
    n = 5000
    probs = rng.uniform(0.1, 0.9, size=n)
    outcomes = (rng.uniform(size=n) < probs).astype(float)
    slope = reliability_slope(probs, outcomes, bins=10)
    assert not math.isnan(slope)
    assert abs(slope - 1.0) < 0.4


def test_reliability_slope_returns_nan_when_too_few_bins():
    """Returns nan when fewer than 2 bins are populated (all probs in one bin)."""
    probs = np.full(20, 0.5)
    outcomes = np.array([1.0] * 10 + [0.0] * 10)
    slope = reliability_slope(probs, outcomes, bins=10)
    assert math.isnan(slope)
