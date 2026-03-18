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

MAX_TRACK       = 10      # frames of CSRT tracking before forced re-detection check
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
    def circle_detect(img):
        blurred = cv2.medianBlur(img, 5)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, 1, 20,
            param1=50, param2=25, minRadius=5, maxRadius=18
        )
        if circles is not None:
            return np.uint16(np.around(circles)).reshape(-1, 3)
        return None

    # ── Template match in a region ───────────────────────────────────────

    def _template_match(self, gray_roi, threshold=DETECT_THRESHOLD):
        """Check if any ball template matches inside gray_roi. Returns (x,y,w,h) or None."""
        centers = self.circle_detect(gray_roi)
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

    def ball_detection(self, frame, threshold=DETECT_THRESHOLD):
        """Full-frame ball detection. Returns (x,y,w,h) or None."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return self._template_match(gray, threshold)

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

        # ── Detection mode ────────────────────────────────────────────────
        if self.do_detection:
            bbox = self.ball_detection(frame, DETECT_THRESHOLD)
            if bbox is not None:
                self.tracker = self._make_csrt()
                self.tracker.init(frame, bbox)
                self.do_detection  = False
                self.check_track   = MAX_TRACK
                self._flow_active  = False
                self._flow_age     = 0

        # ── CSRT tracking mode ────────────────────────────────────────────
        else:
            res, bbox = self.tracker.update(frame)
            if not res:
                bbox = None

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
                        self._flow_active = False
                        self._flow_age    = 0
                        self.do_detection = True

            # Both CSRT and flow failed — try trajectory prediction
            if bbox is None:
                pred = self._predict_center()
                if pred is not None:
                    cx, cy = pred
                    pad    = 60  # larger search window around prediction
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
                        # Re-init CSRT at found position
                        self.tracker = self._make_csrt()
                        self.tracker.init(frame, bbox)
                        self.check_track  = MAX_TRACK
                        self._flow_active = False
                        self._flow_age    = 0
                    else:
                        self.do_detection = True

        # ── Validate bbox before updating state ───────────────────────────
        if bbox is not None:
            _cx_new = int(bbox[0] + bbox[2] / 2)
            _cy_new = int(bbox[1] + bbox[3] / 2)
            _h_fr, _w_fr = frame.shape[:2]

            # Guard 1: reject out-of-bounds center (CSRT drifted outside frame)
            if not (0 <= _cx_new < _w_fr and 0 <= _cy_new < _h_fr):
                bbox = None
                self.do_detection = True
            # Guard 2: reject >200px position jump (camera cut or tracker error)
            elif self._trajectory and (
                np.hypot(_cx_new - self._trajectory[-1][0],
                         _cy_new - self._trajectory[-1][1]) > 200
            ):
                bbox = None
                self.do_detection = True
                self.tracker    = self._make_csrt()
                self._flow_active = False
                self._flow_age    = 0
                self._flow_point  = None

        # Guard 3: no-ball streak — reset stale CSRT after 30 consecutive misses
        if bbox is None:
            self._no_ball_streak += 1
            if self._no_ball_streak >= 30:
                self.do_detection  = True
                self.tracker       = self._make_csrt()
                self._flow_active  = False
                self._flow_age     = 0
                self._trajectory   = []
                self._flow_point   = None
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
                self.last_2d_pos = (int(homo[0]), int(homo[1]))
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
