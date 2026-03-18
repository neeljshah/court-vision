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
from typing import Optional

import cv2
import numpy as np

from .player_detection import FeetDetector

# Orange color guard: NBA basketball HSV range (OpenCV 0-180 hue scale)
# Rejects CSRT bbox if the center 3×3 patch median is not basketball-orange.
# Prevents CSRT from latching onto scoreboards, crowd, or court markings.
_BALL_H_LO, _BALL_H_HI = 8,  25   # hue: orange-amber range
_BALL_S_MIN             = 80        # saturation: must be saturated (not grey/white)
_BALL_V_MIN             = 80        # value: not too dark

MAX_TRACK       = 20      # frames of CSRT tracking before forced re-detection check
_CSRT_FAIL_THRESH  = 3   # consecutive CSRT ok=False before forcing re-detection
_REENTRY_ATTEMPTS  = 3   # frames to use wider Hough radius after a forced reset
_REENTRY_MAX_R     = 28  # wider Hough maxRadius for re-entry (vs normal 18)
                          # (raised from 10: halves premature local-check resets; drift
                          # and negative-coord guards catch bad projections instead)
FLOW_MAX_FRAMES = 8       # frames to keep optical flow active during blur
IOU_BALL_PAD    = 35      # IoU box half-size for possession detection
PREDICT_FRAMES  = 6       # frames of history used for trajectory prediction
REDET_THRESHOLD = 0.85    # template match threshold during re-detection (looser)
DETECT_THRESHOLD = 0.88   # template match threshold for initial detection

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

        # Consecutive frames with no ball detected — reset CSRT when it hits 30
        self._no_ball_streak: int = 0

        # CSRT consecutive failure counter — triggers immediate re-detection at
        # threshold=3 instead of waiting for the 30-frame no-ball-streak.
        # Each CSRT ok=False increments; ok=True resets; at 3 → do_detection=True.
        self._csrt_consecutive_fails: int = 0

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

        # Load templates once at init
        self._templates = self._load_templates()

    # ── CSRT factory (handles API change in opencv-contrib >= 4.5.1) ──────

    @staticmethod
    def _make_csrt():
        if hasattr(cv2, "TrackerCSRT_create"):
            return cv2.TrackerCSRT_create()
        if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
            return cv2.legacy.TrackerCSRT_create()
        raise RuntimeError(
            "TrackerCSRT not found. Install opencv-contrib-python:\n"
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
        x1, x2 = max(0, cx - 1), min(w, cx + 2)
        y1, y2 = max(0, cy - 1), min(h, cy + 2)
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
    def circle_detect(img, max_radius: int = 18):
        """Run Hough circle detection on a grayscale image.

        Args:
            img:        Grayscale image (any size).
            max_radius: Upper radius bound for Hough circles.  Normal ops use 18;
                        re-entry mode uses _REENTRY_MAX_R (28) to catch balls at
                        steep angles or partially out-of-frame.
        """
        blurred = cv2.medianBlur(img, 5)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, 1, 20,
            param1=50, param2=25, minRadius=5, maxRadius=max_radius
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

    def ball_detection(self, frame, threshold=DETECT_THRESHOLD, max_radius: int = 18):
        """Full-frame ball detection. Returns (x,y,w,h) or None."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return self._template_match(gray, threshold, max_radius)

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
        # Sanity check: reject if moved more than 150px in one frame
        old_cx, old_cy = self._flow_point[0]
        if np.hypot(new_cx - old_cx, new_cy - old_cy) > 150:
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

    # ── Main tracker ──────────────────────────────────────────────────────

    def ball_tracker(self, M, M1, frame, map_2d, map_2d_text, timestamp):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        bbox = None
        _bbox_from_hough = False  # True when Hough/template detection set bbox

        # ── Detection mode ────────────────────────────────────────────────
        if self.do_detection:
            _max_r = _REENTRY_MAX_R if self._reentry_mode else 18
            bbox = self.ball_detection(frame, DETECT_THRESHOLD, max_radius=_max_r)
            if bbox is not None:
                _bbox_from_hough = True
                self.tracker = self._make_csrt()
                self.tracker.init(frame, bbox)
                self.do_detection    = False
                self.check_track     = MAX_TRACK
                self._flow_active    = False
                self._flow_age       = 0
                self._reentry_mode   = False
                self._reentry_frames = 0
            elif self._reentry_mode:
                self._reentry_frames += 1
                if self._reentry_frames >= _REENTRY_ATTEMPTS:
                    self._reentry_mode   = False
                    self._reentry_frames = 0

        # ── CSRT tracking mode ────────────────────────────────────────────
        else:
            res, bbox = self.tracker.update(frame)
            if res:
                self._csrt_consecutive_fails = 0
            else:
                bbox = None
                self._csrt_consecutive_fails += 1
                if self._csrt_consecutive_fails >= _CSRT_FAIL_THRESH:
                    self.do_detection            = True
                    self._reentry_mode           = True
                    self._reentry_frames         = 0
                    self._csrt_consecutive_fails = 0

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
                    if self._flow_age > FLOW_MAX_FRAMES:
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
                    roi = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                    found = self._template_match(roi, threshold=REDET_THRESHOLD)
                    if found is not None:
                        fx, fy, fw, fh = found
                        bbox = (x1 + fx, y1 + fy, fw, fh)
                        _bbox_from_hough = True   # template match = Hough-like detection
                        # Re-init CSRT at found position
                        self.tracker = self._make_csrt()
                        self.tracker.init(frame, bbox)
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
            # Guard 2: reject >200px position jump (camera cut or tracker error).
            # Skipped for fresh Hough/template re-detections — Hough independently
            # found a new circle; the "jump" is the ball moving while CSRT was
            # tracking the wrong object, not a real CSRT drift error.
            elif (not _bbox_from_hough
                  and self._trajectory
                  and (np.hypot(_cx_new - self._trajectory[-1][0],
                                _cy_new - self._trajectory[-1][1]) > 200)
            ):
                bbox = None
                self._jump_resets   += 1
                self.do_detection    = True
                self._reentry_mode   = True
                self._reentry_frames = 0
                self.tracker         = self._make_csrt()
                self._flow_active    = False
                self._flow_age       = 0
                self._flow_point     = None
            # Guard 3: reject CSRT-tracked bbox whose center patch is not
            # basketball-orange (prevents CSRT from latching onto scoreboards,
            # court text, or crowd). Skipped for fresh Hough/template detections
            # (circularity already validated) to avoid false negatives caused by
            # motion blur, shadow, or broadcast colour grading.
            elif (not _bbox_from_hough
                  and not self._is_ball_orange(frame, _cx_new, _cy_new)):
                bbox = None
                self.do_detection    = True
                self._reentry_mode   = True
                self._reentry_frames = 0
                self.tracker         = self._make_csrt()
                self._flow_active    = False
                self._flow_age       = 0
                self._flow_point     = None

        # Guard 3: no-ball streak — reset stale CSRT after 30 consecutive misses
        if bbox is None:
            self._no_ball_streak += 1
            if self._no_ball_streak >= 30:
                self.do_detection    = True
                self._reentry_mode   = True
                self._reentry_frames = 0
                self.tracker         = self._make_csrt()
                self._flow_active    = False
                self._flow_age       = 0
                self._trajectory     = []
                self._flow_point     = None
                self._no_ball_streak = 0
        else:
            self._no_ball_streak = 0

        # ── Update state ──────────────────────────────────────────────────
        if bbox is not None:
            self._last_bbox = bbox
            cx = int(bbox[0] + bbox[2] / 2)
            cy = int(bbox[1] + bbox[3] / 2)
            self._flow_point = np.array([[cx, cy]], dtype=np.float32)
            if self._trajectory:
                prev_cx, prev_cy = self._trajectory[-1]
                self.pixel_vel = float(np.hypot(cx - prev_cx, cy - prev_cy))
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
                    def center_dist(item):
                        p, _ = item
                        bb = p.previous_bb
                        if bb is None:
                            return float("inf")
                        y1, x1, y2, x2 = bb
                        return np.hypot(cx - (x1 + x2) / 2, cy - (y1 + y2) / 2)
                    best = min(scores, key=center_dist)
                    # Only assign possession if player is close enough (ball-in-air guard)
                    if center_dist(best) > 150:
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
                found = self._template_match(
                    cv2.cvtColor(local, cv2.COLOR_BGR2GRAY),
                    threshold=REDET_THRESHOLD
                )
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
