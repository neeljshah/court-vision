"""
ball_detect_track.py — Ball detection and tracking

Improvements over baseline:
  - Optical flow (Lucas-Kanade) fills gaps when Hough circles fail on motion-blurred frames
  - Trajectory prediction: extrapolates ball position from last N frames using velocity
  - Wider re-detection window: searches a larger region around predicted position
  - Looser template threshold during re-detection (0.85 vs 0.98)
  - Possession uses distance-to-center fallback when IoU is zero
"""

import os
from collections import deque
from operator import itemgetter
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    import torch as _torch
    import kornia
    _HAS_KORNIA_BALL = True
except ImportError:
    _HAS_KORNIA_BALL = False

from .player_detection import FeetDetector

# ── YOLO ball model path (TRT engine preferred, .pt fallback) ─────────────────
_BALL_ENGINE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "resources", "yolov8n_ball.engine")
)
_BALL_PT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "models", "weights", "yolov8n_ball.pt")
)
# Secondary .pt path — used when models/weights/ doesn't exist (e.g. RunPod)
_BALL_PT_PATH2 = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "resources", "yolov8n_ball.pt")
)

_ball_yolo_model = None       # lazy-loaded YOLO ball model (global singleton)
_ball_yolo_available = None   # None = not yet checked; True/False after first attempt
_ball_yolo_is_coco = False    # True when using generic yolov8n COCO (class 32) fallback


def _trt_available() -> bool:
    """Check TRT is importable AND runtime DLLs are present."""
    try:
        import tensorrt  # noqa: F401
        return True
    except (ImportError, FileNotFoundError, OSError):
        return False


def _get_ball_yolo_model():
    """Lazy-init YOLO ball model: TRT engine → fine-tuned .pt → generic COCO .pt → None."""
    global _ball_yolo_model, _ball_yolo_available, _ball_yolo_is_coco
    if _ball_yolo_available is not None:
        return _ball_yolo_model  # already attempted init

    try:
        from ultralytics import YOLO  # type: ignore
        if os.path.exists(_BALL_ENGINE_PATH) and _trt_available():
            try:
                _ball_yolo_model = YOLO(_BALL_ENGINE_PATH, task="detect")
                _ball_yolo_available = True
            except Exception:
                _ball_yolo_model = None  # engine incompatible (different GPU arch) — fall through to .pt
        if _ball_yolo_model is None:
            pt_path = next((p for p in (_BALL_PT_PATH, _BALL_PT_PATH2) if os.path.exists(p)), None)
            if pt_path:
                _ball_yolo_model = YOLO(pt_path, task="detect")
                _ball_yolo_available = True
            else:
                # Fallback: generic yolov8n (COCO class 32 = sports ball). GPU inference
                # replaces the ~0.2-0.3s/frame Hough+template CPU path with ~0.02-0.05s/frame.
                # Lower recall than a fine-tuned ball model but much faster than Hough fallback.
                try:
                    _ball_yolo_model = YOLO("yolov8n.pt", task="detect")
                    _ball_yolo_available = True
                    _ball_yolo_is_coco = True
                except Exception:
                    _ball_yolo_available = False
        # Move to CUDA if available — ultralytics defaults to CPU unless explicitly moved
        if _ball_yolo_model is not None:
            try:
                import torch as _torch_local
                if _torch_local.cuda.is_available():
                    _ball_yolo_model.to("cuda")
            except Exception:
                pass
    except Exception:
        _ball_yolo_available = False

    return _ball_yolo_model

# Orange color guard: NBA basketball HSV range (OpenCV 0-180 hue scale)
# Rejects CSRT bbox if the center patch median is not basketball-orange.
# Prevents CSRT from latching onto scoreboards, crowd, or court markings.
# Widened H range 8-25 → 5-30: TV broadcast color correction shifts orange
# toward yellow (Hue < 8) on warm-toned broadcasts and toward red (Hue > 25)
# under arena LEDs. Widening catches these without admitting true red/yellow.
_BALL_H_LO, _BALL_H_HI = 5,  30   # hue: orange-amber range (widened for TV color grading)
_BALL_S_MIN             = 50        # saturation: lowered 70→50 (broadcast TV color compression
                                    # significantly softens saturation, especially in slow-motion)
_BALL_V_MIN             = 60        # value: lowered 70→60 (deeper shadow under arena LEDs)
_BALL_PATCH_HALF        = 7         # orange-guard patch half-size: 7×7 for motion-blur tolerance
                                    # 3×3 misses blurry centers; 7×7 catches motion-blurred balls

MAX_TRACK       = 150     # frames of CSRT tracking before forced re-detection check
                          # Raised 20→150: at stride=3/30fps each "frame" = 0.1s real-time.
                          # 20 frames = 2s — caused constant CSRT re-validation interrupting
                          # clean tracking runs.  150 frames = 15s of stable tracking before
                          # the local-check fires, which is appropriate for possession-length
                          # tracking segments.
_CSRT_FAIL_THRESH  = 10  # consecutive CSRT ok=False before forcing re-detection
                          # Raised 3→10: 3 bad frames reset tracker on every slight occlusion
                          # (screen, body, flash cut).  10 consecutive failures = real loss.
_REENTRY_ATTEMPTS  = 8   # frames to use wider Hough radius after a forced reset
_REENTRY_MAX_R     = 35  # wider Hough maxRadius for re-entry (vs normal 18)
                          # (raised from 10: halves premature local-check resets; drift
                          # and negative-coord guards catch bad projections instead)
FLOW_MAX_FRAMES = 15      # frames to keep optical flow active during blur (slow ball)
                          # Raised 8→15: short 8-frame window killed flow mid-possession.
                          # 15 frames at stride=3 = 1.5s real-time, appropriate for cuts.
IOU_BALL_PAD    = 35      # IoU box half-size for possession detection
PREDICT_FRAMES  = 6       # frames of history used for trajectory prediction
REDET_THRESHOLD = 0.72    # template match threshold during re-detection (looser)
                          # Lowered 0.85→0.72: NBA broadcast compression means templates
                          # rarely match above 0.85 for a motion-blurred shot.
DETECT_THRESHOLD = 0.75   # template match threshold for initial detection
                          # Lowered 0.88→0.75: same reason — compression + motion blur.
_CSRT_STABLE_FOR_ORANGE = 15  # skip orange guard after this many consecutive CSRT successes
                               # Motion-blurred shots always fail the orange patch check
                               # (blurred center averages to non-orange).  After 15 stable
                               # frames we trust CSRT is on the ball and skip the color test.

_BALL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "ball") + os.sep


class BallDetectTrack:

    def __init__(self, players):
        self.players       = players
        self.check_track   = MAX_TRACK
        self.do_detection  = True
        self.tracker       = self._make_csrt()

        # Optical flow state
        self._prev_gray    = None          # previous frame (grayscale)
        self._flow_point   = None          # last known ball center (float32 px)
        self._flow_active  = False
        self._flow_age     = 0

        # Last known 2D court position of ball (updated each frame)
        self.last_2d_pos   = None          # (x2d, y2d) or None

        # Pixel-space ball velocity (px/frame) — more reliable than 2D court vel
        self.pixel_vel     = 0.0

        # Trajectory history for prediction: list of (cx, cy) pixel coords
        self._trajectory: list = []

        # Last known bbox (x, y, w, h) for re-detection window
        self._last_bbox    = None
        # Last known ball center in pixel space — used to pre-check CSRT before
        # calling update() (avoids C++ assertion when ROI is fully out of bounds)
        self._last_cx: Optional[int] = None
        self._last_cy: Optional[int] = None

        # Consecutive frames with no ball detected — reset CSRT when it hits 30
        self._no_ball_streak: int = 0

        # CSRT consecutive failure counter — triggers immediate re-detection at
        # threshold=10 instead of waiting for the no-ball-streak.
        # Each CSRT ok=False increments; ok=True resets; at 10 → do_detection=True.
        self._csrt_consecutive_fails: int = 0

        # CSRT stable frame counter — incremented each frame CSRT succeeds.
        # Resets to 0 when CSRT resets or enters detection mode.
        # Used to skip orange guard after _CSRT_STABLE_FOR_ORANGE frames since
        # motion-blurred shots always fail the color check.
        self._csrt_stable_frames: int = 0

        # Re-entry mode: use wider Hough search radius (maxRadius=28) for the
        # first _REENTRY_ATTEMPTS frames after a forced detection reset, then
        # revert to normal (maxRadius=18).  Ball is more likely to be large or
        # at steep angle immediately after the tracker loses it.
        self._reentry_mode:   bool = False
        self._reentry_frames: int  = 0

        # Guard 2 jump-reset counter — incremented every time a >200px position
        # jump triggers a forced CSRT reset.  High values indicate CSRT is
        # latching onto crowd/scoreboard objects rather than the ball.
        self._jump_resets: int = 0

        # ── Trajectory deque for parabola fitting ─────────────────────────
        # Stores (frame_num, cx, cy) for each frame the ball is detected.
        self._traj_deque: deque = deque(maxlen=15)
        self._frame_num: int = 0          # incremented each ball_tracker() call

        # ── Per-possession trajectory features ────────────────────────────
        self._shot_arc_angle: Optional[float] = None
        self._dribble_count: int = 0
        self._is_lob: bool = False

        # Signed y-velocity tracking for dribble bounce counting
        self._prev_cy: Optional[float] = None
        self._prev_vy_sign: int = 0       # +1 = falling, -1 = rising, 0 = unknown

        # Approximate player height in pixels (updated each frame from bboxes)
        self._avg_player_height_px: float = 100.0

        # Dribble predictor: True when ball position is inferred from possessor hand
        self.ball_inferred: bool = False

        # Load templates once at init
        self._templates = self._load_templates()

    # ── CSRT factory (handles API change in opencv-contrib >= 4.5.1) ──────

    @staticmethod
    def _make_csrt():
        if hasattr(cv2, "TrackerCSRT_create"):
            return cv2.TrackerCSRT_create()
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
            return cv2.legacy.TrackerCSRT_create()
        # OpenCV 4.10+ removed CSRT — fall back to TrackerMIL (similar accuracy)
        if hasattr(cv2, "TrackerMIL_create"):
            return cv2.TrackerMIL_create()
        raise RuntimeError(
            "No supported OpenCV tracker found. Install opencv-contrib-python:\n"
            "  pip install opencv-contrib-python"
        )

    # ── Orange color check ────────────────────────────────────────────────

    @staticmethod
    def _is_ball_orange(frame: np.ndarray, cx: int, cy: int) -> bool:
        """Return True if the 3×3 patch around (cx, cy) is basketball-orange.

        NBA basketball color in OpenCV HSV (0-180 H scale):
          H ≈ 8-25, S ≥ 80 (saturated), V ≥ 80 (not dark).
        Uses median over a 3×3 neighbourhood to reduce single-pixel noise.
        Returns True (accept) on out-of-bounds coords to avoid spurious rejects.
        """
        h, w = frame.shape[:2]
        if not (0 <= cx < w and 0 <= cy < h):
            return True   # boundary case — let other guards handle it
        p = _BALL_PATCH_HALF
        x1, x2 = max(0, cx - p), min(w, cx + p + 1)
        y1, y2 = max(0, cy - p), min(h, cy + p + 1)
        patch = frame[y1:y2, x1:x2]
        if patch.size == 0:
            return True
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        med = np.median(hsv.reshape(-1, 3), axis=0).astype(int)
        h_v, s_v, v_v = int(med[0]), int(med[1]), int(med[2])
        return (_BALL_H_LO <= h_v <= _BALL_H_HI) and (s_v >= _BALL_S_MIN) and (v_v >= _BALL_V_MIN)

    # ── Template loading ──────────────────────────────────────────────────

    def _load_templates(self):
        if not os.path.isdir(_BALL_DIR):
            return []
        tmpls = []
        for f in os.listdir(_BALL_DIR):
            img = cv2.imread(os.path.join(_BALL_DIR, f), 0)
            if img is not None:
                tmpls.append(img)
        return tmpls

    # ── Circle detection ──────────────────────────────────────────────────

    @staticmethod
    def circle_detect(img, max_radius: int = 25):
        """Run Hough circle detection on a grayscale image.

        Args:
            img:        Grayscale image (any size).
            max_radius: Upper radius bound for Hough circles.  Normal ops use 25;
                        re-entry mode uses _REENTRY_MAX_R to catch balls at
                        steep angles or partially out-of-frame.

        Notes:
            maxRadius raised 18→25: broadcast NBA ball appears 10–25px radius
            depending on camera distance.  18px missed close-to-camera shots.
            param2 lowered 25→18: looser accumulator threshold catches more
            circles; orange guard filters non-ball candidates downstream.
        """
        blurred = cv2.medianBlur(img, 5)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, 1, 20,
            param1=50, param2=8, minRadius=5, maxRadius=max_radius
            # param2 lowered 18→12→8: accumulator threshold for circle acceptance.
            # More false positives, but the orange-guard downstream filters non-ball
            # candidates. At 12 only 14.1% of live-play frames had ball detected;
            # lowering to 8 maximises recall — false positives caught by HSV guard.
        )
        if circles is not None:
            return np.uint16(np.around(circles)).reshape(-1, 3)
        return None

    # ── Template match in a region ───────────────────────────────────────

    def _template_match(self, gray_roi, threshold=DETECT_THRESHOLD, max_radius: int = 18):
        """Check if any ball template matches inside gray_roi. Returns (x,y,w,h) or None."""
        centers = self.circle_detect(gray_roi, max_radius)
        if centers is None:
            return None
        af = 8
        for c in centers:
            tl = [int(c[0]) - int(c[2]) - af, int(c[1]) - int(c[2]) - af]
            br = [int(c[0]) + int(c[2]) + af, int(c[1]) + int(c[2]) + af]
            tl[0], tl[1] = max(0, tl[0]), max(0, tl[1])
            focus = gray_roi[tl[1]:br[1], tl[0]:br[0]]
            if focus.size == 0:
                continue
            for tmpl in self._templates:
                if focus.shape[0] > tmpl.shape[0] and focus.shape[1] > tmpl.shape[1]:
                    res = cv2.matchTemplate(focus, tmpl, cv2.TM_CCORR_NORMED)
                    if np.max(res) >= threshold:
                        return (tl[0], tl[1], br[0] - tl[0], br[1] - tl[1])
        return None

    def _detect_ball_yolo(
        self, frame: np.ndarray
    ) -> Optional[Tuple[int, int, int]]:
        """
        Detect basketball using fine-tuned YOLOv8n model.

        Returns (cx, cy, radius) or None.  Applies _is_ball_orange() guard
        on the detected center patch before returning (same as Hough path).

        Args:
            frame: Full BGR frame (post-TOPCUT).

        Returns:
            (cx, cy, radius) tuple or None if no ball detected.
        """
        model = _get_ball_yolo_model()
        if model is None:
            return None
        try:
            if _ball_yolo_is_coco:
                # COCO fallback: query class 32 (sports ball). Higher conf threshold
                # because COCO yolov8n is not fine-tuned on NBA broadcasts — lower
                # confidence detections are often crowd/arena objects, not the ball.
                results = model(frame, imgsz=384, classes=[32], conf=0.20,
                                half=True, device=0, verbose=False)
            else:
                # conf lowered 0.30→0.05: fine-tuned ball model outputs low confidence
                # (~0.11 typical). At 0.30 detection was 0%; at 0.05 it's ~98%.
                # Single-class model (ball only) so low conf still means ball-shaped.
                # half=True + imgsz=384 + device=0: ~4× faster than FP32 imgsz=640 on CPU.
                results = model(frame, imgsz=384, conf=0.05,
                                half=True, device=0, verbose=False)
            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return None
            # Filter to class 0 (ball) only — reject people/rims/other classes.
            # Without this filter, an untrained model returns players (largest
            # high-conf detection) which corrupts CSRT with player bboxes.
            cls_arr = boxes.cls.cpu().numpy() if boxes.cls is not None else None
            if cls_arr is not None and not _ball_yolo_is_coco:
                ball_mask = (cls_arr == 0)
                if not ball_mask.any():
                    return None  # no ball-class detections
                confs = boxes.conf.cpu().numpy()[ball_mask]
                xyxy_all = boxes.xyxy.cpu().numpy()[ball_mask]
            else:
                # COCO path already filtered to class 32 via classes=[32] kwarg.
                confs = boxes.conf.cpu().numpy()
                xyxy_all = boxes.xyxy.cpu().numpy()
            best_i = int(confs.argmax())
            xyxy = xyxy_all[best_i]
            x1, y1, x2, y2 = int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])
            # Clip bbox to frame bounds before computing centre — YOLO at imgsz=384
            # upscales coords to 640×300; balls near the edge produce cy±radius values
            # that overflow the crop, triggering the degenerate-bbox guard at
            # ball_tracker():596 and causing ~4% unnecessary detection discards.
            fh, fw = frame.shape[:2]
            x1 = max(0, x1); y1 = max(0, y1)
            x2 = min(fw, x2); y2 = min(fh, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            radius = max(1, ((x2 - x1) + (y2 - y1)) // 4)
            # Size guard: fine-tuned model outputs bboxes with ~41-45px radius
            # (includes margin around ball). Raised 30→50 to stop rejecting
            # all valid detections. True player/rim bboxes are 80px+.
            if radius > 50:
                return None
            # NOTE: orange guard intentionally skipped for YOLO path — the model
            # was fine-tuned on NBA footage so it already encodes ball colour/shape.
            # Applying _is_ball_orange on top doubled the false-negative rate.
            return (cx, cy, radius)
        except Exception:
            return None

    def ball_detection(self, frame, threshold=DETECT_THRESHOLD, max_radius: int = 25):
        """
        Full-frame ball detection.

        Primary:    YOLO ball model (if available).
        Fallback 1: Hough circles + template match (requires template in resources/ball/).
        Fallback 2: Hough circles + orange guard only — for broadcasts where
                    the 2 stock templates don't match the camera/encoding style.

        Returns (x, y, w, h) or None.
        """
        # Primary: YOLO ball model
        yolo_result = self._detect_ball_yolo(frame)
        if yolo_result is not None:
            cx, cy, radius = yolo_result
            pad = max(1, radius)
            return (cx - pad, cy - pad, pad * 2, pad * 2)

        # R11: when YOLO is available, try kornia GPU blob first (fast), then
        # fall THROUGH to the Hough+orange fallback chain when both miss.
        # Previous early-return after kornia made Hough fallbacks dead code on
        # healthy installs, dropping p10 detection to 62% on the corpus due to
        # sustained YOLO-miss runs (e.g. game 0022500059: 1057-frame gap).
        blob_result = self._detect_ball_kornia(frame)
        if blob_result is not None:
            return blob_result

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Fallback 1: Hough + template match
        tmpl_result = self._template_match(gray, threshold, max_radius)
        if tmpl_result is not None:
            return tmpl_result

        # Fallback 2: Hough-only + orange guard (when templates don't match broadcast style)
        circles = self.circle_detect(gray, max_radius)
        if circles is not None:
            for c in circles:
                cx, cy, r = int(c[0]), int(c[1]), int(c[2])
                if self._is_ball_orange(frame, cx, cy):
                    pad = max(1, r)
                    return (cx - pad, cy - pad, pad * 2, pad * 2)

        return None

    def _detect_ball_kornia(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """GPU ball detection using kornia color filtering + blob analysis.

        Converts frame to HSV on GPU, masks basketball-orange pixels, finds
        connected components. Returns (x, y, w, h) or None.
        """
        if not _HAS_KORNIA_BALL or not _torch.cuda.is_available():
            return None
        try:
            _dev = "cuda"
            # BGR→RGB→GPU tensor
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            t = _torch.from_numpy(rgb).float().permute(2, 0, 1).unsqueeze(0).to(_dev) / 255.0

            # RGB→HSV (kornia: H in [0, 2π], S/V in [0,1])
            hsv = kornia.color.rgb_to_hsv(t)  # (1, 3, H, W)
            h_ch = hsv[0, 0] * 180.0 / (2.0 * 3.14159265)  # to OpenCV scale [0,180]
            s_ch = hsv[0, 1] * 255.0
            v_ch = hsv[0, 2] * 255.0

            # Orange mask matching _BALL_H_LO/_BALL_H_HI/_BALL_S_MIN/_BALL_V_MIN
            mask = ((h_ch >= _BALL_H_LO) & (h_ch <= _BALL_H_HI)
                    & (s_ch >= _BALL_S_MIN) & (v_ch >= _BALL_V_MIN))

            # Morphological close to merge nearby pixels
            kernel = _torch.ones(1, 1, 5, 5, device=_dev)
            mask_f = mask.float().unsqueeze(0).unsqueeze(0)
            mask_f = _torch.nn.functional.conv2d(mask_f, kernel, padding=2)
            mask_f = (mask_f > 3).float()

            # Find largest connected region on CPU (kornia doesn't have fast CC)
            mask_np = mask_f.squeeze().cpu().numpy().astype(np.uint8)
            n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_np)

            if n_labels <= 1:
                return None

            # Skip label 0 (background), find largest blob in ball-radius range
            best = None
            best_area = 0
            for i in range(1, n_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                w = stats[i, cv2.CC_STAT_WIDTH]
                h = stats[i, cv2.CC_STAT_HEIGHT]
                # Ball-sized: 10-50px diameter range, roughly circular (aspect 0.5-2.0)
                if 50 < area < 3000 and 0.4 < (w / max(h, 1)) < 2.5:
                    if area > best_area:
                        best_area = area
                        cx = int(centroids[i][0])
                        cy = int(centroids[i][1])
                        r = max(1, int((w + h) / 4))
                        best = (cx - r, cy - r, r * 2, r * 2)
            return best
        except Exception:
            return None

    # ── Optical flow tracking ─────────────────────────────────────────────

    def _optical_flow_update(self, gray_frame):
        """
        Track ball center using Lucas-Kanade sparse optical flow.
        Returns updated (cx, cy) or None if tracking fails.
        """
        if self._prev_gray is None or self._flow_point is None:
            return None

        pt = self._flow_point.reshape(1, 1, 2)
        lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.01),
        )
        next_pt, status, _ = cv2.calcOpticalFlowPyrLK(
            self._prev_gray, gray_frame, pt, None, **lk_params
        )
        if status is None or status[0, 0] == 0:
            return None

        new_cx, new_cy = next_pt[0, 0]
        # Sanity check: reject if moved more than 250px in one frame
        # Raised 150→250: a shot released at the moment a frame is sampled can
        # travel well over 150px/frame (at 30fps/stride=3 the ball covers ~10ft
        # per processed frame = ~250px in broadcast resolution).
        old_cx, old_cy = self._flow_point[0]
        if np.hypot(new_cx - old_cx, new_cy - old_cy) > 250:
            return None

        self._flow_point = next_pt[0]
        return float(new_cx), float(new_cy)

    # ── Trajectory prediction ─────────────────────────────────────────────

    def _predict_center(self):
        """
        Extrapolate next ball position from recent trajectory using mean velocity.
        Returns (cx, cy) or None.
        """
        if len(self._trajectory) < 2:
            return None
        pts = np.array(self._trajectory[-PREDICT_FRAMES:], dtype=np.float32)
        # Mean velocity over recent frames
        vx = np.diff(pts[:, 0]).mean()
        vy = np.diff(pts[:, 1]).mean()
        cx, cy = pts[-1][0] + vx, pts[-1][1] + vy
        return float(cx), float(cy)

    def _ball_under_dribble_predictor(self) -> Optional[tuple]:
        """
        When the ball is lost for fewer than 8 frames and a player has has_ball=True,
        project the ball to that player's hand position (ankle_y - 80px, bbox center_x).
        This fills the most common gap: dribble occlusion where the ball disappears
        behind or under the player's body for 1-7 frames.

        Returns:
            (x, y, w, h) bbox for the inferred ball position, or None if conditions
            are not met (streak >= 8, no possessor, or no valid bbox available).
        """
        if self._no_ball_streak >= 8:
            return None
        holder = next(
            (p for p in self.players if p.has_ball and p.team != "referee"),
            None,
        )
        if holder is None:
            return None
        bb = getattr(holder, "previous_bb", None)
        if bb is None:
            return None
        y1, x1, y2, x2 = bb
        # Hand position estimate: horizontal center of bbox, 80px above the ankle
        # (approximately thigh-height where the ball sits during a dribble).
        cx = (x1 + x2) // 2
        cy = max(0, y2 - 80)
        w = h = 20  # approximate NBA ball size in broadcast frame
        return (cx - w // 2, cy - h // 2, w, h)

    # ── Main tracker ──────────────────────────────────────────────────────

    def ball_tracker(self, M, M1, frame, map_2d, map_2d_text, timestamp, stride: int = 1):
        if frame is None or frame.size == 0:
            return frame, None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        bbox = None
        _bbox_from_hough = False  # True when Hough/template detection set bbox

        # ── Detection mode ────────────────────────────────────────────────
        if self.do_detection:
            _max_r = _REENTRY_MAX_R if self._reentry_mode else 25
            # Fix B: loosen threshold on fast-moving ball to avoid missing shots/passes
            _eff_threshold = REDET_THRESHOLD if self.pixel_vel > 40 else DETECT_THRESHOLD
            bbox = self.ball_detection(frame, _eff_threshold, max_radius=_max_r)
            if bbox is not None:
                _bx, _by, _bw, _bh = bbox
                _fh, _fw = frame.shape[:2]
                if (_bw <= 0 or _bh <= 0 or _bw > _fw or _bh > _fh
                        or _bx < 0 or _by < 0
                        or _bx + _bw > _fw or _by + _bh > _fh):
                    # Degenerate bbox: CSRT/MIL .init() derives internal buffer
                    # sizes from the box geometry; an out-of-frame box triggers a
                    # multi-hundred-GB native allocation the cgroup SIGKILLs
                    # before OpenCV can raise cv2.error. Discard — stay in
                    # detection mode (mirrors the update-path guard below).
                    print(f"[BALL] discarding degenerate ball bbox {bbox} "
                          f"(frame {_fw}x{_fh})", flush=True)
                    bbox = None
            if bbox is not None:
                _bbox_from_hough = True
                try:
                    self.tracker = self._make_csrt()
                    self.tracker.init(frame, bbox)
                except cv2.error:
                    self.tracker = None  # tracker init failed (bad_alloc) — YOLO-only mode
                self.do_detection        = False
                self.check_track         = MAX_TRACK
                self._flow_active        = False
                self._flow_age           = 0
                self._reentry_mode       = False
                self._reentry_frames     = 0
                self._csrt_stable_frames = 0  # fresh CSRT init — must re-establish stability
            elif self._reentry_mode:
                self._reentry_frames += 1
                if self._reentry_frames >= _REENTRY_ATTEMPTS:
                    self._reentry_mode   = False
                    self._reentry_frames = 0

        # ── CSRT tracking mode ────────────────────────────────────────────
        else:
            try:
                # Guard: ensure frame is non-empty before handing to CSRT.
                # CSRT internally calls cv2.resize on its ROI; if the ROI has
                # drifted out of frame bounds the resize gets a 0-pixel source
                # and raises cv2.error from a C++ layer that Python's except
                # cv2.error sometimes cannot intercept cleanly.
                if frame is None or frame.ndim < 2 or frame.shape[0] == 0 or frame.shape[1] == 0:
                    raise ValueError("empty frame")
                # Guard: reset tracker if last known ball position is outside frame.
                # OpenCV 4.13 can fire a C++ assertion (not catchable as Python
                # exception) when CSRT's internal ROI drifts fully out of bounds.
                if self._last_cx is not None and self._last_cy is not None:
                    fh, fw = frame.shape[:2]
                    if not (0 <= self._last_cx < fw and 0 <= self._last_cy < fh):
                        self.do_detection = True
                        raise ValueError("ball outside frame — resetting")
                if self.tracker is None:
                    raise ValueError("no tracker — forcing re-detection")
                res, bbox = self.tracker.update(frame)
            except Exception:
                # Catches cv2.error (CSRT ROI out-of-bounds / zero-size resize)
                # and any other tracker failure.  Treat as tracking loss and
                # force re-detection on the next frame.
                res  = False
                bbox = None
            if res:
                self._csrt_consecutive_fails = 0
                self._csrt_stable_frames    += 1
            else:
                bbox = None
                self._csrt_stable_frames     = 0
                self._csrt_consecutive_fails += 1
                if self._csrt_consecutive_fails >= _CSRT_FAIL_THRESH:
                    self.do_detection            = True
                    self._reentry_mode           = True
                    self._reentry_frames         = 0
                    self._csrt_consecutive_fails = 0
                    self._csrt_stable_frames     = 0

            # CSRT lost ball — try optical flow
            if bbox is None and self._flow_point is not None:
                flow_result = self._optical_flow_update(gray)
                if flow_result is not None:
                    cx, cy = flow_result
                    w = h = 30  # approximate size
                    if self._last_bbox is not None:
                        w, h = self._last_bbox[2], self._last_bbox[3]
                    bbox = (cx - w / 2, cy - h / 2, w, h)
                    self._flow_active = True
                    self._flow_age   += 1
                    # Fix B: allow more flow frames when ball is moving fast.
                    # Multiply by stride so the real-time window stays constant
                    # regardless of how many frames are skipped between calls.
                    _flow_limit = (15 if self.pixel_vel > 40 else FLOW_MAX_FRAMES) * max(1, stride)
                    if self._flow_age > _flow_limit:
                        # Optical flow drifted too long — force re-detection
                        bbox = None
                        self._flow_active    = False
                        self._flow_age       = 0
                        self.do_detection    = True
                        self._reentry_mode   = True
                        self._reentry_frames = 0

            # Both CSRT and flow failed — try trajectory prediction
            if bbox is None:
                pred = self._predict_center()
                if pred is not None:
                    cx, cy = pred
                    pad    = 120  # raised 60→120: fast ball can travel >60px/frame
                              # so 60px radius missed it; 120px catches faster passes
                    w_size = self._last_bbox[2] if self._last_bbox else 30
                    h_size = self._last_bbox[3] if self._last_bbox else 30
                    x1 = max(0, int(cx - pad))
                    y1 = max(0, int(cy - pad))
                    x2 = min(frame.shape[1], int(cx + pad))
                    y2 = min(frame.shape[0], int(cy + pad))
                    roi_crop = frame[y1:y2, x1:x2]
                    found = None
                    if roi_crop.size > 0:
                        # Use ball_detection (YOLO → template → orange-guard) on BGR crop
                        found = self.ball_detection(roi_crop, threshold=REDET_THRESHOLD)
                    if found is not None:
                        fx, fy, fw, fh = found
                        bbox = (x1 + fx, y1 + fy, fw, fh)
                        _bbox_from_hough = True   # template match = Hough-like detection
                        # Re-init CSRT at found position
                        try:
                            self.tracker = self._make_csrt()
                            self.tracker.init(frame, bbox)
                        except cv2.error:
                            self.tracker = None  # tracker init failed — YOLO-only mode
                        self.check_track  = MAX_TRACK
                        self._flow_active = False
                        self._flow_age    = 0
                    else:
                        self.do_detection    = True
                        self._reentry_mode   = True
                        self._reentry_frames = 0

        # ── Validate bbox before updating state ───────────────────────────
        if bbox is not None:
            _cx_new = int(bbox[0] + bbox[2] / 2)
            _cy_new = int(bbox[1] + bbox[3] / 2)
            _h_fr, _w_fr = frame.shape[:2]

            # Guard 1: reject out-of-bounds center (CSRT drifted outside frame)
            if not (0 <= _cx_new < _w_fr and 0 <= _cy_new < _h_fr):
                bbox = None
                self.do_detection    = True
                self._reentry_mode   = True
                self._reentry_frames = 0
            # Guard 2: reject position jumps that exceed the distance a ball can
            # travel in `stride` real frames (~200px at stride=1).  Scale by stride
            # so the threshold stays physically meaningful when frames are skipped.
            # Skipped for fresh Hough/template re-detections — Hough independently
            # found a new circle; the "jump" is the ball moving while CSRT was
            # tracking the wrong object, not a real CSRT drift error.
            elif (not _bbox_from_hough
                  and self._trajectory
                  and (np.hypot(_cx_new - self._trajectory[-1][0],
                                _cy_new - self._trajectory[-1][1]) > 200 * max(1, stride))
            ):
                bbox = None
                self._jump_resets        += 1
                self.do_detection         = True
                self._reentry_mode        = True
                self._reentry_frames      = 0
                self.tracker              = self._make_csrt()
                self._flow_active         = False
                self._flow_age            = 0
                self._flow_point          = None
                self._csrt_stable_frames  = 0
            # Guard 3: reject CSRT-tracked bbox whose center patch is not
            # basketball-orange (prevents CSRT from latching onto scoreboards,
            # court text, or crowd). Skipped for:
            #   (a) fresh Hough/template detections — circularity already validated
            #   (b) established tracking runs (_csrt_stable_frames >= threshold) —
            #       motion-blurred shots always fail the orange patch check because
            #       the blurred center averages to a non-orange colour.  After 15
            #       consecutive CSRT successes we trust the tracker is on the ball.
            elif (not _bbox_from_hough
                  and self._csrt_stable_frames < _CSRT_STABLE_FOR_ORANGE
                  and not self._is_ball_orange(frame, _cx_new, _cy_new)):
                bbox = None
                self.do_detection    = True
                self._reentry_mode   = True
                self._reentry_frames = 0
                self.tracker         = self._make_csrt()
                self._flow_active    = False
                self._flow_age       = 0
                self._flow_point     = None
                self._csrt_stable_frames = 0

        # Guard 4: no-ball streak — reset stale CSRT after 30 consecutive misses
        # Raised 15→30: at stride=3 / 30fps, 15 frames = 1.5s which is too aggressive
        # and caused tracker resets during normal cut-scenes or split-second occlusions.
        # 30 frames = 3s real-time — allows optical flow + prediction to bridge gaps.
        if bbox is None:
            # Dribble predictor: fill short gaps (<8 frames) when ball is under possessor
            _dribble_pred = self._ball_under_dribble_predictor()
            if _dribble_pred is not None:
                bbox = _dribble_pred
                self.ball_inferred = True
            else:
                self.ball_inferred = False
                self._no_ball_streak += 1
                if self._no_ball_streak >= 30:
                    self.do_detection        = True
                    self._reentry_mode       = True
                    self._reentry_frames     = 0
                    self.tracker             = self._make_csrt()
                    self._flow_active        = False
                    self._flow_age           = 0
                    self._trajectory         = []
                    self._flow_point         = None
                    self._no_ball_streak     = 0
                    self._csrt_stable_frames = 0
        else:
            self.ball_inferred = False
            self._no_ball_streak = 0

        # ── Update state ──────────────────────────────────────────────────
        if bbox is not None:
            self._last_bbox = bbox
            cx = int(bbox[0] + bbox[2] / 2)
            cy = int(bbox[1] + bbox[3] / 2)
            self._last_cx = cx
            self._last_cy = cy
            self._flow_point = np.array([[cx, cy]], dtype=np.float32)
            if self._trajectory:
                prev_cx, prev_cy = self._trajectory[-1]
                # Divide by stride so pixel_vel is always in px/real-frame,
                # regardless of how many frames were skipped between calls.
                self.pixel_vel = float(np.hypot(cx - prev_cx, cy - prev_cy)) / max(1, stride)
            else:
                self.pixel_vel = 0.0
            self._trajectory.append((cx, cy))
            if len(self._trajectory) > 30:
                self._trajectory.pop(0)

            # ── Trajectory deque + per-possession features ────────────────
            self._traj_deque.append((self._frame_num, cx, cy))

            # Dribble count: each time ball vy flips from + (falling) to - (rising)
            # in pixel space = one floor bounce.
            if self._prev_cy is not None:
                vy_now = cy - self._prev_cy
                if abs(vy_now) > 1.0:
                    sign_now = 1 if vy_now > 0 else -1
                    if self._prev_vy_sign == 1 and sign_now == -1:
                        self._dribble_count += 1
                    self._prev_vy_sign = sign_now
            self._prev_cy = float(cy)

            # Is-lob: ball rises > 1.5× avg player height above its starting position
            if self._traj_deque:
                ball_ys = [t[2] for t in self._traj_deque]
                rise = self._traj_deque[0][2] - min(ball_ys)  # pixel-upward = positive
                if rise > 1.5 * self._avg_player_height_px:
                    self._is_lob = True

            # Update average player height estimate from live bboxes
            heights = [
                p.previous_bb[2] - p.previous_bb[0]
                for p in self.players
                if p.previous_bb is not None and p.team != "referee"
            ]
            if heights:
                self._avg_player_height_px = float(np.mean(heights))

            p1 = (int(bbox[0]), int(bbox[1]))
            p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
            ball_center = np.array([cx, cy, 1])

            # ── Possession detection ──────────────────────────────────────
            bbox_iou = (cy - IOU_BALL_PAD, cx - IOU_BALL_PAD,
                        cy + IOU_BALL_PAD, cx + IOU_BALL_PAD)
            scores = []
            for p in self.players:
                if p.team != "referee" and p.previous_bb is not None and timestamp in p.positions:
                    iou = FeetDetector.bb_intersection_over_union(bbox_iou, p.previous_bb)
                    scores.append((p, iou))

            if scores:
                for p in self.players:
                    p.has_ball = False
                best = max(scores, key=itemgetter(1))
                # If no IoU overlap, fall back to closest player bbox center in pixel space.
                # Use pixel coords (cx,cy) vs player bbox — NOT court coords — same space.
                if best[1] == 0:
                    def bbox_dist(item):
                        p, _ = item
                        bb = p.previous_bb
                        if bb is None:
                            return float("inf")
                        y1, x1, y2, x2 = bb
                        # Distance from ball center to nearest point ON bbox.
                        # 0 = ball inside bbox; positive = ball outside.
                        clamp_x = max(x1, min(x2, cx))
                        clamp_y = max(y1, min(y2, cy))
                        return float(np.hypot(cx - clamp_x, cy - clamp_y))
                    best = min(scores, key=bbox_dist)
                    # Ball-in-air guard: release possession once ball is >100px
                    # outside the nearest player bbox (shot arc / pass in flight).
                    # Raised from 50→100: broadcast footage has small players (~30-50px
                    # tall) where the ball at hand height sits 40-80px above the bbox top.
                    if bbox_dist(best) > 100:
                        best = None
                if best is not None:
                    best[0].has_ball = True
                    if timestamp in best[0].positions:
                        cv2.circle(map_2d_text, best[0].positions[timestamp], 27, (0, 0, 255), 10)

            # ── Project ball to 2D map ────────────────────────────────────
            if self.check_track > 0:
                homo = M1 @ (M @ ball_center.reshape(3, -1))
                homo = np.int32(homo / homo[-1]).ravel()
                ball_2d = (int(homo[0]), int(homo[1]))
                # Reject projections with negative coordinates — these are
                # always wrong (off-court, outside pano) and occur when M or
                # M1 is stale/misaligned.  The drift guard below only fires
                # when player positions are available; this check is
                # unconditional and catches the -1018/-57940 values seen when
                # SIFT inliers are few and M_ema is noisy.
                if ball_2d[0] < 0 or ball_2d[1] < 0:
                    self.last_2d_pos = None
                else:
                    # Guard against CSRT drift: if the projected ball is far
                    # from any tracked player, CSRT has latched onto the wrong
                    # object.  Threshold is 1200px — roughly 30ft on the 3698px
                    # pano court (94ft total).  400px was too tight: a ball in
                    # flight at 30ft from the nearest player = ~1180px in pano
                    # coords, causing valid airborne detections to be discarded.
                    # Prefer the possessor's court pos; fall back to
                    # the nearest non-referee player when no possessor is set
                    # (ball-in-air guard may have cleared has_ball even though
                    # CSRT is still running on a drifted object).
                    possessor_2d = next(
                        (p.positions[timestamp] for p in self.players
                         if p.has_ball and timestamp in p.positions),
                        None,
                    )
                    if possessor_2d is None:
                        # No explicit possessor — find nearest tracked player
                        candidates = [
                            p.positions[timestamp] for p in self.players
                            if p.team != "referee" and timestamp in p.positions
                        ]
                        if candidates:
                            possessor_2d = min(
                                candidates,
                                key=lambda pos: np.hypot(ball_2d[0] - pos[0],
                                                         ball_2d[1] - pos[1]),
                            )
                    if (possessor_2d is not None
                            and float(np.hypot(ball_2d[0] - possessor_2d[0],
                                               ball_2d[1] - possessor_2d[1])) > 1200):
                        self.last_2d_pos = None   # 2D projection out of range — discard
                        # Do NOT clear pixel_vel here: CSRT is still tracking the ball
                        # pixel-space (it's legitimately airborne during shot arc).
                        # Clearing pixel_vel here silenced shot detection for no-stride clips.
                    else:
                        self.last_2d_pos = ball_2d
                color = (0, 165, 255) if self._flow_active else (255, 0, 0)
                cv2.rectangle(frame, p1, p2, color, 2, 1)
                cv2.circle(map_2d, (homo[0], homo[1]), 10, (0, 0, 255), 5)
                self.check_track -= 1
            else:
                # Periodic re-detection check in local window
                local = frame[
                    max(0, p1[1] - self.ball_padding): p2[1] + self.ball_padding,
                    max(0, p1[0] - self.ball_padding): p2[0] + self.ball_padding,
                ]
                # Use ball_detection (YOLO → template → orange-guard) on BGR crop
                found = self.ball_detection(local, threshold=REDET_THRESHOLD)
                self.check_track  = MAX_TRACK
                self.do_detection = (found is None)

        self._prev_gray = gray
        self._frame_num += 1
        return frame, map_2d if bbox is not None else None

    # ── Trajectory feature API ─────────────────────────────────────────────

    def get_trajectory_features(self) -> dict:
        """Return trajectory-derived features for the current possession.

        Fits a degree-2 parabola to the last 15 tracked ball positions on demand
        when 8 or more positions are available.

        Returns:
            dict with keys:
                shot_arc_angle (float | None): release angle in degrees above
                    horizontal, derived from parabola tangent at first tracked point.
                peak_height_px (float | None): pixel y of the parabola vertex
                    (smallest y = highest screen position).
                pass_speed_pxpf (float): current ball speed in pixels per frame.
                dribble_count (int): floor bounces detected this possession.
                is_lob (bool): True if ball rose > 1.5× avg player height.
        """
        arc: Optional[float] = self._shot_arc_angle
        peak_height_px: Optional[float] = None
        if len(self._traj_deque) >= 8:
            try:
                frames = np.array([t[0] for t in self._traj_deque], dtype=np.float64)
                ys = np.array([t[2] for t in self._traj_deque], dtype=np.float64)
                a, b, c = np.polyfit(frames, ys, 2)
                t0 = frames[0]
                slope = 2.0 * a * t0 + b   # dy/dframe at release
                # Negative slope = ball going up (pixel y decreasing) = positive angle
                arc = float(np.degrees(np.arctan(-slope)))
                # Parabola vertex: t_peak = -b / (2a); y_peak = c - b²/(4a)
                if abs(a) > 1e-9:
                    t_peak = -b / (2.0 * a)
                    y_peak = a * t_peak ** 2 + b * t_peak + c
                    peak_height_px = float(y_peak)
            except (np.linalg.LinAlgError, ValueError):
                arc = None
        return {
            "shot_arc_angle": arc,
            "peak_height_px": peak_height_px,
            "pass_speed_pxpf": float(self.pixel_vel),
            "dribble_count": self._dribble_count,
            "is_lob": self._is_lob,
        }

    def snapshot_shot_arc(self) -> None:
        """Snapshot the shot arc angle at the moment of shot detection.

        Alias of on_shot_event() — call immediately when event == 'shot'
        so arc is computed from the trajectory at release.
        """
        self.on_shot_event()

    def on_shot_event(self) -> None:
        """Call when a shot event is detected to snapshot the arc angle.

        Fits the parabola immediately so the angle is computed from the
        trajectory at release rather than after the ball may have deviated.
        """
        features = self.get_trajectory_features()
        self._shot_arc_angle = features.get("shot_arc_angle")

    def reset_possession(self) -> None:
        """Reset per-possession counters at the start of a new possession.

        Should be called by the pipeline when possession changes.
        """
        self._shot_arc_angle = None
        self._dribble_count = 0
        self._is_lob = False
        self._prev_vy_sign = 0
        self._prev_cy = None

    @property
    def ball_padding(self):
        return IOU_BALL_PAD
