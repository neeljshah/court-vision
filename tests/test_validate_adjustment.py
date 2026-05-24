"""Tests for scripts/validate_adjustment.py (cycle 78).

These tests verify the HARNESS itself works correctly — they don't make
claims about whether any particular adjustment improves MAE. That's an
empirical question the harness answers when actually run against the
production dataset.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.validate_adjustment as va  # noqa: E402


def test_no_op_returns_identical_array():
    """no_op MUST return predictions unchanged — if it doesn't, every
    adjustment validation downstream becomes meaningless."""
    pred = np.array([10.0, 20.0, 30.0])
    out = va.no_op(pred, [{}, {}, {}], "pts")
    assert np.array_equal(out, pred)
    # And a separate buffer — not the same numpy object — so a caller
    # mutating the result doesn't mutate the original.
    out[0] = 999
    assert pred[0] == 10.0


def test_scale_constant_applies_factor_and_floors_at_zero():
    pred = np.array([10.0, 20.0, -5.0])    # -5 shouldn't happen but test the floor
    fn = va.make_scale_constant(0.5)
    out = fn(pred, [{}, {}, {}], "pts")
    assert out[0] == pytest.approx(5.0)
    assert out[1] == pytest.approx(10.0)
    assert out[2] == 0.0     # clipped at zero


def test_scale_by_min_ratio_buckets_correctly():
    """Each row's prev_min/l10_min ratio drives the bucket."""
    pred = np.array([20.0, 20.0, 20.0])
    rows = [
        {"prev_min": 10.0, "l10_min": 30.0},   # ratio 0.33 → low → 0.50x
        {"prev_min": 24.0, "l10_min": 30.0},   # ratio 0.80 → mid → 0.85x
        {"prev_min": 30.0, "l10_min": 30.0},   # ratio 1.00 → starter → 1.0x
    ]
    fn = va.make_scale_by_min_ratio()
    out = fn(pred, rows, "pts")
    assert out[0] == pytest.approx(10.0)    # 20 * 0.50
    assert out[1] == pytest.approx(17.0)    # 20 * 0.85
    assert out[2] == pytest.approx(20.0)    # 20 * 1.00


def test_scale_by_min_ratio_no_op_on_zero_l10():
    """Rookies / players with no L10 history shouldn't trigger scaling
    (would divide-by-zero or silently zero good predictions)."""
    pred = np.array([20.0])
    rows = [{"prev_min": 0.0, "l10_min": 0.0}]
    fn = va.make_scale_by_min_ratio()
    out = fn(pred, rows, "pts")
    assert out[0] == pytest.approx(20.0)    # untouched


def test_scale_by_min_ratio_custom_thresholds():
    """Caller can pass tighter/looser bands than the default 0.5/0.9."""
    pred = np.array([20.0])
    rows = [{"prev_min": 20.0, "l10_min": 30.0}]    # ratio 0.667
    # With default bands (0.5/0.9), 0.667 falls in mid → 0.85x → 17.0
    out_default = va.make_scale_by_min_ratio()(pred, rows, "pts")
    assert out_default[0] == pytest.approx(17.0)
    # With looser low band (0.7), 0.667 falls in low → 0.50x → 10.0
    out_loose = va.make_scale_by_min_ratio(
        low_thr=0.7, factor_low=0.50)(pred, rows, "pts")
    assert out_loose[0] == pytest.approx(10.0)


def test_validate_no_op_returns_zero_delta_on_synthetic_data(monkeypatch):
    """The killer sanity test: validate(no_op) on a tiny synthetic stand-in
    must report delta_mae == 0 for every stat. If it doesn't, the harness
    itself is broken and every downstream conclusion is suspect."""
    # Mock _bulk_predict to return a known array — no model files needed.
    pred = np.array([10.0, 20.0, 30.0])
    monkeypatch.setattr(va, "_bulk_predict", lambda stat, X: pred.copy())
    rows = [
        {"target_pts": 12.0, "target_reb": 5.0, "target_ast": 3.0,
         "target_fg3m": 1.0, "target_stl": 1.0, "target_blk": 0.0, "target_tov": 2.0},
        {"target_pts": 22.0, "target_reb": 8.0, "target_ast": 7.0,
         "target_fg3m": 2.0, "target_stl": 0.0, "target_blk": 1.0, "target_tov": 3.0},
        {"target_pts": 28.0, "target_reb": 10.0, "target_ast": 9.0,
         "target_fg3m": 3.0, "target_stl": 1.0, "target_blk": 1.0, "target_tov": 4.0},
    ]
    X = np.zeros((3, 1), dtype=float)
    out = va.validate(va.no_op, rows, X, stats=["pts"])
    assert out["pts"]["delta_mae"] == pytest.approx(0.0)
    assert out["pts"]["baseline_mae"] == out["pts"]["adjusted_mae"]
    assert out["pts"]["n"] == 3


def test_validate_constant_scale_changes_mae_correctly(monkeypatch):
    """If predictions are [10,20,30] and actuals are also [10,20,30],
    baseline MAE is 0. Scaling by 0.5 gives [5,10,15] → MAE = 10.0.
    Delta should be exactly +10.0 (worse)."""
    pred = np.array([10.0, 20.0, 30.0])
    monkeypatch.setattr(va, "_bulk_predict", lambda stat, X: pred.copy())
    rows = [{"target_pts": 10.0}, {"target_pts": 20.0}, {"target_pts": 30.0}]
    X = np.zeros((3, 1))
    out = va.validate(va.make_scale_constant(0.5), rows, X, stats=["pts"])
    assert out["pts"]["baseline_mae"] == pytest.approx(0.0)
    assert out["pts"]["adjusted_mae"] == pytest.approx(10.0)    # (5+10+15)/3 = 10
    assert out["pts"]["delta_mae"] == pytest.approx(10.0)


def test_validate_excludes_nan_targets(monkeypatch):
    """Rows with missing target (rare but possible for rookies) shouldn't
    contribute to the MAE — silently dropping them is correct."""
    pred = np.array([10.0, 20.0, 30.0])
    monkeypatch.setattr(va, "_bulk_predict", lambda stat, X: pred.copy())
    rows = [{"target_pts": 10.0}, {"target_pts": None}, {"target_pts": 30.0}]
    X = np.zeros((3, 1))
    out = va.validate(va.no_op, rows, X, stats=["pts"])
    # Only 2 rows had valid targets; MAE = 0 on both.
    assert out["pts"]["n"] == 2
    assert out["pts"]["baseline_mae"] == 0.0


def test_validate_treats_zero_target_as_valid_not_nan(monkeypatch):
    """REGRESSION: the previous `r.get(...) or np.nan` idiom evaluated
    0.0 as falsy and excluded the row. For sparse stats (BLK, STL),
    most games HAVE a zero target — excluding them inflated MAE wildly
    (BLK went 0.44 -> 1.19). Lock the fix in: zero target counts."""
    pred = np.array([0.5, 0.5, 0.5])
    monkeypatch.setattr(va, "_bulk_predict", lambda stat, X: pred.copy())
    # Three players: actuals 0, 0, 1 (typical BLK distribution).
    rows = [{"target_blk": 0.0}, {"target_blk": 0.0}, {"target_blk": 1.0}]
    X = np.zeros((3, 1))
    out = va.validate(va.no_op, rows, X, stats=["blk"])
    # All 3 rows must be counted. MAE = (0.5 + 0.5 + 0.5) / 3 = 0.5
    assert out["blk"]["n"] == 3
    assert out["blk"]["baseline_mae"] == pytest.approx(0.5)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
