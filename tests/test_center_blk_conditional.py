"""Cycle 98b (loop 5) — tests for make_center_blk_conditional.

6 tests covering the conditional gate:
  1. factor=1.0 → exact zero MAE delta (no-op)
  2. factor=1.30 + center + top-quartile opp → BLK pred scales
  3. non-center position → unchanged
  4. center + bottom-3-quartile opp → unchanged (conditional gate works)
  5. non-BLK stat → unchanged
  6. position=None → unchanged
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.probe_center_blk_conditional import (  # noqa: E402
    make_center_blk_conditional,
)


_PROXY = "opp_def_blk"
# Synthetic cutoff: rows with proxy >= 1.20 are "in window" (top-quartile).
_CUTOFF = 1.20


def _row(position, proxy_val):
    return {"position": position, _PROXY: proxy_val}


def test_noop_factor_1_zero_delta():
    """factor=1.0 → predictions returned unchanged for ANY input."""
    rows = [
        _row("Center", 1.50),
        _row("Center-Forward", 1.40),
        _row("Forward-Center", 1.30),
        _row("Guard", 1.80),
        _row(None, 1.50),
        _row("Center", 0.50),
        _row("Center", None),
    ]
    pred = np.array([0.8, 1.2, 0.6, 0.4, 0.5, 0.9, 1.1], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.0, invert_proxy=False)
    adj = fn(pred, rows, "blk")
    # MAE delta against the original prediction must be EXACTLY 0
    assert np.array_equal(adj, pred), \
        f"factor=1.0 must be a no-op; got delta={adj - pred}"
    # MAE-against-self must also be exactly 0
    assert float(np.mean(np.abs(adj - pred))) == 0.0


def test_center_top_quartile_scales():
    """Center + opp_def_blk >= cutoff → pred scales by factor."""
    rows = [
        _row("Center", 1.50),           # gated (top-Q)
        _row("Center-Forward", 1.25),   # gated
        _row("Forward-Center", 1.20),   # gated (>= cutoff)
        _row("Forward", 1.50),          # NOT gated (non-center)
        _row("Center", 1.10),           # NOT gated (below cutoff)
    ]
    pred = np.array([1.0, 1.0, 1.0, 1.0, 1.0], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.30, invert_proxy=False)
    adj = fn(pred, rows, "blk")
    expected = np.array([1.30, 1.30, 1.30, 1.00, 1.00], dtype=float)
    np.testing.assert_allclose(adj, expected)


def test_non_center_unchanged():
    """Non-center positions are never scaled, even with top-Q opp."""
    rows = [
        _row("Guard", 2.00),
        _row("Forward", 1.99),
        _row("Guard-Forward", 1.50),
        _row("Forward-Guard", 1.30),
    ]
    pred = np.array([0.5, 0.8, 0.4, 0.6], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.50, invert_proxy=False)
    adj = fn(pred, rows, "blk")
    np.testing.assert_allclose(adj, pred)


def test_center_bottom_quartiles_unchanged():
    """Center + opp below cutoff (bottom-3-quartile) → unchanged."""
    rows = [
        _row("Center", 1.19),         # just below cutoff
        _row("Center", 1.00),         # league average
        _row("Center-Forward", 0.80), # below average
        _row("Forward-Center", 0.50), # well below
    ]
    pred = np.array([0.7, 0.9, 0.5, 0.3], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.40, invert_proxy=False)
    adj = fn(pred, rows, "blk")
    np.testing.assert_allclose(adj, pred)


def test_non_blk_stat_unchanged():
    """Adjustment fires only for stat=='blk'; other stats are no-op even on
    perfectly-gated center top-Q rows."""
    rows = [
        _row("Center", 1.80),
        _row("Center-Forward", 1.50),
        _row("Forward-Center", 1.30),
    ]
    pred = np.array([15.0, 8.0, 4.0], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.40, invert_proxy=False)
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "tov"):
        adj = fn(pred, rows, stat)
        np.testing.assert_allclose(adj, pred,
            err_msg=f"non-BLK stat {stat} got modified: {adj} vs {pred}")


def test_position_none_unchanged():
    """position=None back-compat path → unchanged predictions even at top-Q."""
    rows = [
        _row(None, 2.00),
        _row(None, 1.50),
        _row(None, 1.25),
    ]
    pred = np.array([0.6, 0.8, 0.5], dtype=float)
    fn = make_center_blk_conditional(
        top_quartile_cutoff=_CUTOFF, proxy_feature=_PROXY,
        factor=1.40, invert_proxy=False)
    adj = fn(pred, rows, "blk")
    np.testing.assert_allclose(adj, pred)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
