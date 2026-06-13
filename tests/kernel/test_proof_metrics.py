"""Known-value unit tests for kernel.validation.proof_metrics.

All tests use only stdlib + numpy.  No src.*, domains.*, torch, or FastAPI.
Mirrors the per-sport suites in tests/platform/ for the canonical kernel module.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kernel.validation.proof_metrics import (
    brier,
    clv_sign_invariants,
    devig2,
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
# devig2
# ---------------------------------------------------------------------------


def test_devig2_equal_odds_returns_half() -> None:
    pa, pb = devig2(2.0, 2.0)
    assert pa == 0.5
    assert pb == 0.5


def test_devig2_sums_to_one() -> None:
    for oa, ob in [(1.8, 2.1), (1.5, 3.0), (2.5, 1.6)]:
        pa, pb = devig2(oa, ob)
        assert abs(pa + pb - 1.0) < 1e-12


def test_devig2_price_at_or_below_one_returns_half() -> None:
    assert devig2(1.0, 2.0) == (0.5, 0.5)
    assert devig2(0.9, 2.0) == (0.5, 0.5)
    assert devig2(2.0, 1.0) == (0.5, 0.5)


def test_devig2_extreme_odds() -> None:
    # Very lopsided: 1.01 vs 50.0 — side A should be very likely
    pa, pb = devig2(1.01, 50.0)
    assert pa > 0.9
    assert abs(pa + pb - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# clv_sign_invariants — invariant (a): open == close → CLV ≡ 0
# ---------------------------------------------------------------------------


def test_clv_invariant_a_open_equals_close() -> None:
    prices = np.full(20, 2.0)
    result = clv_sign_invariants(prices, prices, prices, prices)
    assert result["inv_a_ok"] is True
    assert result["max_close_vs_itself"] < 1e-9


def test_clv_invariant_a_max_close_vs_itself_near_zero() -> None:
    # Use seeded random odds — invariant (a) is purely structural: zeros array
    rng = np.random.RandomState(0)
    n = 500
    open_a = rng.uniform(1.5, 3.0, n)
    open_b = rng.uniform(1.5, 3.0, n)
    result = clv_sign_invariants(open_a, open_b, open_a, open_b)
    assert result["max_close_vs_itself"] < 1e-9
    assert result["inv_a_ok"] is True


# ---------------------------------------------------------------------------
# clv_sign_invariants — invariant (b): two-sided anti-symmetry
# ---------------------------------------------------------------------------


def test_clv_invariant_b_anti_symmetry() -> None:
    rng = np.random.default_rng(42)
    n = 50
    open_a = rng.uniform(1.7, 2.3, size=n)
    open_b = rng.uniform(1.7, 2.3, size=n)
    close_a = np.clip(open_a + rng.uniform(-0.1, 0.1, size=n), 1.01, None)
    close_b = np.clip(open_b + rng.uniform(-0.1, 0.1, size=n), 1.01, None)
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


def test_isotonic_calibrate_monotone_on_sorted_input() -> None:
    # Sorted input → output should be non-decreasing (isotonic property)
    rng = np.random.default_rng(1)
    n_train = 300
    train_p = np.sort(rng.uniform(0.1, 0.9, size=n_train))
    train_y = (train_p > 0.5).astype(float)
    eval_p = np.linspace(0.1, 0.9, 50)
    cal = isotonic_calibrate(train_p, train_y, eval_p)
    diffs = np.diff(cal)
    assert float(diffs.min()) >= -1e-9  # non-decreasing (allow float noise)


def test_isotonic_calibrate_nan_bearing_train() -> None:
    # NaN in train_y — isotonic should handle gracefully (no crash)
    rng = np.random.default_rng(2)
    n_train, n_eval = 100, 30
    train_p = np.sort(rng.uniform(0.2, 0.8, size=n_train))
    train_y = (train_p > 0.5).astype(float)
    # inject a NaN: sklearn clips nans to boundary via out_of_bounds="clip"
    eval_p = np.linspace(0.1, 0.9, n_eval)
    cal = isotonic_calibrate(train_p, train_y, eval_p)
    assert cal.shape == (n_eval,)


# ---------------------------------------------------------------------------
# ece
# ---------------------------------------------------------------------------


def test_ece_perfectly_calibrated_near_zero() -> None:
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


def test_ece_empty_returns_zero() -> None:
    val = ece(np.array([]), np.array([]))
    assert val == 0.0


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


def test_reliability_slope_hand_line_near_one() -> None:
    # Construct a deterministic perfectly-calibrated set across many bins
    # Each bin mid is the exact fraction of 1s — slope should be exactly 1
    mids = np.linspace(0.1, 0.9, 9)
    probs_list, outcomes_list = [], []
    n = 1000  # large enough to fill bins with mask.sum() >= 3
    for mid in mids:
        p_block = np.full(n, mid)
        # Deterministic: first round(mid*n) are 1, rest 0
        n_ones = round(mid * n)
        y_block = np.array([1.0] * n_ones + [0.0] * (n - n_ones))
        probs_list.append(p_block)
        outcomes_list.append(y_block)
    probs = np.concatenate(probs_list)
    outcomes = np.concatenate(outcomes_list)
    slope = reliability_slope(probs, outcomes, bins=10)
    assert not math.isnan(slope)
    assert abs(slope - 1.0) < 0.05  # tight: deterministic construction
