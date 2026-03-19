"""
unified_pipeline.py — Full NBA AI tracking pipeline

Combines:
  - AdvancedFeetDetector: player tracking (Detectron2 + Kalman + Hungarian + ReID)
  - YOLO-NAS detection: ball, rim, shot-attempt, made-basket (when weights available)
  - Hough+CSRT ball tracker: fallback when no YOLO weights
  - StatsTracker: shot attempts + made baskets per player

Output: data/tracking_data.csv + data/stats.json
"""

import csv
import json
import os
import sys
import uuid
from typing import Optional, List, Dict

import cv2
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.tracking import (
    Player, AdvancedFeetDetector, BallDetectTrack,
    COLORS, hsv2bgr, TOPCUT,
    binarize_erode_dilate, rectangularize_court, rectify, add_frame,
    evaluate_tracking,
)
from src.tracking.event_detector import EventDetector
from src.tracking.court_detector import detect_court_homography
from src.tracking.scoreboard_ocr import ScoreboardOCR
from src.tracking.possession_classifier import PossessionClassifier
from src.tracking.play_type_classifier import PlayTypeClassifier
from src.stats_tracker.tracker import StatsTracker

try:
    from scipy.spatial import ConvexHull as _ConvexHull
    _SCIPY = True
except ImportError:
    _SCIPY = False

_RESOURCES = os.path.join(PROJECT_DIR, "resources")
_DATA      = os.path.join(PROJECT_DIR, "data")

FLANN = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))

# Homography EMA — smooths per-frame SIFT homography to reduce jitter/drift
_H_EMA_ALPHA        = 0.25   # 0 = heavy smooth, 1 = raw (no memory)
                             # Reduced from 0.35: low-inlier broadcast matches (5-7) add noise;
                             # heavier smoothing averages out per-frame jitter.
_H_MIN_INLIERS      = 4      # below this → reject and use last-known good M
                             # Lowered from 5 by 20%: broadcast NBA frames sometimes yield
                             # 4 good inliers when the court is partially visible.
                             # EMA smoothing compensates for noisy low-inlier estimates.
_H_RESET_INLIERS    = 40     # ≥ this → hard-reset EMA (very clean SIFT match)
_REANCHOR_INTERVAL  = 30     # court-line drift check every N frames
_REANCHOR_ALIGN_MIN = 0.35   # projected boundary alignment below this → force re-anchor
_SIFT_INTERVAL      = 15     # run SIFT only every N frames; use cached EMA in between
                             # Increased from 5: SIFT costs 290ms detect + 150ms FLANN = 440ms/call.
                             # At 15-frame intervals: 33 calls per 500 frames = 14s vs 44s.
                             # EMA smoothing (α=0.25) keeps homography stable between updates.
_SIFT_SCALE         = 0.5   # downsample frame before SIFT detect (4x speedup, minimal quality loss)

# Checkpoint — flush tracking rows to CSV every N frames so a crash doesn't lose all data
_CHECKPOINT_INTERVAL = 2000  # ~6 min of gameplay at 5.7fps

# Frame stride — process every Nth frame on long clips to cut compute on broadcast footage
_FRAME_STRIDE       = 2      # process every 2nd frame when clip is > 3000 frames (~50 s at 60fps)

# Gameplay detection — skip non-play frames (intro, halftime, timeouts, replays)
MIN_GAMEPLAY_PERSONS = 5     # YOLO person count below this → skip frame
_GAMEPLAY_CACHE_FRAMES = 30  # once gameplay confirmed, trust it for N frames (~1 sec)

# Shot-clock non-live filter — suppresses ball tracking during replays / halftime.
# When OCR runs (_OCR_INTERVAL=15 frames) and finds no shot clock for this many
# consecutive scans, ball tracking is suspended until the clock reappears.
# Guard: suspension only fires if the clock was seen at least once on this clip
# (safety net for clips where ScoreboardOCR can't read the broadcast font at all).
# 40 scans × 15 frames = 600 frames ≈ 20 s — catches timeouts, replays, halftime;
# tight enough not to suppress live play on short OCR gaps (made baskets, etc.).
_SHOT_CLOCK_ABSENT_THRESHOLD = 40
_PANO_SCAN_INTERVAL  = 150   # check every N frames when scanning for gameplay (5s @ 30fps)
_PANO_STITCH_FRAMES  = 30    # consecutive frames to stitch into panorama

# Basket positions (normalised 0–1 of 2D court width/height, full-court top-down)
_BASKET_L            = (0.045, 0.5)   # left-baseline basket
_BASKET_R            = (0.955, 0.5)   # right-baseline basket
_DRIVE_VEL_THRESHOLD  = 3.0           # px/frame toward basket → counts as a drive
_ISOLATION_DEFAULT    = 200.0         # px — "wide open" sentinel when no opponents detected
_FAST_BREAK_VEL_MIN  = 3.5            # px/frame team-mean toward basket → fast break


# ── YOLO-NAS wrapper (optional) ───────────────────────────────────────────────

class YoloDetector:
    """Wraps YOLO-NAS-L. Falls back gracefully if weights missing."""

    LABELS = {1: "ball", 2: "made", 3: "person", 4: "rim", 5: "shoot"}

    def __init__(self, weight_path: str = None):
        self.model = None
        if weight_path and os.path.exists(weight_path):
            try:
                from src.detection.models.detection_model import Yolo_Nas_L
                from src.detection.tools.classes import class_names
                self.model = Yolo_Nas_L(
                    num_classes=len(class_names),
                    checkpoint_path=weight_path
                )
                print(f"YOLO-NAS loaded: {weight_path}")
            except Exception as e:
                print(f"YOLO-NAS load failed ({e}) — using Hough fallback")
        else:
            print("No YOLO weights found — using Hough+CSRT for ball detection")

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, frame):
        """Returns list of {label, bbox:(x1,y1,x2,y2), confidence}."""
        if not self.available:
            return []
        try:
            results = self.model.predict(frame)
            detections = []
            for row in results.numpy().tolist():
                x1, y1, x2, y2, conf, label = row
                detections.append({
                    "label":      self.LABELS.get(int(label), "unknown"),
                    "bbox":       (float(x1), float(y1), float(x2), float(y2)),
                    "confidence": float(conf),
                    "raw_label":  int(label),
                })
            return detections
        except Exception:
            return []


# ── Main pipeline ─────────────────────────────────────────────────────────────

class UnifiedPipeline:
    """
    Full basketball tracking pipeline.

    Args:
        video_path:         Input video file.
        yolo_weight_path:   Path to YOLO-NAS weights (.pth). Optional.
        max_frames:         Stop after N frames (None = full video).
        show:               Display live window.
        output_video_path:  Write annotated video here. Optional.
    """

    def __init__(
        self,
        video_path: str,
        yolo_weight_path: str = None,
        max_frames: int = None,
        start_frame: int = 0,
        show: bool = True,
        output_video_path: str = None,
        game_id: str = None,
    ):
        self.video_path        = video_path
        self.max_frames        = max_frames
        self.start_frame       = start_frame
        self.show              = show
        self.output_video_path = output_video_path
        self.game_id           = game_id
        self.clip_id           = str(uuid.uuid4())  # unique per pipeline run

        self.yolo    = YoloDetector(yolo_weight_path)
        self.players = self._build_players()

        # Build player detector early — reused for gameplay filter
        self.feet_det = AdvancedFeetDetector(self.players)

        pano = self._load_pano(video_path)

        # Collect frames for per-clip homography detection (ISSUE-017).
        # Cap at 60 frames evenly sampled from the first 3600 frames (60 s at 60fps).
        # Raised from 1800: gameplay starts at frame ~1400 on most broadcast clips,
        # leaving only ~14 court frames at 1800 — not enough for detect_court_homography.
        # At 3600 and step=60, we get ~35 gameplay frames which is sufficient.
        _STARTUP_MAX_FRAMES = 60
        _STARTUP_SCAN_END   = 3600   # 60 s at 60fps
        _startup_cap = cv2.VideoCapture(video_path)
        _total = int(_startup_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        _scan_end = min(_total, _STARTUP_SCAN_END)
        _step = max(1, _scan_end // _STARTUP_MAX_FRAMES)
        _startup_frames: list = []
        for _idx in range(0, _scan_end, _step):
            if len(_startup_frames) >= _STARTUP_MAX_FRAMES:
                break
            _startup_cap.set(cv2.CAP_PROP_POS_FRAMES, _idx)
            _ok, _f = _startup_cap.read()
            if not _ok:
                break
            _startup_frames.append(_f[TOPCUT:])
        _startup_cap.release()

        # M1 recovery state — updated by _build_court and _try_recover_court_M1
        self._last_good_M1:        Optional[np.ndarray] = None
        self._M1_stale_frames:     int                  = 0
        self._M1_failed_attempts:  int                  = 0  # consecutive detection failures
        # Rolling frame buffer for mid-run court re-detection (5 frames gives more
        # line candidates than a single frame, improving detect_court_homography success rate)
        from collections import deque as _deque
        self._recover_frame_buf: _deque = _deque(maxlen=5)

        self.map_2d, self.M1 = self._build_court(pano, startup_frames=_startup_frames)
        self.pano = pano

        self._gameplay_cache_until: int = 0   # frame index; skip check before this
        self._sc_absent_streak:     int = 0     # consecutive OCR runs with no shot clock
        self._sc_ever_seen:         bool = False  # True once OCR reads a valid shot clock
        self._ball_track_suspended: bool = False  # True during replay / halftime sequences
        # Vision-based non-live fallback: counts consecutive frames where ball is absent
        # and fewer than 8 persons are visible, to detect warmups / ad breaks / halftime
        # on clips where ScoreboardOCR never fires (no readable shot clock font).
        self._no_ball_vision_streak: int = 0

        self.ball_det = BallDetectTrack(self.players)  # Hough fallback

        cap0 = cv2.VideoCapture(video_path)
        _, f0 = cap0.read(); cap0.release()
        h, w  = (f0[TOPCUT:].shape[:2]) if f0 is not None else (720, 1280)
        fps   = cv2.VideoCapture(video_path).get(cv2.CAP_PROP_FPS) or 30
        self.stats_tracker = StatsTracker(frame_w=w, frame_h=h, fps=fps)

        sift = cv2.xfeatures2d.SIFT_create()
        self.sift = sift
        self.kp1, self.des1 = sift.compute(pano, sift.detect(pano))
        self._M_ema:              Optional[np.ndarray] = None
        self._last_ball_2d:       Optional[tuple]      = None  # (x2d, y2d) this frame
        self._frames_since_anchor: int                 = 0
        self._sift_frame_counter:  int                 = 0

        self.event_det = EventDetector(map_w=self.map_2d.shape[1],
                                       map_h=self.map_2d.shape[0])

        # ── Context classifiers ───────────────────────────────────────────
        _fw, _fh = w, h   # frame dims captured above for StatsTracker
        self.scoreboard_ocr = ScoreboardOCR(frame_width=_fw, frame_height=_fh)
        self.poss_cls = PossessionClassifier(
            fps=fps,
            map_w=self.map_2d.shape[1],
            map_h=self.map_2d.shape[0],
        )
        self.play_cls = PlayTypeClassifier()

    # ── setup helpers ─────────────────────────────────────────────────────

    def _build_players(self):
        # 5 green slots (IDs 1-5) + 5 white slots (IDs 6-10) + 1 referee (ID 0).
        # Hungarian matching operates on two distinct team pools so detections
        # classified as "green" or "white" by HSV each route to their own slots.
        players = []
        for i in range(1, 6):
            players.append(Player(i, "green", hsv2bgr(COLORS["green"][2])))
        for i in range(6, 11):
            players.append(Player(i, "white", hsv2bgr(COLORS["white"][2])))
        players.append(Player(0, "referee", hsv2bgr(COLORS["referee"][2])))
        return players

    @staticmethod
    def _auto_pano_path(video_path: str) -> str:
        """Return per-video panorama cache path under resources/panos/."""
        import re
        stem = re.sub(r'[^\w\-]', '_', os.path.splitext(os.path.basename(video_path))[0])[:60]
        pano_dir = os.path.join(_RESOURCES, "panos")
        os.makedirs(pano_dir, exist_ok=True)
        return os.path.join(pano_dir, f"pano_{stem}.png")

    @staticmethod
    def _pano_valid(pano: np.ndarray) -> bool:
        """Return True if the panorama looks like a valid court (landscape, wide enough).

        A usable court pano must be:
        - ≥2000 px wide (to produce a ~2800px rectified court)
        - w/h ratio between 3.0 and 10.0 (basketball court ≈1.88:1, stitching adds width;
          ratio >10 means over-stitched — SIFT homography will map all points far outside
          the expected court region; ratio <3 means portrait/wrong corners)
        """
        if pano is None:
            return False
        h, w = pano.shape[:2]
        ratio = w / max(h, 1)
        return w >= 2000 and 3.0 <= ratio <= 10.0

    def _load_pano(self, video_path: str) -> np.ndarray:
        """Load panorama for this video, building it from gameplay frames if needed."""
        # 1. Video-specific cached pano — validate before using
        cached = UnifiedPipeline._auto_pano_path(video_path)
        if os.path.exists(cached):
            pano = cv2.imread(cached)
            if UnifiedPipeline._pano_valid(pano):
                print(f" Pano cache hit: {os.path.basename(cached)}")
                return np.vstack((pano, np.zeros((100, pano.shape[1], 3), dtype=pano.dtype)))
            else:
                h, w = (pano.shape[:2]) if pano is not None else (0, 0)
                print(f" Cached pano {os.path.basename(cached)} invalid ({w}×{h}) — discarding")
                os.remove(cached)

        # 2. Auto-build per-clip pano from this video's gameplay frames.
        print(" No video-specific pano cached — building from gameplay frames...")
        try:
            pano = self._scan_and_build_pano(video_path)
            if UnifiedPipeline._pano_valid(pano):
                return np.vstack((pano, np.zeros((100, pano.shape[1], 3), dtype=pano.dtype)))
            else:
                h, w = pano.shape[:2]
                print(f" Built pano still invalid ({w}×{h}) — falling back to general pano")
        except Exception as e:
            print(f" Per-clip pano build failed ({e}) — falling back to general pano")

        # 3. General fallback — always use pano_enhanced (last resort).
        # IMPORTANT: M1 (Rectify1.npy) is calibrated for the Short4Mosaicing panorama
        # (3698×500px). A per-video broadcast frame (1280×660) would break M1 because
        # M1 maps pano-coordinate-space → 2D court; using a different pano invalidates
        # that mapping and clusters all players into a ~590px wide strip.
        # Broadcast frames give 5–7 SIFT inliers vs pano_enhanced — _H_MIN_INLIERS=5
        # ensures these are accepted rather than falling back to stale EMA.
        for fname in ("pano_enhanced.png", "pano.png"):
            general = os.path.join(_RESOURCES, fname)
            if os.path.exists(general):
                img = cv2.imread(general)
                if UnifiedPipeline._pano_valid(img):
                    print(f" Using general pano (fallback): {fname}")
                    return np.vstack((img, np.zeros((100, img.shape[1], 3), dtype=img.dtype)))

    def _scan_and_build_pano(self, video_path: str) -> np.ndarray:
        """Scan video for gameplay frames, stitch into panorama, cache per-video."""
        import torch
        model     = self.feet_det.model
        use_half  = self.feet_det._use_half

        cap   = cv2.VideoCapture(video_path)
        fps   = cap.get(cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f" Scanning {total / fps / 60:.1f} min video for gameplay...")

        first_gameplay = -1
        for fno in range(0, total, _PANO_SCAN_INTERVAL):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ok, frame = cap.read()
            if not ok:
                break
            frame = frame[TOPCUT:]
            r = model(frame, classes=[0], conf=0.4, verbose=False,
                      half=use_half, imgsz=640)
            n = len(r[0].boxes) if r[0].boxes is not None else 0
            if n >= MIN_GAMEPLAY_PERSONS:
                first_gameplay = fno
                print(f"  Gameplay at frame {fno} ({fno / fps / 60:.1f} min, {n} people)")
                break

        if first_gameplay < 0:
            cap.release()
            raise RuntimeError(
                "No gameplay detected in video — check that this is an NBA broadcast "
                f"with {MIN_GAMEPLAY_PERSONS}+ players visible on court."
            )

        # Sample frames from a tight window (~5 s) starting at first gameplay.
        # Spreading across the full video caused excessive camera drift → over-wide
        # panoramas (30:1 ratio) that break SIFT homography for individual frames.
        # A short window keeps the camera stable so SIFT has a consistent reference.
        window_frames = min(int(fps * 5), total - first_gameplay)  # 5 s window
        step = max(1, window_frames // _PANO_STITCH_FRAMES)
        stitch_frames = []
        for fno in range(first_gameplay, first_gameplay + window_frames, step):
            if len(stitch_frames) >= _PANO_STITCH_FRAMES:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
            ok, f = cap.read()
            if not ok:
                break
            stitch_frames.append(f[TOPCUT:])
        cap.release()

        print(f" Stitching {len(stitch_frames)} frames into panorama...")
        from src.tracking.rectify_court import collage
        try:
            pano = collage(stitch_frames)
        except Exception as e:
            print(f"  Stitch failed ({e}), using single frame as pano")
            pano = stitch_frames[0]

        # Validate stitched result — an over-wide pano (ratio >10) means the camera
        # moved too much between sampled frames and SIFT stitched across multiple
        # distinct views.  Fall back to a single gameplay frame in that case.
        if not UnifiedPipeline._pano_valid(pano):
            h, w = pano.shape[:2]
            print(f"  Stitched pano invalid ({w}×{h}, ratio={w/max(h,1):.1f}) — using single gameplay frame")
            pano = stitch_frames[0]

        out = UnifiedPipeline._auto_pano_path(video_path)
        cv2.imwrite(out, pano)
        print(f" Pano saved → {os.path.basename(out)} ({pano.shape[1]}×{pano.shape[0]})")
        return pano

    def _is_gameplay(self, frame: np.ndarray, frame_idx: int) -> bool:
        """Return True when YOLO detects enough players — skips non-play frames."""
        if frame_idx < self._gameplay_cache_until:
            return True
        r = self.feet_det.model(
            frame, classes=[0], conf=0.35, verbose=False,
            imgsz=640, half=self.feet_det._use_half,
        )
        n = len(r[0].boxes) if r[0].boxes is not None else 0
        if n >= MIN_GAMEPLAY_PERSONS:
            self._gameplay_cache_until = frame_idx + _GAMEPLAY_CACHE_FRAMES
            return True
        return False

    def _build_court(self, pano, startup_frames: list = None):
        """Build 2D court map and compute homography M1.

        Attempts per-clip homography detection from startup_frames using
        detect_court_homography(). Falls back to static resources/Rectify1.npy
        if detection returns None (< 4 court line intersections found).

        Args:
            pano: Panorama image used for court rectification.
            startup_frames: Optional list of BGR frames (first ~60) from the
                            video source. When provided, attempts per-clip M1
                            detection. When None, skips detection and uses
                            Rectify1.npy directly.

        Returns:
            Tuple of (map_2d, M1) where M1 is a 3x3 float64 homography.
        """
        rect1 = os.path.join(_RESOURCES, "Rectify1.npy")
        map_img = cv2.imread(os.path.join(_RESOURCES, "2d_map.png"))

        img = binarize_erode_dilate(pano, plot=False)
        _, corners = rectangularize_court(img, plot=False)
        rectified = rectify(pano, corners, plot=False)
        map_2d = cv2.resize(map_img, (rectified.shape[1], rectified.shape[0]))

        # Per-clip homography detection (ISSUE-017 fix).
        # NOTE: detect_court_homography returns M1 mapping frame→940×500 directly.
        # The pipeline applies M1 @ (M @ x) where M maps frame→pano, so M1 must
        # map pano→court.  The correct adjustment (M1_adjusted = M1_raw @ inv(M_ema))
        # requires M_ema (SIFT EMA) which is NOT available at __init__ time.
        # Therefore, startup detection is SKIPPED here; _try_recover_court_M1
        # performs the same detection during gameplay with M_ema available so it
        # can compute the proper inverse-adjusted M1.  Meanwhile, use Rectify1.npy
        # as the initial fallback (calibrated for pano_enhanced, 3698×500px).
        if self._last_good_M1 is not None:
            M1 = self._last_good_M1
            clip = os.path.basename(getattr(self, "video_path", "unknown"))
            print(f"[unified_pipeline] Reusing last good M1 for '{clip}'")
        else:
            M1 = np.load(rect1)
            clip = os.path.basename(getattr(self, "video_path", "unknown"))
            print(f"[unified_pipeline] Using static Rectify1.npy for '{clip}' — per-clip M1 will be updated during gameplay")

        return map_2d, M1

    def _try_recover_court_M1(self, frame: np.ndarray) -> None:
        """Attempt to re-detect court homography after camera cuts / zooms.

        Called every gameplay frame in run(). Increments a staleness counter each
        frame. Once the counter exceeds 30 consecutive frames with no successful
        per-clip detection, retries detect_court_homography on the current frame.
        Lowered from 150→30 (2026-03-18) so clips where startup scan fails get
        a valid per-clip M1 within the first ~5s of gameplay rather than ~25s.
        Updates self.M1 and self._last_good_M1 on success and resets the counter.

        Args:
            frame: Current BGR frame (already cropped by TOPCUT).
        """
        # Maintain a rolling buffer; detect_court_homography works better with
        # multiple frames (accumulates hardwood mask, more line candidates).
        self._recover_frame_buf.append(frame)

        self._M1_stale_frames += 1
        # Threshold logic:
        # - Initial fallback (M1 never found): 30-frame window for fast first recovery.
        # - After recovery: 150-frame window to avoid disrupting arc polyfit.
        # - After 5 consecutive failed detection attempts: back off to 500-frame window
        #   so clips where court detection never works don't burn CPU on every 30 frames.
        if self._last_good_M1 is None:
            threshold = 500 if self._M1_failed_attempts >= 5 else 30
        else:
            threshold = 150
        if self._M1_stale_frames > threshold:
            new_M1_raw = detect_court_homography(list(self._recover_frame_buf))
            if new_M1_raw is not None:
                # detect_court_homography returns M1 mapping frame→940×500 court.
                # The pipeline applies M1 @ (M @ x) where M maps frame→pano.
                # To be correct, M1 must map pano→court so that:
                #   M1 @ M @ x  =  (pano→court) @ (frame→pano) @ x  =  frame→court
                # Adjust: M1_adjusted = M1_raw @ inv(M_ema)
                #   M1_adjusted @ M_ema  =  M1_raw @ I  =  M1_raw  (correct)
                new_M1 = new_M1_raw
                if self._M_ema is not None:
                    try:
                        import numpy as _np
                        new_M1 = new_M1_raw @ _np.linalg.inv(self._M_ema)
                    except (np.linalg.LinAlgError, AttributeError):
                        pass  # M_ema singular or unavailable — use raw M1
                self.M1 = new_M1
                self._last_good_M1 = new_M1
                self._M1_stale_frames = 0
                self._M1_failed_attempts = 0
            else:
                self._M1_failed_attempts += 1
                self._M1_stale_frames = 0  # reset so we wait another threshold period

    def _get_homography(self, frame) -> Optional[np.ndarray]:
        """
        Compute SIFT-based frame→panorama homography with EMA smoothing and
        court-line re-anchoring.

        Three tiers:
          1. inliers < _H_MIN_INLIERS  → reject, keep last good M (no change)
          2. inliers ≥ _H_RESET_INLIERS → hard-reset EMA (very clean match,
             discards accumulated drift immediately)
          3. _H_MIN_INLIERS ≤ inliers < _H_RESET_INLIERS → EMA blend as before

        Additionally, every _REANCHOR_INTERVAL frames a court-line alignment
        check projects the 4 court boundary lines through inv(M_ema·M1) and
        measures how many projected samples land on white court-line pixels.
        Alignment below _REANCHOR_ALIGN_MIN signals slow drift → hard-reset
        to the freshest SIFT M.
        """
        self._sift_frame_counter += 1
        if self._sift_frame_counter % _SIFT_INTERVAL != 0 and self._M_ema is not None:
            return self._M_ema

        h, w = frame.shape[:2]
        small = cv2.resize(frame, (int(w * _SIFT_SCALE), int(h * _SIFT_SCALE)))
        kp2_small, des2 = self.sift.detectAndCompute(small, None)
        if des2 is None or len(des2) < 4:
            return self._M_ema
        inv_s = 1.0 / _SIFT_SCALE
        kp2 = [cv2.KeyPoint(kp.pt[0] * inv_s, kp.pt[1] * inv_s,
                             kp.size * inv_s, kp.angle, kp.response,
                             kp.octave, kp.class_id) for kp in kp2_small]

        matches = FLANN.knnMatch(self.des1, des2, k=2)
        good    = [m for m, n in matches if m.distance < 0.7 * n.distance]
        if len(good) < 4:
            return self._M_ema

        src = np.float32([self.kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        M, mask = cv2.findHomography(dst, src, cv2.RANSAC, 5.0)

        if M is None:
            return self._M_ema

        inliers = int(mask.sum()) if mask is not None else 0
        # First-frame bootstrap: accept 3+ inliers if no EMA exists yet.
        # After bootstrap, use stricter _H_MIN_INLIERS to avoid noisy updates.
        min_inliers = 3 if self._M_ema is None else _H_MIN_INLIERS
        if inliers < min_inliers:
            return self._M_ema

        # Sanity gate: reject M if it maps reference points too far from current EMA.
        # This prevents a single bad SIFT match from teleporting all tracked players.
        if self._M_ema is not None and inliers < _H_RESET_INLIERS:
            h_pano, w_pano = self.pano.shape[:2]
            test_pts = np.float32([
                [w_pano * 0.25, h_pano * 0.5, 1],
                [w_pano * 0.50, h_pano * 0.5, 1],
                [w_pano * 0.75, h_pano * 0.5, 1],
                [w_pano * 0.50, h_pano * 0.25, 1],
            ])
            def _proj(mat, pt):
                p = mat @ pt.reshape(3, 1)
                return p[:2] / p[2]
            dists = [
                float(np.linalg.norm(_proj(M, p) - _proj(self._M_ema, p)))
                for p in test_pts
            ]
            if max(dists) > 99999:  # sanity gate disabled — position-level smoothing used instead
                return self._M_ema

        # Tier 1: very clean match — hard-reset to eliminate accumulated drift
        if self._M_ema is None or inliers >= _H_RESET_INLIERS:
            self._M_ema = M
        else:
            # Tier 2: EMA blend
            self._M_ema = _H_EMA_ALPHA * M + (1 - _H_EMA_ALPHA) * self._M_ema

        # Periodic court-line drift check
        self._frames_since_anchor += 1
        if self._frames_since_anchor >= _REANCHOR_INTERVAL:
            self._frames_since_anchor = 0
            if self._check_court_drift(frame):
                # Drift confirmed — snap to freshest SIFT M
                self._M_ema = M

        return self._M_ema

    def _check_court_drift(self, frame: np.ndarray) -> bool:
        """
        Detect slow homography drift by projecting the 4 court boundary lines
        through inv(M_ema) · inv(M1) into frame space and measuring white-pixel
        alignment.

        Returns True when alignment < _REANCHOR_ALIGN_MIN (drift detected).
        """
        if self._M_ema is None:
            return False

        h, w = frame.shape[:2]
        map_h, map_w = self.map_2d.shape[:2]

        try:
            # 2D court → frame: inv(M_ema) · inv(M1)
            M_ct2f = np.linalg.inv(self._M_ema) @ np.linalg.inv(self.M1)
        except np.linalg.LinAlgError:
            return False

        # White court-line mask (high V, low S)
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        white = cv2.inRange(hsv, (0, 0, 175), (180, 45, 255))

        total = aligned = 0
        for cx, cy in self._court_boundary_samples(map_w, map_h, n=20):
            pt = M_ct2f @ np.array([cx, cy, 1.0])
            if abs(pt[2]) < 1e-6:
                continue
            fx, fy = int(pt[0] / pt[2]), int(pt[1] / pt[2])
            if 0 <= fx < w and 0 <= fy < h:
                total += 1
                r = 8
                if white[max(0, fy - r):min(h, fy + r),
                         max(0, fx - r):min(w, fx + r)].any():
                    aligned += 1

        if total < 8:
            return False  # not enough projected points visible — can't judge

        alignment = aligned / total
        return alignment < _REANCHOR_ALIGN_MIN

    @staticmethod
    def _court_boundary_samples(map_w: int, map_h: int, n: int = 20):
        """Yield (x, y) samples evenly spaced along the 4 court boundary edges."""
        xs = np.linspace(0, map_w, n, dtype=int)
        ys = np.linspace(0, map_h, n, dtype=int)
        for x in xs:
            yield int(x), 0        # top sideline
            yield int(x), map_h    # bottom sideline
        for y in ys:
            yield 0,     int(y)    # left baseline
            yield map_w, int(y)    # right baseline

    # ── main run ──────────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Process video end-to-end.

        Returns dict with:
          predictions  — per-frame tracking results
          stats        — per-player shot attempts + made baskets
          id_switches  — estimated ID switch count
          stability    — track stability score
          total_frames — frames processed
        """
        cap    = cv2.VideoCapture(self.video_path)
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
        map_h, map_w = self.map_2d.shape[:2]
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        _use_stride = total_video_frames > 3000
        if self.start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame)
        writer = self._make_writer(cap)

        tracking_rows:    List[dict] = []
        ball_rows:        List[dict] = []
        predictions:      List[dict] = []
        player_stats:     dict       = {}
        possession_rows:  List[dict] = []
        shot_log_rows:    List[dict] = []
        suspended_frame_count: int   = 0  # frames where ball tracking was suspended
        frame_idx    = 0  # absolute frame counter (for position keys, CSV timestamps)
        gameplay_frames = 0  # gameplay frames actually processed (for max_frames check)
        prev_pos:    Dict[int, tuple] = {}   # player_id → (x2d, y2d)
        prev_vel:    Dict[int, float] = {}   # player_id → velocity prev frame
        poss_team_prev:   str            = ""
        possession_dur:   int            = 0
        last_handler:     Optional[dict] = None   # last player who had ball (for shot log)
        prev_ball_2d_f:   Optional[tuple] = None
        possession_id:    int            = 0
        possession_start: int            = 0
        possession_buf:   List[dict]     = []
        fast_break:       int            = 0
        poss_no_ball_streak: int         = 0   # consecutive frames without detected ball handler
        _POSS_PERSIST_FRAMES = 5               # frames without ball before possession resets

        while cap.isOpened():
            ok, frame = cap.read()
            if not ok or (self.max_frames and gameplay_frames >= self.max_frames):
                break

            # Skip odd frames on long clips to halve compute without affecting short benchmarks
            if _use_stride and frame_idx % _FRAME_STRIDE != 0:
                frame_idx += 1
                continue

            frame = frame[TOPCUT:]

            # Skip non-gameplay frames (intro, halftime, timeout, replay, crowd shots)
            if not self._is_gameplay(frame, frame_idx):
                frame_idx += 1
                continue

            # Periodically re-detect court homography to recover from camera cuts.
            self._try_recover_court_M1(frame)

            M = self._get_homography(frame)
            if M is None:
                frame_idx += 1
                continue

            map_snap = self.map_2d.copy()
            self._last_ball_2d = None

            # ── Player tracking ───────────────────────────────────────────
            frame, map_snap, map_txt = self.feet_det.get_players_pos(
                M, self.M1, frame, frame_idx, map_snap,
                skip_jersey_ocr=self._ball_track_suspended,
            )

            # ── Scoreboard OCR (before ball tracking — drives non-live filter) ──
            sb_state = self.scoreboard_ocr.read(frame)
            _sc_result = self.scoreboard_ocr.current_scan_result  # None|True|False
            if _sc_result is not None:   # an actual OCR scan ran this frame
                if _sc_result:
                    self._sc_absent_streak     = 0
                    self._sc_ever_seen         = True
                    self._ball_track_suspended = False
                elif self._sc_ever_seen:
                    # Only count absence once we know OCR can read this clip's clock.
                    # Prevents spurious suspension on clips where ScoreboardOCR never
                    # successfully reads the broadcast font (would suspend after 40×15=600
                    # frames even on live gameplay).
                    self._sc_absent_streak += 1
                    if self._sc_absent_streak >= _SHOT_CLOCK_ABSENT_THRESHOLD:
                        self._ball_track_suspended = True

            # Vision-based fallback: if shot clock OCR never fired on this clip,
            # use YOLO person count + ball-absent streak as a proxy non-live signal.
            # Fires when: clock never seen + ball absent 20+ consecutive gameplay frames
            # + fewer than 8 persons visible (warmup / between-period / ad break).
            yolo_results = self.yolo.predict(frame) if self.yolo.available else []
            if (self.yolo.available
                    and not self._sc_ever_seen
                    and not self._ball_track_suspended
                    and self._no_ball_vision_streak >= 20
                    and len(yolo_results) < 8):
                self._ball_track_suspended = True

            # ── Ball + event detection ────────────────────────────────────
            # Skip Hough/CSRT during confirmed non-live sequences (replays,
            # halftime, warmups) — the shot clock is absent there and the ball
            # can't be reliably located.  Player tracking above still runs so
            # lineup and position data accumulate.
            if self._ball_track_suspended:
                self._last_ball_2d = None   # clear stale position
                suspended_frame_count += 1
            elif yolo_results:
                frame, map_snap = self._apply_yolo(
                    frame, map_snap, map_txt, yolo_results, M, frame_idx
                )
            else:
                frame, _ = self.ball_det.ball_tracker(
                    M, self.M1, frame, map_snap.copy(), map_txt, frame_idx
                )
                self._last_ball_2d = self.ball_det.last_2d_pos

            if yolo_results and self.yolo.available and not self._ball_track_suspended:
                self._update_stats(frame, yolo_results, player_stats, frame_idx)

            # Update vision-based no-ball streak for non-live fallback.
            # Increment when ball is absent; reset when ball is found.
            if self._last_ball_2d is None and not self._ball_track_suspended:
                self._no_ball_vision_streak += 1
            else:
                self._no_ball_vision_streak = 0

            timestamp_sec = round(frame_idx / fps, 3)
            ball_pos      = self._last_ball_2d

            # Ball position fallback: when Hough/CSRT loses the ball, use the
            # possessor's 2D court position so EventDetector can still fire
            # dribble events.  Shot detection needs true ball trajectory so we
            # only apply this for stable possession (not in-flight).
            if ball_pos is None:
                for p in self.players:
                    if p.has_ball and p.team != "referee" and frame_idx in p.positions:
                        ball_pos = p.positions[frame_idx]
                        break

            # ── Ball tracking row ─────────────────────────────────────────
            ball_rows.append({
                "frame":     frame_idx,
                "timestamp": timestamp_sec,
                "ball_x2d":  ball_pos[0] if ball_pos else "",
                "ball_y2d":  ball_pos[1] if ball_pos else "",
                "detected":  int(ball_pos is not None),
            })

            # ── Collect per-player data ───────────────────────────────────
            # Pass 1: build frame-level position map for cross-player metrics
            # Referees are excluded — their positions contaminate spacing/pressure metrics
            # and inflate feature counts in ML training data.
            team_pos: Dict[int, tuple] = {}   # player_id → (team, x2d, y2d)
            frame_tracks: List[dict]   = []
            for p in self.players:
                if p.team == "referee":
                    continue
                if frame_idx not in p.positions:
                    continue
                x2d, y2d = p.positions[frame_idx]

                # Position jump suppression: if this position jumped >350px from
                # last known position (bad homography frame), use previous position.
                last_pos = prev_pos.get(p.ID)
                if last_pos is not None:
                    dx = x2d - last_pos[0]
                    dy = y2d - last_pos[1]
                    if (dx * dx + dy * dy) > 350 * 350:
                        x2d, y2d = last_pos[0], last_pos[1]

                slot     = self.players.index(p)
                conf     = max(0.0, 1.0 - self.feet_det._lost_ages.get(slot, 0) / 15)
                team_pos[p.ID] = (p.team, int(x2d), int(y2d))
                frame_tracks.append({
                    "player_id":        p.ID,
                    "team":             p.team,
                    "bbox":             p.previous_bb,
                    "x2d":              int(x2d),
                    "y2d":              int(y2d),
                    "confidence":       round(conf, 3),
                    "has_ball":         p.has_ball,
                    "ankle_x":          getattr(p, "ankle_x", None),
                    "ankle_y":          getattr(p, "ankle_y", None),
                    "contest_arm_angle": getattr(p, "contest_arm_angle", 0.0),
                })

            # ── Post-clamp duplicate suppression ──────────────────────────
            # Position jump clamping can re-introduce duplicates; strip them here.
            _seen: Dict[str, set] = {}
            _dedup: List[dict] = []
            for t in frame_tracks:
                tm = t["team"]
                if tm not in _seen:
                    _seen[tm] = set()
                x, y = t["x2d"], t["y2d"]
                is_dup = any(
                    abs(x - ox) < 130 and abs(y - oy) < 130
                    and (abs(x - ox) ** 2 + abs(y - oy) ** 2) < 130 ** 2
                    for ox, oy in _seen[tm]
                )
                if not is_dup:
                    _seen[tm].add((x, y))
                    _dedup.append(t)
            frame_tracks = _dedup

            predictions.append({"frame": frame_idx, "tracks": frame_tracks})
            gameplay_frames += 1

            # ── Frame-level metrics (shared across all players this frame) ──
            event = self.event_det.update(
                frame_idx, ball_pos, frame_tracks,
                pixel_vel=self.ball_det.pixel_vel,
                ball_y_pixel=self.ball_det._prev_cy,
                frame_height=frame.shape[0],
            )

            # ── Ball trajectory features (computed once per frame) ─────────
            _ball_traj = self.ball_det.get_trajectory_features()

            spatial = self._frame_spatial(frame_tracks, ball_pos, map_w, map_h)

            # ── Possession classification ─────────────────────────────────
            # Build simplified player list expected by PossessionClassifier
            _players_simple = [
                {
                    "player_id": t["player_id"],
                    "x":         float(t["x2d"]),
                    "y":         float(t["y2d"]),
                    "speed":     float(
                        round(float(np.hypot(
                            t["x2d"] - prev_pos[t["player_id"]][0],
                            t["y2d"] - prev_pos[t["player_id"]][1],
                        )), 2) if t["player_id"] in prev_pos else 0.0
                    ),
                    "team":      t["team"],
                    "has_ball":  t["has_ball"],
                }
                for t in frame_tracks
            ]
            poss_ctx = self.poss_cls.update(_players_simple, ball_pos, frame_idx)

            # ── Play type classification (uses predictions buffer) ─────────
            play_type = self.play_cls.update(
                [{"frame": frame_idx, "tracks": [
                    {**t, "event": event} for t in frame_tracks
                ]}],
                poss_ctx["possession_type"],
            )

            # ── Possession duration + possession ID ───────────────────────
            handler_now = next((t for t in frame_tracks if t.get("has_ball")), None)
            if handler_now:
                last_handler = handler_now
            curr_poss   = handler_now["team"] if handler_now else ""

            # Possession persistence: don't reset on brief ball-detection gaps.
            # Only switch to "no possession" after _POSS_PERSIST_FRAMES consecutive misses.
            if not curr_poss and poss_team_prev:
                poss_no_ball_streak += 1
                if poss_no_ball_streak < _POSS_PERSIST_FRAMES:
                    curr_poss = poss_team_prev  # extend possession through gap
            else:
                poss_no_ball_streak = 0

            if curr_poss and curr_poss == poss_team_prev:
                possession_dur += 1
            else:
                # Possession changed — finalize previous possession
                if poss_team_prev and possession_buf:
                    row = UnifiedPipeline._summarize_possession(
                        possession_id, poss_team_prev,
                        possession_start, frame_idx - 1,
                        possession_buf, fps,
                    )
                    if row:
                        possession_rows.append(row)
                possession_id   += 1
                possession_start = frame_idx
                possession_buf   = []
                possession_dur   = 1 if curr_poss else 0
                poss_team_prev   = curr_poss

            # Build handler average velocity-toward-basket for buffer
            handler_vtb = 0.0
            if handler_now:
                pxy_h = prev_pos.get(handler_now["player_id"])
                if pxy_h:
                    dx_h = handler_now["x2d"] - pxy_h[0]
                    dy_h = handler_now["y2d"] - pxy_h[1]
                    handler_vtb = UnifiedPipeline._vel_toward_basket(
                        handler_now["x2d"], handler_now["y2d"],
                        dx_h, dy_h, map_w, map_h
                    )
            if curr_poss:
                possession_buf.append({
                    "frame":      frame_idx,
                    "spacing":    spatial.get(curr_poss, {}).get("spacing", 0.0),
                    "isolation":  spatial.get("_isolation", 0.0),
                    "vtb":        handler_vtb,
                    "drive":      int(handler_now is not None and handler_vtb > _DRIVE_VEL_THRESHOLD),
                    "shot_event": event == "shot",
                    "fast_break": fast_break,
                })

            # ── Shot log entry ─────────────────────────────────────────────
            shooter = handler_now or last_handler  # use last known handler if ball in air
            if event == "shot" and shooter:
                shot_log_rows.append({
                    "shot_id":            len(shot_log_rows) + 1,
                    "frame":              frame_idx,
                    "timestamp":          timestamp_sec,
                    "player_id":          shooter["player_id"],
                    "team":               shooter["team"],
                    "x_position":         shooter["x2d"],
                    "y_position":         shooter["y2d"],
                    "court_zone":         UnifiedPipeline._court_zone(
                                              shooter["x2d"], shooter["y2d"],
                                              map_w, map_h),
                    "defender_distance":  round(spatial.get("_isolation", 0.0), 1),
                    "team_spacing":       round(
                                              spatial.get(shooter["team"], {})
                                                    .get("spacing", 0.0), 1),
                    "possession_id":      possession_id,
                    "possession_duration": possession_dur,
                    "made":               "",   # filled by nba_enricher
                })

            # ── Ball velocity (2D court px/frame) ─────────────────────────
            ball_vel_2d = 0.0
            if ball_pos and prev_ball_2d_f:
                ball_vel_2d = round(float(np.hypot(
                    ball_pos[0] - prev_ball_2d_f[0],
                    ball_pos[1] - prev_ball_2d_f[1],
                )), 2)
            prev_ball_2d_f = ball_pos

            # ── Fast-break flag (frame-level) ─────────────────────────────
            fast_break = UnifiedPipeline._fast_break_flag(
                frame_tracks, prev_pos, map_w, map_h
            )

            # Pass 2: enrich each track into a full CSV row
            for track in frame_tracks:
                pid, team = track["player_id"], track["team"]
                x2d, y2d  = track["x2d"], track["y2d"]

                pxy  = prev_pos.get(pid)
                vel  = round(float(np.hypot(x2d - pxy[0], y2d - pxy[1])), 2) if pxy else 0.0
                acc  = round(vel - prev_vel.get(pid, 0.0), 3)
                hdg  = round(float(np.degrees(
                    np.arctan2(y2d - pxy[1], x2d - pxy[0])
                )) % 360, 1) if (pxy and vel > 0) else 0.0
                prev_pos[pid] = (x2d, y2d)
                prev_vel[pid] = vel

                dx_v    = float(x2d - pxy[0]) if pxy else 0.0
                dy_v    = float(y2d - pxy[1]) if pxy else 0.0
                d_bask  = UnifiedPipeline._dist_to_basket(x2d, y2d, map_w, map_h)
                vtb     = UnifiedPipeline._vel_toward_basket(x2d, y2d, dx_v, dy_v, map_w, map_h)
                drv_flg = int(bool(track["has_ball"]) and vtb > _DRIVE_VEL_THRESHOLD)

                dist_ball = round(float(np.hypot(
                    x2d - ball_pos[0], y2d - ball_pos[1]
                )), 1) if ball_pos else ""

                opp_d = [float(np.hypot(x2d - ox, y2d - oy))
                         for uid, (ut, ox, oy) in team_pos.items()
                         if uid != pid and ut != team and ut != "referee"]
                tm_d  = [float(np.hypot(x2d - ox, y2d - oy))
                         for uid, (ut, ox, oy) in team_pos.items()
                         if uid != pid and ut == team]

                ts = spatial.get(team, {})
                opp_teams = [t for t in spatial if t != team and t != "referee" and not t.startswith("_")]
                os_ = spatial.get(opp_teams[0], {}) if opp_teams else {}

                bbox = track["bbox"]  # stored as (y1, x1, y2, x2)
                tracking_rows.append({
                    "frame":              frame_idx,
                    "timestamp":          timestamp_sec,
                    "player_id":          pid,
                    "team":               team,
                    "x_position":         x2d,
                    "y_position":         y2d,
                    "velocity":           vel,
                    "acceleration":       acc,
                    "direction_deg":      hdg,
                    "court_zone":         self._court_zone(x2d, y2d, map_w, map_h),
                    "ball_possession":    int(track["has_ball"]),
                    "distance_to_ball":   dist_ball,
                    "nearest_opponent":   round(min(opp_d), 1) if opp_d else "",
                    "nearest_teammate":   round(min(tm_d), 1)  if tm_d  else "",
                    "event":              event,
                    # Spatial — own team
                    "team_spacing":       round(ts.get("spacing", 0.0), 1),
                    "team_centroid_x":    round(ts.get("cx", 0.0), 1),
                    "team_centroid_y":    round(ts.get("cy", 0.0), 1),
                    "paint_count_own":    ts.get("paint_n", 0),
                    "paint_count_opp":    os_.get("paint_n", 0),
                    # Spatial — ball
                    "possession_side":    spatial.get("_ball_side", ""),
                    "handler_isolation":  round(spatial.get("_isolation", 0.0), 1),
                    # Raw bbox + ball
                    "bbox_x1":            bbox[1] if bbox else "",
                    "bbox_y1":            bbox[0] if bbox else "",
                    "bbox_x2":            bbox[3] if bbox else "",
                    "bbox_y2":            bbox[2] if bbox else "",
                    "ball_x2d":           ball_pos[0] if ball_pos else "",
                    "ball_y2d":           ball_pos[1] if ball_pos else "",
                    "ball_velocity":      ball_vel_2d,
                    "confidence":         track["confidence"],
                    # Basket / drive / break
                    "distance_to_basket": d_bask,
                    "vel_toward_basket":  vtb,
                    "drive_flag":         drv_flg,
                    "fast_break_flag":    fast_break,
                    "possession_id":       possession_id,
                    "possession_duration": possession_dur,
                    # ── Scoreboard context ─────────────────────────────────
                    "scoreboard_game_clock":  sb_state.get("game_clock_sec", ""),
                    "scoreboard_shot_clock":  sb_state.get("shot_clock", ""),
                    "scoreboard_score_diff":  sb_state.get("score_diff", ""),
                    "scoreboard_period":      sb_state.get("period", ""),
                    # ── Possession + play-type context ─────────────────────
                    "possession_type":         poss_ctx.get("possession_type", "half_court"),
                    "play_type":               play_type,
                    "possession_duration_sec": poss_ctx.get("possession_duration_sec", 0.0),
                    "paint_touches":           poss_ctx.get("paint_touches", 0),
                    "off_ball_distance":       poss_ctx.get("off_ball_distance", 0.0),
                    "shot_clock_est":          poss_ctx.get("shot_clock_est", 24.0),
                    # ── Pose estimation fields ─────────────────────────────
                    "ankle_x":            track.get("ankle_x", ""),
                    "ankle_y":            track.get("ankle_y", ""),
                    "contest_arm_angle":  track.get("contest_arm_angle", ""),
                    # ── Ball trajectory features ───────────────────────────
                    "ball_shot_arc_angle":  _ball_traj.get("shot_arc_angle", ""),
                    "ball_peak_height_px":  _ball_traj.get("peak_height_px", ""),
                    "ball_pass_speed_pxpf": _ball_traj.get("pass_speed_pxpf", ""),
                })

            # ── Visualise ─────────────────────────────────────────────────
            if self.show or writer:
                vis_map = cv2.resize(map_txt, (frame.shape[1], frame.shape[1] // 2))
                vis = np.vstack((frame, vis_map))
                if self.show:
                    cv2.imshow("NBA AI — Unified Tracker", vis)
                    if cv2.waitKey(1) & 0xFF == 27:
                        break
                if writer:
                    writer.write(vis)

            frame_idx += 1
            print(f"\r Frame {frame_idx}...", end="", flush=True)

            # Periodic checkpoint — flush rows to CSV so a crash doesn't lose everything
            if frame_idx % _CHECKPOINT_INTERVAL == 0 and tracking_rows:
                self._checkpoint_csv(tracking_rows)
                tracking_rows.clear()

        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()
        print()

        # Finalize last open possession
        if poss_team_prev and possession_buf:
            row = UnifiedPipeline._summarize_possession(
                possession_id, poss_team_prev,
                possession_start, frame_idx - 1,
                possession_buf, fps,
            )
            if row:
                possession_rows.append(row)

        self._export_csv(tracking_rows)
        self._export_ball_csv(ball_rows)
        self._export_stats(player_stats)
        self._export_possessions_csv(possession_rows)
        self._export_shot_log(shot_log_rows)
        self._export_player_stats(tracking_rows, fps)

        metrics = evaluate_tracking(predictions)
        return {
            "predictions":    predictions,
            "stats":          player_stats,
            "id_switches":    metrics.get("id_switches_estimated", 0),
            "stability":      metrics.get("track_stability", 0),
            "total_frames":   frame_idx,
            "jump_resets":      self.ball_det._jump_resets,
            "suspended_frames": suspended_frame_count,
        }

    # ── YOLO integration ──────────────────────────────────────────────────

    def _apply_yolo(self, frame, map_2d, map_txt, results, M, frame_idx):
        """Draw YOLO detections and update ball possession from YOLO bbox."""
        ball_bbox = None
        for det in results:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            label, conf = det["label"], det["confidence"]

            color = {
                "ball":   (0,   165, 255),
                "rim":    (255, 255,   0),
                "shoot":  (0,   255, 255),
                "made":   (0,   255,   0),
                "person": (200, 200, 200),
            }.get(label, (128, 128, 128))

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {conf:.2f}", (x1, max(0, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

            if label == "ball":
                ball_bbox = det["bbox"]

        # Update ball possession using YOLO ball bbox
        if ball_bbox is not None:
            x1, y1, x2, y2 = ball_bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            ball_center = np.array([cx, cy, 1])
            homo = self.M1 @ (M @ ball_center.reshape(3, 1))
            homo = np.int32(homo / homo[-1]).ravel()
            self._last_ball_2d = (int(homo[0]), int(homo[1]))
            cv2.circle(map_2d, (homo[0], homo[1]), 10, (0, 0, 255), 5)

            bbox_iou = (cy - 30, cx - 30, cy + 30, cx + 30)
            scores = []
            for p in self.players:
                if p.team != "referee" and p.previous_bb is not None and frame_idx in p.positions:
                    from src.tracking.player_detection import FeetDetector
                    iou = FeetDetector.bb_intersection_over_union(bbox_iou, p.previous_bb)
                    scores.append((p, iou))
            if scores:
                best_p, best_iou = max(scores, key=lambda s: s[1])
                for p in self.players:
                    p.has_ball = False
                # Only assign possession if ball bbox overlaps player bbox (IoU > 0)
                # or ball center is within 80px of player feet — prevents always-assigned
                # possession that blocks shot detection when ball is in the air.
                if best_iou > 0:
                    best_p.has_ball = True
                else:
                    # Fallback: proximity in pixel space
                    px_scores = []
                    for p in self.players:
                        if p.team != "referee" and p.previous_bb is not None and frame_idx in p.positions:
                            pb = p.previous_bb  # (y1, x1, y2, x2)
                            foot_x = (pb[1] + pb[3]) / 2
                            foot_y = pb[2]
                            dist = float(np.hypot(cx - foot_x, cy - foot_y))
                            px_scores.append((p, dist))
                    if px_scores:
                        nearest_p, nearest_dist = min(px_scores, key=lambda s: s[1])
                        if nearest_dist <= 80:
                            nearest_p.has_ball = True

        return frame, map_2d

    def _update_stats(self, frame, yolo_results, player_stats, frame_idx):
        """Feed YOLO results into StatsTracker for shot counting."""
        try:
            import torch
            # Build results tensor for StatsTracker [x1,y1,x2,y2,conf,label]
            rows = [[*det["bbox"], det["confidence"], det["raw_label"]]
                    for det in yolo_results]
            if not rows:
                return
            results_tensor = torch.tensor(rows, dtype=torch.float32)
            # StatsTracker needs re_id object — pass None-safe stub
            self.stats_tracker.track(frame, results_tensor, _ReIdStub(), {})
        except Exception:
            pass  # StatsTracker is best-effort; don't crash pipeline

    # ── export ────────────────────────────────────────────────────────────

    def _make_writer(self, cap):
        if not self.output_video_path:
            return None
        os.makedirs(os.path.dirname(self.output_video_path), exist_ok=True)
        _, f0 = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if f0 is None:
            return None
        h, w = f0[TOPCUT:].shape[:2]
        return cv2.VideoWriter(
            self.output_video_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            cap.get(cv2.CAP_PROP_FPS) or 25.0,
            (w, h + h // 2),
        )

    @staticmethod
    def _frame_spatial(
        frame_tracks: List[dict],
        ball_pos: Optional[tuple],
        map_w: int,
        map_h: int,
    ) -> dict:
        """
        Compute frame-level spatial metrics grouped by team.

        Returns a dict keyed by team name with sub-dicts:
          spacing, cx, cy, paint_n
        Plus top-level keys _ball_side and _isolation.
        """
        from src.tracking.event_detector import _DRIBBLE_MAX_DIST  # noqa: F401

        by_team: Dict[str, List[tuple]] = {}
        handler_team = None
        handler_pos  = None

        for t in frame_tracks:
            team = t["team"]
            if team == "referee":
                continue
            by_team.setdefault(team, []).append((t["x2d"], t["y2d"]))
            if t.get("has_ball"):
                handler_team = team
                handler_pos  = (t["x2d"], t["y2d"])

        result: dict = {}
        for team, pts in by_team.items():
            arr = np.array(pts, dtype=float)
            cx, cy = arr.mean(axis=0) if len(arr) else (0.0, 0.0)
            spacing = 0.0
            if _SCIPY and len(arr) >= 3:
                try:
                    spacing = float(_ConvexHull(arr).volume)
                except Exception:
                    pass
            paint_n = sum(
                1 for x, y in pts
                if UnifiedPipeline._court_zone(x, y, map_w, map_h) == "paint"
            )
            result[team] = {"spacing": spacing, "cx": cx, "cy": cy, "paint_n": paint_n}

        # Ball side
        if ball_pos:
            result["_ball_side"] = "left" if ball_pos[0] < map_w / 2 else "right"
        else:
            result["_ball_side"] = ""

        # Handler isolation — nearest opponent distance.
        # Default: _ISOLATION_DEFAULT (wide open) so that frames where opponents
        # are not yet tracked don't falsely register as maximum defensive pressure.
        # 0.0 would mean "defender is standing on the handler" — never a safe default.
        isolation = _ISOLATION_DEFAULT
        if handler_pos and handler_team:
            opp_pts = [
                (x, y)
                for team, pts in by_team.items()
                if team != handler_team
                for x, y in pts
            ]
            if opp_pts:
                dists = [float(np.hypot(handler_pos[0] - x, handler_pos[1] - y))
                         for x, y in opp_pts]
                isolation = min(dists)
        result["_isolation"] = isolation

        return result

    @staticmethod
    def _court_zone(x: int, y: int, map_w: int, map_h: int) -> str:
        """Classify 2D court position. Full-court top-down view, both halves."""
        xn = x / max(map_w, 1)
        yn = y / max(map_h, 1)
        # Paint: within ~15% of each baseline, centred vertically
        if (xn < 0.15 or xn > 0.85) and (0.28 < yn < 0.72):
            return "paint"
        # Corner 3: near sideline and outside paint x
        if (yn < 0.14 or yn > 0.86) and (xn < 0.28 or xn > 0.72):
            return "corner_3"
        # 3pt arc: within 28% of each baseline (outside paint y)
        if xn < 0.28 or xn > 0.72:
            return "3pt_arc"
        # Mid-range: between paint and 3pt
        if xn < 0.42 or xn > 0.58:
            return "mid_range"
        return "backcourt"

    @staticmethod
    def _dist_to_basket(x2d: int, y2d: int, map_w: int, map_h: int) -> float:
        """Euclidean distance to the nearest basket in 2D court pixels."""
        bl = (_BASKET_L[0] * map_w, _BASKET_L[1] * map_h)
        br = (_BASKET_R[0] * map_w, _BASKET_R[1] * map_h)
        return round(min(
            float(np.hypot(x2d - bl[0], y2d - bl[1])),
            float(np.hypot(x2d - br[0], y2d - br[1])),
        ), 1)

    @staticmethod
    def _vel_toward_basket(
        x2d: int, y2d: int, dx: float, dy: float, map_w: int, map_h: int
    ) -> float:
        """
        Signed projection of the velocity vector onto the direction toward the
        nearest basket.  Positive = moving toward basket, negative = away.
        """
        bl = (_BASKET_L[0] * map_w, _BASKET_L[1] * map_h)
        br = (_BASKET_R[0] * map_w, _BASKET_R[1] * map_h)
        dl = float(np.hypot(x2d - bl[0], y2d - bl[1]))
        dr = float(np.hypot(x2d - br[0], y2d - br[1]))
        bx, by  = bl if dl <= dr else br
        tb_len  = min(dl, dr)
        if tb_len < 1e-6 or (abs(dx) < 1e-6 and abs(dy) < 1e-6):
            return 0.0
        # Unit vector toward basket
        tbx, tby = (bx - x2d) / tb_len, (by - y2d) / tb_len
        return round(float(dx * tbx + dy * tby), 2)

    @staticmethod
    def _fast_break_flag(
        frame_tracks: List[dict],
        prev_pos: Dict[int, tuple],
        map_w: int,
        map_h: int,
    ) -> int:
        """
        Returns 1 if ≥3 players from the same team are moving toward the same
        basket at ≥ _FAST_BREAK_VEL_MIN px/frame, else 0.
        """
        team_vtb: Dict[str, List[float]] = {}
        for t in frame_tracks:
            if t["team"] == "referee":
                continue
            pxy = prev_pos.get(t["player_id"])
            if not pxy:
                continue
            dx = float(t["x2d"] - pxy[0])
            dy = float(t["y2d"] - pxy[1])
            vtb = UnifiedPipeline._vel_toward_basket(
                t["x2d"], t["y2d"], dx, dy, map_w, map_h
            )
            team_vtb.setdefault(t["team"], []).append(vtb)
        for vals in team_vtb.values():
            if sum(1 for v in vals if v >= _FAST_BREAK_VEL_MIN) >= 3:
                return 1
        return 0

    # ── possession / shot helpers ──────────────────────────────────────────

    @staticmethod
    def _summarize_possession(
        pid: int,
        team: str,
        start_f: int,
        end_f: int,
        buf: List[dict],
        fps: float,
    ) -> dict:
        """Aggregate a possession buffer into one summary row."""
        if not buf:
            return {}
        dur = max(1, end_f - start_f + 1)
        spacings   = [b["spacing"]   for b in buf if b["spacing"]]
        isolations = [b["isolation"] for b in buf if b["isolation"]]
        vtbs       = [b["vtb"]       for b in buf if b["vtb"] != 0]
        shot_frames = [b["frame"]    for b in buf if b["shot_event"]]
        return {
            "possession_id":           pid,
            "team":                    team,
            "start_frame":             start_f,
            "end_frame":               end_f,
            "duration_frames":         dur,
            "duration_sec":            round(dur / fps, 2),
            "avg_spacing":             round(float(np.mean(spacings)),   1) if spacings   else "",
            "avg_defensive_pressure":  round(float(np.mean(isolations)), 1) if isolations else "",
            "avg_vel_toward_basket":   round(float(np.mean(vtbs)),       2) if vtbs       else "",
            "drive_attempts":          sum(1 for b in buf if b.get("drive")),
            "shot_attempted":          int(bool(shot_frames)),
            "shot_frame":              shot_frames[0] if shot_frames else "",
            "fast_break":              int(any(b["fast_break"] for b in buf)),
            "result":                  "",   # filled by nba_enricher
            "outcome_score":           "",   # filled by nba_enricher
        }

    def _export_possessions_csv(self, rows: List[dict]):
        if not rows:
            return
        os.makedirs(_DATA, exist_ok=True)
        path   = os.path.join(_DATA, "possessions.csv")
        fields = [
            "possession_id", "team", "start_frame", "end_frame",
            "duration_frames", "duration_sec",
            "avg_spacing", "avg_defensive_pressure", "avg_vel_toward_basket",
            "drive_attempts", "shot_attempted", "shot_frame",
            "fast_break", "result", "outcome_score",
        ]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Possessions     → {path}  ({len(rows)} rows)")

    def _export_shot_log(self, rows: List[dict]):
        os.makedirs(_DATA, exist_ok=True)
        path   = os.path.join(_DATA, "shot_log.csv")
        fields = [
            "shot_id", "frame", "timestamp", "player_id", "team",
            "x_position", "y_position", "court_zone",
            "defender_distance", "team_spacing",
            "possession_id", "possession_duration", "made",
        ]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Shot log        → {path}  ({len(rows)} shots)")

    def _export_player_stats(self, tracking_rows: List[dict], fps: float):
        """Aggregate per-player stats across the entire clip."""
        if not tracking_rows:
            return
        from collections import defaultdict
        stats: dict = defaultdict(lambda: {
            "player_id": 0, "team": "",
            "frames_tracked": 0, "total_distance": 0.0,
            "max_velocity": 0.0, "vel_sum": 0.0,
            "possession_frames": 0,
            "shots_attempted": 0, "drive_attempts": 0,
            "paint_frames": 0,
            "dist_to_basket_sum": 0.0, "opp_dist_sum": 0.0, "opp_dist_n": 0,
        })
        total_frames = max((r["frame"] for r in tracking_rows), default=0) + 1
        for r in tracking_rows:
            pid = r["player_id"]
            s   = stats[pid]
            s["player_id"] = pid
            s["team"]      = r["team"]
            s["frames_tracked"]    += 1
            vel = float(r.get("velocity", 0) or 0)
            s["total_distance"]    += vel
            s["vel_sum"]           += vel
            s["max_velocity"]       = max(s["max_velocity"], vel)
            s["possession_frames"] += int(r.get("ball_possession", 0) or 0)
            s["shots_attempted"]   += int(r.get("event") == "shot")
            s["drive_attempts"]    += int(r.get("drive_flag", 0) or 0)
            s["paint_frames"]      += int(r.get("court_zone") == "paint")
            db = r.get("distance_to_basket")
            if db not in ("", None):
                s["dist_to_basket_sum"] += float(db)
            od = r.get("nearest_opponent")
            if od not in ("", None):
                s["opp_dist_sum"] += float(od)
                s["opp_dist_n"]   += 1

        rows = []
        for pid, s in sorted(stats.items()):
            ft = max(1, s["frames_tracked"])
            rows.append({
                "player_id":           pid,
                "team":                s["team"],
                "frames_tracked":      ft,
                "tracking_pct":        round(ft / max(1, total_frames), 3),
                "total_distance_px":   round(s["total_distance"], 1),
                "avg_velocity":        round(s["vel_sum"] / ft, 2),
                "max_velocity":        round(s["max_velocity"], 2),
                "possession_frames":   s["possession_frames"],
                "possession_pct":      round(s["possession_frames"] / ft, 3),
                "shots_attempted":     s["shots_attempted"],
                "drive_attempts":      s["drive_attempts"],
                "drive_rate":          round(s["drive_attempts"] / ft, 4),
                "paint_frames":        s["paint_frames"],
                "paint_pct":           round(s["paint_frames"] / ft, 3),
                "avg_dist_to_basket":  round(s["dist_to_basket_sum"] / ft, 1),
                "avg_nearest_opponent": round(s["opp_dist_sum"] / max(1, s["opp_dist_n"]), 1),
            })

        os.makedirs(_DATA, exist_ok=True)
        path = os.path.join(_DATA, "player_clip_stats.csv")
        fields = list(rows[0].keys()) if rows else []
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Player stats    → {path}  ({len(rows)} players)")

    def _pg_write_tracking_rows(self, rows: List[dict]) -> None:
        """
        Write tracking rows to the tracking_frames PostgreSQL table.

        Silently skips if DATABASE_URL is not set.
        Works with or without game_id — when game_id is absent the column is
        NULL (requires migration 001_tracking_nullable_game_id.sql applied first).
        Uses INSERT ... ON CONFLICT DO NOTHING so re-runs are safe.

        Args:
            rows: List of tracking row dicts (same as CSV output).
        """
        import os as _os
        if not _os.environ.get("DATABASE_URL"):
            print("[pg] DATABASE_URL not set — skipping PostgreSQL write")
            return
        if not rows:
            return
        game_id = self.game_id or None   # NULL when --game-id not passed
        if game_id is None:
            print("[pg] No game_id — rows written with NULL game_id "
                  "(pass --game-id to link to a game record)")
        try:
            from src.data.db import get_connection
            conn = get_connection()
            cur  = conn.cursor()
            insert_sql = """
                INSERT INTO tracking_frames (
                    game_id, clip_id, frame_number, timestamp_sec,
                    tracker_player_id, x_pos, y_pos,
                    speed, acceleration, ball_possession,
                    event, confidence, team_spacing,
                    paint_count_own, paint_count_opp, tracker_version
                ) VALUES (
                    %(game_id)s, %(clip_id)s::uuid, %(frame_number)s, %(timestamp_sec)s,
                    %(tracker_player_id)s, %(x_pos)s, %(y_pos)s,
                    %(speed)s, %(acceleration)s, %(ball_possession)s,
                    %(event)s, %(confidence)s, %(team_spacing)s,
                    %(paint_count_own)s, %(paint_count_opp)s, %(tracker_version)s
                )
                ON CONFLICT DO NOTHING
            """
            pg_rows = [
                {
                    "game_id":           game_id,
                    "clip_id":           self.clip_id,
                    "frame_number":      r.get("frame"),
                    "timestamp_sec":     r.get("timestamp"),
                    "tracker_player_id": r.get("player_id"),
                    "x_pos":             r.get("x_position"),
                    "y_pos":             r.get("y_position"),
                    "speed":             r.get("velocity"),
                    "acceleration":      r.get("acceleration"),
                    "ball_possession":   r.get("ball_possession"),
                    "event":             r.get("event"),
                    "confidence":        r.get("confidence"),
                    "team_spacing":      r.get("team_spacing"),
                    "paint_count_own":   r.get("paint_count_own"),
                    "paint_count_opp":   r.get("paint_count_opp"),
                    "tracker_version":   "v1",
                }
                for r in rows
            ]
            import psycopg2.extras as _extras
            _extras.execute_batch(cur, insert_sql, pg_rows, page_size=500)
            conn.commit()
            cur.close()
            conn.close()
            print(f"[pg] tracking_frames ← {len(pg_rows)} rows "
                  f"(game_id={game_id}, clip_id={self.clip_id[:8]}…)")
        except Exception as e:
            print(f"[pg] WARNING: PostgreSQL write failed — {e}")

    def _checkpoint_csv(self, rows: List[dict]) -> None:
        """Flush rows to CSV mid-run so a crash doesn't lose all data."""
        if not rows:
            return
        os.makedirs(_DATA, exist_ok=True)
        path = os.path.join(_DATA, "tracking_data.csv")
        file_exists = os.path.exists(path) and os.path.getsize(path) > 0
        fields = self._tracking_csv_fields()
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            w.writerows(rows)
        print(f"\n[checkpoint] flushed {len(rows)} rows → {path}")

    @staticmethod
    def _tracking_csv_fields() -> List[str]:
        return [
            "frame", "timestamp", "player_id", "team",
            "x_position", "y_position",
            "velocity", "acceleration", "direction_deg",
            "court_zone",
            "ball_possession", "distance_to_ball",
            "nearest_opponent", "nearest_teammate",
            "event",
            "team_spacing", "team_centroid_x", "team_centroid_y",
            "paint_count_own", "paint_count_opp",
            "possession_side", "handler_isolation",
            "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
            "ball_x2d", "ball_y2d", "ball_velocity",
            "distance_to_basket", "vel_toward_basket",
            "drive_flag", "fast_break_flag",
            "possession_id", "possession_duration",
            "confidence",
            "play_type", "paint_touches", "off_ball_distance", "shot_clock_est",
            "scoreboard_shot_clock", "scoreboard_game_clock",
            "scoreboard_period", "scoreboard_score_diff",
            "possession_duration_sec", "possession_type",
            "ankle_x", "ankle_y", "contest_arm_angle",
            "ball_shot_arc_angle", "ball_peak_height_px", "ball_pass_speed_pxpf",
        ]

    def _export_csv(self, rows: List[dict]):
        """Write any remaining rows not yet flushed by _checkpoint_csv."""
        if not rows:
            return
        self._checkpoint_csv(rows)
        self._pg_write_tracking_rows(rows)
        print(f"Tracking data → data/tracking_data.csv  (clip_id={self.clip_id})")

    def _export_ball_csv(self, rows: List[dict]):
        if not rows:
            return
        os.makedirs(_DATA, exist_ok=True)
        path   = os.path.join(_DATA, "ball_tracking.csv")
        fields = ["frame", "timestamp", "ball_x2d", "ball_y2d", "detected"]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Ball tracking  → {path}  ({len(rows)} rows)")

    def _export_stats(self, player_stats):
        if not player_stats:
            return
        os.makedirs(_DATA, exist_ok=True)
        path = os.path.join(_DATA, "stats.json")
        with open(path, "w") as f:
            json.dump(player_stats, f, indent=2)
        print(f"Player stats → {path}")


class _ReIdStub:
    """Stub so StatsTracker doesn't crash when re_id weights aren't loaded."""
    shot_id = -1
    player_dict = {}
    faiss_index = None

    def person_query_lst(self, *a, **kw):
        return [], []

    def hard_voting(self, *a, **kw):
        return {}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA AI — unified tracking pipeline")
    ap.add_argument("--video",    required=True, help="Path to input video (.mp4)")
    ap.add_argument("--game-id",  default=None,  help="NBA Stats game ID for enrichment")
    ap.add_argument("--output",   default=None,  help="Output CSV path (default: data/tracking_data.csv)")
    ap.add_argument("--frames",   type=int, default=None, help="Max frames to process")
    ap.add_argument("--start-frame", type=int, default=0, help="Frame to start from")
    ap.add_argument("--no-show",  action="store_true", help="Disable live preview window")
    ap.add_argument("--yolo",     default=None, help="Path to YOLO-NAS weights (.pth)")
    args = ap.parse_args()

    pipeline = UnifiedPipeline(
        video_path=args.video,
        yolo_weight_path=args.yolo,
        max_frames=args.frames,
        start_frame=args.start_frame,
        show=not args.no_show,
        game_id=args.game_id,
    )
    pipeline.run()
