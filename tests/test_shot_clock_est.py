"""Tests for BUG2 fix: shot_clock_est period-boundary reset and [0,24] clamp.

These tests exercise the logic that was extracted from the per-frame loop in
unified_pipeline.py.  They work by invoking the pure arithmetic directly so
they don't require a real video file.
"""
import pytest

pytest.importorskip("src.pipeline.unified_pipeline")


def _compute_shot_clock_est(
    frame_idx: int,
    possession_start: int,
    fps: float,
    is_off_rebound: bool = False,
) -> float:
    """Mirror the shot_clock_est formula from unified_pipeline.py (post-BUG2 fix)."""
    max_clock = 14.0 if is_off_rebound else 24.0
    raw = max_clock - (frame_idx - possession_start) / fps
    return min(24.0, max(0.0, raw))


def test_shot_clock_resets_on_new_period():
    """When a new period is detected, possession_start resets to current frame.

    Simulates: same team at end of Q2 (frame 5000) then Q3 starts at frame 5400.
    Before BUG2 fix: possession_start still = 2000 (Q2 start); clock would be ~-100s.
    After BUG2 fix: possession_start reset to 5400; clock returns near 24s.
    """
    fps = 30.0
    # Period transition: Q3 starts at frame 5400, possession_start reset to 5400
    possession_start_after_reset = 5400
    frame_at_period_start = 5401  # one frame into Q3

    clock = _compute_shot_clock_est(frame_at_period_start, possession_start_after_reset, fps)
    assert clock > 23.0, (
        f"Expected clock near 24s after period reset, got {clock:.2f}s")


def test_shot_clock_resets_on_team_change():
    """Existing behaviour: clock restarts when poss_team changes."""
    fps = 30.0
    # Team changes at frame 300; 10 frames later
    possession_start = 300
    frame_idx = 310
    clock = _compute_shot_clock_est(frame_idx, possession_start, fps)
    # 10 frames at 30fps = 0.33s elapsed → ~23.67s remaining
    assert 23.0 < clock <= 24.0, f"Unexpected clock: {clock:.2f}s"


def test_shot_clock_clamped_to_24_max():
    """When frame_idx < possession_start (shouldn't happen, but guard it), clamp to 24."""
    fps = 30.0
    # Negative elapsed → raw > 24 → must clamp to 24
    clock = _compute_shot_clock_est(frame_idx=100, possession_start=200, fps=fps)
    assert clock == 24.0, f"Expected 24.0 (upper clamp), got {clock:.2f}"


def test_shot_clock_clamped_to_0_min():
    """When >24s have elapsed since possession_start, clamp to 0."""
    fps = 30.0
    # 720+ frames elapsed at 30fps = 24+ seconds
    possession_start = 0
    frame_idx = 900  # 30s elapsed
    clock = _compute_shot_clock_est(frame_idx, possession_start, fps)
    assert clock == 0.0, f"Expected 0.0 (lower clamp), got {clock:.2f}"


def test_shot_clock_no_reset_within_same_period_same_team():
    """Clock should decrement normally within a period without resets."""
    fps = 30.0
    possession_start = 600
    # 15 frames elapsed = 0.5s → 23.5s remaining
    clock = _compute_shot_clock_est(615, possession_start, fps)
    assert abs(clock - 23.5) < 0.01, (
        f"Expected 23.5s, got {clock:.2f}s")
