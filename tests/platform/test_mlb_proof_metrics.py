"""Known-value tests for scripts.platformkit.proof_mlb.proof_metrics.

All tests use only stdlib + numpy.  No src.*, domains.*, torch, or FastAPI.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.platformkit.proof_mlb.proof_metrics import (
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


def test_brier_perfect_forecast_is_zero() -> None:
    probs = np.array([1.0, 1.0, 0.0, 0.0])
    outcomes = np.array([1.0, 1.0, 0.0, 0.0])
    assert brier(probs, outcomes) == 0.0


def test_brier_constant_half_balanced() -> None:
    probs = np.full(1000, 0.5)
    outcomes = np.array([1.0, 0.0] * 500)
    assert abs(brier(probs, outcomes) - 0.25) < 1e-9


# ---------------------------------------------------------------------------
# _devig2
# ---------------------------------------------------------------------------


def test_devig2_equal_odds_returns_half() -> None:
    pa, pb = _devig2(2.0, 2.0)
    assert pa == 0.5
    assert pb == 0.5


def test_devig2_sums_to_one() -> None:
    for oa, ob in [(1.8, 2.1), (1.5, 3.0), (2.5, 1.6)]:
        pa, pb = _devig2(oa, ob)
        assert abs(pa + pb - 1.0) < 1e-12


def test_devig2_price_at_or_below_one_returns_half() -> None:
    assert _devig2(1.0, 2.0) == (0.5, 0.5)
    assert _devig2(0.9, 2.0) == (0.5, 0.5)
    assert _devig2(2.0, 1.0) == (0.5, 0.5)


# ---------------------------------------------------------------------------
# clv_sign_invariants — invariant (a): open == close → CLV ≡ 0
# ---------------------------------------------------------------------------


def test_clv_invariant_a_open_equals_close() -> None:
    prices = np.full(20, 2.0)
    result = clv_sign_invariants(prices, prices, prices, prices)
    assert result["inv_a_ok"] is True
    assert result["max_close_vs_itself"] < 1e-9


# ---------------------------------------------------------------------------
# clv_sign_invariants — invariant (b): two-sided anti-symmetry
# ---------------------------------------------------------------------------


def test_clv_invariant_b_anti_symmetry() -> None:
    rng = np.random.default_rng(42)
    n = 50
    # Open odds: around 2.0; close odds: small random shifts
    open_a = rng.uniform(1.7, 2.3, size=n)
    open_b = rng.uniform(1.7, 2.3, size=n)
    close_a = open_a + rng.uniform(-0.1, 0.1, size=n)
    close_b = open_b + rng.uniform(-0.1, 0.1, size=n)
    # Clamp to >1.0
    close_a = np.clip(close_a, 1.01, None)
    close_b = np.clip(close_b, 1.01, None)
    result = clv_sign_invariants(open_a, open_b, close_a, close_b)
    assert result["inv_b_ok"] is True
    assert result["anti_sym_gap"] < 1e-9


# ---------------------------------------------------------------------------
# isotonic_calibrate
# ---------------------------------------------------------------------------


def test_isotonic_calibrate_output_shape_and_range() -> None:
    rng = np.random.default_rng(0)
    n_train, n_eval = 200, 80
    train_p = np.sort(rng.uniform(0.2, 0.8, size=n_train))
    train_y = (train_p > 0.5).astype(float)
    eval_p = rng.uniform(0.2, 0.8, size=n_eval)
    cal = isotonic_calibrate(train_p, train_y, eval_p)
    assert cal.shape == (n_eval,)
    assert float(cal.min()) >= 0.0
    assert float(cal.max()) <= 1.0


# ---------------------------------------------------------------------------
# ece
# ---------------------------------------------------------------------------


def test_ece_perfectly_calibrated_near_zero() -> None:
    # Build a perfectly calibrated synthetic set: for each bin mid-point,
    # set exactly that fraction of outcomes to 1.
    rng = np.random.default_rng(7)
    n_per_bin = 200
    probs_list, outcomes_list = [], []
    for mid in np.linspace(0.05, 0.95, 10):
        p_block = np.full(n_per_bin, mid)
        y_block = rng.binomial(1, mid, size=n_per_bin).astype(float)
        probs_list.append(p_block)
        outcomes_list.append(y_block)
    probs = np.concatenate(probs_list)
    outcomes = np.concatenate(outcomes_list)
    val = ece(probs, outcomes, bins=10)
    assert val < 0.05  # well-calibrated synthetic → near zero


# ---------------------------------------------------------------------------
# reliability_slope
# ---------------------------------------------------------------------------


def test_reliability_slope_perfectly_calibrated_near_one() -> None:
    rng = np.random.default_rng(13)
    n_per_bin = 300
    probs_list, outcomes_list = [], []
    for mid in np.linspace(0.05, 0.95, 10):
        p_block = np.full(n_per_bin, mid)
        y_block = rng.binomial(1, mid, size=n_per_bin).astype(float)
        probs_list.append(p_block)
        outcomes_list.append(y_block)
    probs = np.concatenate(probs_list)
    outcomes = np.concatenate(outcomes_list)
    slope = reliability_slope(probs, outcomes, bins=10)
    assert not math.isnan(slope)
    assert abs(slope - 1.0) < 0.3  # loose tolerance for stochastic data


def test_reliability_slope_nan_when_fewer_than_two_bins() -> None:
    # Only one distinct prob value → only one bin populated
    probs = np.full(100, 0.5)
    outcomes = np.array([1.0, 0.0] * 50)
    slope = reliability_slope(probs, outcomes, bins=10)
    assert math.isnan(slope)
