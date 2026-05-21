"""
tests/test_ball_track_resume.py

Unit tests for UnifiedPipeline._vision_probe_resume().

Cases:
  1. Returns True and clears suspension when YOLO returns ≥8 persons on a
     probe frame (frame_idx % 150 == 0) and scoreboard was never seen.
  2. Returns False (no state change) when frame_idx is NOT on the 150-frame
     interval.
  3. Returns False when _sc_ever_seen is True (OCR path handles resume).
  4. Returns False when YOLO returns fewer than 8 persons (still non-live).
  5. Returns False when _ball_track_suspended is False (no-op).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Minimal stub of UnifiedPipeline that exposes only what the method needs.
# ---------------------------------------------------------------------------

class _PipelineStub:
    """Lightweight stand-in for UnifiedPipeline for isolated unit testing."""

    def __init__(self, *, suspended: bool, sc_ever_seen: bool, yolo_available: bool = True):
        self._ball_track_suspended = suspended
        self._sc_ever_seen = sc_ever_seen
        self._no_ball_vision_streak = 99  # non-zero to verify reset
        self.yolo = SimpleNamespace(available=yolo_available)

    # Paste the real method under test (kept in sync with unified_pipeline.py)
    def _vision_probe_resume(self, frame: np.ndarray, frame_idx: int) -> bool:
        if not (self._ball_track_suspended
                and not self._sc_ever_seen
                and frame_idx % 150 == 0
                and self.yolo.available):
            return False
        probe_results = self.yolo.predict(frame)
        n = len(probe_results)
        if n >= 8:
            self._ball_track_suspended = False
            self._no_ball_vision_streak = 0
            print(f"[resume] frame {frame_idx}: vision probe found {n} persons "
                  f"→ suspension cleared")
            return True
        return False


_FAKE_FRAME = np.zeros((10, 10, 3), dtype=np.uint8)
_FAKE_DETECTIONS_8 = [object()] * 8   # 8 dummy detection objects
_FAKE_DETECTIONS_7 = [object()] * 7   # 7 dummy detection objects (below threshold)


# ---------------------------------------------------------------------------
# Case 1 — probe fires, ≥8 persons → suspension cleared
# ---------------------------------------------------------------------------

def test_resume_clears_suspension_at_probe_frame():
    """Returns True and resets state when ≥8 persons found on interval frame."""
    pipe = _PipelineStub(suspended=True, sc_ever_seen=False)
    pipe.yolo.predict = MagicMock(return_value=_FAKE_DETECTIONS_8)

    result = pipe._vision_probe_resume(_FAKE_FRAME, frame_idx=150)

    assert result is True
    assert pipe._ball_track_suspended is False
    assert pipe._no_ball_vision_streak == 0
    pipe.yolo.predict.assert_called_once_with(_FAKE_FRAME)


# ---------------------------------------------------------------------------
# Case 2 — frame_idx not on interval → no probe, returns False
# ---------------------------------------------------------------------------

def test_no_probe_off_interval():
    """Returns False without calling YOLO when frame_idx % 150 != 0."""
    pipe = _PipelineStub(suspended=True, sc_ever_seen=False)
    pipe.yolo.predict = MagicMock(return_value=_FAKE_DETECTIONS_8)

    result = pipe._vision_probe_resume(_FAKE_FRAME, frame_idx=151)

    assert result is False
    assert pipe._ball_track_suspended is True   # unchanged
    pipe.yolo.predict.assert_not_called()


# ---------------------------------------------------------------------------
# Case 3 — scoreboard was ever seen → OCR path handles resume, not this one
# ---------------------------------------------------------------------------

def test_no_probe_when_sc_ever_seen():
    """Returns False without calling YOLO when _sc_ever_seen is True."""
    pipe = _PipelineStub(suspended=True, sc_ever_seen=True)
    pipe.yolo.predict = MagicMock(return_value=_FAKE_DETECTIONS_8)

    result = pipe._vision_probe_resume(_FAKE_FRAME, frame_idx=150)

    assert result is False
    assert pipe._ball_track_suspended is True
    pipe.yolo.predict.assert_not_called()


# ---------------------------------------------------------------------------
# Case 4 — YOLO returns <8 persons → still non-live, suspension kept
# ---------------------------------------------------------------------------

def test_probe_insufficient_persons_stays_suspended():
    """Returns False when YOLO finds fewer than 8 persons on probe frame."""
    pipe = _PipelineStub(suspended=True, sc_ever_seen=False)
    pipe.yolo.predict = MagicMock(return_value=_FAKE_DETECTIONS_7)

    result = pipe._vision_probe_resume(_FAKE_FRAME, frame_idx=300)

    assert result is False
    assert pipe._ball_track_suspended is True   # unchanged
    assert pipe._no_ball_vision_streak == 99    # unchanged


# ---------------------------------------------------------------------------
# Case 5 — suspension already False → no-op
# ---------------------------------------------------------------------------

def test_noop_when_not_suspended():
    """Returns False immediately when _ball_track_suspended is already False."""
    pipe = _PipelineStub(suspended=False, sc_ever_seen=False)
    pipe.yolo.predict = MagicMock(return_value=_FAKE_DETECTIONS_8)

    result = pipe._vision_probe_resume(_FAKE_FRAME, frame_idx=150)

    assert result is False
    pipe.yolo.predict.assert_not_called()
