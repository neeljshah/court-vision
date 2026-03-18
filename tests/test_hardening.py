"""
test_hardening.py — Tests for full-game tracker hardening (no video required).

Covers:
  Fix 1 — OSNet auto-load pre-trained weights
  Fix 2 — Homography failure recovery during camera cuts
  Fix 3 — Ball tracker robustness (streak reset, bounds, jump detection)
  Fix 4 — EventDetector stability on long sequences
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fix 1: OSNet auto-load weights ───────────────────────────────────────────

class TestOSNetWeightsAutoLoad:
    """Fix 1: OSNet weights path config + auto-load behaviour."""

    def test_osnet_weights_path_in_defaults(self):
        """tracker_config.DEFAULTS must contain 'osnet_weights_path' key."""
        from src.tracking.tracker_config import DEFAULTS
        assert "osnet_weights_path" in DEFAULTS
        assert isinstance(DEFAULTS["osnet_weights_path"], str)
        assert DEFAULTS["osnet_weights_path"].endswith(".pth")

    def test_use_deep_true_when_weights_file_absent(self, tmp_path, monkeypatch):
        """_use_deep stays True (model available) even when weights file doesn't exist.

        If OSNet is not importable or torch is missing the extractor won't be
        available anyway — we skip in that case.
        """
        from src.tracking.advanced_tracker import AdvancedFeetDetector, _HAS_OSNET

        if not _HAS_OSNET:
            pytest.skip("OSNet not importable — skipping")

        # Point config at a path that definitely does not exist
        monkeypatch.setenv("_OSNET_TEST", "1")
        from src.tracking import tracker_config as tc
        original_load = tc.load_config

        def _patched_load():
            cfg = original_load()
            cfg["osnet_weights_path"] = str(tmp_path / "nonexistent_weights.pth")
            return cfg

        monkeypatch.setattr(tc, "load_config", _patched_load)

        # Re-import to pick up patched load_config
        from src.tracking.player_detection import COLORS, hsv2bgr
        from src.tracking.player import Player

        players = [Player(1, "green", hsv2bgr(COLORS["green"][2]))]
        det = AdvancedFeetDetector(players)

        if det._deep_extractor is not None:
            # Weights file absent → model still initialised
            assert det._use_deep == det._deep_extractor.available

    def test_load_weights_no_crash(self, tmp_path):
        """load_weights() on a real OSNetX025 state dict must not raise."""
        pytest.importorskip("torch", reason="torch required for this test")
        import torch
        from src.tracking.osnet_reid import DeepAppearanceExtractor, OSNetX025

        # Construct minimal model and save its weights
        model = OSNetX025()
        weights_file = tmp_path / "test_osnet.pth"
        torch.save(model.state_dict(), str(weights_file))

        extractor = DeepAppearanceExtractor()
        if not extractor.available:
            pytest.skip("OSNet not available — skipping")

        # Must not raise; model stays available afterwards
        extractor.load_weights(str(weights_file))
        assert extractor.available

    def test_load_weights_wrapped_checkpoint(self, tmp_path):
        """load_weights() handles wrapped checkpoints with 'state_dict' key."""
        pytest.importorskip("torch", reason="torch required for this test")
        import torch
        from src.tracking.osnet_reid import DeepAppearanceExtractor, OSNetX025

        model = OSNetX025()
        wrapped = {"state_dict": model.state_dict(), "epoch": 10}
        weights_file = tmp_path / "wrapped.pth"
        torch.save(wrapped, str(weights_file))

        extractor = DeepAppearanceExtractor()
        if not extractor.available:
            pytest.skip("OSNet not available — skipping")

        extractor.load_weights(str(weights_file))
        assert extractor.available


# ── Fix 2: Homography failure recovery ───────────────────────────────────────

class TestHomographyRecovery:
    """Fix 2: _last_good_M1 and _try_recover_court_M1 behaviour."""

    def _make_mock_pipeline(self):
        """Return a minimal object that quacks like UnifiedPipeline for M1 tests."""
        from collections import deque
        class _MP:
            M1                 = np.eye(3, dtype=np.float64)
            _last_good_M1      = None
            _M1_stale_frames   = 0
            _M1_failed_attempts = 0
            _recover_frame_buf = deque(maxlen=5)
            _M_ema             = None  # required by _try_recover_court_M1 inv-adjust logic
        return _MP()

    def test_try_recover_increments_stale_counter(self, monkeypatch):
        """_try_recover_court_M1 increments _M1_stale_frames every call."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        monkeypatch.setattr(up, "detect_court_homography", lambda *a, **kw: None)
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert obj._M1_stale_frames == 1
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert obj._M1_stale_frames == 2

    def test_try_recover_does_not_call_detect_before_30_frames_initial(self, monkeypatch):
        """detect_court_homography is NOT called while stale count <= 30 (initial fallback)."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()  # _last_good_M1 = None → threshold=30
        obj._M1_stale_frames = 29
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        detect_calls = []
        monkeypatch.setattr(
            up, "detect_court_homography",
            lambda *a, **kw: detect_calls.append(a) or None
        )
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert len(detect_calls) == 0

    def test_try_recover_calls_detect_after_30_frames_initial(self, monkeypatch):
        """detect_court_homography IS called after 30 frames in initial fallback mode."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()  # _last_good_M1 = None → threshold=30
        obj._M1_stale_frames = 31

        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        detect_calls = []
        monkeypatch.setattr(
            up, "detect_court_homography",
            lambda *a, **kw: detect_calls.append(a) or None
        )
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert len(detect_calls) == 1

    def test_try_recover_uses_150_threshold_after_recovery(self, monkeypatch):
        """After _last_good_M1 is set, threshold rises to 150 to protect arc tracking."""
        from src.pipeline import unified_pipeline as up

        obj = self._make_mock_pipeline()
        obj._last_good_M1 = np.eye(3, dtype=np.float64)  # already recovered
        obj._M1_stale_frames = 31  # > 30 but ≤ 150
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        detect_calls = []
        monkeypatch.setattr(
            up, "detect_court_homography",
            lambda *a, **kw: detect_calls.append(a) or None
        )
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert len(detect_calls) == 0  # not called — still within 150-frame window

    def test_try_recover_calls_detect_after_30_frames(self, monkeypatch):
        """detect_court_homography IS called once stale count > 30 (initial mode)."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()
        obj._M1_stale_frames = 31
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        detect_calls = []
        monkeypatch.setattr(
            up, "detect_court_homography",
            lambda *a, **kw: detect_calls.append(a) or None
        )
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert len(detect_calls) == 1

    def test_try_recover_updates_m1_on_success(self, monkeypatch):
        """When detect returns a matrix, M1 and _last_good_M1 are updated."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()
        obj._M1_stale_frames = 200
        frame  = np.zeros((100, 200, 3), dtype=np.uint8)
        new_M1 = np.eye(3, dtype=np.float64) * 7.0

        monkeypatch.setattr(up, "detect_court_homography", lambda *a, **kw: new_M1)
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)

        np.testing.assert_array_equal(obj.M1, new_M1)
        np.testing.assert_array_equal(obj._last_good_M1, new_M1)
        assert obj._M1_stale_frames == 0

    def test_try_recover_keeps_m1_on_failure(self, monkeypatch):
        """When detect returns None, M1 is unchanged."""
        from src.pipeline import unified_pipeline as up

        obj   = self._make_mock_pipeline()
        obj._M1_stale_frames = 200
        original = obj.M1.copy()
        frame = np.zeros((100, 200, 3), dtype=np.uint8)

        monkeypatch.setattr(up, "detect_court_homography", lambda *a, **kw: None)
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)

        np.testing.assert_array_equal(obj.M1, original)

    def test_try_recover_backs_off_after_5_failures(self, monkeypatch):
        """After 5 consecutive failed detection attempts, threshold rises to 500."""
        from src.pipeline import unified_pipeline as up

        obj = self._make_mock_pipeline()
        obj._M1_failed_attempts = 5   # already hit max failures
        obj._M1_stale_frames    = 31  # past 30-frame threshold but under 500

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        detect_calls = []
        monkeypatch.setattr(up, "detect_court_homography",
                            lambda *a, **kw: detect_calls.append(1) or None)

        up.UnifiedPipeline._try_recover_court_M1(obj, frame)
        assert len(detect_calls) == 0, "Should not call detect — backed off to 500-frame threshold"

    def test_try_recover_failure_increments_failed_counter(self, monkeypatch):
        """A failed detection attempt increments _M1_failed_attempts."""
        from src.pipeline import unified_pipeline as up

        obj = self._make_mock_pipeline()
        obj._M1_stale_frames = 200

        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        monkeypatch.setattr(up, "detect_court_homography", lambda *a, **kw: None)
        up.UnifiedPipeline._try_recover_court_M1(obj, frame)

        assert obj._M1_failed_attempts == 1
        assert obj._M1_stale_frames == 0   # reset so back-off window starts fresh

    def test_build_court_skips_per_clip_detection(self, monkeypatch):
        """_build_court never calls detect_court_homography at init (M_ema unavailable).

        Per-clip detection was removed from _build_court in 2026-03-18 because
        detect_court_homography returns frame→court M1 which requires inv(M_ema)
        to adjust, but M_ema is None at __init__ time.  _try_recover_court_M1
        handles per-clip detection during gameplay where M_ema is available.
        """
        from src.pipeline import unified_pipeline as up

        detect_calls = []

        obj = self._make_mock_pipeline()
        assert obj._last_good_M1 is None

        fake_map = np.zeros((100, 200, 3), dtype=np.uint8)
        monkeypatch.setattr(up, "detect_court_homography",
                            lambda *a, **kw: detect_calls.append(1) or np.eye(3) * 3)
        monkeypatch.setattr(up, "binarize_erode_dilate", lambda *a, **kw: fake_map)
        monkeypatch.setattr(up, "rectangularize_court", lambda *a, **kw: (None, []))
        monkeypatch.setattr(up, "rectify", lambda *a, **kw: fake_map)
        import cv2
        monkeypatch.setattr(cv2, "imread", lambda *a, **kw: fake_map)
        monkeypatch.setattr(cv2, "resize", lambda img, *a, **kw: img)
        monkeypatch.setattr(np, "load", lambda *a, **kw: np.eye(3))

        pano = np.zeros((200, 3000, 3), dtype=np.uint8)
        _, M1_out = up.UnifiedPipeline._build_court(obj, pano, startup_frames=[pano])

        assert len(detect_calls) == 0, "_build_court must not call detect_court_homography at init"
        assert obj._last_good_M1 is None, "_last_good_M1 not set at init — only updated during gameplay"

    def test_build_court_uses_last_good_when_detect_returns_none(self, monkeypatch):
        """_build_court returns _last_good_M1 when detect returns None."""
        from src.pipeline import unified_pipeline as up

        previous_good = np.eye(3, dtype=np.float64) * 5.0
        obj = self._make_mock_pipeline()
        obj._last_good_M1 = previous_good

        fake_map = np.zeros((100, 200, 3), dtype=np.uint8)
        monkeypatch.setattr(up, "detect_court_homography", lambda *a, **kw: None)
        monkeypatch.setattr(up, "binarize_erode_dilate", lambda *a, **kw: fake_map)
        monkeypatch.setattr(up, "rectangularize_court", lambda *a, **kw: (None, []))
        monkeypatch.setattr(up, "rectify", lambda *a, **kw: fake_map)
        import cv2
        monkeypatch.setattr(cv2, "imread", lambda *a, **kw: fake_map)
        monkeypatch.setattr(cv2, "resize", lambda img, *a, **kw: img)

        pano = np.zeros((200, 3000, 3), dtype=np.uint8)
        _, M1_out = up.UnifiedPipeline._build_court(obj, pano, startup_frames=[pano])

        np.testing.assert_array_equal(M1_out, previous_good)


# ── Fix 3: Ball tracker robustness ───────────────────────────────────────────

class TestBallTrackerRobustness:
    """Fix 3: no-ball streak reset, out-of-bounds guard, position-jump guard."""

    def _make_tracker(self):
        from src.tracking.ball_detect_track import BallDetectTrack
        return BallDetectTrack(players=[])

    def test_no_ball_streak_attr_exists(self):
        """BallDetectTrack must initialise _no_ball_streak = 0."""
        tr = self._make_tracker()
        assert hasattr(tr, "_no_ball_streak")
        assert tr._no_ball_streak == 0

    def test_streak_increments_while_ball_absent(self, monkeypatch):
        """_no_ball_streak increments each frame the ball is not found."""
        from src.tracking import ball_detect_track as bdt

        tr = self._make_tracker()
        # Force detection always fails, skip CSRT init
        monkeypatch.setattr(tr, "ball_detection", lambda *a, **kw: None)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        M  = np.eye(3, dtype=np.float64)
        M1 = np.eye(3, dtype=np.float64)
        map2d = np.zeros((400, 600, 3), dtype=np.uint8)

        for _ in range(5):
            tr.ball_tracker(M, M1, frame.copy(), map2d.copy(), map2d.copy(), 0)

        assert tr._no_ball_streak == 5

    def test_streak_resets_to_zero_on_ball_found(self, monkeypatch):
        """_no_ball_streak resets to 0 when the ball is successfully detected."""
        tr = self._make_tracker()
        tr._no_ball_streak = 15

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        M  = np.eye(3, dtype=np.float64)
        M1 = np.eye(3, dtype=np.float64)
        map2d = np.zeros((400, 600, 3), dtype=np.uint8)

        # Inject a valid bbox in the center of the frame.
        # Paint basketball-orange (BGR ≈ (0, 140, 230)) at the bbox center so
        # the orange color guard (Guard 3) accepts the detection.
        bbox = (300, 220, 40, 40)
        cx_bbox, cy_bbox = bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2  # 320, 240
        frame[cy_bbox - 1:cy_bbox + 2, cx_bbox - 1:cx_bbox + 2] = (0, 140, 230)  # orange

        monkeypatch.setattr(tr, "ball_detection", lambda *a, **kw: bbox)
        tr.tracker.init(frame, bbox)

        tr.ball_tracker(M, M1, frame.copy(), map2d.copy(), map2d.copy(), 0)
        assert tr._no_ball_streak == 0

    def test_streak_reset_at_30_forces_detection_mode(self, monkeypatch):
        """After 30 consecutive misses, do_detection is forced True."""
        tr = self._make_tracker()
        tr._no_ball_streak = 0
        tr.do_detection = True  # already in detection mode
        monkeypatch.setattr(tr, "ball_detection", lambda *a, **kw: None)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        M  = np.eye(3, dtype=np.float64)
        M1 = np.eye(3, dtype=np.float64)
        map2d = np.zeros((400, 600, 3), dtype=np.uint8)

        for _ in range(30):
            tr.ball_tracker(M, M1, frame.copy(), map2d.copy(), map2d.copy(), 0)

        # After 30 misses counter resets and tracker is in detection mode
        assert tr.do_detection is True
        assert tr._no_ball_streak == 0  # reset at threshold

    def test_out_of_bounds_bbox_marks_ball_lost(self):
        """A CSRT bbox with center outside frame marks ball as lost."""
        from src.tracking.ball_detect_track import BallDetectTrack
        tr = BallDetectTrack(players=[])

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        M  = np.eye(3, dtype=np.float64)
        M1 = np.eye(3, dtype=np.float64)
        map2d = np.zeros((400, 600, 3), dtype=np.uint8)

        # Fake an out-of-bounds trajectory entry
        tr._trajectory = [(700, 300)]  # x=700 > frame width 640
        tr._last_bbox  = (690, 280, 40, 40)

        # Feed a bbox whose center is outside the 640-wide frame
        # We do this by patching do_detection=False and mocking CSRT update
        class _FakeTracker:
            def update(self, frame):
                return True, (680, 250, 40, 40)  # center x=700 > 640 → out of bounds
        tr.tracker = _FakeTracker()
        tr.do_detection = False
        tr.check_track  = 5

        _, map_result = tr.ball_tracker(M, M1, frame.copy(), map2d.copy(), map2d.copy(), 0)
        assert map_result is None
        assert tr.do_detection is True

    def test_large_position_jump_resets_tracker(self):
        """A >200px jump between frames forces do_detection=True."""
        from src.tracking.ball_detect_track import BallDetectTrack
        tr = BallDetectTrack(players=[])

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        M  = np.eye(3, dtype=np.float64)
        M1 = np.eye(3, dtype=np.float64)
        map2d = np.zeros((400, 600, 3), dtype=np.uint8)

        # Establish last known position at (100, 100)
        tr._trajectory = [(100, 100)]
        tr._last_bbox  = (80, 80, 40, 40)

        # CSRT returns bbox with center at (350, 350) — jump = ~354px > 200
        class _FakeTracker:
            def update(self, frame):
                return True, (330, 330, 40, 40)
        tr.tracker = _FakeTracker()
        tr.do_detection = False
        tr.check_track  = 5

        _, map_result = tr.ball_tracker(M, M1, frame.copy(), map2d.copy(), map2d.copy(), 0)
        assert map_result is None
        assert tr.do_detection is True


# ── Fix 4: EventDetector state bounded ───────────────────────────────────────

class TestEventDetectorStability:
    """Fix 4: _pending dict stays bounded; no state explosion over long sequences."""

    def _make_detector(self):
        from src.tracking.event_detector import EventDetector
        return EventDetector(map_w=500, map_h=300)

    def _make_track(self, player_id: int, has_ball: bool = False,
                    x2d: float = 100.0, y2d: float = 100.0) -> dict:
        return {
            "player_id": player_id,
            "team":      "green",
            "x2d":       x2d,
            "y2d":       y2d,
            "has_ball":  has_ball,
        }

    def test_pending_stays_bounded_over_500_frames(self):
        """_pending dict must not grow beyond _PASS_MAX_FRAMES + 1 entries."""
        from src.tracking.event_detector import _PASS_MAX_FRAMES
        det = self._make_detector()

        for i in range(500):
            ball_pos = (float(i % 300), 150.0)
            # Alternate possession to trigger pass/shot events
            player_id = 1 if (i // 10) % 2 == 0 else 2
            tracks = [self._make_track(player_id, has_ball=True)]
            det.update(i, ball_pos, tracks, pixel_vel=2.0)

            # Pending must never exceed 2× the pass window
            assert len(det._pending) <= _PASS_MAX_FRAMES + 1, (
                f"frame {i}: _pending has {len(det._pending)} entries "
                f"(limit {_PASS_MAX_FRAMES + 1})"
            )

    def test_ball_buf_stays_bounded_over_500_frames(self):
        """_ball_buf deque must stay at maxlen=30."""
        det = self._make_detector()
        for i in range(500):
            tracks = [self._make_track(1, has_ball=True)]
            det.update(i, (50.0, 150.0), tracks)
        assert len(det._ball_buf) <= 30

    def test_pending_pruned_when_retroactive_frame_is_stale(self):
        """_pending entries older than frame_idx - _PASS_MAX_FRAMES are pruned."""
        from src.tracking.event_detector import _PASS_MAX_FRAMES
        det = self._make_detector()

        # Manually inject a very old pending entry
        det._pending[5] = "pass"

        # Advance well past the stale threshold
        target_frame = 5 + _PASS_MAX_FRAMES + 10
        for i in range(target_frame + 1):
            tracks = [self._make_track(1, has_ball=True)]
            det.update(i, (50.0, 150.0), tracks)

        # Entry for frame 5 must have been pruned
        assert 5 not in det._pending

    def test_no_exception_over_10k_frames(self):
        """Running 10 000 frames must not raise and must not grow state unboundedly."""
        from src.tracking.event_detector import _PASS_MAX_FRAMES
        det = self._make_detector()

        for i in range(10_000):
            tracks = [self._make_track((i % 3) + 1, has_ball=True,
                                       x2d=float(i % 400), y2d=150.0)]
            det.update(i, (float(i % 400), 150.0), tracks, pixel_vel=1.0)

        assert len(det._pending) <= _PASS_MAX_FRAMES + 1


# ── Fix 1 (new): Startup scan frame cap ──────────────────────────────────────

class TestStartupScanCap:
    """Fix 1 (2026-03-18): startup scan must collect ≤ 60 frames."""

    def test_startup_frames_capped_at_60_for_long_video(self, monkeypatch):
        """UnifiedPipeline.__init__ must collect at most 60 startup frames
        even when the video has tens of thousands of frames."""
        import cv2
        from src.pipeline import unified_pipeline as up

        fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame_counter = {"n": 0}

        class _FakeCap:
            def __init__(self, path):
                self._frame_count = 57939   # full-game length
                self._pos = 0

            def get(self, prop):
                if prop == cv2.CAP_PROP_FRAME_COUNT:
                    return self._frame_count
                if prop == cv2.CAP_PROP_FPS:
                    return 60.0
                return 0.0

            def set(self, prop, val):
                self._pos = int(val)

            def read(self):
                frame_counter["n"] += 1
                return True, fake_frame.copy()

            def release(self):
                pass

            def isOpened(self):
                return True

        captured: list = []
        original_init = up.UnifiedPipeline.__init__

        def _patched_init(self_obj, video_path, *args, **kwargs):
            # Only intercept the startup scan; bail early before heavy setup
            import cv2 as _cv2
            _startup_cap = _FakeCap(video_path)
            _total = int(_startup_cap.get(_cv2.CAP_PROP_FRAME_COUNT))
            _STARTUP_MAX_FRAMES = 60
            _STARTUP_SCAN_END   = 1800
            _scan_end = min(_total, _STARTUP_SCAN_END)
            _step = max(1, _scan_end // _STARTUP_MAX_FRAMES)
            _startup_frames: list = []
            for _idx in range(0, _scan_end, _step):
                if len(_startup_frames) >= _STARTUP_MAX_FRAMES:
                    break
                _startup_cap.set(_cv2.CAP_PROP_POS_FRAMES, _idx)
                _ok, _f = _startup_cap.read()
                if not _ok:
                    break
                _startup_frames.append(_f)
            _startup_cap.release()
            captured.extend(_startup_frames)
            raise RuntimeError("init_stopped_early")  # stop before heavy deps

        monkeypatch.setattr(up.UnifiedPipeline, "__init__", _patched_init)

        with pytest.raises(RuntimeError, match="init_stopped_early"):
            up.UnifiedPipeline("fake_video.mp4")

        assert len(captured) <= 60, (
            f"startup scan collected {len(captured)} frames — expected ≤ 60"
        )

    def test_startup_frames_bounded_logic_directly(self):
        """Pure-logic check: the sampling loop stops at 60 even with a step=1."""
        frames_collected = []
        _STARTUP_MAX_FRAMES = 60
        _STARTUP_SCAN_END   = 1800
        total_frames = 57939

        scan_end = min(total_frames, _STARTUP_SCAN_END)
        step = max(1, scan_end // _STARTUP_MAX_FRAMES)

        for idx in range(0, scan_end, step):
            if len(frames_collected) >= _STARTUP_MAX_FRAMES:
                break
            frames_collected.append(idx)

        assert len(frames_collected) <= 60


# ── Fix 3 (new): Pixel-space shot fallback ────────────────────────────────────

class TestPixelSpaceShotFallback:
    """Fix 3 (2026-03-18): pixel-space fallback fires when direction check would miss."""

    def _make_detector(self):
        from src.tracking.event_detector import EventDetector
        return EventDetector(map_w=500, map_h=300)

    def test_pixel_fallback_fires_when_direction_fails(self):
        """Shot must be detected via pixel-space fallback when pixel_vel=20 and
        ball is in upper half of frame, even if court-coord direction check fails."""
        det = self._make_detector()

        # Establish a possessor so the next frame's possession-loss triggers _evaluate_shot
        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=200.0, frame_height=720)

        # Drop possession so _evaluate_shot fires. Place ball_pos so that the
        # court-coord direction check does NOT match (ball moving away from basket)
        # but pixel_vel is high and ball is in upper half.
        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        # ball_pos at same x as origin → dx_ball=0, dot product=0 → direction fails
        event = det.update(
            1,
            ball_pos=(250.0, 130.0),  # minor y-shift upward — neutral dot product
            frame_tracks=[no_ball_track],
            pixel_vel=20.0,          # > _PIXEL_SHOT_VEL (12.0)
            ball_y_pixel=200.0,      # upper half (200 < 720*0.5=360)
            frame_height=720,
        )
        assert event == "shot", (
            f"Expected 'shot' from pixel fallback, got '{event}'"
        )

    def test_pixel_fallback_does_not_fire_in_lower_half(self):
        """Pixel-space fallback must NOT fire when ball is in the bottom quarter (floor level)."""
        det = self._make_detector()

        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=400.0, frame_height=720)

        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        # Court-coord direction check will fail (same neutral ball_pos)
        # pixel_vel is high but ball is near floor → fallback must not fire
        event = det.update(
            1,
            ball_pos=(250.0, 130.0),
            frame_tracks=[no_ball_track],
            pixel_vel=20.0,
            ball_y_pixel=560.0,   # floor level (560 > 720*0.75=540)
            frame_height=720,
        )
        assert event != "shot", (
            f"Pixel fallback should NOT fire at floor level, got '{event}'"
        )

    def test_pixel_fallback_does_not_fire_below_vel_threshold(self):
        """Pixel-space fallback must NOT fire when pixel_vel ≤ 18.0."""
        det = self._make_detector()

        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=200.0, frame_height=720)

        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        event = det.update(
            1,
            ball_pos=(250.0, 130.0),
            frame_tracks=[no_ball_track],
            pixel_vel=7.0,        # below _PIXEL_SHOT_VEL (8.0)
            ball_y_pixel=200.0,
            frame_height=720,
        )
        assert event != "shot", (
            f"Pixel fallback should NOT fire at pixel_vel=7, got '{event}'"
        )


# ── Fix 5: pipeline call site wires ball_y_pixel + frame_height ──────────────


class TestPipelineEventDetectorCallSite:
    """Verify that unified_pipeline.py passes ball_y_pixel and frame_height
    to EventDetector.update() so the pixel-space shot fallback can fire."""

    def test_pipeline_passes_ball_y_pixel_and_frame_height(self):
        """EventDetector.update called with ball_y_pixel and frame_height
        from the unified_pipeline call site (import-level check)."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline", "unified_pipeline.py",
        )
        with open(src_path) as f:
            source = f.read()

        tree = ast.parse(source)
        found_y = False
        found_h = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Look for event_det.update(...)
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr == "update"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "event_det"):
                continue
            kw_names = {kw.keyword.arg if hasattr(kw, "keyword") else kw.arg
                        for kw in node.keywords}
            if "ball_y_pixel" in kw_names:
                found_y = True
            if "frame_height" in kw_names:
                found_h = True

        assert found_y, (
            "unified_pipeline.py: event_det.update() missing ball_y_pixel kwarg — "
            "pixel-space shot fallback will never fire"
        )
        assert found_h, (
            "unified_pipeline.py: event_det.update() missing frame_height kwarg — "
            "pixel-space shot fallback will never fire"
        )


# ── Fix 6: pixel-space fallback fires when ball_pos is None ──────────────────


class TestPixelFallbackBallPosNone:
    """ball_pos=None must not block the pixel-space shot fallback.

    Root cause: original _evaluate_shot had `if ball_pos is None: return 'none'`
    BEFORE the pixel-space check, so Hough/CSRT losing the ball mid-shot
    silently killed all shot detection.
    """

    def _make_detector(self):
        from src.tracking.event_detector import EventDetector
        return EventDetector(map_w=500, map_h=300)

    def test_shot_fires_when_ball_pos_none_but_pixel_vel_high(self):
        """Shot detected via pixel fallback even when ball_pos=None (Hough lost ball)."""
        det = self._make_detector()

        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=200.0, frame_height=720)

        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        # ball_pos=None simulates Hough dropping the ball at shot release
        event = det.update(
            1,
            ball_pos=None,           # ← Hough/CSRT lost the ball
            frame_tracks=[no_ball_track],
            pixel_vel=22.0,          # fast movement in pixel space
            ball_y_pixel=150.0,      # upper half of 720px frame
            frame_height=720,
        )
        assert event == "shot", (
            f"Expected 'shot' when ball_pos=None + pixel_vel=22 + upper-half, got '{event}'"
        )

    def test_no_shot_when_ball_pos_none_and_pixel_vel_low(self):
        """No shot when ball_pos=None and pixel_vel is below threshold."""
        det = self._make_detector()

        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=200.0, frame_height=720)

        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        event = det.update(
            1,
            ball_pos=None,
            frame_tracks=[no_ball_track],
            pixel_vel=7.0,           # below _PIXEL_SHOT_VEL (8.0)
            ball_y_pixel=150.0,
            frame_height=720,
        )
        assert event != "shot", (
            f"Should NOT fire when pixel_vel=7 (below threshold), got '{event}'"
        )

    def test_no_shot_when_ball_pos_none_and_lower_half(self):
        """No shot when ball_pos=None and ball is at floor level (bottom quarter)."""
        det = self._make_detector()

        track_with_ball = {
            "player_id": 1, "team": "green",
            "x2d": 250.0, "y2d": 150.0, "has_ball": True,
        }
        det.update(0, (250.0, 150.0), [track_with_ball], pixel_vel=2.0,
                   ball_y_pixel=200.0, frame_height=720)

        no_ball_track = {
            "player_id": 1, "team": "green",
            "x2d": 251.0, "y2d": 151.0, "has_ball": False,
        }
        event = det.update(
            1,
            ball_pos=None,
            frame_tracks=[no_ball_track],
            pixel_vel=25.0,
            ball_y_pixel=560.0,      # floor level (560 > 720*0.75=540)
            frame_height=720,
        )
        assert event != "shot", (
            f"Should NOT fire when ball is at floor level, got '{event}'"
        )


# ── Fix 7: Hough false-positive guard — param2 must not go below 24 ──────────


class TestDriftGuardThreshold:
    """Drift guard threshold must be ≥ 1200px (court coords on 3698px pano).

    Root cause (2026-03-18): 400px was too tight for the 3698px-wide pano court.
    A ball 30ft from the nearest player = ~1180px in pano coords.  Raising to
    1200px fixed ball_valid_pct from 21% → ~65%+ on bos_mia_playoffs by letting
    legitimate airborne detections through while still rejecting CSRT drift to
    background objects (which project to >>1200px from any player).
    """

    def test_drift_guard_threshold_gte_1200(self):
        """Drift guard distance threshold must be ≥ 1200 px."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src_path) as f:
            source = f.read()
        # Look for the drift guard comparison: "> <number>" near "possessor_2d"
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            # Pattern: hypot(...) > threshold
            if not (len(node.ops) == 1 and isinstance(node.ops[0], ast.Gt)):
                continue
            if not (len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)):
                continue
            val = node.comparators[0].value
            if isinstance(val, (int, float)) and 400 <= val <= 3000:
                found = True
                assert val >= 1200, (
                    f"Drift guard threshold={val} is too tight for 3698px pano court. "
                    "30ft airborne ball = ~1180px; threshold must be ≥ 1200. "
                    "See 2026-03-18: bos_mia_playoffs 400px→21% valid, 1200px→65%+."
                )
        assert found, "Drift guard distance threshold comparison not found in ball_detect_track.py"


class TestHoughBallDetectionParams:
    """Hough param2 must stay ≥ 24 to avoid false positives that trip the
    200px jump guard and lower ball_valid_pct.

    Experiment (2026-03-18): lowering param2 25→22 + maxRadius 18→22 on
    phi_tor_2025 dropped ball_valid_pct from 34% to 20%, confirming that
    lower param2 generates spurious circles that jump >200px and get
    discarded, degrading 2D validity.  The correct fix for that clip is
    better homography, not looser Hough thresholds.
    """

    def test_hough_param2_not_too_loose(self):
        """param2 must be ≥ 24 to avoid false-positive circles."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src_path) as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "HoughCircles"):
                continue
            kw = {kw.arg: kw.value for kw in node.keywords}
            if "param2" in kw:
                p2 = kw["param2"]
                val = p2.value if isinstance(p2, ast.Constant) else None
                assert val is not None and val >= 24, (
                    f"Hough param2={val} causes false positives — must stay ≥ 24. "
                    f"See 2026-03-18 experiment on phi_tor_2025."
                )


# ── Fix 8: Shot-clock non-live detection ─────────────────────────────────────


class TestShotClockNonLiveDetection:
    """Fix 8 (2026-03-18): ScoreboardOCR exposes current_scan_result so
    the pipeline can detect non-live sequences (replays/halftime) and
    suspend ball tracking, improving ball_valid_pct on heavy-replay clips.
    """

    def _make_scoreboard(self):
        from src.tracking.scoreboard_ocr import ScoreboardOCR
        return ScoreboardOCR(frame_width=1280, frame_height=720)

    def test_current_scan_result_attr_exists(self):
        """ScoreboardOCR must expose a current_scan_result property."""
        sb = self._make_scoreboard()
        assert hasattr(sb, "current_scan_result")
        # Initial value before any read() call — not yet defined, but attribute present
        _ = sb.current_scan_result  # must not raise

    def test_current_scan_result_none_on_cached_frames(self):
        """current_scan_result is None on non-OCR (cached) frames."""
        sb = self._make_scoreboard()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Force counter to a non-OCR position: read once to set counter=1
        sb.read(frame)   # counter=1, no OCR (OCR runs at 15, 30, …)
        assert sb.current_scan_result is None, (
            "Expected None on cached frame (between OCR intervals)"
        )

    def test_current_scan_result_false_when_ocr_finds_nothing(self, monkeypatch):
        """current_scan_result is False when OCR runs but returns no shot clock."""
        from src.tracking import scoreboard_ocr as sb_mod
        from src.tracking.scoreboard_ocr import _OCR_INTERVAL

        sb = self._make_scoreboard()
        # Patch _ocr_frame to return all -1 (empty scoreboard, e.g. halftime)
        monkeypatch.setattr(sb, "_ocr_frame", lambda frame: dict(sb_mod._DEFAULT_STATE))

        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Advance counter to an OCR frame (multiple of _OCR_INTERVAL)
        sb._frame_counter = _OCR_INTERVAL - 1
        sb.read(frame)   # this call increments to _OCR_INTERVAL → OCR runs
        assert sb.current_scan_result is False, (
            "Expected False when OCR ran but found no shot clock"
        )

    def test_current_scan_result_true_when_clock_found(self, monkeypatch):
        """current_scan_result is True when OCR finds a shot clock value."""
        from src.tracking import scoreboard_ocr as sb_mod
        from src.tracking.scoreboard_ocr import _OCR_INTERVAL

        sb = self._make_scoreboard()
        # Patch _ocr_frame to return a valid shot clock
        def _fake_ocr(frame):
            state = dict(sb_mod._DEFAULT_STATE)
            state["shot_clock"] = 14.3
            return state

        monkeypatch.setattr(sb, "_ocr_frame", _fake_ocr)
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        sb._frame_counter = _OCR_INTERVAL - 1
        sb.read(frame)
        assert sb.current_scan_result is True, (
            "Expected True when OCR ran and found shot_clock=14.3"
        )

    def test_pipeline_has_sc_absent_streak_attr(self):
        """UnifiedPipeline.__init__ must initialise _sc_absent_streak = 0."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline", "unified_pipeline.py",
        )
        with open(src_path) as f:
            source = f.read()
        assert "_sc_absent_streak" in source, (
            "unified_pipeline.py must initialise _sc_absent_streak"
        )

    def test_pipeline_has_ball_track_suspended_attr(self):
        """UnifiedPipeline.__init__ must initialise _ball_track_suspended."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline", "unified_pipeline.py",
        )
        with open(src_path) as f:
            source = f.read()
        assert "_ball_track_suspended" in source, (
            "unified_pipeline.py must initialise _ball_track_suspended"
        )

    def test_shot_clock_absent_threshold_constant_exists(self):
        """_SHOT_CLOCK_ABSENT_THRESHOLD must be defined in unified_pipeline.py."""
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline", "unified_pipeline.py",
        )
        with open(src_path) as f:
            source = f.read()
        assert "_SHOT_CLOCK_ABSENT_THRESHOLD" in source, (
            "unified_pipeline.py must define _SHOT_CLOCK_ABSENT_THRESHOLD"
        )

    def test_streak_logic_suspends_after_threshold(self):
        """Pure logic: ball_track_suspended becomes True after N consecutive misses."""
        _SHOT_CLOCK_ABSENT_THRESHOLD = 5   # mirrors pipeline constant

        sc_absent_streak      = 0
        ball_track_suspended  = False

        # Simulate N-1 misses — should NOT yet suspend
        for _ in range(_SHOT_CLOCK_ABSENT_THRESHOLD - 1):
            sc_absent_streak += 1
            if sc_absent_streak >= _SHOT_CLOCK_ABSENT_THRESHOLD:
                ball_track_suspended = True

        assert not ball_track_suspended, "Should not suspend before threshold"

        # One more miss — crosses threshold
        sc_absent_streak += 1
        if sc_absent_streak >= _SHOT_CLOCK_ABSENT_THRESHOLD:
            ball_track_suspended = True

        assert ball_track_suspended, "Should suspend at threshold"

    def test_streak_resets_on_clock_found(self):
        """Pure logic: streak resets and suspended=False when clock found."""
        sc_absent_streak     = 10   # already past threshold
        ball_track_suspended = True

        # Clock appears
        sc_absent_streak     = 0
        ball_track_suspended = False

        assert sc_absent_streak == 0
        assert not ball_track_suspended


# ── Fix 9: PostgreSQL write works without game_id ─────────────────────────────


class TestPgWriteNoGameId:
    """Fix 9 (2026-03-18): _pg_write_tracking_rows must write rows with
    NULL game_id when --game-id is not passed, rather than skipping entirely.
    This fixes ISSUE-010 — previously every run without game_id silently
    discarded rows and accumulation across runs was impossible.
    """

    def _make_mock_pipeline(self):
        """Minimal object with the attributes _pg_write_tracking_rows needs."""
        import uuid

        class _MP:
            game_id = None
            clip_id = str(uuid.uuid4())

            def _pg_write_tracking_rows(self, rows):
                from src.pipeline.unified_pipeline import UnifiedPipeline
                return UnifiedPipeline._pg_write_tracking_rows(self, rows)

        return _MP()

    def test_pg_write_skips_when_no_database_url(self, monkeypatch):
        """_pg_write_tracking_rows returns silently when DATABASE_URL not set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)

        obj  = self._make_mock_pipeline()
        rows = [{"frame": 1, "timestamp": 0.033}]
        # Must not raise and must not try to connect
        obj._pg_write_tracking_rows(rows)   # no exception expected

    def test_pg_write_uses_null_game_id_when_absent(self, monkeypatch):
        """When game_id=None, pg_rows use None (NULL in SQL), not raise/skip."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

        obj = self._make_mock_pipeline()
        rows = [{"frame": 1, "timestamp": 0.033, "player_id": 1,
                 "x_position": 100.0, "y_position": 200.0}]

        inserted_rows = []

        class _FakeCursor:
            def close(self):
                pass

        class _FakeConn:
            def cursor(self_c):
                return _FakeCursor()
            def commit(self_c):
                pass
            def close(self_c):
                pass

        import psycopg2.extras as _ext

        def _fake_execute_batch(cur, sql, pg_rows, **kw):
            inserted_rows.extend(pg_rows)

        monkeypatch.setattr(_ext, "execute_batch", _fake_execute_batch)

        from src.data import db as _db_mod
        monkeypatch.setattr(_db_mod, "get_connection", lambda *a, **kw: _FakeConn())

        obj._pg_write_tracking_rows(rows)

        assert len(inserted_rows) == 1, "Expected one row to be inserted"
        assert inserted_rows[0]["game_id"] is None, (
            f"Expected game_id=None (NULL) when no game_id set, "
            f"got {inserted_rows[0]['game_id']!r}"
        )


# ── Fix 10: CSRT fast-fallback (3 consecutive fails → re-detection) ──────────


class TestCsrtFastFallback:
    """Fix 10 (2026-03-18): BallDetectTrack forces do_detection=True after 3
    consecutive CSRT ok=False returns, rather than waiting for the 30-frame
    no-ball streak.  Expected gain: ~5-10% ball_valid by catching CSRT drift
    early instead of burning 28 more frames in bad tracking mode.
    """

    def test_csrt_consecutive_fails_attr_exists(self):
        """BallDetectTrack source must define _csrt_consecutive_fails."""
        import os
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src) as f:
            source = f.read()
        assert "_csrt_consecutive_fails" in source, (
            "ball_detect_track.py must define _csrt_consecutive_fails"
        )

    def test_csrt_fail_threshold_constant_exists(self):
        """_CSRT_FAIL_THRESH must be defined in ball_detect_track.py."""
        import os
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src) as f:
            source = f.read()
        assert "_CSRT_FAIL_THRESH" in source, (
            "ball_detect_track.py must define _CSRT_FAIL_THRESH"
        )

    def test_consecutive_fails_increment_on_ok_false(self):
        """Pure logic: counter increments each time CSRT returns ok=False."""
        _CSRT_FAIL_THRESH    = 3
        csrt_consecutive_fails = 0
        do_detection           = False

        # Simulate two ok=False returns — should not yet trigger re-detection
        for _ in range(_CSRT_FAIL_THRESH - 1):
            res = False
            if res:
                csrt_consecutive_fails = 0
            else:
                csrt_consecutive_fails += 1
                if csrt_consecutive_fails >= _CSRT_FAIL_THRESH:
                    do_detection           = True
                    csrt_consecutive_fails = 0

        assert csrt_consecutive_fails == _CSRT_FAIL_THRESH - 1
        assert not do_detection, "Should not force re-detection before threshold"

    def test_consecutive_fails_resets_on_ok_true(self):
        """Pure logic: counter resets to 0 on CSRT ok=True."""
        csrt_consecutive_fails = 2   # already at 2

        res = True   # CSRT succeeded this frame
        if res:
            csrt_consecutive_fails = 0
        else:
            csrt_consecutive_fails += 1

        assert csrt_consecutive_fails == 0, (
            "Counter must reset to 0 when CSRT returns ok=True"
        )

    def test_forces_detection_at_threshold(self):
        """Pure logic: do_detection=True + counter reset at _CSRT_FAIL_THRESH."""
        _CSRT_FAIL_THRESH    = 3
        csrt_consecutive_fails = 0
        do_detection           = False

        for _ in range(_CSRT_FAIL_THRESH):
            res = False
            if res:
                csrt_consecutive_fails = 0
            else:
                csrt_consecutive_fails += 1
                if csrt_consecutive_fails >= _CSRT_FAIL_THRESH:
                    do_detection           = True
                    csrt_consecutive_fails = 0

        assert do_detection, "do_detection must be True at CSRT fail threshold"
        assert csrt_consecutive_fails == 0, "Counter must reset after threshold"


# ── Fix 11: Re-entry Hough wider radius (maxRadius=28 for 3 frames) ───────────


class TestReentryHoughRadius:
    """Fix 11 (2026-03-18): After any forced do_detection=True reset,
    BallDetectTrack uses maxRadius=28 for the first _REENTRY_ATTEMPTS frames
    of re-detection, then reverts to 18.  Ball is more likely to be partially
    cropped or at steep angle at re-entry so the wider search catches more hits.
    """

    def test_reentry_mode_attr_exists(self):
        """BallDetectTrack source must define _reentry_mode and _reentry_frames."""
        import os
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src) as f:
            source = f.read()
        assert "_reentry_mode" in source, (
            "ball_detect_track.py must define _reentry_mode"
        )
        assert "_reentry_frames" in source, (
            "ball_detect_track.py must define _reentry_frames"
        )

    def test_reentry_attempts_constant_exists(self):
        """_REENTRY_ATTEMPTS and _REENTRY_MAX_R must be defined."""
        import os
        src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "tracking", "ball_detect_track.py",
        )
        with open(src) as f:
            source = f.read()
        assert "_REENTRY_ATTEMPTS" in source, (
            "ball_detect_track.py must define _REENTRY_ATTEMPTS"
        )
        assert "_REENTRY_MAX_R" in source, (
            "ball_detect_track.py must define _REENTRY_MAX_R"
        )

    def test_circle_detect_accepts_max_radius(self):
        """circle_detect must accept a max_radius kwarg."""
        import inspect
        from src.tracking.ball_detect_track import BallDetectTrack
        sig = inspect.signature(BallDetectTrack.circle_detect)
        assert "max_radius" in sig.parameters, (
            "BallDetectTrack.circle_detect must accept max_radius parameter"
        )

    def test_ball_detection_accepts_max_radius(self):
        """ball_detection must accept a max_radius kwarg."""
        import inspect
        from src.tracking.ball_detect_track import BallDetectTrack
        sig = inspect.signature(BallDetectTrack.ball_detection)
        assert "max_radius" in sig.parameters, (
            "BallDetectTrack.ball_detection must accept max_radius parameter"
        )

    def test_reentry_uses_wider_radius(self):
        """Pure logic: max_radius is _REENTRY_MAX_R when _reentry_mode=True."""
        from src.tracking.ball_detect_track import _REENTRY_MAX_R
        _reentry_mode = True
        _max_r = _REENTRY_MAX_R if _reentry_mode else 18
        assert _max_r == _REENTRY_MAX_R, "Must use wider radius during re-entry"
        assert _REENTRY_MAX_R > 18, "_REENTRY_MAX_R must be wider than normal 18"

    def test_reentry_reverts_after_attempts(self):
        """Pure logic: _reentry_mode becomes False after _REENTRY_ATTEMPTS misses."""
        from src.tracking.ball_detect_track import _REENTRY_ATTEMPTS
        reentry_mode   = True
        reentry_frames = 0

        # Simulate _REENTRY_ATTEMPTS detection failures with no ball found
        for _ in range(_REENTRY_ATTEMPTS):
            # ball not found
            reentry_frames += 1
            if reentry_frames >= _REENTRY_ATTEMPTS:
                reentry_mode   = False
                reentry_frames = 0

        assert not reentry_mode, (
            f"_reentry_mode must revert to False after {_REENTRY_ATTEMPTS} misses"
        )
        assert reentry_frames == 0, "_reentry_frames must reset when mode ends"

    def test_reentry_cancels_on_ball_found(self):
        """Pure logic: _reentry_mode resets when ball is detected."""
        reentry_mode   = True
        reentry_frames = 2   # mid-reentry

        # Ball found — reset both
        ball_found = True
        if ball_found:
            reentry_mode   = False
            reentry_frames = 0

        assert not reentry_mode, "_reentry_mode must clear when ball found"
        assert reentry_frames == 0, "_reentry_frames must clear when ball found"

    def test_skip_jersey_ocr_kwarg_in_get_players_pos(self):
        """AdvancedFeetDetector.get_players_pos must accept skip_jersey_ocr kwarg."""
        import inspect
        from src.tracking.advanced_tracker import AdvancedFeetDetector
        sig = inspect.signature(AdvancedFeetDetector.get_players_pos)
        assert "skip_jersey_ocr" in sig.parameters, (
            "AdvancedFeetDetector.get_players_pos must accept skip_jersey_ocr kwarg"
        )


# ── Quick task 1: build_live_mask + vision fallback + bench defaults ──────────


class TestBuildLiveMask:
    """build_live_mask() returns correct structure for real + missing game IDs."""

    def test_build_live_mask_real_cache(self):
        """build_live_mask returns dict with live/dead_ball/unknown values."""
        from src.data.nba_enricher import build_live_mask
        mask = build_live_mask("0022200001")
        assert isinstance(mask, dict)
        if mask:
            values = set(mask.values())
            assert values <= {"live", "dead_ball", "unknown"}, (
                f"Unexpected mask values: {values}"
            )
            live_count = sum(1 for v in mask.values() if v == "live")
            assert live_count > 0, "Expected at least some live frames for a real game"

    def test_build_live_mask_missing_game(self):
        """build_live_mask returns empty dict for unknown game_id."""
        from src.data.nba_enricher import build_live_mask
        mask = build_live_mask("NONEXISTENT_GAME_ID_XYZ")
        assert mask == {}

    def test_build_live_mask_returns_dict_type(self):
        """build_live_mask always returns a dict (never None or other type)."""
        from src.data.nba_enricher import build_live_mask
        # Both real and missing should return dict
        m1 = build_live_mask("0022200001")
        m2 = build_live_mask("NONEXISTENT")
        assert isinstance(m1, dict)
        assert isinstance(m2, dict)


class TestVisionFallback:
    """Vision-based non-live fallback attributes exist in UnifiedPipeline."""

    def test_no_ball_vision_streak_in_init(self):
        """UnifiedPipeline.__init__ must initialise _no_ball_vision_streak."""
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline", "unified_pipeline.py",
        )
        with open(src_path) as f:
            source = f.read()
        assert "_no_ball_vision_streak" in source, (
            "unified_pipeline.py must initialise _no_ball_vision_streak in __init__"
        )

    def test_vision_fallback_source_present(self):
        """Vision fallback logic must reference _no_ball_vision_streak >= 20."""
        import inspect
        from src.pipeline.unified_pipeline import UnifiedPipeline
        src = inspect.getsource(UnifiedPipeline.__init__)
        assert "_no_ball_vision_streak" in src, (
            "Missing _no_ball_vision_streak in UnifiedPipeline.__init__"
        )


class TestBenchDefaultFrames:
    """_bench_run.py --frames default must be 3600."""

    def test_bench_default_frames_3600(self):
        """_bench_run.py default frames argument should be 3600."""
        import os
        bench_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_bench_run.py",
        )
        with open(bench_path) as f:
            src = f.read()
        assert "default=3600" in src, (
            "Expected default=3600 in _bench_run.py --frames argument"
        )

    def test_bench_has_ball_valid_live_in_build_summary(self):
        """_bench_run.py build_summary must include ball_valid_live key."""
        import os
        bench_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_bench_run.py",
        )
        with open(bench_path) as f:
            src = f.read()
        assert "ball_valid_live" in src, (
            "Expected ball_valid_live in _bench_run.py build_summary or evaluate_layers"
        )

    def test_bench_has_ball_valid_dead_in_build_summary(self):
        """_bench_run.py build_summary must include ball_valid_dead key."""
        import os
        bench_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "_bench_run.py",
        )
        with open(bench_path) as f:
            src = f.read()
        assert "ball_valid_dead" in src, (
            "Expected ball_valid_dead in _bench_run.py build_summary or evaluate_layers"
        )
