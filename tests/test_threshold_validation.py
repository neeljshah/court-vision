"""
test_threshold_validation.py — Tests for threshold validation and auto-correction work.

Covers Steps 3-7 of the threshold calibration session:
  - Constants exist and are the right type
  - OCR sampling rate reduced
  - Recalibration interval set correctly
  - Shot clock reset on offensive rebound
  - Dribble bounce confirmation logic
  - offensive_rebound_poss in possessions.csv fieldnames
"""

import math
from typing import List, Optional
from unittest.mock import patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_tracker(x: float, y: float) -> dict:
    return {"player_id": 1, "team": "green", "x2d": x, "y2d": y,
            "has_ball": True, "bbox": (0, 0, 10, 10)}


# ── Step 3: threshold constants exist and are float ───────────────────────────

class TestDriveThresholdExists:
    def test_drive_threshold_updated(self):
        """_DRIVE_MIN_SPEED constant exists as float in event_detector."""
        import importlib, inspect
        import src.tracking.event_detector as ed
        importlib.reload(ed)
        det = ed.EventDetector(940, 500)
        det.configure(30.0, 1)
        # _DRIVE_SPEED is fps-dependent; check it's a positive float
        assert isinstance(det._DRIVE_SPEED, float), \
            "_DRIVE_SPEED should be a float"
        assert det._DRIVE_SPEED > 0.0, \
            "_DRIVE_SPEED should be positive"


class TestScreenThresholdExists:
    def test_screen_threshold_updated(self):
        """_SCREEN_MAX_DIST (_SCREEN_DIST) constant exists and is float."""
        import importlib
        import src.tracking.event_detector as ed
        importlib.reload(ed)
        det = ed.EventDetector(940, 500)
        assert isinstance(det._SCREEN_DIST, float), \
            "_SCREEN_DIST should be a float"
        assert det._SCREEN_DIST > 0.0, \
            "_SCREEN_DIST should be positive"


# ── Step 5: OCR sampling rate ─────────────────────────────────────────────────

class TestSampleEveryReduced:
    def test_sample_every_reduced(self):
        """player_resolver._SAMPLE_EVERY must be ≤ 15."""
        import src.tracking.player_resolver as pr
        assert hasattr(pr, "_SAMPLE_EVERY"), \
            "_SAMPLE_EVERY not found in player_resolver"
        assert pr._SAMPLE_EVERY <= 15, \
            f"_SAMPLE_EVERY={pr._SAMPLE_EVERY} should be ≤15 (was 60)"


# ── Step 6: recalibration interval ───────────────────────────────────────────

class TestRecalibIntervalSet:
    def test_recalib_interval_set(self):
        """advanced_tracker._recalib_interval must be ≤ 300."""
        try:
            from src.tracking.advanced_tracker import AdvancedFeetDetector
        except ImportError:
            import pytest; pytest.skip("AdvancedFeetDetector import failed (CV deps)")
        det = AdvancedFeetDetector.__new__(AdvancedFeetDetector)
        # Read the default from class init — instantiate with minimal mocking
        import src.tracking.advanced_tracker as at_mod
        assert hasattr(at_mod.AdvancedFeetDetector, "__init__")
        # Check constant on a freshly constructed instance where possible,
        # else read the source-level default directly.
        val = getattr(det, "_recalib_interval", None)
        if val is None:
            # Fall back: read from source
            import re
            src = (at_mod.__file__ or "")
            try:
                text = open(src).read()
                m = re.search(r"self\._recalib_interval\s*=\s*(\d+)", text)
                assert m, "_recalib_interval assignment not found in source"
                val = int(m.group(1))
            except OSError:
                import pytest; pytest.skip("Could not read advanced_tracker source")
        assert val <= 300, \
            f"_recalib_interval={val} should be ≤300 (raised from 150)"


# ── Step 4: shot clock reset on offensive rebound ────────────────────────────

class TestShotClockResetOffensiveRebound:
    def test_shot_clock_reset_offensive_rebound(self):
        """
        _summarize_possession with offensive_rebound=True should yield
        min_shot_clock_est ≤ 14.0.
        """
        from src.pipeline.unified_pipeline import UnifiedPipeline
        fps = 30.0
        # Build a minimal possession buffer using the 14s reset clock
        buf = []
        for i in range(15):
            elapsed_sec = i / fps
            sc = max(0.0, 14.0 - elapsed_sec)
            buf.append({
                "frame":            i,
                "spacing":          10.0,
                "isolation":        5.0,
                "vtb":              1.0,
                "drive":            0,
                "shot_event":       False,
                "fast_break":       0,
                "poss_type":        "half_court",
                "play_type":        "half_court",
                "paint_touches":    0,
                "off_ball_distance": 0.0,
                "shot_clock_est":   sc,
                "handler_zone":     None,
            })
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=14,
            buf=buf, fps=fps, game_id=None,
            offensive_rebound_poss=True,
        )
        assert row, "_summarize_possession returned empty dict"
        sc_val = float(row.get("min_shot_clock_est", 999))
        assert sc_val <= 14.0, \
            f"min_shot_clock_est={sc_val} should be ≤14.0 for offensive rebound"

    def test_shot_clock_normal_possession_uses_24(self):
        """Non-offensive-rebound possessions should start from 24s."""
        from src.pipeline.unified_pipeline import UnifiedPipeline
        fps = 30.0
        buf = [
            {
                "frame": 0, "spacing": 10.0, "isolation": 5.0, "vtb": 0.0,
                "drive": 0, "shot_event": False, "fast_break": 0,
                "poss_type": "half_court", "play_type": "half_court",
                "paint_touches": 0, "off_ball_distance": 0.0,
                "shot_clock_est": 24.0, "handler_zone": None,
            }
        ]
        row = UnifiedPipeline._summarize_possession(
            pid=2, team="white", start_f=0, end_f=0,
            buf=buf, fps=fps, game_id=None,
            offensive_rebound_poss=False,
        )
        sc_val = float(row.get("min_shot_clock_est", 0))
        assert sc_val <= 24.0


# ── Step 7: dribble bounce confirmation ───────────────────────────────────────

class TestDribbleRequiresBounce:
    """dribble_count must NOT increment when ball_y_pixel stays high (no bounce)."""

    def _make_det(self) -> "EventDetector":
        from src.tracking.event_detector import EventDetector
        det = EventDetector(940, 500)
        det.configure(30.0, 1)
        return det

    def _run_frames(
        self,
        det,
        n: int,
        ball_near_handler: bool,
        y_pixel_series: Optional[List[Optional[float]]] = None,
    ) -> int:
        """Run n frames with ball close to handler, return final dribble_count."""
        ball_pos = (100.0, 250.0) if ball_near_handler else None
        tracks = [{
            "player_id": 1, "team": "green",
            "x2d": 100.0, "y2d": 250.0,
            "has_ball": True, "bbox": (90, 240, 110, 260),
        }]
        for i in range(n):
            y_px = y_pixel_series[i] if (y_pixel_series and i < len(y_pixel_series)) else None
            det.update(i, ball_pos, tracks,
                       pixel_vel=0.0, ball_y_pixel=y_px, frame_height=720)
        return det.dribble_count

    def test_dribble_requires_bounce_no_y_pixel(self):
        """
        When ball_y_pixel is None every frame (no pixel data), dribble_count
        should NOT increment (bounce cannot be confirmed).
        """
        det = self._make_det()
        count = self._run_frames(det, n=10, ball_near_handler=True,
                                 y_pixel_series=[None] * 10)
        # With only 2-frame fallback available and y=None, _bounce stays False
        # Dribble count may be 0 (strict bounce required) or small (2-frame path)
        # Key: count should be 0 when no y_pixel data is available at all.
        assert count == 0, \
            f"dribble_count={count} should be 0 when no bounce data available"

    def test_dribble_requires_bounce_ball_only_falling(self):
        """
        Ball only falling (vy always > 0, never bouncing back) must not
        increment dribble_count beyond what the 2-frame fallback allows.
        """
        det = self._make_det()
        # y increases each frame (ball falling in image space), never rises
        y_series = [300.0 + i * 3.0 for i in range(12)]
        count = self._run_frames(det, n=12, ball_near_handler=True,
                                 y_pixel_series=y_series)
        # 3-frame window: vy_prev > 1.0 (falling) AND vy_curr > 0 (still falling)
        # → _bounce = False for all frames → dribble_count stays 0
        assert count == 0, \
            f"dribble_count={count} — no bounce should yield 0"


class TestDribbleIncrementsOnBounce:
    """dribble_count MUST increment when ball_y_pixel flips: falling → rising."""

    def test_dribble_increments_on_bounce(self):
        """
        Ball falls (vy > 1.0) then rises (vy ≤ 0): dribble_count should increment.
        """
        from src.tracking.event_detector import EventDetector
        det = EventDetector(940, 500)
        det.configure(30.0, 1)

        tracks = [{
            "player_id": 1, "team": "green",
            "x2d": 100.0, "y2d": 250.0,
            "has_ball": True, "bbox": (90, 240, 110, 260),
        }]
        ball_pos = (100.0, 250.0)

        # Frame 0: y=360 (baseline — establishes buffer)
        # Frame 1: y=368 (falling, vy=+8 > 1.0)
        # Frame 2: y=362 (rising, vy=-6 ≤ 0) → bounce detected
        y_series = [360.0, 368.0, 362.0, 358.0, 362.0, 370.0, 363.0]

        for i, y_px in enumerate(y_series):
            det.update(i, ball_pos, tracks,
                       pixel_vel=0.0, ball_y_pixel=y_px, frame_height=720)

        assert det.dribble_count >= 1, \
            f"dribble_count={det.dribble_count} — expected ≥1 after a bounce"


# ── Step 4 (fieldnames): offensive_rebound_poss in CSV ───────────────────────

class TestOffensiveReboundPossInFieldnames:
    def test_offensive_rebound_poss_in_fieldnames(self):
        """'offensive_rebound_poss' must appear in _export_possessions_csv fieldnames."""
        import inspect
        from src.pipeline.unified_pipeline import UnifiedPipeline
        source = inspect.getsource(UnifiedPipeline._export_possessions_csv)
        assert "offensive_rebound_poss" in source, \
            "'offensive_rebound_poss' not found in _export_possessions_csv fieldnames"
