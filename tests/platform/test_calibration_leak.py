"""tests/platform/test_calibration_leak.py

Leak battery for domains/soccer/calibration.py::walk_forward_calibrate.

Tests:
  (1) OUTCOME-INDEPENDENCE — permuting/flipping outcomes[k:] for k > j leaves
      calibrated[:j+1] bit-identical.  Core leak proof by construction.
  (2) DETERMINISM — two calls identical.
  (3) TRUNCATION-INVARIANCE — calibrated[:k] on the full sequence == calibrated
      on the length-k prefix.
  (4) BOUNDS — all calibrated values in [0, 1].
  (5) NaN/inf INPUTS — don't crash; output stays bounded.
      If the implementation does NOT guard NaN, the test is xfail(strict=False)
      with a clear finding note.

No corpora needed — all synthetic data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Make repo root importable when run directly.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.soccer.calibration import walk_forward_calibrate  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture: synthetic sequence long enough to clear warmup (50)
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)
_N = 150
_MIN_H = 50  # matches MIN_HISTORY default; passed explicitly for clarity

_RAW: np.ndarray = _RNG.uniform(0.3, 0.7, size=_N)
_OUT: np.ndarray = (_RNG.uniform(size=_N) < _RAW).astype(float)


# ---------------------------------------------------------------------------
# (1) OUTCOME-INDEPENDENCE
# ---------------------------------------------------------------------------


def test_outcome_independence_permute():
    """Permuting outcomes[k:] must not affect calibrated[:j+1] for any j < k."""
    k = 80   # future boundary
    j = 60   # inspect calibrated through this index (warmup-cleared)

    ref = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)

    rng2 = np.random.default_rng(99)
    out_permuted = _OUT.copy()
    perm_idx = rng2.permutation(np.arange(k, _N))
    out_permuted[k:] = out_permuted[perm_idx]

    perturbed = walk_forward_calibrate(_RAW, out_permuted, min_history=_MIN_H)

    assert np.array_equal(ref[: j + 1], perturbed[: j + 1]), (
        "LEAK DETECTED: calibrated[:j+1] changed when outcomes[k:] were permuted. "
        f"k={k}, j={j}. "
        f"Max diff = {np.max(np.abs(ref[:j+1] - perturbed[:j+1]))}"
    )


def test_outcome_independence_flip():
    """Flipping outcomes[k:] must not affect calibrated[:j+1] for j < k."""
    k = 90
    j = 70

    ref = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)

    out_flipped = _OUT.copy()
    out_flipped[k:] = 1.0 - out_flipped[k:]

    flipped = walk_forward_calibrate(_RAW, out_flipped, min_history=_MIN_H)

    assert np.array_equal(ref[: j + 1], flipped[: j + 1]), (
        "LEAK DETECTED: calibrated[:j+1] changed when outcomes[k:] were flipped. "
        f"k={k}, j={j}. "
        f"Max diff = {np.max(np.abs(ref[:j+1] - flipped[:j+1]))}"
    )


def test_outcome_independence_warmup_zone():
    """Warmup-zone outputs (i < min_history) must be raw regardless of ANY outcomes."""
    out_all_zero = np.zeros(_N)
    out_all_one = np.ones(_N)

    cal_zero = walk_forward_calibrate(_RAW, out_all_zero, min_history=_MIN_H)
    cal_one = walk_forward_calibrate(_RAW, out_all_one, min_history=_MIN_H)

    # In warmup zone calibrated[i] == raw[i]; outcomes are irrelevant.
    np.testing.assert_array_equal(
        cal_zero[:_MIN_H],
        cal_one[:_MIN_H],
        err_msg="Warmup-zone outputs differ between all-0 and all-1 outcomes — "
                "should be identical (pass-through raw).",
    )
    np.testing.assert_array_equal(
        cal_zero[:_MIN_H],
        _RAW[:_MIN_H].astype(float),
        err_msg="Warmup-zone outputs do not match raw inputs.",
    )


# ---------------------------------------------------------------------------
# (2) DETERMINISM
# ---------------------------------------------------------------------------


def test_determinism():
    """Two calls with identical inputs must return bit-identical arrays."""
    a = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)
    b = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)
    np.testing.assert_array_equal(
        a, b, err_msg="walk_forward_calibrate is non-deterministic across two calls."
    )


# ---------------------------------------------------------------------------
# (3) TRUNCATION-INVARIANCE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("k", [_MIN_H, _MIN_H + 10, _MIN_H + 30, _N - 1])
def test_truncation_invariance(k: int):
    """calibrated[:k] on the full sequence must equal calibrated on the prefix [:k]."""
    full = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)
    prefix = walk_forward_calibrate(_RAW[:k], _OUT[:k], min_history=_MIN_H)

    np.testing.assert_array_equal(
        full[:k],
        prefix,
        err_msg=(
            f"Truncation-invariance violated at k={k}: "
            f"calibrated[:k] on full != calibrated on prefix. "
            f"First mismatch at index {np.argmax(full[:k] != prefix)}."
        ),
    )


# ---------------------------------------------------------------------------
# (4) BOUNDS [0, 1]
# ---------------------------------------------------------------------------


def test_output_bounds():
    """All calibrated values must lie in [0, 1]."""
    cal = walk_forward_calibrate(_RAW, _OUT, min_history=_MIN_H)
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0), (
        f"Output out of [0, 1]: min={cal.min():.6f}, max={cal.max():.6f}"
    )


def test_output_bounds_extreme_probs():
    """Even with raw probs near 0 and 1 the output stays in [0, 1]."""
    rng = np.random.default_rng(7)
    raw_extreme = rng.choice([0.01, 0.99], size=_N)
    out = (rng.uniform(size=_N) < 0.5).astype(float)
    cal = walk_forward_calibrate(raw_extreme, out, min_history=_MIN_H)
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0), (
        f"Output out of [0, 1] on extreme probs: min={cal.min():.6f}, max={cal.max():.6f}"
    )


# ---------------------------------------------------------------------------
# (5) NaN / inf INPUTS
# ---------------------------------------------------------------------------

# The core walk_forward_calibrate now guards NaN/inf: invalid entries are
# dropped from the fit window, and invalid query points are passed through.
# These were xfail; they are now real PASS assertions.


def test_nan_in_raw_probs_does_not_crash():
    """NaN in raw_probs must not crash; output at non-NaN indices must be finite."""
    raw_with_nan = _RAW.copy()
    raw_with_nan[55] = float("nan")  # past warmup, was poisoning future IR fits

    cal = walk_forward_calibrate(raw_with_nan, _OUT, min_history=_MIN_H)

    finite_mask = ~np.isnan(raw_with_nan)
    assert np.all(np.isfinite(cal[finite_mask])), (
        "Non-NaN input positions produced non-finite calibrated values."
    )


def test_inf_in_raw_probs_does_not_crash():
    """inf in raw_probs must not crash; all finite-input outputs must stay finite."""
    raw_with_inf = _RAW.copy()
    raw_with_inf[60] = float("inf")

    cal = walk_forward_calibrate(raw_with_inf, _OUT, min_history=_MIN_H)

    # The inf entry itself passes through (clipped to 1.0); all others finite.
    finite_mask = np.isfinite(raw_with_inf)
    assert np.all(np.isfinite(cal[finite_mask])), (
        f"Finite-input positions produced non-finite calibrated output: "
        f"{cal[finite_mask][~np.isfinite(cal[finite_mask])]}"
    )
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0), (
        f"Output out of [0, 1]: min={cal.min():.6f}, max={cal.max():.6f}"
    )


def test_nan_in_outcomes_does_not_crash():
    """NaN in outcomes must not crash the function; output must stay bounded."""
    out_with_nan = _OUT.copy()
    out_with_nan[55] = float("nan")

    cal = walk_forward_calibrate(_RAW, out_with_nan, min_history=_MIN_H)

    # Output is a valid array (no exception); all values in [0, 1].
    assert cal is not None
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0), (
        f"Output out of [0, 1] with NaN outcome: min={cal.min():.6f}, max={cal.max():.6f}"
    )
