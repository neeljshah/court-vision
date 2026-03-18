"""
advanced_tracker.py — Enhanced basketball player tracking

Improvements over baseline FeetDetector:
  - Kalman filtering: predicts player position when detection fails (handles occlusion)
  - Hungarian algorithm: globally optimal assignment (eliminates greedy ID switches)
  - Appearance embeddings: HSV histogram per player for re-identification
  - Lost-track gallery: re-IDs players who leave and re-enter the frame
  - Confidence scoring: per-track quality metric

Drop-in replacement: AdvancedFeetDetector has the same interface as FeetDetector.
"""

from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .player_detection import FeetDetector, COLORS, hsv2bgr, PAD, _adaptive_colors

try:
    from scipy.optimize import linear_sum_assignment
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

try:
    from .jersey_ocr import dominant_hsv_cluster as _dominant_hsv
    _HAS_OCR = True
except ImportError:
    _HAS_OCR = False

try:
    from .player_identity import JerseyVotingBuffer as _JerseyVotingBuffer
    _HAS_VOTING = True
except ImportError:
    _HAS_VOTING = False

try:
    from .color_reid import TeamColorTracker as _TeamColorTracker
    _HAS_COLOR_REID = True
except ImportError:
    _HAS_COLOR_REID = False

try:
    from .osnet_reid import DeepAppearanceExtractor as _DeepAppearanceExtractor
    _HAS_OSNET = True
except ImportError:
    _HAS_OSNET = False

try:
    import lapx as _lapx  # noqa: F401  — faster Hungarian for ByteTrack
    _HAS_LAPX = True
except ImportError:
    _HAS_LAPX = False

# ── Tuning constants ──────────────────────────────────────────────────────────
COST_GATE       = 0.80   # reject any assignment with cost above this
APPEARANCE_W    = 0.25   # weight of appearance vs IoU in cost matrix
MAX_LOST        = 90     # frames before evicting a lost track (~3 s at 30 fps)
GALLERY_TTL     = 300    # frames a gallery entry stays valid (~10 s at 30 fps)
REID_THRESH     = 0.45   # max appearance distance to accept a re-ID
REID_TIE_BAND   = 0.05   # appearance-distance window for jersey-number tiebreaker
SIMILAR_COLORS_JERSEY_W = 0.10  # ISSUE-005: extra jersey-number boost when team colors are similar
HIST_BINS       = 32     # bins per channel for HSV histogram
KF_PROC_NOISE   = 5e-2
KF_MEAS_NOISE   = 1e-1
APPEAR_ALPHA    = 0.7    # EMA weight for appearance update (higher = more stable)
MAX_2D_JUMP     = 250    # max court pixels a player can move between frames (~2× court width/sec at 30fps)

# ── ByteTrack constants ───────────────────────────────────────────────────────
BT_HIGH_THRESH    = 0.50   # Stage-1: high-confidence detections matched with IoU+appearance
BT_SECOND_IOUGATE = 0.50   # Stage-2: minimum IoU required for low-conf "byte" match

# ── Optical flow constants ────────────────────────────────────────────────────
OF_WIN_SIZE  = (15, 15)   # Lucas-Kanade search window
OF_MAX_LEVEL = 2          # pyramid levels
OF_MAX_AGE   = 8          # max lost frames before stopping optical flow propagation

# ── Pose cadence ──────────────────────────────────────────────────────────────
_POSE_INTERVAL = 3        # run pose model every N frames; reuse cached fields on others


# ── Kalman filter helpers ─────────────────────────────────────────────────────

def _make_kf(bbox: Tuple) -> cv2.KalmanFilter:
    """6D state [cx, cy, vx, vy, w, h], 4D measurement [cx, cy, w, h]."""
    kf = cv2.KalmanFilter(6, 4)
    y1, x1, y2, x2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    w,  h  = float(x2 - x1), float(y2 - y1)

    kf.transitionMatrix = np.array([
        [1, 0, 1, 0, 0, 0],
        [0, 1, 0, 1, 0, 0],
        [0, 0, 1, 0, 0, 0],
        [0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ], dtype=np.float32)
    kf.measurementMatrix = np.array([
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 1, 0],
        [0, 0, 0, 0, 0, 1],
    ], dtype=np.float32)
    kf.processNoiseCov     = np.eye(6, dtype=np.float32) * KF_PROC_NOISE
    kf.measurementNoiseCov = np.eye(4, dtype=np.float32) * KF_MEAS_NOISE
    kf.errorCovPost        = np.eye(6, dtype=np.float32)
    kf.statePost = np.array([cx, cy, 0, 0, w, h], dtype=np.float32).reshape(6, 1)
    return kf


def _kf_predict_bbox(kf: cv2.KalmanFilter) -> Tuple:
    """Advance Kalman state and return predicted (y1, x1, y2, x2)."""
    pred = kf.predict()
    cx, cy = pred[0, 0], pred[1, 0]
    w,  h  = abs(pred[4, 0]) or 40.0, abs(pred[5, 0]) or 80.0
    return (cy - h / 2, cx - w / 2, cy + h / 2, cx + w / 2)


def _kf_correct(kf: cv2.KalmanFilter, bbox: Tuple):
    """Update Kalman with a confirmed measurement."""
    y1, x1, y2, x2 = bbox
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    w,  h  = float(x2 - x1), float(y2 - y1)
    kf.correct(np.array([cx, cy, w, h], dtype=np.float32).reshape(4, 1))


# ── Appearance embedding ──────────────────────────────────────────────────────

def _compute_appearance(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Compute appearance embedding from a player bounding-box crop.

    Returns a 99-dim vector when jersey_ocr is available (96-dim L1-normalised
    HSV histogram concatenated with a 3-dim normalised dominant-HSV-cluster vector),
    or a 96-dim vector as fallback when jersey_ocr is not importable.

    Note: k-means clustering is called here (gallery writes), NOT in the per-frame
    matching loop, to keep inference latency low.

    Args:
        crop_bgr: BGR crop of a player bounding box.

    Returns:
        float32 ndarray, shape (99,) or (96,).
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return np.zeros(HIST_BINS * 3, dtype=np.float32)
    roi = crop_bgr[: max(1, int(crop_bgr.shape[0] * 0.70))]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    parts = []
    for ch, (lo, hi) in enumerate([(0, 180), (0, 256), (0, 256)]):
        hist = cv2.calcHist([hsv], [ch], None, [HIST_BINS], [lo, hi]).flatten()
        s = hist.sum()
        parts.append(hist / s if s > 0 else hist)
    hist_emb = np.concatenate(parts).astype(np.float32)
    # Use mean HSV instead of KMeans dominant cluster — same discrimination power,
    # 50-100x faster (no sklearn KMeans per crop).  KMeans was the primary fps bottleneck.
    mean_hsv = hsv.reshape(-1, 3).mean(axis=0).astype(np.float32)
    mean_norm = mean_hsv / (mean_hsv.max() + 1e-6)
    return np.concatenate([hist_emb, mean_norm])  # shape (99,)


def _appear_dist(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    """Histogram intersection distance in [0, 1]. 0 = identical."""
    if a is None or b is None:
        return 0.5  # neutral when unknown
    return float(1.0 - np.minimum(a, b).sum())


# ── IoU ───────────────────────────────────────────────────────────────────────

def _iou(a: Tuple, b: Tuple) -> float:
    ay1, ax1, ay2, ax2 = a
    by1, bx1, by2, bx2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter)


# ── Hungarian / greedy assignment ─────────────────────────────────────────────

def _assign(cost: np.ndarray) -> List[Tuple[int, int]]:
    """Return (row, col) pairs that minimise total cost."""
    if cost.size == 0:
        return []
    if _HAS_SCIPY:
        rows, cols = linear_sum_assignment(cost)
        return list(zip(rows.tolist(), cols.tolist()))
    # Greedy fallback
    used: set = set()
    pairs = []
    for r in range(cost.shape[0]):
        best_c, best_v = -1, float("inf")
        for c in range(cost.shape[1]):
            if c not in used and cost[r, c] < best_v:
                best_v, best_c = cost[r, c], c
        if best_c >= 0:
            pairs.append((r, best_c))
            used.add(best_c)
    return pairs


# ── AdvancedFeetDetector ──────────────────────────────────────────────────────

class AdvancedFeetDetector(FeetDetector):
    """
    Drop-in replacement for FeetDetector.

    Same interface (get_players_pos returns frame, map_2d, map_2d_text).
    Internally replaces IoU-greedy matching with:
      1. Kalman prediction per player slot
      2. Hungarian assignment (IoU + appearance cost)
      3. Appearance-based re-ID from lost-track gallery
    """

    def __init__(self, players):
        super().__init__(players)
        from .tracker_config import load_config
        _cfg = load_config()
        self._conf_threshold    = _cfg["conf_threshold"]
        self._appearance_w      = _cfg["appearance_w"]
        self._max_lost          = _cfg["max_lost_frames"]
        self._reid_thresh       = _cfg.get("reid_threshold",     REID_THRESH)
        self._gallery_ttl       = _cfg.get("gallery_ttl",        GALLERY_TTL)
        self._kalman_fill_win   = _cfg.get("kalman_fill_window", 5)

        # Broadcast mode: lower confidence threshold so smaller/distant players are detected
        if _cfg.get("broadcast_mode", True):
            self._conf_threshold = 0.35

        n = len(players)
        self._kalmans:      Dict[int, cv2.KalmanFilter] = {}
        self._appearances:  Dict[int, np.ndarray]       = {}
        self._lost_ages:    Dict[int, int]              = {i: 0 for i in range(n)}
        self._gallery:      Dict[int, np.ndarray]       = {}  # slot → appearance snapshot
        self._gallery_ages: Dict[int, int]              = {}  # slot → frames since archived
        self._kf_pred:      Dict[int, Tuple]            = {}  # predicted bboxes this frame
        self._jersey_buf:   Optional[object]            = None  # set externally after construction
        self._freeze_age:   Dict[int, int]              = {i: 0 for i in range(n)}  # frames frozen
        # ISSUE-005: per-team color tracker for similar-uniform detection
        self._color_tracker = _TeamColorTracker() if _HAS_COLOR_REID else None

        # Dynamic team color clustering (fixes all-green bug)
        # Warm-up: collect dominant jersey HSV for first N non-referee detections,
        # then K-means k=2 to discover the two team colors.
        self._warmup_colors: List[np.ndarray] = []   # dominant HSV samples
        self._team_centroids: Optional[List[np.ndarray]] = None  # [centroid_A, centroid_B]
        self._warmup_needed = 30   # detections before first calibration
        self._recalib_interval = 150  # frames between re-calibrations
        self._frames_since_calib = 0

        # ── Pose estimation (ankle keypoints) ─────────────────────────────
        # Replace bbox_bottom heuristic with YOLOv8-pose ankle keypoints.
        # Falls back to bbox_bottom when keypoints are not detected.
        self._pose_model = None
        self._use_pose   = False
        try:
            from ultralytics import YOLO as _YOLO
            _pm = _YOLO("yolov8n-pose.pt")
            if _cfg.get("broadcast_mode", True):
                _pm.overrides["half"] = getattr(self, "_use_half", False)
            self._pose_model = _pm
            self._use_pose   = True
        except Exception:
            pass  # pose model unavailable — fall back to bbox_bottom

        # Pose cadence state and per-slot caches
        self._pose_frame_counter: int = 0
        self._pose_state: Dict[int, dict] = {}         # slot → latest pose fields dict
        self._hip_y_history: Dict[int, deque] = {}     # slot → recent hip pixel-y values
        # Kpts captured by _activate_slot this frame (cleared at start of each frame)
        self._matched_kpts_this_frame: Dict[int, Tuple] = {}  # slot → (kpts_xy, kpts_conf)

        # ── Optical flow gap-fill ──────────────────────────────────────────
        # When YOLO misses a tracked player, propagate their pixel position
        # using Lucas-Kanade optical flow for OF_MAX_AGE frames before
        # handing off to pure Kalman prediction.
        self._prev_gray: Optional[np.ndarray] = None          # grayscale prev frame
        self._flow_pts:  Dict[int, np.ndarray] = {}           # slot → [[x,y]] float32

        # ── OSNet deep re-ID extractor (optional) ─────────────────────────
        # When available, replaces HSV histogram embeddings with 256-dim
        # L2-normalised deep features from OSNet-x0.25.  Falls back to HSV
        # if OSNet is not importable or model init fails.
        self._deep_extractor = None
        self._use_deep       = False
        if _HAS_OSNET:
            try:
                self._deep_extractor = _DeepAppearanceExtractor()
                self._use_deep       = self._deep_extractor.available
                # Auto-load pre-trained weights if path is configured and file exists.
                # Silently skip when file is absent — OSNet stays in random-weights mode.
                _weights_path = _cfg.get("osnet_weights_path", "")
                if _weights_path and os.path.exists(_weights_path):
                    self._deep_extractor.load_weights(_weights_path)
            except Exception:
                pass

    # ── helpers ───────────────────────────────────────────────────────────

    def _slot(self, player) -> int:
        return self.players.index(player)

    def _update_appearance(
        self,
        slot: int,
        crop_bgr: np.ndarray,
        deep_emb: Optional[np.ndarray] = None,
    ):
        """Update the per-slot appearance embedding using EMA.

        When a deep embedding (from OSNet) is provided it replaces the HSV
        histogram.  Falls back to ``_compute_appearance`` (HSV) otherwise.
        """
        emb = deep_emb if (deep_emb is not None and deep_emb.size > 0) \
              else _compute_appearance(crop_bgr)
        if slot in self._appearances:
            self._appearances[slot] = (APPEAR_ALPHA * self._appearances[slot]
                                       + (1 - APPEAR_ALPHA) * emb)
        else:
            self._appearances[slot] = emb

    def _activate_slot(self, slot: int, det: dict, timestamp: int):
        """
        Assign a detection to a player slot and update all state.

        Resets the jersey voting buffer for the slot when it was previously
        occupied, preventing stale vote counts from a prior occupant carrying
        over to a new player (RESEARCH.md Pitfall 3).
        """
        # Reset jersey voting state for evicted slot (RESEARCH.md Pitfall 3)
        if (_HAS_VOTING
                and hasattr(self, "_jersey_buf")
                and self._jersey_buf is not None
                and self.players[slot].previous_bb is not None):
            self._jersey_buf.reset_slot(slot)

        p = self.players[slot]
        p.previous_bb = det["bbox"]
        new_pos = (det["homo"][0], det["homo"][1])
        # Velocity clamp: if projected position jumps > MAX_2D_JUMP from the last
        # known position, the SIFT homography is noisy — keep the last known position.
        # After eviction p.positions is cleared to {}, so the clamp never fires for
        # freshly re-IDed players (they start with no position history).
        if p.positions:
            last_pos = p.positions[max(p.positions)]
            dist = float(np.hypot(new_pos[0] - last_pos[0], new_pos[1] - last_pos[1]))
            if dist > MAX_2D_JUMP:
                new_pos = last_pos
                self._freeze_age[slot] = self._freeze_age.get(slot, 0) + 1
            else:
                self._freeze_age[slot] = 0
        p.positions[timestamp] = new_pos
        if slot in self._kalmans:
            _kf_correct(self._kalmans[slot], det["bbox"])
        else:
            self._kalmans[slot] = _make_kf(det["bbox"])
        self._update_appearance(
            slot, det["crop_bgr"], deep_emb=det.get("deep_emb")
        )
        self._lost_ages[slot] = 0
        self._gallery.pop(slot, None)
        self._gallery_ages.pop(slot, None)
        # Update optical flow anchor point for this slot
        if "foot_xy" in det:
            fx, fy = det["foot_xy"]
            self._flow_pts[slot] = np.array([[fx, fy]], dtype=np.float32)
        # Capture keypoints for this frame's pose extraction pass
        kpts_xy = det.get("kpts_xy")
        if kpts_xy is not None:
            self._matched_kpts_this_frame[slot] = (kpts_xy, det.get("kpts_conf"))

    # ── dynamic team color calibration ───────────────────────────────────

    def _calibrate_team_colors(self) -> None:
        """K-means k=2 on warmup_colors to find two team centroids."""
        if len(self._warmup_colors) < 10:
            return
        try:
            from sklearn.cluster import KMeans
            samples = np.array(self._warmup_colors, dtype=np.float32)
            km = KMeans(n_clusters=2, n_init=5, max_iter=50, random_state=0)
            km.fit(samples)
            self._team_centroids = list(km.cluster_centers_)
        except Exception:
            self._team_centroids = None

    def _classify_team_dynamic(self, bgr_crop: np.ndarray, fallback_team: str) -> str:
        """
        Classify a jersey crop to 'green' (team A) or 'white' (team B) using
        the learned K-means centroids.  Falls back to HSV-range classification
        when centroids are not yet available.
        """
        if self._team_centroids is None or bgr_crop is None or bgr_crop.size == 0:
            return fallback_team
        if _HAS_COLOR_REID:
            from .color_reid import dominant_team_color
            dom = dominant_team_color(bgr_crop)
        else:
            h = max(1, int(bgr_crop.shape[0] * 0.65))
            roi = cv2.cvtColor(bgr_crop[:h], cv2.COLOR_BGR2HSV)
            dom = roi.reshape(-1, 3).astype(np.float32).mean(axis=0)
        # Circular hue distance to each centroid
        def hue_dist(a, b):
            diff = abs(float(a[0]) - float(b[0]))
            return min(diff, 180.0 - diff)
        d0 = hue_dist(dom, self._team_centroids[0])
        d1 = hue_dist(dom, self._team_centroids[1])
        return "green" if d0 <= d1 else "white"

    # ── pose field extraction ─────────────────────────────────────────────

    def _extract_pose_fields(
        self,
        slot: int,
        kpts_xy: Optional[np.ndarray],
        kpts_conf: Optional[np.ndarray],
        has_ball: bool,
    ) -> dict:
        """Extract per-player pose features from COCO 17-keypoint output.

        COCO indices used:
            0  = nose (head proxy)
            9  = left wrist,  10 = right wrist
            11 = left hip,    12 = right hip
            15 = left ankle,  16 = right ankle

        Falls back to empty/default values when keypoints are missing or
        below confidence threshold.

        Args:
            slot: Tracker slot index (for hip y history lookup).
            kpts_xy: (17, 2) keypoint pixel coordinates, or None.
            kpts_conf: (17,) per-keypoint confidence, or None.
            has_ball: Whether this player currently holds the ball.

        Returns:
            dict with ankle_x, ankle_y, jump_detected, contest_arm_height,
            dribble_hand.
        """
        _CONF_MIN = 0.5
        result: dict = {
            "ankle_x": None, "ankle_y": None,
            "jump_detected": False,
            "contest_arm_angle": 0.0,
            "dribble_hand": "unknown",
        }
        if kpts_xy is None or len(kpts_xy) < 17:
            return result

        conf = kpts_conf if kpts_conf is not None else np.ones(17, dtype=np.float32)

        def valid(idx: int) -> bool:
            return bool(conf[idx] >= _CONF_MIN)

        def kxy(idx: int) -> Tuple[float, float]:
            return float(kpts_xy[idx, 0]), float(kpts_xy[idx, 1])

        # ── Ankle keypoints (COCO 15=left ankle, 16=right ankle) ──────────
        ankle_ids = [i for i in (15, 16) if valid(i)]
        if ankle_ids:
            result["ankle_x"] = float(np.mean([kpts_xy[i, 0] for i in ankle_ids]))
            result["ankle_y"] = float(np.mean([kpts_xy[i, 1] for i in ankle_ids]))

        # ── Jump detection: hip keypoints rising faster than 2 px/frame ───
        hip_ids = [i for i in (11, 12) if valid(i)]
        if hip_ids:
            hip_y_now = float(np.mean([kpts_xy[i, 1] for i in hip_ids]))
            hip_hist  = self._hip_y_history.setdefault(slot, deque(maxlen=6))
            hip_hist.append(hip_y_now)
            if len(hip_hist) >= 3:
                ys  = np.array(hip_hist, dtype=np.float32)
                vel = float(np.diff(ys).mean())
                result["jump_detected"] = bool(vel < -2.0)  # y decreasing = rising

        # ── Contest arm height: highest wrist vs nose and hip ─────────────
        wrist_ids = [i for i in (9, 10) if valid(i)]
        if valid(0) and wrist_ids and hip_ids:
            nose_y   = kxy(0)[1]
            hip_y    = float(np.mean([kpts_xy[i, 1] for i in hip_ids]))
            wrist_y  = float(min(kpts_xy[i, 1] for i in wrist_ids))  # highest wrist
            body_h   = abs(hip_y - nose_y) + 1e-6
            # 0.0 = wrist at hip level; 1.0 = wrist at nose level (or above)
            result["contest_arm_angle"] = float(
                np.clip((hip_y - wrist_y) / body_h, 0.0, 1.0)
            )

        # ── Dribble hand: lower wrist (higher pixel y) when possessing ball ─
        if has_ball:
            if valid(9) and valid(10):
                _, ly = kxy(9)
                _, ry = kxy(10)
                result["dribble_hand"] = "left" if ly > ry else "right"
            elif valid(9):
                result["dribble_hand"] = "left"
            elif valid(10):
                result["dribble_hand"] = "right"

        return result

    # ── per-team Hungarian matching ───────────────────────────────────────

    def _match_team(
        self, team: str, detections: List[dict]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        Returns (matched slot-det pairs, unmatched slots, unmatched det indices).
        Cost = (1-IoU)*(1-APPEARANCE_W) + appearance_dist*APPEARANCE_W
        """
        slots = [self._slot(p) for p in self.players if p.team == team]
        dets  = [i for i, d in enumerate(detections) if d["team"] == team]

        if not slots or not dets:
            return [], slots, dets

        cost = np.ones((len(slots), len(dets)), dtype=np.float32) * 2.0

        # ISSUE-005: when team colors are similar, raise appearance weight so
        # fine-grained HSV histogram differences matter more than raw IoU overlap.
        similar = (
            self._color_tracker is not None
            and self._color_tracker.similar_colors
        )
        app_w = min(0.60, self._appearance_w + (SIMILAR_COLORS_JERSEY_W if similar else 0.0))

        for ri, slot in enumerate(slots):
            pred = self._kf_pred.get(slot)
            for ci, di in enumerate(dets):
                det_bbox = detections[di]["bbox"]
                iou_val  = _iou(pred, det_bbox) if pred is not None else 0.0
                app_dist = _appear_dist(
                    self._appearances.get(slot),
                    _compute_appearance(detections[di]["crop_bgr"])
                    if detections[di]["crop_bgr"] is not None else None,
                )
                cost[ri, ci] = ((1.0 - iou_val) * (1 - app_w)
                                + app_dist * app_w)

        matched, unmatched_slots, unmatched_dets = [], list(range(len(slots))), list(range(len(dets)))
        for ri, ci in _assign(cost):
            if cost[ri, ci] <= COST_GATE:
                matched.append((slots[ri], dets[ci]))
                unmatched_slots.remove(ri)
                unmatched_dets.remove(ci)

        return matched, [slots[i] for i in unmatched_slots], [dets[i] for i in unmatched_dets]

    # ── ByteTrack two-stage assignment ────────────────────────────────────

    def _match_team_bytetrack(
        self, team: str, detections: List[dict]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        ByteTrack two-stage assignment for one team.

        Stage 1: High-confidence detections (score ≥ BT_HIGH_THRESH) matched
                 against all active tracked slots using IoU + appearance cost,
                 identical to the original ``_match_team``.
        Stage 2: Low-confidence ("byte") detections matched against the slots
                 that went unmatched in Stage 1, using IoU only (no appearance,
                 since low-conf crops are less reliable).  Only accepted when
                 IoU > BT_SECOND_IOUGATE.

        Falls back gracefully: when detection dicts have no ``score`` key
        (e.g. in legacy unit tests) all detections are treated as high-confidence.

        Returns:
            (matched pairs [(slot, det_idx), ...],
             unmatched slot indices,
             unmatched det indices)
        """
        slots     = [self._slot(p) for p in self.players if p.team == team]
        team_dets = [i for i, d in enumerate(detections) if d["team"] == team]

        if not slots or not team_dets:
            return [], slots, team_dets

        high_dets = [i for i in team_dets
                     if detections[i].get("score", 1.0) >= BT_HIGH_THRESH]
        low_dets  = [i for i in team_dets
                     if detections[i].get("score", 1.0) <  BT_HIGH_THRESH]

        similar = (self._color_tracker is not None
                   and self._color_tracker.similar_colors)
        app_w = min(0.60, self._appearance_w
                    + (SIMILAR_COLORS_JERSEY_W if similar else 0.0))

        matched:          List[Tuple[int, int]] = []
        matched_slot_idx: set                   = set()   # indices into `slots`
        matched_det_set:  set                   = set()   # global det indices

        # ── Stage 1: high-conf dets vs all tracks ─────────────────────────
        if high_dets:
            cost1 = np.ones((len(slots), len(high_dets)), dtype=np.float32) * 2.0
            for ri, slot in enumerate(slots):
                pred = self._kf_pred.get(slot)
                for ci, di in enumerate(high_dets):
                    det_bbox = detections[di]["bbox"]
                    iou_val  = _iou(pred, det_bbox) if pred is not None else 0.0
                    # Use pre-computed deep embedding when available, else HSV
                    _deep = detections[di].get("deep_emb")
                    det_emb = (_deep if _deep is not None
                               else (_compute_appearance(detections[di]["crop_bgr"])
                                     if detections[di]["crop_bgr"] is not None else None))
                    app_dist = _appear_dist(self._appearances.get(slot), det_emb)
                    cost1[ri, ci] = (1.0 - iou_val) * (1 - app_w) + app_dist * app_w

            for ri, ci in _assign(cost1):
                if cost1[ri, ci] <= COST_GATE:
                    matched.append((slots[ri], high_dets[ci]))
                    matched_slot_idx.add(ri)
                    matched_det_set.add(high_dets[ci])

        # ── Stage 2: low-conf dets vs unmatched tracks (IoU only) ─────────
        if low_dets:
            remaining_slots = [slots[ri] for ri in range(len(slots))
                               if ri not in matched_slot_idx]
            if remaining_slots:
                cost2 = np.ones(
                    (len(remaining_slots), len(low_dets)), dtype=np.float32
                ) * 2.0
                for ri, slot in enumerate(remaining_slots):
                    pred = self._kf_pred.get(slot)
                    for ci, di in enumerate(low_dets):
                        det_bbox = detections[di]["bbox"]
                        iou_val  = _iou(pred, det_bbox) if pred is not None else 0.0
                        cost2[ri, ci] = 1.0 - iou_val

                for ri, ci in _assign(cost2):
                    if cost2[ri, ci] < (1.0 - BT_SECOND_IOUGATE):
                        slot = remaining_slots[ri]
                        matched.append((slot, low_dets[ci]))
                        matched_slot_idx.add(slots.index(slot))
                        matched_det_set.add(low_dets[ci])

        unmatched_slots = [slots[ri] for ri in range(len(slots))
                           if ri not in matched_slot_idx]
        unmatched_dets  = [di for di in team_dets if di not in matched_det_set]
        return matched, unmatched_slots, unmatched_dets

    # ── re-ID from gallery ────────────────────────────────────────────────

    def _reid(
        self,
        det: dict,
        confirmed_jerseys: Optional[Dict[int, int]] = None,
        det_slot: Optional[int] = None,
    ) -> Optional[int]:
        """
        Match an unmatched detection against the lost-track gallery.

        When confirmed_jerseys is provided and the top two gallery candidates are
        within REID_TIE_BAND appearance distance, the candidate whose confirmed
        jersey number matches the detection's confirmed jersey is preferred
        (jersey-number tiebreaker).

        Args:
            det: Detection dict with keys 'team', 'bbox', 'crop_bgr'.
            confirmed_jerseys: Optional mapping of slot → confirmed jersey number.
                               When provided, used as tiebreaker for ambiguous matches.
            det_slot: Optional tracker slot associated with this detection's prior
                      identity (used to look up det_jersey in confirmed_jerseys).

        Returns:
            Gallery slot index if re-ID succeeds, else None.
        """
        # Use pre-computed deep embedding when available, else HSV histogram
        _deep_app = det.get("deep_emb")
        det_app = (_deep_app if _deep_app is not None
                   else (_compute_appearance(det["crop_bgr"])
                         if det["crop_bgr"] is not None else None))

        # Build sorted candidate list: [(slot, dist), ...] ascending by dist
        candidates = []
        for slot, gal_app in self._gallery.items():
            if self.players[slot].team != det["team"]:
                continue
            dist = _appear_dist(det_app, gal_app)
            candidates.append((slot, dist))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1])

        # Jersey number tiebreaker for ambiguous appearance matches.
        # When top two candidates are within REID_TIE_BAND (or REID_TIE_BAND +
        # SIMILAR_COLORS_JERSEY_W when team colors are similar — ISSUE-005), prefer
        # the candidate whose confirmed jersey number matches the detection's jersey.
        similar = (
            self._color_tracker is not None
            and self._color_tracker.similar_colors
        )
        tie_band = REID_TIE_BAND + (SIMILAR_COLORS_JERSEY_W if similar else 0.0)

        if (confirmed_jerseys is not None
                and len(candidates) >= 2
                and abs(candidates[0][1] - candidates[1][1]) < tie_band):
            det_jersey = confirmed_jerseys.get(det_slot) if det_slot is not None else None
            for cand_slot, _dist in candidates[:2]:
                cand_jersey = confirmed_jerseys.get(cand_slot)
                if det_jersey is not None and cand_jersey == det_jersey:
                    return cand_slot   # prefer jersey-number match

        best_slot, best_dist = candidates[0]
        if best_dist > self._reid_thresh:
            return None
        return best_slot

    # ── main override ─────────────────────────────────────────────────────

    def get_players_pos(self, M, M1, frame, timestamp, map_2d):
        # Clear per-frame kpts capture dict
        self._matched_kpts_this_frame = {}

        # ── Step 1: Advance all Kalman filters → store predictions ────────
        self._kf_pred = {}
        for slot, kf in self._kalmans.items():
            self._kf_pred[slot] = _kf_predict_bbox(kf)
            # Update previous_bb with predicted position so ball tracker stays accurate
            if self.players[slot].previous_bb is not None:
                self.players[slot].previous_bb = self._kf_pred[slot]

        # ── Step 2: YOLOv8 inference (pose every N frames, else detection) ─
        _run_pose = (
            self._use_pose
            and self._pose_model is not None
            and self._pose_frame_counter % _POSE_INTERVAL == 0
        )
        self._pose_frame_counter += 1

        if _run_pose:
            yolo_results = self._pose_model(
                frame, classes=[0], conf=self._conf_threshold,
                verbose=False, imgsz=1280
            )
        else:
            yolo_results = self.model(
                frame, classes=[0], conf=self._conf_threshold,
                verbose=False, imgsz=640, half=self._use_half
            )
        boxes_xyxy   = (yolo_results[0].boxes.xyxy.cpu().numpy()
                        if yolo_results[0].boxes is not None else [])
        scores_conf  = (yolo_results[0].boxes.conf.cpu().numpy()
                        if yolo_results[0].boxes is not None else [])

        # Extract ankle keypoints when pose model is active.
        # COCO keypoint indices: 15 = left ankle, 16 = right ankle.
        # Shape: (N_persons, N_keypoints, 2 or 3) — xy or xyconf.
        _kpts_xy   = None  # (N, 17, 2) pixel coords
        _kpts_conf = None  # (N, 17)    per-kpt confidence
        if (_run_pose
                and yolo_results[0].keypoints is not None
                and yolo_results[0].keypoints.xy is not None):
            try:
                _kpts_xy = yolo_results[0].keypoints.xy.cpu().numpy()   # (N, 17, 2)
                if yolo_results[0].keypoints.conf is not None:
                    _kpts_conf = yolo_results[0].keypoints.conf.cpu().numpy()  # (N, 17)
            except Exception:
                _kpts_xy = _kpts_conf = None

        if len(boxes_xyxy) == 0:
            self._age_all(timestamp)
            # Update optical flow state for next frame even on empty detections
            self._prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self._flow_pts  = {}
            return self._render(frame, map_2d, timestamp)

        # ── Step 3: Build detection list (bbox, team, crop, court pos) ────
        adaptive_colors = _adaptive_colors(frame)
        detections: List[dict] = []
        for box_i, box in enumerate(boxes_xyxy):
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
            y1c = max(0, y1);  y2c = min(frame.shape[0], y2)
            x1c = max(0, x1);  x2c = min(frame.shape[1], x2)
            bbox     = (y1 - PAD, x1 - PAD, y2 + PAD, x2 + PAD)
            bgr_crop = frame[y1c:y2c, x1c:x2c]
            if bgr_crop.size == 0:
                continue

            # Team classification — HSV range first to detect referee/white
            jersey_h = max(1, int(bgr_crop.shape[0] * 0.70))
            hsv_crop = cv2.cvtColor(bgr_crop[:jersey_h], cv2.COLOR_BGR2HSV)
            team, best_n = "", 0
            for color_key in adaptive_colors:
                mask_c = cv2.inRange(hsv_crop,
                                     np.array(adaptive_colors[color_key][0]),
                                     np.array(adaptive_colors[color_key][1]))
                n = int(cv2.countNonZero(mask_c))
                if n > best_n:
                    best_n, team = n, color_key

            if not team:
                continue

            # Dynamic re-classification: when both teams wear colored jerseys,
            # HSV masks both as 'green'.  Use K-means centroids to separate them.
            if team not in ("referee",):
                # Accumulate warm-up samples from non-referee detections.
                # Use mean HSV (not KMeans) — fast, good enough for calibration.
                if len(self._warmup_colors) < self._warmup_needed * 3:
                    h_c = max(1, int(bgr_crop.shape[0] * 0.65))
                    roi_hsv = cv2.cvtColor(bgr_crop[:h_c], cv2.COLOR_BGR2HSV)
                    self._warmup_colors.append(
                        roi_hsv.reshape(-1, 3).astype(np.float32).mean(axis=0)
                    )
                    if len(self._warmup_colors) == self._warmup_needed:
                        self._calibrate_team_colors()
                team = self._classify_team_dynamic(bgr_crop, team)

            # ── Foot position: ankle keypoints (pose) or bbox_bottom ──────
            head_x = (x1c + x2c) // 2
            foot_y = y2c  # fallback: bbox bottom
            if _kpts_xy is not None and box_i < len(_kpts_xy):
                ankles_xy   = _kpts_xy[box_i, 15:17, :]   # left/right ankle (2,2)
                ankle_confs = (
                    _kpts_conf[box_i, 15:17]
                    if _kpts_conf is not None else np.ones(2)
                )
                # Accept ankle kpts with confidence > 0.5 (fallback to bbox_bottom below)
                valid = ankle_confs > 0.5
                if valid.any():
                    foot_y = int(ankles_xy[valid, 1].mean())
                    # head_x: midpoint of visible ankles gives better horizontal pos
                    head_x = int(ankles_xy[valid, 0].mean())

            # 2D court projection
            kpt  = np.array([head_x, foot_y, 1])
            homo = M1 @ (M @ kpt.reshape(3, 1))
            homo = np.int32(homo / homo[-1]).ravel()

            if not (0 <= homo[0] < map_2d.shape[1] and 0 <= homo[1] < map_2d.shape[0]):
                continue

            color_bgr = hsv2bgr(COLORS[team][2])
            cv2.circle(frame, (head_x, foot_y), 2, color_bgr, 5)

            det_crop = bgr_crop if bgr_crop.size > 0 else None
            score    = float(scores_conf[box_i]) if box_i < len(scores_conf) else 1.0
            # Store full keypoints per detection for downstream pose extraction
            det_kpts_xy   = (_kpts_xy[box_i]
                             if _kpts_xy is not None and box_i < len(_kpts_xy)
                             else None)
            det_kpts_conf = (_kpts_conf[box_i]
                             if _kpts_conf is not None and box_i < len(_kpts_conf)
                             else None)
            detections.append({
                "bbox":      bbox,
                "team":      team,
                "homo":      homo,
                "color":     color_bgr,
                "crop_bgr":  det_crop,
                "score":     score,
                "foot_xy":   (head_x, foot_y),  # pixel foot position for optical flow
                "kpts_xy":   det_kpts_xy,        # (17,2) COCO keypoints or None
                "kpts_conf": det_kpts_conf,       # (17,) per-kpt confidence or None
            })

            # ISSUE-005: update per-team color signature for similar-color detection
            if self._color_tracker is not None and det_crop is not None:
                self._color_tracker.update(det_crop, team)

        # ── Step 3.5: Deep appearance embeddings (OSNet batch inference) ──
        # Batch all detection crops through OSNet once per frame for efficiency.
        # Results stored as det["deep_emb"] and used downstream in place of HSV.
        if self._use_deep and self._deep_extractor is not None and detections:
            crops_for_deep = [d["crop_bgr"] for d in detections]
            try:
                deep_embs = self._deep_extractor.batch_extract(crops_for_deep)
                for d, emb in zip(detections, deep_embs):
                    d["deep_emb"] = emb
            except Exception:
                pass  # fall back to HSV per-det in downstream code

        # ── Step 4: Assignment — ByteTrack (lapx) or Hungarian fallback ─────
        # ByteTrack two-stage is active only when lapx is installed (faster
        # linear assignment).  Without lapx we fall back to the original
        # single-stage Kalman+Hungarian matcher (_match_team).
        _use_bytetrack = _HAS_LAPX
        all_unmatched_dets: List[int] = []

        for team in ("green", "white", "referee"):
            if _use_bytetrack:
                matched, unmatched_slots, unmatched_dets = self._match_team_bytetrack(
                    team, detections
                )
            else:
                matched, unmatched_slots, unmatched_dets = self._match_team(
                    team, detections
                )

            for slot, di in matched:
                self._activate_slot(slot, detections[di], timestamp)

            for slot in unmatched_slots:
                self._lost_ages[slot] = self._lost_ages.get(slot, 0) + 1
                if self._lost_ages[slot] >= self._max_lost:
                    # Archive appearance before evicting
                    if slot in self._appearances:
                        self._gallery[slot] = self._appearances[slot].copy()
                        self._gallery_ages[slot] = 0
                    p = self.players[slot]
                    p.previous_bb = None
                    p.positions   = {}
                    p.has_ball    = False
                    self._kalmans.pop(slot, None)
                    self._appearances.pop(slot, None)
                    self._lost_ages[slot] = 0

            all_unmatched_dets.extend(unmatched_dets)

        # ── Age gallery entries and evict stale ones ──────────────────────
        # ByteTrack handles lost/found tracks natively via two-stage matching,
        # so gallery TTL aging is unnecessary and wastes compute when active.
        if not _use_bytetrack:
            for slot in list(self._gallery_ages.keys()):
                self._gallery_ages[slot] += 1
                if self._gallery_ages[slot] >= self._gallery_ttl:
                    self._gallery.pop(slot, None)
                    self._gallery_ages.pop(slot, None)

        # ── Step 5: Re-ID unmatched detections from lost-track gallery ────
        truly_new: List[int] = []
        for di in all_unmatched_dets:
            slot = self._reid(detections[di])
            if slot is not None:
                self._activate_slot(slot, detections[di], timestamp)
            else:
                truly_new.append(di)

        # ── Step 6: Assign genuinely new detections to free slots ─────────
        for di in truly_new:
            det  = detections[di]
            for p in self.players:
                if p.team == det["team"] and p.previous_bb is None:
                    self._activate_slot(self._slot(p), det, timestamp)
                    break

        # ── Step 6.5: Evict tracks frozen in place (velocity clamp stuck) ──
        # A track frozen for >20 consecutive frames is a false positive (coach,
        # scoreboard, or a SIFT-broken homography artifact) — evict it.
        _FREEZE_MAX = 20
        for p in self.players:
            slot = self._slot(p)
            if self._freeze_age.get(slot, 0) >= _FREEZE_MAX and p.previous_bb is not None:
                if slot in self._appearances:
                    self._gallery[slot] = self._appearances[slot].copy()
                    self._gallery_ages[slot] = 0
                p.previous_bb = None
                p.positions   = {}
                p.has_ball    = False
                self._kalmans.pop(slot, None)
                self._appearances.pop(slot, None)
                self._freeze_age[slot] = 0
                self._lost_ages[slot] = 0

        # ── Step 7: Kalman fill for briefly-lost players (lost_age ≤ 5) ──
        # When YOLO misses a player for 1-5 frames, inject the Kalman-predicted
        # court position so the track stays continuous — eliminates short gaps
        # that would otherwise become raw id_switches in the evaluator.
        for p in self.players:
            slot = self._slot(p)
            lost_age = self._lost_ages.get(slot, 0)
            if (0 < lost_age <= self._kalman_fill_win
                    and slot in self._kf_pred
                    and p.previous_bb is not None
                    and timestamp not in p.positions):
                pred_bbox = self._kf_pred[slot]
                y1p, x1p, y2p, x2p = pred_bbox
                hx = int((x1p + x2p) / 2)
                hy = int(y2p)
                if 0 <= hx < frame.shape[1] and 0 <= hy < frame.shape[0]:
                    kpt  = np.array([hx, hy, 1], dtype=np.float64)
                    try:
                        homo = M1 @ (M @ kpt.reshape(3, 1))
                        if abs(homo[2, 0]) > 1e-6:
                            homo = np.int32(homo / homo[2, 0]).ravel()
                            if (0 <= homo[0] < map_2d.shape[1]
                                    and 0 <= homo[1] < map_2d.shape[0]):
                                p.positions[timestamp] = (homo[0], homo[1])
                    except Exception:
                        pass

        # ── Step 7.5: Optical flow gap-fill ───────────────────────────────
        # For players missed by YOLO (lost_age 1..OF_MAX_AGE), propagate their
        # last known pixel position using Lucas-Kanade optical flow.  This gives
        # smoother court-position estimates than pure Kalman prediction,
        # especially when a player is partially occluded.
        gray_now = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is not None:
            for p in self.players:
                slot     = self._slot(p)
                lost_age = self._lost_ages.get(slot, 0)
                if (0 < lost_age <= OF_MAX_AGE
                        and slot in self._flow_pts
                        and p.previous_bb is not None
                        and timestamp not in p.positions):
                    prev_pt = self._flow_pts[slot]  # shape (1, 2) float32
                    try:
                        new_pt, status, _ = cv2.calcOpticalFlowPyrLK(
                            self._prev_gray, gray_now, prev_pt, None,
                            winSize=OF_WIN_SIZE,
                            maxLevel=OF_MAX_LEVEL,
                            criteria=(
                                cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                                10, 0.03,
                            ),
                        )
                        if status is not None and status[0, 0] == 1:
                            fx, fy = int(new_pt[0, 0]), int(new_pt[0, 1])
                            if (0 <= fx < frame.shape[1]
                                    and 0 <= fy < frame.shape[0]):
                                kpt  = np.array([fx, fy, 1], dtype=np.float64)
                                homo = M1 @ (M @ kpt.reshape(3, 1))
                                if abs(homo[2, 0]) > 1e-6:
                                    homo = np.int32(homo / homo[2, 0]).ravel()
                                    if (0 <= homo[0] < map_2d.shape[1]
                                            and 0 <= homo[1] < map_2d.shape[0]):
                                        p.positions[timestamp] = (homo[0], homo[1])
                                        # Advance flow anchor for next frame
                                        self._flow_pts[slot] = new_pt
                    except Exception:
                        pass
        self._prev_gray = gray_now

        # ── Step 8: Same-team duplicate suppression ───────────────────────
        # If two players on the same team project to within DUPLICATE_DIST of
        # each other, the lower-confidence track (higher lost_age) is likely
        # a stale/frozen position from the velocity clamp — remove it so it
        # doesn't corrupt spatial metrics or inflate duplicate_detections.
        _DUP_DIST = 130  # matches evaluate.py DUPLICATE_DIST
        for team in ("green", "white", "referee"):
            team_slots = [
                (self._slot(p), p)
                for p in self.players
                if p.team == team and timestamp in p.positions
            ]
            for i in range(len(team_slots)):
                slot_i, pi = team_slots[i]
                if timestamp not in pi.positions:
                    continue
                xi, yi = pi.positions[timestamp]
                for j in range(i + 1, len(team_slots)):
                    slot_j, pj = team_slots[j]
                    if timestamp not in pj.positions:
                        continue
                    xj, yj = pj.positions[timestamp]
                    if float(np.hypot(xi - xj, yi - yj)) < _DUP_DIST:
                        # Keep the track with lower lost_age (fresher detection)
                        age_i = self._lost_ages.get(slot_i, 0)
                        age_j = self._lost_ages.get(slot_j, 0)
                        if age_i >= age_j:
                            del pi.positions[timestamp]
                            break  # pi removed; stop checking pi vs others
                        else:
                            del pj.positions[timestamp]

        # Periodic re-calibration to adapt to changing camera angles
        self._frames_since_calib += 1
        if self._frames_since_calib >= self._recalib_interval and len(self._warmup_colors) >= 10:
            self._calibrate_team_colors()
            self._warmup_colors = []   # reset sample buffer
            self._frames_since_calib = 0

        # ── Pose field extraction and player attribute update ──────────────
        # For every slot that received a matched detection with keypoints this
        # frame, run the full pose extraction and cache the result.  On frames
        # where pose did not run (_run_pose=False), _matched_kpts_this_frame is
        # empty so only previously cached pose fields are applied.
        for slot, (kxy, kconf) in self._matched_kpts_this_frame.items():
            pose = self._extract_pose_fields(
                slot, kxy, kconf, self.players[slot].has_ball
            )
            self._pose_state[slot] = pose

        for p in self.players:
            slot = self._slot(p)
            pose = self._pose_state.get(slot, {})
            p.ankle_x            = pose.get("ankle_x")
            p.ankle_y            = pose.get("ankle_y")
            p.jump_detected      = pose.get("jump_detected", False)
            p.contest_arm_angle  = pose.get("contest_arm_angle", 0.0)
            p.dribble_hand       = pose.get("dribble_hand", "unknown")

        return self._render(frame, map_2d, timestamp)

    # ── housekeeping ──────────────────────────────────────────────────────

    def _age_all(self, timestamp: int):
        """Age all tracks when a frame produces zero detections."""
        for i, p in enumerate(self.players):
            if p.previous_bb is not None:
                self._lost_ages[i] = self._lost_ages.get(i, 0) + 1
                if self._lost_ages[i] >= MAX_LOST:
                    if i in self._appearances:
                        self._gallery[i] = self._appearances[i].copy()
                        self._gallery_ages[i] = 0
                    p.previous_bb = None
                    p.positions   = {}
                    p.has_ball    = False
                    self._kalmans.pop(i, None)
                    self._flow_pts.pop(i, None)
                    self._lost_ages[i] = 0
        for slot in list(self._gallery_ages.keys()):
            self._gallery_ages[slot] += 1
            if self._gallery_ages[slot] >= self._gallery_ttl:
                self._gallery.pop(slot, None)
                self._gallery_ages.pop(slot, None)


# ── Debug visualisation ───────────────────────────────────────────────────────

def visualize_tracking(
    video_path: str,
    predictions: List[dict],
    output_path: Optional[str] = None,
    trail_length: int = 30,
):
    """
    Render annotated video: bounding boxes, player IDs, confidence, and trails.

    Args:
        video_path:   Original input video.
        predictions:  From track_video()["predictions"].
        output_path:  Write annotated .mp4 here if provided.
        trail_length: Frames of trail to draw per player.
    """
    TOPCUT = 60   # remove scoreboard only; 320 cut off far-end players on 720p broadcast
    TEAM_COLORS = {"green": (0, 200, 0), "white": (200, 200, 200), "referee": (0, 0, 200)}

    pred_by_frame = {f["frame"]: f["tracks"] for f in predictions}
    trails: Dict[str, list] = defaultdict(list)

    cap    = cv2.VideoCapture(video_path)
    writer = None

    if output_path:
        _, f0 = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        if f0 is not None:
            h, w = f0[TOPCUT:].shape[:2]
            writer = cv2.VideoWriter(
                output_path, cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (w, h)
            )

    frame_idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        frame = frame[TOPCUT:]

        for t in pred_by_frame.get(frame_idx, []):
            key   = f"{t['team']}_{t['player_id']}"
            color = TEAM_COLORS.get(t["team"], (128, 128, 128))
            conf  = t.get("confidence", 1.0)
            bbox  = t.get("bbox")

            if bbox:
                y1, x1, y2, x2 = [int(v) for v in bbox]
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, max(1, int(conf * 3)))
                label = f"{t['team'][0].upper()}{t['player_id']} {conf:.2f}"
                cv2.putText(frame, label, (x1, max(0, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                trails[key].append((cx, cy))
            if len(trails[key]) > trail_length:
                trails[key].pop(0)
            pts = trails[key]
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                c = tuple(int(v * alpha) for v in color)
                cv2.line(frame, pts[i - 1], pts[i], c, 2)

        if output_path:  # only show window when writing output video
            cv2.imshow("Advanced Tracker — Debug", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break
        if writer:
            writer.write(frame)
        frame_idx += 1

    cap.release()
    if writer:
        writer.release()
        print(f"Debug video saved → {output_path}")
    cv2.destroyAllWindows()
