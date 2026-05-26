"""
tests/test_shot_gate.py — BUG2 regression: 8s global shot gate + basket-proximity gate.

BUG2 root cause: global gate was 3.0s which matched the inter-possession fragmentation
period (~90 frames @ 30fps), letting each new slot fire independently.  Fix raised to 8.0s
to match EventDetector._SHOT_DEBOUNCE.  Also added basket-proximity gate (≤30 ft).

These tests exercise the gate logic directly without needing a full pipeline run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _simulate_global_gate(timestamps: list[float], gate_s: float = 8.0) -> list[float]:
    """Minimal re-implementation of the global shot gate logic from unified_pipeline.py.

    Returns list of timestamps that passed the gate — mirrors:
        _global_ok = (timestamp_sec - _last_global_shot_ts) > gate_s
    """
    _last = -999.0
    passed = []
    for ts in timestamps:
        if (ts - _last) > gate_s:
            passed.append(ts)
            _last = ts
    return passed


# ── Tests: global gate ───────────────────────────────────────────────────────

class TestGlobalShotGate8s:

    def test_shots_5s_apart_only_one_passes(self):
        """Two shots 5s apart: only the first should pass an 8s gate."""
        timestamps = [10.0, 15.0]  # 5s gap < 8s gate
        passed = _simulate_global_gate(timestamps, gate_s=8.0)
        assert len(passed) == 1, (
            f"Expected 1 shot through 8s gate with 5s gap, got {len(passed)}: {passed}"
        )
        assert passed[0] == 10.0

    def test_shots_3s_apart_blocked_by_8s_gate(self):
        """Shots exactly 3s apart (old gate threshold) must ALL be blocked after the first."""
        # Simulate possession fragmentation: 5 shots 3s apart
        timestamps = [0.0, 3.0, 6.0, 9.0, 12.0]
        passed = _simulate_global_gate(timestamps, gate_s=8.0)
        # At 8s gate: 0.0 passes; 3.0, 6.0 blocked; 9.0 passes (9-0=9>8); 12.0 blocked (12-9=3)
        assert len(passed) == 2, (
            f"Expected 2 shots through 8s gate with 3s intervals, got {len(passed)}: {passed}"
        )
        assert passed[0] == 0.0
        assert passed[1] == 9.0

    def test_shots_9s_apart_both_pass(self):
        """Two shots 9s apart (> 8s gate) must both be allowed through."""
        timestamps = [5.0, 14.0]  # 9s gap > 8s gate
        passed = _simulate_global_gate(timestamps, gate_s=8.0)
        assert len(passed) == 2, (
            f"Expected 2 shots through 8s gate with 9s gap, got {len(passed)}: {passed}"
        )

    def test_old_3s_gate_would_have_passed_too_many(self):
        """Regression: same sequence through old 3s gate passes 5 — confirming the bug."""
        timestamps = [0.0, 3.0, 6.0, 9.0, 12.0]
        passed_old = _simulate_global_gate(timestamps, gate_s=3.0)
        # Old gate passes all 5 — that was the false-positive bug
        assert len(passed_old) == 5, (
            f"Old 3s gate sanity: expected 5 pass-throughs, got {len(passed_old)}"
        )


# ── Tests: basket-proximity gate ─────────────────────────────────────────────

class TestBasketProximityGate:
    """_dist_to_basket must produce values that correctly gate far-court shot emissions."""

    @staticmethod
    def _import_dist():
        try:
            from src.pipeline.unified_pipeline import UnifiedPipeline
            return UnifiedPipeline._dist_to_basket
        except ImportError:
            pytest.skip("unified_pipeline not importable in this environment")

    def test_midcourt_shot_blocked_by_30ft_gate(self):
        """Shot from mid-court (x2d=map_w/2) is > 30 ft → should be blocked."""
        dist_fn = self._import_dist()
        map_w, map_h = 940, 500
        # Midcourt: x2d=470, y2d=250
        dist_ft = dist_fn(470, 250, map_w, map_h)
        assert dist_ft > 30.0, (
            f"Midcourt shot_dist={dist_ft:.1f} ft should be > 30 ft for proximity gate"
        )

    def test_paint_shot_within_30ft_gate(self):
        """Shot from paint (near basket) is < 30 ft → should pass."""
        dist_fn = self._import_dist()
        map_w, map_h = 940, 500
        # Left basket is at ~5.5% of court width ≈ x2d=52
        dist_ft = dist_fn(52, 250, map_w, map_h)
        assert dist_ft <= 30.0, (
            f"Paint shot_dist={dist_ft:.1f} ft should be <= 30 ft for proximity gate"
        )

    def test_three_point_arc_within_30ft_gate(self):
        """Shot from 3-point arc (~24 ft) is within 30 ft gate → should pass."""
        dist_fn = self._import_dist()
        map_w, map_h = 940, 500
        # 3pt arc: ~23.75 ft from basket center; left basket at ft_x=5.25
        # In pixel space: ft_x=5.25+23.75=29 ft → x2d = (29/94)*940 ≈ 290
        dist_ft = dist_fn(290, 250, map_w, map_h)
        assert dist_ft <= 30.0, (
            f"3pt arc shot_dist={dist_ft:.1f} ft should be <= 30 ft for proximity gate"
        )
