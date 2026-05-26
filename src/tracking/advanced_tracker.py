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
    from .player_identity import reset_confirmed_slot as _reset_confirmed_slot
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
    import lap as _lapx  # noqa: F401  — lapx installs as 'lap'; faster Hungarian for ByteTrack
    _HAS_LAPX = True
except ImportError:
    try:
        import lapx as _lapx  # noqa: F401  — older install name fallback
        _HAS_LAPX = True
    except ImportError:
        _HAS_LAPX = False

try:
    import supervision as _sv
    _HAS_SUPERVISION = True
except ImportError:
    _HAS_SUPERVISION = False

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
BT_HIGH_THRESH    = 0.35   # Stage-1: align with _conf_threshold so broadcast dets use IoU+appearance
BT_SECOND_IOUGATE = 0.30   # Stage-2: lower gate for occluded players (smaller bbox → lower IoU)
BT_STAGE2_PROX_PX = 80.0  # Stage-2 proximity fallback: pixel radius when IoU=0 but position matches

# ── Optical flow constants ────────────────────────────────────────────────────
OF_WIN_SIZE  = (15, 15)   # Lucas-Kanade search window
OF_MAX_LEVEL = 2          # pyramid levels
OF_MAX_AGE   = 8          # max lost frames before stopping optical flow propagation

# ── Pose cadence ──────────────────────────────────────────────────────────────
_POSE_INTERVAL_ACTIVE    = 5   # R15: in-play with ball holder — keypoints fresh at shot release
_POSE_INTERVAL           = 15  # in-play no ball holder — keypoints still reasonably current
_POSE_INTERVAL_SUSPENDED = 30  # Slower cadence when no ball holder + game suspended


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
    if a.shape != b.shape:
        return 0.5  # neutral when embeddings have different dims (deep vs HSV mismatch)
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

        # YOLO model + image size — configurable for post-game high-quality runs
        _yolo_stem = _cfg.get("yolo_model", "yolov8n")
        self._yolo_imgsz: int = int(_cfg.get("yolo_imgsz", 640))
        # Pose model — configurable separately. Investigated 2026-05-26:
        # - At imgsz=640: ankle keypoint conf ~0.005 (model literally cannot
        #   see ankles in 640x360 broadcast — ankle_x/y stays NaN), but
        #   contest_arm_angle works (45% nonzero) because nose/wrist/hip
        #   conf is fine at 640.
        # - At imgsz=960 (rebuilt engine, see .bak_640 + new engine): standalone
        #   tests show ankle conf rises to 0.4-0.7. BUT in-pipeline contest_arm
        #   drops to 0% — some dispatch-side regression we couldn't trace in
        #   that session. Default reverted to 640 to preserve the 45% contest
        #   feature until the pipeline-side issue is found. See Open Issues #10.
        # To experiment: pass `pose_imgsz: 960` in _cfg and ensure
        # resources/yolov8n-pose.engine is the 960-built one (or use .bak_640).
        self._pose_imgsz: int = int(_cfg.get("pose_imgsz", 640))
        self._yolo_device = 0 if self._use_half else "cpu"
        if _yolo_stem != "yolov8n":
            try:
                from ultralytics import YOLO as _YOLO
                from .player_detection import _best_yolo_model
                self.model = _YOLO(_best_yolo_model(_yolo_stem))
                self.model(
                    __import__("numpy").zeros((self._yolo_imgsz, self._yolo_imgsz, 3),
                                             dtype=__import__("numpy").uint8),
                    verbose=False, half=self._use_half, device=self._yolo_device,
                )
            except Exception:
                pass  # fall back to yolov8n loaded by FeetDetector.__init__

        self._fill_conf_threshold = 0.22  # lower threshold for
        # slots that have active Kalman predictions — catches
        # partially-occluded players YOLO would otherwise discard

        n = len(players)
        self._kalmans:      Dict[int, cv2.KalmanFilter] = {}
        self._appearances:  Dict[int, np.ndarray]       = {}
        self._lost_ages:    Dict[int, int]              = {i: 0 for i in range(n)}
        self._gallery:        Dict[int, np.ndarray]       = {}  # slot → appearance snapshot
        self._gallery_ages:   Dict[int, int]              = {}  # slot → frames since archived
        self._gallery_last_pos: Dict[int, Tuple]          = {}  # slot → (x2d, y2d) at eviction
        self._kf_pred:      Dict[int, Tuple]            = {}  # predicted bboxes this frame
        self._jersey_buf:   Optional[object]            = None  # set externally after construction
        self._freeze_age:   Dict[int, int]              = {i: 0 for i in range(n)}  # frames frozen
        # Task 2: stable-track OSNet skip — counts consecutive matched frames per slot;
        # when >= 30 a 4-frame OSNet skip window is triggered for that slot.
        self._stable_frames: Dict[int, int]             = {i: 0 for i in range(n)}
        self._stable_skip:   Dict[int, int]             = {i: 0 for i in range(n)}
        # ISSUE-005: per-team color tracker for similar-uniform detection
        self._color_tracker = _TeamColorTracker() if _HAS_COLOR_REID else None

        # Dynamic team color clustering (fixes all-green bug)
        # Warm-up: collect dominant jersey HSV for first N non-referee detections,
        # then K-means k=2 to discover the two team colors.
        self._warmup_colors: List[np.ndarray] = []   # dominant HSV samples
        self._team_centroids: Optional[List[np.ndarray]] = None  # [centroid_A, centroid_B]
        self._warmup_needed = 30   # detections before first calibration
        self._recalib_interval = 300  # frames between periodic re-calibrations (raised 150→300)
        self._frames_since_calib = 0
        # Rolling HSV buffer for periodic re-calibration (replaces warmup_colors after warmup).
        # Uses the most recent 300 frames of detection HSV rather than an ever-growing pool.
        from collections import deque as _deque
        self._rolling_hsv_buf: "_deque[np.ndarray]" = _deque(maxlen=300)
        # Per-slot confidence-based sample pool for the initial calibration window.
        # Only detections within the first _WARMUP_FRAME_LIMIT source frames are used;
        # up to _WARMUP_TOP_K highest-confidence crops per slot are kept so similar-
        # colored uniforms (e.g. OKC blue vs DAL navy) get representative coverage.
        self._warmup_per_slot: Dict[int, List] = {}   # slot → [(conf, hsv_mean), ...]
        self._warmup_frame_limit = 300  # stop per-slot confidence sampling after this frame
        self._warmup_top_k      = 10   # keep top-K crops per slot by YOLO confidence

        # ── Pose estimation (ankle keypoints) ─────────────────────────────
        # Replace bbox_bottom heuristic with YOLOv8-pose ankle keypoints.
        # Falls back to bbox_bottom when keypoints are not detected.
        self._pose_model = None
        self._use_pose   = False
        try:
            from ultralytics import YOLO as _YOLO
            from .player_detection import _best_yolo_model
            _pm = _YOLO(_best_yolo_model("yolov8n-pose"))
            if _cfg.get("broadcast_mode", True):
                _pm.overrides["half"] = getattr(self, "_use_half", False)
            # Warmup on GPU to avoid first-call latency
            _pm(
                __import__("numpy").zeros((640, 640, 3), dtype=__import__("numpy").uint8),
                verbose=False, half=self._use_half, device=self._yolo_device,
            )
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

        # Batch YOLO inference buffer — accumulates frames for GPU batch processing
        # When the result cache has entries, YOLO is skipped entirely for that frame.
        # True 16-frame batching activates automatically when the caller pushes
        # multiple frames before consuming results (async / prefetch architecture).
        self._yolo_frame_buf: deque = deque(maxlen=16)
        self._yolo_result_buf: deque = deque(maxlen=16)  # cached [(yolo_results, ran_pose), ...]

        # Background YOLO prefetch thread
        self._prefetch_thread: Optional["threading.Thread"] = None
        self._prefetch_lock = __import__("threading").Lock()

        # supervision ByteTrack tracker (GPU-native when available)
        self._sv_tracker = None
        if _HAS_SUPERVISION:
            try:
                self._sv_tracker = _sv.ByteTrack(
                    track_activation_threshold=BT_HIGH_THRESH,
                    lost_track_buffer=MAX_LOST,
                    minimum_matching_threshold=BT_SECOND_IOUGATE,
                    frame_rate=30,
                )
            except Exception:
                pass

    # ── YOLO batch prefetch ──────────────────────────────────────────────

    def prefetch_yolo(self, frames: List[np.ndarray], run_pose_flags: Optional[List[bool]] = None) -> None:
        """Push N frames into YOLO batch buffer via background thread.

        Runs YOLO inference on up to 8 frames in a single GPU batch call.
        Results are cached in _yolo_result_buf so get_players_pos() serves
        them with zero GPU cost for the next N-1 frames.
        """
        import threading
        if not frames:
            return
        n = min(len(frames), 8)
        frames = frames[:n]
        if run_pose_flags is None:
            run_pose_flags = [False] * n

        def _run():
            _imgsz = getattr(self, "_infer_imgsz", self._yolo_imgsz)
            _dev = getattr(self, "_yolo_device", 0 if self._use_half else "cpu")
            _pose_idx = [i for i, rp in enumerate(run_pose_flags) if rp]
            _det_idx = [i for i, rp in enumerate(run_pose_flags) if not rp]
            _pending: list = [(None, None)] * n

            if _pose_idx and self._use_pose and self._pose_model is not None:
                _pimgs = [frames[i] for i in _pose_idx]
                _pres = list(self._pose_model(
                    _pimgs, classes=[0], conf=self._fill_conf_threshold,
                    verbose=False, imgsz=self._pose_imgsz, half=self._use_half, device=_dev
                ))
                for _j, _r in zip(_pose_idx, _pres):
                    _pending[_j] = ([_r], True)

            if _det_idx:
                _dimgs = [frames[i] for i in _det_idx]
                _dres = list(self.model(
                    _dimgs, classes=[0], conf=self._fill_conf_threshold,
                    verbose=False, imgsz=_imgsz, half=self._use_half, device=_dev
                ))
                for _j, _r in zip(_det_idx, _dres):
                    _pending[_j] = ([_r], False)

            with self._prefetch_lock:
                self._yolo_result_buf.extend(_pending)

        t = threading.Thread(target=_run, daemon=True, name="YOLOPrefetch")
        t.start()
        self._prefetch_thread = t

    # ── Per-game state reset ─────────────────────────────────────────────

    def _reset_per_game(self) -> None:
        """Clear all per-game tracking state. Model weights are preserved."""
        import threading as _th
        n = len(self.players)
        self._kalmans.clear()
        self._appearances.clear()
        self._lost_ages = {i: 0 for i in range(n)}
        self._gallery.clear()
        self._gallery_ages.clear()
        self._gallery_last_pos.clear()
        self._kf_pred.clear()
        self._freeze_age = {i: 0 for i in range(n)}
        self._stable_frames = {i: 0 for i in range(n)}
        self._stable_skip = {i: 0 for i in range(n)}
        self._warmup_colors.clear()
        self._team_centroids = None
        self._frames_since_calib = 0
        self._rolling_hsv_buf.clear()
        self._warmup_per_slot.clear()
        self._pose_frame_counter = 0
        self._pose_state.clear()
        self._hip_y_history.clear()
        self._matched_kpts_this_frame.clear()
        self._prev_gray = None
        self._flow_pts.clear()
        self._yolo_frame_buf.clear()
        self._yolo_result_buf.clear()
        self._prefetch_thread = None
        self._prefetch_lock = _th.Lock()
        if self._color_tracker is not None and _HAS_COLOR_REID:
            try:
                self._color_tracker = _TeamColorTracker()
            except Exception:
                pass
        if self._sv_tracker is not None and _HAS_SUPERVISION:
            try:
                self._sv_tracker = _sv.ByteTrack(
                    track_activation_threshold=BT_HIGH_THRESH,
                    lost_track_buffer=MAX_LOST,
                    minimum_matching_threshold=BT_SECOND_IOUGATE,
                    frame_rate=30,
                )
            except Exception:
                pass

    # ── GPU ROI pooling for OSNet crops ────────────────────────────────

    def _gpu_roi_extract(
        self, frame: np.ndarray, detections: List[dict], indices: List[int]
    ) -> Optional[List[np.ndarray]]:
        """Extract OSNet embeddings via torchvision.ops.roi_align (GPU, zero CPU crops).

        Converts frame to GPU tensor once, builds ROI boxes from detection bboxes,
        runs roi_align → OSNet in a single GPU pipeline. Returns None on failure
        so caller can fall back to CPU crop path.
        """
        try:
            import torch
            from torchvision.ops import roi_align
        except ImportError:
            return None

        if not self._use_deep or self._deep_extractor is None:
            return None

        _dev = getattr(self._deep_extractor, "_device", "cuda")
        if _dev == "cpu":
            return None

        # Frame → GPU tensor (H, W, 3) BGR → (1, 3, H, W) RGB float32 [0,1]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_t = torch.from_numpy(frame_rgb).permute(2, 0, 1).unsqueeze(0).float().to(_dev) / 255.0

        # Build ROI tensor: (N, 5) where col0=batch_idx, cols1-4=xyxy
        rois = []
        for idx in indices:
            bb = detections[idx]["bbox"]  # (y1, x1, y2, x2)
            y1, x1, y2, x2 = bb
            # Clamp to frame
            x1c = max(0, x1); y1c = max(0, y1)
            x2c = min(frame.shape[1], x2); y2c = min(frame.shape[0], y2)
            rois.append([0, x1c, y1c, x2c, y2c])

        if not rois:
            return None

        rois_t = torch.tensor(rois, dtype=torch.float32, device=_dev)

        # roi_align → (N, 3, 256, 128) — OSNet input size
        pooled = roi_align(frame_t, rois_t, output_size=(256, 128), aligned=True)

        # ImageNet normalize
        _mean = torch.tensor([0.485, 0.456, 0.406], device=_dev).view(1, 3, 1, 1)
        _std = torch.tensor([0.229, 0.224, 0.225], device=_dev).view(1, 3, 1, 1)
        pooled = (pooled - _mean) / _std

        # Run through OSNet model directly (skip preprocessing)
        extractor = self._deep_extractor
        with torch.no_grad():
            if getattr(extractor, "_use_torchreid", False):
                feats = extractor._torchreid_model._model.featuremaps(pooled.to(_dev))
                v = extractor._torchreid_model._model.global_avgpool(feats).view(feats.size(0), -1)
                emb = extractor._torchreid_model._model.fc(v)
                emb = torch.nn.functional.normalize(emb, dim=1)
            elif getattr(extractor, "_use_trt", False):
                return None  # TRT path uses its own memory — fall back
            elif extractor._model is not None:
                emb = extractor._model(pooled.to(_dev))
            else:
                return None
            return [e.cpu().numpy() for e in emb]

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
            prior = self._appearances[slot]
            if prior.shape == emb.shape:
                self._appearances[slot] = APPEAR_ALPHA * prior + (1 - APPEAR_ALPHA) * emb
            else:
                # Dimension mismatch (deep ↔ HSV switch) — replace instead of blend
                self._appearances[slot] = emb
        else:
            self._appearances[slot] = emb

    # Fix C: sticky binding threshold.  A slot must be absent for at least this
    # many frames before its jersey confirmation is cleared.  Below this threshold
    # the re-activation is just a brief occlusion, not a real substitution — do
    # not wipe the hard-won jersey vote so re-binding can't fire on a bad OCR
    # read from the moment the player returns into frame.
    _STICKY_REBIND_MIN_ABSENCE = 90  # frames (~3 s at 30 fps)

    def _activate_slot(self, slot: int, det: dict, timestamp: int, stride: int = 1):
        """
        Assign a detection to a player slot and update all state.

        Resets the jersey voting buffer for the slot only when the slot has been
        absent for > _STICKY_REBIND_MIN_ABSENCE frames (true substitution event).
        Brief disappearances (occlusion, YOLO miss) keep the existing confirmed
        jersey so re-binding cannot fire on a single noisy OCR read when the
        player returns (Fix C — audit 2026-05-26, pid=10 cycling 4 names).
        """
        # Fix C: only reset jersey when the slot has been absent long enough to
        # represent a real substitution (not a brief occlusion / YOLO miss).
        _absent_frames = self._lost_ages.get(slot, 0)
        if (_HAS_VOTING
                and hasattr(self, "_jersey_buf")
                and self._jersey_buf is not None
                and self.players[slot].previous_bb is not None
                and _absent_frames >= self._STICKY_REBIND_MIN_ABSENCE):
            _reset_confirmed_slot(slot, self._jersey_buf)

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
            if dist > MAX_2D_JUMP * max(1, stride):
                new_pos = last_pos
                self._freeze_age[slot] = self._freeze_age.get(slot, 0) + 1
            else:
                self._freeze_age[slot] = 0
        p.positions[timestamp] = new_pos
        # Prune old positions — prevent unbounded growth during full-game runs.
        # Keep last 300 frames (~10s at 30fps). All downstream consumers
        # (velocity calc, duplicate suppression, Kalman fill) need at most 10s.
        _PRUNE_AFTER = 300
        if len(p.positions) > _PRUNE_AFTER:
            cutoff = timestamp - _PRUNE_AFTER
            for _k in [k for k in p.positions if k < cutoff]:
                del p.positions[_k]
        if slot in self._kalmans:
            _kf_correct(self._kalmans[slot], det["bbox"])
        else:
            self._kalmans[slot] = _make_kf(det["bbox"])
        self._update_appearance(
            slot, det["crop_bgr"], deep_emb=det.get("deep_emb")
        )
        self._lost_ages[slot] = 0
        # Task 2: track consecutive matched frames; trigger OSNet skip after 15
        self._stable_frames[slot] = self._stable_frames.get(slot, 0) + 1
        if self._stable_frames[slot] >= 15:
            self._stable_skip[slot] = 30
            self._stable_frames[slot] = 0
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

    def _calibrate_team_colors(self, min_cluster_size: int = 5) -> None:
        """K-means k=2 on warmup_colors to find two team centroids.

        Uses a numpy-only implementation to avoid sklearn/threadpoolctl
        Windows DLL errors.  Initialized with the two samples furthest apart
        by hue, giving stable clusters for any pair of jersey colors.

        Args:
            min_cluster_size: Reject result if either cluster has fewer than this
                              many samples.  Default 5 (warmup pass); periodic
                              rolling-buf recalibration uses 20 (tighter gate).
        """
        if len(self._warmup_colors) < 10:
            return
        try:
            samples = np.array(self._warmup_colors, dtype=np.float32)
            # Init: pick the two samples with max hue separation
            hues = samples[:, 0]
            i0 = int(np.argmin(hues))
            i1 = int(np.argmax(hues))
            c0, c1 = samples[i0].copy(), samples[i1].copy()
            for _ in range(30):
                # Circular hue distance
                d0 = np.minimum(np.abs(samples[:,0]-c0[0]), 180.-np.abs(samples[:,0]-c0[0]))
                d1 = np.minimum(np.abs(samples[:,0]-c1[0]), 180.-np.abs(samples[:,0]-c1[0]))
                labels = (d1 < d0).astype(np.int32)
                new_c0 = samples[labels==0].mean(axis=0) if (labels==0).any() else c0
                new_c1 = samples[labels==1].mean(axis=0) if (labels==1).any() else c1
                if np.allclose(new_c0, c0, atol=0.5) and np.allclose(new_c1, c1, atol=0.5):
                    break
                c0, c1 = new_c0, new_c1
            # Reject clusters below the minimum size gate — k-means didn't find two
            # distinct jersey colors; keep existing centroids (don't clear to None).
            n0 = int((labels == 0).sum())
            n1 = int((labels == 1).sum())
            if n0 < min_cluster_size or n1 < min_cluster_size:
                self._team_centroids = None
                return
            self._team_centroids = [c0, c1]
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

        # Pre-compute detection embeddings once (O(n_dets) not O(n_slots*n_dets))
        # Use deep embedding if available (batch-computed by OSNet), else HSV.
        det_embs = []
        for di in dets:
            _deep = detections[di].get("deep_emb")
            det_embs.append(
                _deep if _deep is not None
                else (_compute_appearance(detections[di]["crop_bgr"])
                      if detections[di]["crop_bgr"] is not None else None)
            )

        for ri, slot in enumerate(slots):
            pred = self._kf_pred.get(slot)
            for ci, di in enumerate(dets):
                det_bbox = detections[di]["bbox"]
                iou_val  = _iou(pred, det_bbox) if pred is not None else 0.0
                app_dist = _appear_dist(self._appearances.get(slot), det_embs[ci])
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

        # ── Stage 2: low-conf dets vs unmatched tracks (IoU + proximity) ─
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
                        # Proximity fallback for partially-occluded players whose
                        # shrunken bbox has near-zero IoU with the full-body prediction.
                        # Only fires when IoU=0 AND slot has an active Kalman prediction.
                        if iou_val == 0.0 and pred is not None:
                            py1, px1, py2, px2 = pred
                            dy1, dx1, dy2, dx2 = det_bbox
                            dist = ((px1 + px2) / 2 - (dx1 + dx2) / 2) ** 2 + \
                                   ((py1 + py2) / 2 - (dy1 + dy2) / 2) ** 2
                            prox = max(0.0, 1.0 - dist ** 0.5 / BT_STAGE2_PROX_PX)
                            iou_val = prox * 0.5  # contributes up to 0.5 IoU-equivalent
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

    def _match_all_supervision(
        self, detections: List[dict]
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """Match all detections at once using supervision.ByteTrack.

        Returns same format as _match_team_bytetrack: (matched, unmatched_slots, unmatched_dets).
        Maps supervision track_ids back to player slots for downstream compatibility.
        """
        if not detections:
            return [], list(range(len(self.players))), []

        # Build xyxy + conf arrays for supervision
        xyxy = np.zeros((len(detections), 4), dtype=np.float32)
        confs = np.zeros(len(detections), dtype=np.float32)
        class_ids = np.zeros(len(detections), dtype=np.int32)
        _team_map = {"green": 0, "white": 1, "referee": 2}

        for i, d in enumerate(detections):
            bb = d["bbox"]  # (y1, x1, y2, x2)
            xyxy[i] = [bb[1], bb[0], bb[3], bb[2]]  # to x1,y1,x2,y2
            confs[i] = d.get("score", 1.0)
            class_ids[i] = _team_map.get(d["team"], 0)

        sv_dets = _sv.Detections(
            xyxy=xyxy,
            confidence=confs,
            class_id=class_ids,
        )
        tracked = self._sv_tracker.update_with_detections(sv_dets)

        # Map supervision tracker_ids → player slots
        # supervision assigns persistent track_ids; we map them to our slot system
        matched: List[Tuple[int, int]] = []
        used_slots: set = set()
        if not hasattr(self, "_sv_track_to_slot"):
            self._sv_track_to_slot: Dict[int, int] = {}

        all_slots = set(range(len(self.players)))

        for i in range(len(tracked)):
            det_idx = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else i
            sv_tid = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else -1

            # Find original detection index by matching xyxy
            orig_idx = None
            for di, d in enumerate(detections):
                bb = d["bbox"]
                if (abs(xyxy[di][0] - tracked.xyxy[i][0]) < 1 and
                    abs(xyxy[di][1] - tracked.xyxy[i][1]) < 1):
                    orig_idx = di
                    break
            if orig_idx is None:
                continue

            # Resolve track_id → slot
            if sv_tid in self._sv_track_to_slot:
                slot = self._sv_track_to_slot[sv_tid]
            else:
                # Assign to first available slot for this team
                team = detections[orig_idx]["team"]
                team_slots = [self._slot(p) for p in self.players if p.team == team]
                available = [s for s in team_slots if s not in used_slots]
                if available:
                    slot = available[0]
                    self._sv_track_to_slot[sv_tid] = slot
                else:
                    continue

            if slot not in used_slots:
                matched.append((slot, orig_idx))
                used_slots.add(slot)

        unmatched_slots = [s for s in all_slots if s not in used_slots]
        matched_dets = {di for _, di in matched}
        unmatched_dets = [i for i in range(len(detections)) if i not in matched_dets]
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

    def get_players_pos(self, M, M1, frame, timestamp, map_2d,
                        skip_jersey_ocr: bool = False,
                        suspended: bool = False,
                        stride: int = 1):
        """Track players in one frame and return annotated frame + map images.

        Args:
            skip_jersey_ocr: When True, suppress EasyOCR jersey reads for this
                frame.  Set True by the pipeline during confirmed non-live sequences
                (replays, halftime) when _ball_track_suspended is active — saves
                ~20-30% compute on replay-heavy clips with no identity benefit.
            suspended: When True (halftime, timeout), skip team-color re-calibration
                so halftime studio footage doesn't corrupt the learned team centroids.
        """
        # SUB-PROFILER (temporary) -----------------------------------------
        import time as _subt
        _sp = {}
        _sp_t0 = _subt.perf_counter()
        self._sub_profile = _sp  # expose for pipeline to print
        # ------------------------------------------------------------------

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
        # Task 3: use a longer pose interval when the game is suspended (replay /
        # halftime) AND no player currently holds the ball — pose adds little value
        # in those frames and costs ~15% of per-frame GPU time.
        # R15: three-tier cadence — active (ball holder exists) gets 5-frame interval
        # so defender pose is fresh at shot release (was 15-frame, allowing 0-14 frames
        # stale at shot moment). Suspended uses 30, otherwise 15. Net GPU cost ~7%.
        _pose_any_ball = any(p.has_ball for p in self.players)
        if _pose_any_ball:
            _pose_ivl = _POSE_INTERVAL_ACTIVE
        elif suspended:
            _pose_ivl = _POSE_INTERVAL_SUSPENDED
        else:
            _pose_ivl = _POSE_INTERVAL
        _run_pose = (
            self._use_pose
            and self._pose_model is not None
            and self._pose_frame_counter % _pose_ivl == 0
        )
        self._pose_frame_counter += 1

        _imgsz = getattr(self, "_infer_imgsz", self._yolo_imgsz)
        _dev   = getattr(self, "_yolo_device", 0 if self._use_half else "cpu")
        _BATCH = 16

        # ── Batch YOLO inference with 16-frame deque buffer ───────────────
        # Wait for prefetch thread if running, then serve from cache.
        if self._prefetch_thread is not None and self._prefetch_thread.is_alive():
            self._prefetch_thread.join()
        with self._prefetch_lock:
            _has_cached = bool(self._yolo_result_buf)
        if _has_cached:
            with self._prefetch_lock:
                yolo_results, _run_pose = self._yolo_result_buf.popleft()
        else:
            # Accumulate current frame; flush entire buffer as one GPU batch call.
            # In the current sequential architecture the batch will typically be
            # size 1; it scales to 16 automatically when a prefetch/async caller
            # pushes multiple frames before consuming results.
            self._yolo_frame_buf.append((frame, _run_pose))
            _batch = list(self._yolo_frame_buf)
            self._yolo_frame_buf.clear()

            _pose_idx = [i for i, (_, rp) in enumerate(_batch) if rp]
            _det_idx  = [i for i, (_, rp) in enumerate(_batch) if not rp]
            _pending: list = [(None, None)] * len(_batch)

            if _pose_idx and self._use_pose and self._pose_model is not None:
                _pimgs = [_batch[i][0] for i in _pose_idx]
                _pres  = list(self._pose_model(
                    _pimgs, classes=[0], conf=self._fill_conf_threshold,
                    verbose=False, imgsz=self._pose_imgsz, half=self._use_half, device=_dev
                ))
                for _j, _r in zip(_pose_idx, _pres):
                    _pending[_j] = ([_r], True)

            if _det_idx:
                _dimgs = [_batch[i][0] for i in _det_idx]
                _dres  = list(self.model(
                    _dimgs, classes=[0], conf=self._fill_conf_threshold,
                    verbose=False, imgsz=_imgsz, half=self._use_half, device=_dev
                ))
                for _j, _r in zip(_det_idx, _dres):
                    _pending[_j] = ([_r], False)

            yolo_results, _run_pose = _pending[0]
            if len(_pending) > 1:
                self._yolo_result_buf.clear()
                self._yolo_result_buf.extend(_pending[1:])

        _sp["yolo"] = _subt.perf_counter() - _sp_t0
        _sp_last = _subt.perf_counter()

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

        # Release YOLO Results immediately — each holds orig_img (~6MB frame ref)
        # and GPU tensor refs.  Without this, they linger until GC collects them,
        # fragmenting both VRAM and CPU heap in multi-worker runs.
        del yolo_results
        # Also clear predictor's cached results/batch (holds orig_img refs)
        for _m in (self.model, self._pose_model):
            if _m is not None and hasattr(_m, "predictor") and _m.predictor is not None:
                _m.predictor.results = None
                _m.predictor.batch = None

        if len(boxes_xyxy) == 0:
            self._age_all(timestamp)
            gray_now = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Run optical flow gap-fill even on fully-empty frames (YOLO blackout).
            # Broadcast footage has frequent YOLO misses; skipping flow here causes
            # the same positional gaps as the YOLO miss itself.
            if self._prev_gray is not None and self._flow_pts:
                _of_candidates = [
                    (self._slot(p), p, self._flow_pts[self._slot(p)])
                    for p in self.players
                    if (0 < self._lost_ages.get(self._slot(p), 0) <= OF_MAX_AGE
                        and self._slot(p) in self._flow_pts
                        and p.previous_bb is not None
                        and timestamp not in p.positions)
                ]
                if _of_candidates:
                    _prev_batch = np.array(
                        [c[2][0] for c in _of_candidates], dtype=np.float32
                    ).reshape(-1, 1, 2)
                    try:
                        _new_batch, _statuses, _ = cv2.calcOpticalFlowPyrLK(
                            self._prev_gray, gray_now, _prev_batch, None,
                            winSize=OF_WIN_SIZE, maxLevel=OF_MAX_LEVEL,
                            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                                      10, 0.03),
                        )
                        for (_slot, _p, _), _new_pt, _st in zip(
                            _of_candidates, _new_batch, _statuses
                        ):
                            if _st[0] != 1:
                                continue
                            _fx, _fy = int(_new_pt[0, 0]), int(_new_pt[0, 1])
                            if not (0 <= _fx < frame.shape[1]
                                    and 0 <= _fy < frame.shape[0]):
                                continue
                            _kpt  = np.array([_fx, _fy, 1], dtype=np.float64)
                            _homo = M1 @ (M @ _kpt.reshape(3, 1))
                            if abs(_homo[2, 0]) > 1e-6:
                                _homo = np.int32(_homo / _homo[2, 0]).ravel()
                                if (0 <= _homo[0] < map_2d.shape[1]
                                        and 0 <= _homo[1] < map_2d.shape[0]):
                                    _p.positions[timestamp] = (_homo[0], _homo[1])
                                    self._flow_pts[_slot] = _new_pt
                    except Exception:
                        pass
            self._prev_gray = gray_now
            self._flow_pts = {
                s: pts for s, pts in self._flow_pts.items()
                if self._lost_ages.get(s, 0) <= OF_MAX_AGE
            }
            return self._render(frame, map_2d, timestamp)

        # ── Step 3: Build detection list (bbox, team, crop, court pos) ────
        _sp_ac_t0 = _subt.perf_counter()
        adaptive_colors = _adaptive_colors(frame)
        _sp["ac_call"] = _subt.perf_counter() - _sp_ac_t0
        _sp["hsv"] = 0.0
        _sp["warmup"] = 0.0
        _sp["classify_dyn"] = 0.0
        _sp["ctrack_upd"] = 0.0
        _sp["n_boxes"] = len(boxes_xyxy)
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
            _hsv_t0 = _subt.perf_counter()
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
            _sp["hsv"] += _subt.perf_counter() - _hsv_t0

            if not team:
                continue

            # Early score extraction so it's available for warmup filtering below.
            _early_score = float(scores_conf[box_i]) if box_i < len(scores_conf) else 1.0

            # Dynamic re-classification: when both teams wear colored jerseys,
            # HSV masks both as 'green'.  Use K-means centroids to separate them.
            _wu_t0 = _subt.perf_counter()
            if team not in ("referee",):
                # Per-slot confidence-based warmup (first _warmup_frame_limit frames).
                # Keeps top-_warmup_top_k highest-confidence crops per detection slot
                # so similar-colored uniforms (e.g. OKC blue vs DAL navy) are correctly
                # separated — low-conf noisy crops that blur the centroids are excluded.
                if timestamp < self._warmup_frame_limit:
                    if _early_score >= self._conf_threshold:
                        h_c = max(1, int(bgr_crop.shape[0] * 0.65))
                        roi_hsv = cv2.cvtColor(bgr_crop[:h_c], cv2.COLOR_BGR2HSV)
                        hsv_mean = roi_hsv.reshape(-1, 3).astype(np.float32).mean(axis=0)
                        slot_samples = self._warmup_per_slot.setdefault(box_i, [])
                        slot_samples.append((_early_score, hsv_mean))
                        slot_samples.sort(key=lambda x: -x[0])
                        del slot_samples[self._warmup_top_k:]
                        # Rebuild flat warmup_colors from all per-slot top-K samples
                        self._warmup_colors = [
                            hsv for samples in self._warmup_per_slot.values()
                            for _, hsv in samples
                        ]
                        if len(self._warmup_colors) >= self._warmup_needed:
                            self._calibrate_team_colors()
                        # Feed rolling buf for post-warmup periodic re-calibration
                        self._rolling_hsv_buf.append(hsv_mean)
                elif len(self._warmup_colors) < self._warmup_needed * 3:
                    # Fallback: after warmup window, still collect low-conf samples
                    # (maintains backward-compat for clips with no high-conf phase)
                    h_c = max(1, int(bgr_crop.shape[0] * 0.65))
                    roi_hsv = cv2.cvtColor(bgr_crop[:h_c], cv2.COLOR_BGR2HSV)
                    hsv_mean_fb = roi_hsv.reshape(-1, 3).astype(np.float32).mean(axis=0)
                    self._warmup_colors.append(hsv_mean_fb)
                    self._rolling_hsv_buf.append(hsv_mean_fb)
                    if len(self._warmup_colors) == self._warmup_needed:
                        self._calibrate_team_colors()
                else:
                    # Post-warmup: still feed the rolling buf for periodic re-calibration
                    h_c = max(1, int(bgr_crop.shape[0] * 0.65))
                    roi_hsv = cv2.cvtColor(bgr_crop[:h_c], cv2.COLOR_BGR2HSV)
                    self._rolling_hsv_buf.append(
                        roi_hsv.reshape(-1, 3).astype(np.float32).mean(axis=0)
                    )
                _cd_t0 = _subt.perf_counter()
                team = self._classify_team_dynamic(bgr_crop, team)
                _sp["classify_dyn"] += _subt.perf_counter() - _cd_t0
            _sp["warmup"] += _subt.perf_counter() - _wu_t0 - (_sp["classify_dyn"] if False else 0)

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
            high_conf = score >= self._conf_threshold
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
                "high_conf": high_conf,          # True if conf >= _conf_threshold
                "foot_xy":   (head_x, foot_y),  # pixel foot position for optical flow
                "kpts_xy":   det_kpts_xy,        # (17,2) COCO keypoints or None
                "kpts_conf": det_kpts_conf,       # (17,) per-kpt confidence or None
            })

        # ISSUE-005: batch update per-team color signatures (GPU when available)
        if self._color_tracker is not None and detections:
            _ct_t0 = _subt.perf_counter()
            _ct_crops = [d.get("crop_bgr") for d in detections]
            _ct_teams = [d["team"] for d in detections]
            if hasattr(self._color_tracker, "batch_update"):
                self._color_tracker.batch_update(_ct_crops, _ct_teams)
            else:
                for c, t in zip(_ct_crops, _ct_teams):
                    if c is not None:
                        self._color_tracker.update(c, t)
            _sp["ctrack_upd"] = _subt.perf_counter() - _ct_t0

        _sp["crops_step3"] = _subt.perf_counter() - _sp_last
        _sp_last = _subt.perf_counter()

        # ── Step 3.5: Deep appearance embeddings (OSNet batch inference) ──
        # Batch all detection crops through OSNet once per frame for efficiency.
        # F4: Skip OSNet on detections that moved <5px from nearest KF prediction.
        # Task 2: Also skip OSNet for slots that have been stably tracked for
        # ≥30 consecutive frames (4-frame skip window, ~40% OSNet call reduction).
        if self._use_deep and self._deep_extractor is not None and detections:
            # Slot-aware center lookup so we can match detections to specific slots
            kf_slot_centers = {
                s: ((b[1] + b[3]) / 2.0, (b[0] + b[2]) / 2.0)
                for s, b in self._kf_pred.items()
            }
            # Task 2: decrement stable-skip countdowns before checking
            for _s in self._stable_skip:
                if self._stable_skip[_s] > 0:
                    self._stable_skip[_s] -= 1
            slots_skipping = {s for s, c in self._stable_skip.items() if c > 0}

            def _det_moved(d: dict) -> bool:
                bb = d["bbox"]
                dcx, dcy = (bb[1] + bb[3]) / 2.0, (bb[0] + bb[2]) / 2.0
                if not kf_slot_centers:
                    return True
                best_slot, best_dist = None, float("inf")
                for _slot, (pcx, pcy) in kf_slot_centers.items():
                    dist = (dcx - pcx) ** 2 + (dcy - pcy) ** 2
                    if dist < best_dist:
                        best_dist, best_slot = dist, _slot
                # Task 2: skip OSNet if nearest slot is in stable-skip window
                if best_slot in slots_skipping:
                    return False
                return best_dist > 25.0  # F4: skip stationary detections

            moving_indices = [i for i, d in enumerate(detections) if _det_moved(d)]
            try:
                if moving_indices:
                    deep_embs = self._gpu_roi_extract(frame, detections, moving_indices)
                    if deep_embs is None:
                        # Fallback: CPU crop path
                        crops_for_deep = [detections[i]["crop_bgr"] for i in moving_indices]
                        deep_embs = self._deep_extractor.batch_extract(crops_for_deep)
                    for i, emb in zip(moving_indices, deep_embs):
                        detections[i]["deep_emb"] = emb
            except Exception:
                pass  # fall back to HSV per-det in downstream code

        _sp["osnet"] = _subt.perf_counter() - _sp_last
        _sp_last = _subt.perf_counter()

        # ── Step 4: Assignment — supervision ByteTrack (GPU) or custom two-stage
        _use_sv = self._sv_tracker is not None
        all_unmatched_dets: List[int] = []

        if _use_sv and detections:
            # supervision ByteTrack handles all teams at once
            _all_matched, _all_unmatched_slots, _all_unmatched_dets = \
                self._match_all_supervision(detections)
            # Process matched
            for slot, di in _all_matched:
                self._activate_slot(slot, detections[di], timestamp, stride)
            for slot in _all_unmatched_slots:
                self._lost_ages[slot] = self._lost_ages.get(slot, 0) + 1
                self._stable_frames[slot] = 0
                self._stable_skip[slot] = 0
                if self._lost_ages[slot] >= self._max_lost:
                    if slot in self._appearances:
                        self._gallery[slot] = self._appearances[slot].copy()
                        self._gallery_ages[slot] = 0
                    p = self.players[slot]
                    if p.positions:
                        last_frame = max(p.positions)
                        self._gallery_last_pos[slot] = p.positions[last_frame]
                    p.previous_bb = None
                    p.positions = {}
                    p.has_ball = False
                    self._kalmans.pop(slot, None)
                    self._appearances.pop(slot, None)
                    self._lost_ages[slot] = 0
            all_unmatched_dets = _all_unmatched_dets
        else:
            for team in ("green", "white", "referee"):
                matched, unmatched_slots, unmatched_dets = self._match_team_bytetrack(
                    team, detections
                )

                for slot, di in matched:
                    self._activate_slot(slot, detections[di], timestamp, stride)

                for slot in unmatched_slots:
                    self._lost_ages[slot] = self._lost_ages.get(slot, 0) + 1
                    self._stable_frames[slot] = 0
                    self._stable_skip[slot]   = 0
                    if self._lost_ages[slot] >= self._max_lost:
                        if slot in self._appearances:
                            self._gallery[slot] = self._appearances[slot].copy()
                            self._gallery_ages[slot] = 0
                        p = self.players[slot]
                        if p.positions:
                            last_frame = max(p.positions)
                            self._gallery_last_pos[slot] = p.positions[last_frame]
                        p.previous_bb = None
                        p.positions   = {}
                        p.has_ball    = False
                        self._kalmans.pop(slot, None)
                        self._appearances.pop(slot, None)
                        self._lost_ages[slot] = 0

                all_unmatched_dets.extend(unmatched_dets)

        # ── Age gallery entries and evict stale ones ──────────────────────
        # Always age regardless of ByteTrack — without aging the gallery bloats
        # with stale embeddings from early in the game, wasting memory and
        # causing false-positive re-IDs late in long clips.
        for slot in list(self._gallery_ages.keys()):
            self._gallery_ages[slot] += 1
            if self._gallery_ages[slot] >= self._gallery_ttl:
                self._gallery.pop(slot, None)
                self._gallery_ages.pop(slot, None)
                self._gallery_last_pos.pop(slot, None)

        # ── Step 5: Re-ID unmatched detections from lost-track gallery ────
        truly_new: List[int] = []
        for di in all_unmatched_dets:
            slot = self._reid(detections[di])
            if slot is not None:
                self._activate_slot(slot, detections[di], timestamp, stride)
            else:
                truly_new.append(di)

        # ── Step 6: Assign genuinely new detections to free slots ─────────
        for di in truly_new:
            det  = detections[di]
            for p in self.players:
                if p.team == det["team"] and p.previous_bb is None:
                    self._activate_slot(self._slot(p), det, timestamp, stride)
                    break

        # ── Step 6.5: Evict tracks frozen in place (velocity clamp stuck) ──
        # A track frozen for >20 consecutive frames is a false positive (coach,
        # scoreboard, or a SIFT-broken homography artifact) — evict it.
        _FREEZE_MAX = 20
        for p in self.players:
            slot = self._slot(p)
            if (self._freeze_age.get(slot, 0) >= _FREEZE_MAX
                    and p.previous_bb is not None
                    and not p.has_ball):  # never evict the confirmed ball-holder
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

        # ── Step 7.5: Optical flow gap-fill (batched) ────────────────────
        # Batch all lost-track flow points into a single calcOpticalFlowPyrLK
        # call — avoids per-player Python overhead on frames with multiple misses.
        gray_now = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is not None:
            of_candidates = [
                (self._slot(p), p, self._flow_pts[self._slot(p)])
                for p in self.players
                if (0 < self._lost_ages.get(self._slot(p), 0) <= OF_MAX_AGE
                    and self._slot(p) in self._flow_pts
                    and p.previous_bb is not None
                    and timestamp not in p.positions)
            ]
            if of_candidates:
                prev_pts_batch = np.array(
                    [c[2][0] for c in of_candidates], dtype=np.float32
                ).reshape(-1, 1, 2)
                try:
                    new_pts_batch, statuses, _ = cv2.calcOpticalFlowPyrLK(
                        self._prev_gray, gray_now, prev_pts_batch, None,
                        winSize=OF_WIN_SIZE,
                        maxLevel=OF_MAX_LEVEL,
                        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                                  10, 0.03),
                    )
                    for (slot, p, _), new_pt, status in zip(
                        of_candidates, new_pts_batch, statuses
                    ):
                        if status[0] != 1:
                            continue
                        fx, fy = int(new_pt[0, 0]), int(new_pt[0, 1])
                        if not (0 <= fx < frame.shape[1]
                                and 0 <= fy < frame.shape[0]):
                            continue
                        kpt  = np.array([fx, fy, 1], dtype=np.float64)
                        homo = M1 @ (M @ kpt.reshape(3, 1))
                        if abs(homo[2, 0]) > 1e-6:
                            homo = np.int32(homo / homo[2, 0]).ravel()
                            if (0 <= homo[0] < map_2d.shape[1]
                                    and 0 <= homo[1] < map_2d.shape[0]):
                                p.positions[timestamp] = (homo[0], homo[1])
                                self._flow_pts[slot] = new_pt  # advance anchor
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

        # Periodic re-calibration using a rolling window of the most recent
        # _rolling_hsv_buf detections rather than the ever-growing warmup buffer.
        # This lets the centroids adapt when teams change jerseys (home/away) or
        # lighting conditions shift mid-game, while the tighter 20-sample gate
        # prevents noisy re-calibration on sparse detection frames.
        # Skip during halftime/timeouts (suspended=True) to avoid studio footage.
        self._frames_since_calib += 1
        if (not suspended
                and self._frames_since_calib >= self._recalib_interval
                and len(self._rolling_hsv_buf) >= 50):
            # Swap warmup_colors to rolling window for this recalibration pass
            _saved = self._warmup_colors
            self._warmup_colors = list(self._rolling_hsv_buf)
            self._calibrate_team_colors(min_cluster_size=20)  # tighter gate than warmup's 5
            self._warmup_colors = _saved
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

        _sp["assign_render"] = _subt.perf_counter() - _sp_last
        _sp["total"]         = _subt.perf_counter() - _sp_t0
        return self._render(frame, map_2d, timestamp)

    # ── housekeeping ──────────────────────────────────────────────────────

    def _age_all(self, timestamp: int):
        """Age all tracks when a frame produces zero detections."""
        for i, p in enumerate(self.players):
            if p.previous_bb is not None:
                self._lost_ages[i] = self._lost_ages.get(i, 0) + 1
                # Task 2: reset stable counters — all players lost this frame
                self._stable_frames[i] = 0
                self._stable_skip[i]   = 0
                if self._lost_ages[i] >= MAX_LOST:
                    if i in self._appearances:
                        self._gallery[i] = self._appearances[i].copy()
                        self._gallery_ages[i] = 0
                    if p.positions:
                        last_frame = max(p.positions)
                        self._gallery_last_pos[i] = p.positions[last_frame]
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
                self._gallery_last_pos.pop(slot, None)


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
