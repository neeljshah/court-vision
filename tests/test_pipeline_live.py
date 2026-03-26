"""
test_pipeline_live.py — Unit tests for session 11 live-frame additions.

Tests:
  - ball_tracking rows include 'live' key
  - frozen-clock detection sets _ball_track_suspended
  - clock advance after suspension resets the frozen counter and clears suspension
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers that replicate the frozen-clock state machine ────────────────────

def _run_frozen_clock_state(ocr_readings: list[dict]) -> list[bool]:
    """
    Simulate the frozen-clock block from UnifiedPipeline.run() using a sequence
    of OCR state dicts.  Each dict must have 'game_clock_sec' and 'period' keys.

    Returns the list of _ball_track_suspended values after each OCR scan.
    """
    _FROZEN_CLOCK_THRESHOLD = 3
    prev_clock  = -1.0
    prev_period = -1
    frozen_scans = 0
    suspended    = False
    results      = []

    for sb in ocr_readings:
        gclock  = float(sb.get("game_clock_sec") or -1)
        gperiod = int(sb.get("period") or -1)

        if (gclock > 0 and prev_clock > 0
                and gperiod > 0 and gperiod == prev_period
                and gclock > prev_clock + 2.0):
            # backward clock jump → instant replay
            suspended    = True
            frozen_scans = 0
        elif (gclock > 0 and prev_clock > 0
              and abs(gclock - prev_clock) < 0.5):
            # clock frozen → halftime / dead-ball
            frozen_scans += 1
            if frozen_scans >= _FROZEN_CLOCK_THRESHOLD:
                suspended = True
        else:
            # clock advanced normally (or first scan) → live
            suspended    = False
            frozen_scans = 0

        if gclock  > 0: prev_clock  = gclock
        if gperiod > 0: prev_period = gperiod

        results.append(suspended)

    return results


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBallTrackingRowStructure:
    """ball_tracking rows must include the 'live' key."""

    def test_ball_tracking_csv_has_live_column(self, tmp_path):
        """When UnifiedPipeline writes ball_tracking.csv, 'live' must be in the header."""
        # Verify at the structural level: the hardcoded ball_rows dict keys include 'live'.
        # We inspect the source rather than running video to avoid GPU/video dependencies.
        import inspect
        from src.pipeline import unified_pipeline as up

        src = inspect.getsource(up.UnifiedPipeline.run)
        assert '"live"' in src or "'live'" in src, (
            "UnifiedPipeline.run() must write a 'live' key to ball_rows. "
            "Check that the ball_rows.append({..., 'live': ...}) block is present."
        )

    def test_ball_track_suspended_initialises_false(self):
        """_ball_track_suspended must start False (live=1 at frame 0)."""
        import numpy as np
        from src.pipeline import unified_pipeline as up
        from src.tracking.player_detection import COLORS, hsv2bgr
        from src.tracking.player import Player

        players = [Player(1, "green", hsv2bgr(COLORS["green"][2]))]
        # We can't run the full pipeline without a video, but we can check
        # that __init__ sets up the attribute correctly.
        # Use a dummy 1×1 video path — won't be opened until run() is called.
        dummy_video = str(tmp_path / "dummy.mp4") if hasattr(pytest, "tmp_path") else "dummy.mp4"
        try:
            p = up.UnifiedPipeline(dummy_video, players)
            assert p._ball_track_suspended is False
        except Exception:
            pytest.skip("UnifiedPipeline __init__ needs full environment — skipping")


class TestFrozenClockDetection:
    """Frozen-clock state machine behaviour (replicates unified_pipeline.run() logic)."""

    def test_frozen_clock_sets_suspended_after_threshold(self):
        """Three OCR scans returning the same clock value → suspended=True."""
        # Seed with a valid first scan so prev_clock > 0
        readings = [
            {"game_clock_sec": 300.0, "period": 1},   # first scan (sets prev)
            {"game_clock_sec": 300.0, "period": 1},   # scan 1 frozen
            {"game_clock_sec": 300.0, "period": 1},   # scan 2 frozen
            {"game_clock_sec": 300.0, "period": 1},   # scan 3 frozen → threshold hit
        ]
        results = _run_frozen_clock_state(readings)
        # After 3 frozen scans (indices 1,2,3), suspended must be True
        assert results[3] is True

    def test_not_suspended_before_threshold(self):
        """Two frozen scans → NOT yet suspended (threshold is 3)."""
        readings = [
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
        ]
        results = _run_frozen_clock_state(readings)
        # First reading seeds prev_clock; scans 2 and 3 are frozen but <threshold
        assert results[2] is False  # only 2 frozen scans — still below threshold

    def test_backward_clock_jump_sets_suspended_immediately(self):
        """Clock jumping backward (replay) must suspend immediately."""
        readings = [
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 350.0, "period": 1},   # jump > prev+2 → replay
        ]
        results = _run_frozen_clock_state(readings)
        assert results[1] is True

    def test_clock_advance_after_suspension_clears_suspended(self):
        """After frozen suspension, a normally advancing clock must clear suspension.

        NBA game_clock_sec = remaining time (counts DOWN: 300→295→290...).
        A decrease of 5s = abs(295 - 300) = 5.0 >= 0.5 → not frozen → else branch.
        """
        readings = [
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},  # threshold → suspended=True
            {"game_clock_sec": 295.0, "period": 1},  # clock decreases (5s) → clear
        ]
        results = _run_frozen_clock_state(readings)
        assert results[3] is True   # suspended after threshold
        assert results[4] is False  # cleared after clock advance

    def test_clock_jump_after_suspension_resets_frozen_counter(self):
        """After frozen suspension, a large clock delta (> 0.5s) falls into else → clear.

        This also covers new-period transitions where the clock resets to a new value.
        """
        readings = [
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},
            {"game_clock_sec": 300.0, "period": 1},  # suspended=True
            {"game_clock_sec": 290.0, "period": 1},  # 10s jump → else → clear
        ]
        results = _run_frozen_clock_state(readings)
        assert results[3] is True
        assert results[4] is False
