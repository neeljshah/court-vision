"""tests/test_center_blk_scale.py — Cycle 97b (loop 5).

Position-conditioned BLK scale adjustment factory tests:
  1. factor=1.0  -> exactly zero MAE delta (no-op baseline)
  2. factor=1.4  -> BLK pred scales for centers only
  3. non-center position (Guard) -> unchanged
  4. position=None -> unchanged (back-compat for fresh checkouts)
  5. non-BLK stat -> unchanged (single-stat probe)
  6. Walk-forward fold sign matches single-split sign (consistency check)

These tests run without on-disk models — make_center_blk_scale is a pure
post-prediction transform that doesn't depend on the production blend.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.probe_center_blk_scale import (  # noqa: E402
    make_center_blk_scale,
    _CENTER_POSITIONS,
)


# ── synthetic fixtures ───────────────────────────────────────────────────────

def _rows(positions):
    """Build minimal row dicts with only the keys make_center_blk_scale reads."""
    return [{"position": p} for p in positions]


def _mae(pred, truth, mask=None):
    pred = np.asarray(pred, dtype=float)
    truth = np.asarray(truth, dtype=float)
    if mask is None:
        return float(np.mean(np.abs(pred - truth)))
    return float(np.mean(np.abs(pred[mask] - truth[mask])))


# ── tests ────────────────────────────────────────────────────────────────────

def test_factor_one_is_exact_noop_on_blk():
    """factor=1.0 must produce IDENTICAL float values on BLK (cycle 97a)."""
    fn = make_center_blk_scale(factor=1.0)
    pred = np.array([0.5, 1.2, 0.8, 0.3, 2.1], dtype=float)
    rows = _rows(["Center", "Guard", "Center-Forward", None, "Forward-Center"])
    out = fn(pred, rows, "blk")
    np.testing.assert_array_equal(out, pred)
    # MAE delta against any truth vector is exactly 0.
    truth = np.array([0.0, 1.0, 1.0, 0.0, 3.0], dtype=float)
    assert _mae(out, truth) - _mae(pred, truth) == 0.0


def test_factor_scales_blk_for_centers_only():
    """factor=1.4 multiplies BLK pred only for rows whose position is a center bucket."""
    fn = make_center_blk_scale(factor=1.4)
    pred = np.array([1.0, 1.0, 1.0, 1.0, 1.0], dtype=float)
    rows = _rows(["Center", "Guard", "Center-Forward", "Forward", "Forward-Center"])
    out = fn(pred, rows, "blk")
    # Centers (idx 0, 2, 4) scaled to 1.4; others (1, 3) unchanged.
    expected = np.array([1.4, 1.0, 1.4, 1.0, 1.4], dtype=float)
    np.testing.assert_allclose(out, expected, rtol=0, atol=1e-12)


def test_non_center_position_unchanged():
    """Guards / Forwards / unknown strings must never be scaled."""
    fn = make_center_blk_scale(factor=1.5)
    pred = np.array([0.7, 0.4, 0.2, 0.9], dtype=float)
    # Mix of non-center positions including 'Forward', 'Guard', 'Guard-Forward',
    # and a totally unrecognised string. None of them are in _CENTER_POSITIONS.
    rows = _rows(["Guard", "Forward", "Guard-Forward", "PointGuard"])
    out = fn(pred, rows, "blk")
    np.testing.assert_array_equal(out, pred)


def test_position_none_back_compat_noop():
    """position=None (fresh-checkout / parquet absent) must be a no-op (back-compat)."""
    fn = make_center_blk_scale(factor=1.74)
    pred = np.array([0.6, 0.6, 0.6, 0.6], dtype=float)
    rows = _rows([None, None, None, None])
    out = fn(pred, rows, "blk")
    np.testing.assert_array_equal(out, pred)


def test_non_blk_stat_unchanged():
    """Every non-BLK stat must be untouched even when rows are all centers."""
    fn = make_center_blk_scale(factor=1.5)
    pred = np.array([10.0, 5.0, 3.0, 1.0], dtype=float)
    rows = _rows(["Center", "Center-Forward", "Forward-Center", "Center"])
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "tov"):
        out = fn(pred, rows, stat)
        np.testing.assert_array_equal(
            out, pred,
            err_msg=f"stat={stat!r} must be unchanged (single-stat probe)"
        )


def test_walk_forward_fold_sign_matches_single_split_sign():
    """Consistency check: BLK MAE delta sign on synthetic folds equals single-split sign.

    Build a deterministic dataset where the truth values for centers are
    larger than the prediction (so a >1 factor improves MAE), and confirm
    that each fold AND the aggregate single-split MAE delta are all negative
    (improvement). This pins the post-prediction adjustment's monotonicity:
    when WF folds agree with single-split, the ship gate's dual-test isn't
    a coin flip on the holdout slicing.
    """
    rng = np.random.default_rng(42)
    n = 200
    positions = list(_CENTER_POSITIONS) + ["Guard", "Forward", "Guard-Forward"]
    rows = []
    truth = []
    pred = []
    for _ in range(n):
        p = positions[rng.integers(0, len(positions))]
        rows.append({"position": p})
        if p in _CENTER_POSITIONS:
            # Centers: model under-predicts (matches cycle 96e finding)
            t = 1.0
            pr = 0.6
        else:
            # Non-centers: model is calibrated
            t = 0.3
            pr = 0.3
        truth.append(t)
        pred.append(pr)
    pred_arr = np.array(pred, dtype=float)
    truth_arr = np.array(truth, dtype=float)

    factor = 1.5
    fn = make_center_blk_scale(factor=factor)

    # Single-split delta
    adj = fn(pred_arr, rows, "blk")
    ss_delta = _mae(adj, truth_arr) - _mae(pred_arr, truth_arr)
    assert ss_delta < 0, f"single-split delta {ss_delta:+.4f} must improve"

    # 4-fold deltas
    fold_size = n // 4
    fold_signs = []
    for fold_i in range(4):
        lo = fold_i * fold_size
        hi = n if fold_i == 3 else (fold_i + 1) * fold_size
        sub_rows = rows[lo:hi]
        sub_pred = pred_arr[lo:hi]
        sub_truth = truth_arr[lo:hi]
        sub_adj = fn(sub_pred, sub_rows, "blk")
        d = _mae(sub_adj, sub_truth) - _mae(sub_pred, sub_truth)
        fold_signs.append(d)
    # Every fold must agree with the single-split sign — same direction
    # of improvement, no fold-by-fold reversal.
    assert all(d < 0 for d in fold_signs), (
        f"WF folds {fold_signs} disagree with single-split delta {ss_delta:+.4f}"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
