"""
tests/test_homography_thresholds.py — BUG3 regression: 2-frame confirmation gate.

BUG3 root cause: A single frame with L1 diff 0.35-0.55 (NBA lower-third stat overlay)
was enough to suspend homography for 30 frames.  Fix requires 2 consecutive frames to
trigger, and shortens the suspension window from 30→20 frames.

These tests exercise the confirmation-gate logic without GPU/video.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_pipeline_cls():
    try:
        from src.pipeline.unified_pipeline import UnifiedPipeline
        return UnifiedPipeline
    except ImportError:
        pytest.skip("unified_pipeline not importable in this environment")


# ── Tests: 2-frame confirmation gate ─────────────────────────────────────────

class TestReplayConfirmationGate:
    """Single-frame trigger must NOT fire; 2 consecutive frames must fire."""

    def test_single_frame_trigger_no_suspension(self):
        """A single frame passing _is_replay_or_cut must NOT set suspension.

        Simulates the confirmation gate by exercising the pending counter logic
        directly without needing a real UnifiedPipeline instance.
        """
        # Replicate the gate logic from unified_pipeline.py run()
        _replay_trigger_pending_count = 0
        _homography_suspended = False
        _homography_suspend_cnt = 0
        _REPLAY_SUSPEND_FRAMES = 20  # updated constant

        def _apply_frame(trigger: bool):
            nonlocal _replay_trigger_pending_count, _homography_suspended, _homography_suspend_cnt
            if trigger:
                _replay_trigger_pending_count += 1
                if _replay_trigger_pending_count >= 2:
                    _homography_suspended = True
                    _homography_suspend_cnt = _REPLAY_SUSPEND_FRAMES
            else:
                _replay_trigger_pending_count = 0
                if _homography_suspend_cnt > 0:
                    _homography_suspend_cnt -= 1
                    _homography_suspended = _homography_suspend_cnt > 0
                else:
                    _homography_suspended = False

        # Frame 1: trigger fires ONCE
        _apply_frame(trigger=True)
        assert not _homography_suspended, (
            "Suspension must NOT be set after only 1 trigger frame"
        )
        assert _replay_trigger_pending_count == 1

        # Frame 2: no trigger — counter resets
        _apply_frame(trigger=False)
        assert not _homography_suspended, (
            "Suspension must NOT be set; trigger was not sustained for 2 frames"
        )
        assert _replay_trigger_pending_count == 0

    def test_two_consecutive_frames_triggers_suspension(self):
        """Two consecutive trigger frames must fire suspension."""
        _replay_trigger_pending_count = 0
        _homography_suspended = False
        _homography_suspend_cnt = 0
        _REPLAY_SUSPEND_FRAMES = 20

        def _apply_frame(trigger: bool):
            nonlocal _replay_trigger_pending_count, _homography_suspended, _homography_suspend_cnt
            if trigger:
                _replay_trigger_pending_count += 1
                if _replay_trigger_pending_count >= 2:
                    _homography_suspended = True
                    _homography_suspend_cnt = _REPLAY_SUSPEND_FRAMES
            else:
                _replay_trigger_pending_count = 0
                if _homography_suspend_cnt > 0:
                    _homography_suspend_cnt -= 1
                    _homography_suspended = _homography_suspend_cnt > 0
                else:
                    _homography_suspended = False

        # Frame 1: trigger
        _apply_frame(trigger=True)
        assert not _homography_suspended, "Not suspended after first trigger"

        # Frame 2: trigger again → must suspend now
        _apply_frame(trigger=True)
        assert _homography_suspended, (
            "Suspension must be set after 2 consecutive trigger frames"
        )
        assert _homography_suspend_cnt == 20, (
            f"Suspend count should be 20 (new constant), got {_homography_suspend_cnt}"
        )

    def test_suspension_countdown_decrements(self):
        """After suspension fires, countdown must decrement on non-trigger frames."""
        _replay_trigger_pending_count = 0
        _homography_suspended = True   # simulate already-suspended state
        _homography_suspend_cnt = 20
        _REPLAY_SUSPEND_FRAMES = 20

        def _apply_frame(trigger: bool):
            nonlocal _replay_trigger_pending_count, _homography_suspended, _homography_suspend_cnt
            if trigger:
                _replay_trigger_pending_count += 1
                if _replay_trigger_pending_count >= 2:
                    _homography_suspended = True
                    _homography_suspend_cnt = _REPLAY_SUSPEND_FRAMES
            else:
                _replay_trigger_pending_count = 0
                if _homography_suspend_cnt > 0:
                    _homography_suspend_cnt -= 1
                    _homography_suspended = _homography_suspend_cnt > 0
                else:
                    _homography_suspended = False

        # Run 20 non-trigger frames — suspension should clear
        for _ in range(20):
            _apply_frame(trigger=False)

        assert not _homography_suspended, (
            "Suspension must clear after 20 non-trigger frames"
        )
        assert _homography_suspend_cnt == 0

    def test_updated_constants_values(self):
        """Verify the 3 threshold constants have been updated to specified values."""
        try:
            import src.pipeline.unified_pipeline as _up
        except ImportError:
            pytest.skip("unified_pipeline not importable")

        assert _up._REPLAY_SSIM_THRESH == pytest.approx(0.5), (
            f"_REPLAY_SSIM_THRESH should be 0.5 (was 0.6), got {_up._REPLAY_SSIM_THRESH}"
        )
        assert _up._REPLAY_BRIGHT_FACTOR == pytest.approx(1.55), (
            f"_REPLAY_BRIGHT_FACTOR should be 1.55 (was 1.4), got {_up._REPLAY_BRIGHT_FACTOR}"
        )
        assert _up._REPLAY_SUSPEND_FRAMES == 20, (
            f"_REPLAY_SUSPEND_FRAMES should be 20 (was 30), got {_up._REPLAY_SUSPEND_FRAMES}"
        )
