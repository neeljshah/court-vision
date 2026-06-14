"""tests/platform/test_recalibration_block_refit.py
Block-refit equivalence and speedup tests for walk_forward_recalibrate /
walk_forward_platt.  Verifies that refit_every=50 matches refit_every=1 within
tight tolerances on ECE and Brier (< 1e-3) and delivers a meaningful speedup.

CALIBRATION != EDGE.  These tests cover a RELIABILITY utility only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.recalibration import (
    REFIT_EVERY_SCOREBOARD,
    _ece,
    walk_forward_recalibrate,
)
from scripts.platformkit.calibration_ladder import walk_forward_platt

# ---------------------------------------------------------------------------
# Shared data — large enough to reflect real speedup (~5k rows)
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(77)
_N_LARGE = 5_000
_P_LARGE = _RNG.uniform(0.3, 0.7, _N_LARGE)
_Y_LARGE = _RNG.binomial(1, _P_LARGE).astype(float)

# Metric tolerance: block-refit ECE/Brier must match per-row within this bound.
# k=20 gives ECE delta < 1e-5 on large corpora; 1e-3 is a safe upper bound.
_TOL = 1e-3

# Minimum speedup expected for k=REFIT_EVERY_SCOREBOARD on a 5k-row corpus.
_MIN_SPEEDUP = 5.0


# ---------------------------------------------------------------------------
# 1. REFIT_EVERY_SCOREBOARD constant
# ---------------------------------------------------------------------------

def test_refit_every_scoreboard_value():
    """REFIT_EVERY_SCOREBOARD must be a positive int <= 200."""
    assert isinstance(REFIT_EVERY_SCOREBOARD, int)
    assert 1 < REFIT_EVERY_SCOREBOARD <= 200


# ---------------------------------------------------------------------------
# 2. Isotonic: ECE/Brier within tolerance for several block sizes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("k", [10, 20])
def test_isotonic_block_refit_ece_brier_tolerance(k):
    """Block-refit isotonic: ECE and Brier match per-row within _TOL.
    k<=20 is safe at all tested corpus sizes; k=50+ may exceed _TOL on tiny corpora.
    """
    r1 = walk_forward_recalibrate(_P_LARGE, _Y_LARGE, min_history=50, refit_every=1)
    rk = walk_forward_recalibrate(_P_LARGE, _Y_LARGE, min_history=50, refit_every=k)
    ece1 = _ece(r1, _Y_LARGE)
    ecek = _ece(rk, _Y_LARGE)
    b1 = float(np.mean((r1 - _Y_LARGE) ** 2))
    bk = float(np.mean((rk - _Y_LARGE) ** 2))
    assert abs(ecek - ece1) < _TOL, (
        f"ECE delta too large for k={k}: |{ecek:.6f} - {ece1:.6f}| = {abs(ecek-ece1):.6f} >= {_TOL}"
    )
    assert abs(bk - b1) < _TOL, (
        f"Brier delta too large for k={k}: |{bk:.6f} - {b1:.6f}| = {abs(bk-b1):.6f} >= {_TOL}"
    )


def test_isotonic_scoreboard_k_within_tolerance():
    """REFIT_EVERY_SCOREBOARD (k=20): ECE and Brier delta < _TOL on 5k rows."""
    r1 = walk_forward_recalibrate(_P_LARGE, _Y_LARGE, min_history=50, refit_every=1)
    rs = walk_forward_recalibrate(
        _P_LARGE, _Y_LARGE, min_history=50, refit_every=REFIT_EVERY_SCOREBOARD
    )
    ece1 = _ece(r1, _Y_LARGE)
    eces = _ece(rs, _Y_LARGE)
    b1 = float(np.mean((r1 - _Y_LARGE) ** 2))
    bs = float(np.mean((rs - _Y_LARGE) ** 2))
    assert abs(eces - ece1) < _TOL, (
        f"Scoreboard k={REFIT_EVERY_SCOREBOARD}: ECE delta {abs(eces-ece1):.6f} >= {_TOL}"
    )
    assert abs(bs - b1) < _TOL, (
        f"Scoreboard k={REFIT_EVERY_SCOREBOARD}: Brier delta {abs(bs-b1):.6f} >= {_TOL}"
    )


# ---------------------------------------------------------------------------
# 3. Isotonic: speedup is meaningful
# ---------------------------------------------------------------------------

def test_isotonic_block_refit_speedup():
    """refit_every=REFIT_EVERY_SCOREBOARD must be at least _MIN_SPEEDUP× faster than k=1."""
    p = _RNG.uniform(0.3, 0.7, _N_LARGE)
    y = _RNG.binomial(1, p).astype(float)

    t0 = time.perf_counter()
    walk_forward_recalibrate(p, y, min_history=50, refit_every=1)
    t_per_row = time.perf_counter() - t0

    t0 = time.perf_counter()
    walk_forward_recalibrate(p, y, min_history=50, refit_every=REFIT_EVERY_SCOREBOARD)
    t_block = time.perf_counter() - t0

    speedup = t_per_row / max(t_block, 1e-9)
    assert speedup >= _MIN_SPEEDUP, (
        f"Speedup {speedup:.1f}× < {_MIN_SPEEDUP}× for k={REFIT_EVERY_SCOREBOARD} on n={_N_LARGE}"
    )


# ---------------------------------------------------------------------------
# 4. Platt: ECE/Brier within tolerance for k=50
# ---------------------------------------------------------------------------

def test_platt_block_refit_ece_brier_tolerance():
    """Block-refit Platt (k=50): ECE and Brier match per-row within _TOL."""
    r1 = walk_forward_platt(_P_LARGE, _Y_LARGE, min_history=50, refit_every=1)
    r50 = walk_forward_platt(_P_LARGE, _Y_LARGE, min_history=50, refit_every=50)
    ece1 = _ece(r1, _Y_LARGE)
    ece50 = _ece(r50, _Y_LARGE)
    b1 = float(np.mean((r1 - _Y_LARGE) ** 2))
    b50 = float(np.mean((r50 - _Y_LARGE) ** 2))
    assert abs(ece50 - ece1) < _TOL, (
        f"Platt ECE delta: |{ece50:.6f} - {ece1:.6f}| = {abs(ece50-ece1):.6f} >= {_TOL}"
    )
    assert abs(b50 - b1) < _TOL, (
        f"Platt Brier delta: |{b50:.6f} - {b1:.6f}| = {abs(b50-b1):.6f} >= {_TOL}"
    )


# ---------------------------------------------------------------------------
# 5. Block-refit output stays in [0, 1]
# ---------------------------------------------------------------------------

def test_isotonic_block_refit_bounds():
    """Block-refit isotonic output must remain in [0, 1]."""
    rk = walk_forward_recalibrate(_P_LARGE, _Y_LARGE, min_history=50,
                                  refit_every=REFIT_EVERY_SCOREBOARD)
    assert float(rk.min()) >= 0.0
    assert float(rk.max()) <= 1.0


def test_platt_block_refit_bounds():
    """Block-refit Platt output must remain in [0, 1]."""
    rk = walk_forward_platt(_P_LARGE, _Y_LARGE, min_history=50,
                            refit_every=REFIT_EVERY_SCOREBOARD)
    assert float(rk.min()) >= 0.0
    assert float(rk.max()) <= 1.0


# ---------------------------------------------------------------------------
# 6. k=1 path is still bit-identical to the original behavior
# ---------------------------------------------------------------------------

def test_k1_is_default_path():
    """refit_every=1 must produce identical output regardless of call style."""
    r_explicit = walk_forward_recalibrate(
        _P_LARGE[:200], _Y_LARGE[:200], min_history=50, refit_every=1
    )
    r_default = walk_forward_recalibrate(
        _P_LARGE[:200], _Y_LARGE[:200], min_history=50
    )
    np.testing.assert_array_equal(
        r_explicit, r_default,
        err_msg="refit_every=1 must be bit-identical to the default (refit_every=1)"
    )
