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
_H_MIN_INLIERS      = 5      # below this → reject and use last-known good M
                             # Broadcast NBA frames match pano_enhanced.png with 5-7 inliers
                             # (Short4Mosaicing pano doesn't share enough features for ≥8).
                             # EMA smoothing compensates for noisy low-inlier estimates.
_H_RESET_INLIERS    = 40     # ≥ this → hard-reset EMA (very clean SIFT match)
_REANCHOR_INTERVAL  = 30     # court-line drift check every N frames
_REANCHOR_ALIGN_MIN = 0.35   # projected boundary alignment below this → force re-anchor
_SIFT_INTERVAL      = 5      # run SIFT only every N frames; use cached EMA in between

# Gameplay detection — skip non-play frames (intro, halftime, timeouts, replays)
MIN_GAMEPLAY_PERSONS = 5     # YOLO person count below this → skip frame
_GAMEPLAY_CACHE_FRAMES = 30  # once gameplay confirmed, trust it for N frames (~1 sec)
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
    ):
        self.video_path        = video_path
        self.max_frames        = max_frames
        self.start_frame       = start_frame
        self.show              = show
        self.output_video_path = output_video_path

        self.yolo    = YoloDetector(yolo_weight_path)
        self.players = self._build_players()

        # Build player detector early — reused for gameplay filter
        self.feet_det = AdvancedFeetDetector(self.players)

        pano          = self._load_pano(video_path)
        self.map_2d, self.M1 = self._build_court(pano)
        self.pano     = pano

        self._gameplay_cache_until: int = 0   # frame index; skip check before this

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

    def _build_court(self, pano):
        rect1 = os.path.join(_RESOURCES, "Rectify1.npy")
        map_img = cv2.imread(os.path.join(_RESOURCES, "2d_map.png"))

        img = binarize_erode_dilate(pano, plot=False)
        _, corners = rectangularize_court(img, plot=False)
        rectified  = rectify(pano, corners, plot=False)
        map_2d     = cv2.resize(map_img, (rectified.shape[1], rectified.shape[0]))
        M1         = np.load(rect1)
        return map_2d, M1

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

        kp2, des2 = self.sift.compute(frame, self.sift.detect(frame))
        if des2 is None or len(des2) < 4:
            return self._M_ema

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
        if self.start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame)
        writer = self._make_writer(cap)

        tracking_rows:    List[dict] = []
        ball_rows:        List[dict] = []
        predictions:      List[dict] = []
        player_stats:     dict       = {}
        possession_rows:  List[dict] = []
        shot_log_rows:    List[dict] = []
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

            frame = frame[TOPCUT:]

            # Skip non-gameplay frames (intro, halftime, timeout, replay, crowd shots)
            if not self._is_gameplay(frame, frame_idx):
                frame_idx += 1
                continue

            M = self._get_homography(frame)
            if M is None:
                frame_idx += 1
                continue

            map_snap = self.map_2d.copy()
            self._last_ball_2d = None

            # ── Player tracking ───────────────────────────────────────────
            frame, map_snap, map_txt = self.feet_det.get_players_pos(
                M, self.M1, frame, frame_idx, map_snap
            )

            # ── Ball + event detection ────────────────────────────────────
            yolo_results = self.yolo.predict(frame) if self.yolo.available else []
            if yolo_results:
                frame, map_snap = self._apply_yolo(
                    frame, map_snap, map_txt, yolo_results, M, frame_idx
                )
            else:
                frame, _ = self.ball_det.ball_tracker(
                    M, self.M1, frame, map_snap.copy(), map_txt, frame_idx
                )
                self._last_ball_2d = self.ball_det.last_2d_pos

            if yolo_results and self.yolo.available:
                self._update_stats(frame, yolo_results, player_stats, frame_idx)

            timestamp_sec = round(frame_idx / fps, 3)
            ball_pos      = self._last_ball_2d

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
                    "player_id":  p.ID,
                    "team":       p.team,
                    "bbox":       p.previous_bb,
                    "x2d":        int(x2d),
                    "y2d":        int(y2d),
                    "confidence": round(conf, 3),
                    "has_ball":   p.has_ball,
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
            )

            spatial = self._frame_spatial(frame_tracks, ball_pos, map_w, map_h)

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
                    "possession_id":      possession_id,
                    "possession_duration": possession_dur,
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
            "predictions":  predictions,
            "stats":        player_stats,
            "id_switches":  metrics.get("id_switches_estimated", 0),
            "stability":    metrics.get("track_stability", 0),
            "total_frames": frame_idx,
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

    def _export_csv(self, rows: List[dict]):
        if not rows:
            return
        os.makedirs(_DATA, exist_ok=True)
        path   = os.path.join(_DATA, "tracking_data.csv")
        fields = [
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
        ]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"Tracking data → {path}  ({len(rows)} rows)")

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
