"""
ObjectTracker: DeepSORT-based multi-object tracker with:
- Velocity in ft/s (not px/s) when homography is calibrated
- Jersey-color team clustering via k-means (team_a / team_b)
- Referee filtering via low-saturation jersey detection
- Ball tracking via Kalman filter
"""
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

from pipelines.detector import Detection
from tracking.ball_kalman import BallKalman
from tracking.homography import CourtHomography

# Rolling window for velocity smoothing (5 frames ≈ 167ms at 30fps)
_VEL_WINDOW = 5

# Jersey color sampling
_COLOR_HISTORY_LEN   = 10    # samples kept per track
_REF_SAT_THRESHOLD   = 40    # HSV saturation below this → gray/white/black → ref
_MIN_CLUSTER_TRACKS  = 4     # minimum non-ref tracks needed to attempt k-means
_RECLUSTER_INTERVAL  = 45    # frames between k-means re-runs


@dataclass
class TrackedObject:
    """A single tracked object at a specific video frame."""
    track_id:          int
    object_type:       str    # 'player' or 'ball'
    cx:                float  # center x pixels
    cy:                float  # center y pixels
    x_ft:              float  # court feet (0-94), or cx if no homography
    y_ft:              float  # court feet (0-50), or cy if no homography
    bbox:              tuple  # (x1, y1, x2, y2) pixels
    confidence:        float
    frame_number:      int
    timestamp_ms:      float
    velocity_x:        float  # ft/s if homography calibrated, else px/s
    velocity_y:        float
    speed:             float
    direction_degrees: float
    team:              str    # 'team_a', 'team_b', 'ref', or 'ball'


class ObjectTracker:
    """
    DeepSORT tracker with jersey-color team assignment and ft/s velocity.

    Team assignment:
        - Jersey HSV sampled from torso region each frame
        - Low saturation (<40) → referee → filtered out
        - Every 45 frames: k-means on hue/saturation → 'team_a' / 'team_b'
        - Falls back to court-half ('team_a'=left, 'team_b'=right) until
          enough color data is available

    Velocity:
        - History stored in court-feet coordinates when homography is calibrated
        - Speed is therefore in ft/s (directly comparable across games/cameras)
        - When homography is unavailable, falls back to px/s
    """

    def __init__(
        self,
        homography: Optional[CourtHomography] = None,
        max_age: int = 45,
        n_init: int = 3,
    ) -> None:
        self._deepsort    = DeepSort(max_age=max_age, n_init=n_init)
        self._homography  = homography
        self._fps: float  = 30.0

        # Per-track position history (feet when calibrated, pixels otherwise)
        self._history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=_VEL_WINDOW)
        )

        # Per-track jersey HSV history: track_id → deque of (H, S, V) arrays
        self._color_history: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=_COLOR_HISTORY_LEN)
        )

        # Team assignment decided by k-means: track_id → 'team_a' | 'team_b'
        self._team_assignment: Dict[int, str] = {}

        # Last k-means cluster centers in [H, S] space — shape (2, 2)
        # Used to keep team_a/team_b stable across re-clusterings (prevents label flipping)
        self._cluster_centers: Optional[np.ndarray] = None

        self._frame_count = 0
        self._ball_kalman = BallKalman(fps=self._fps)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_fps(self, fps: float) -> None:
        self._fps = max(fps, 1.0)
        self._ball_kalman = BallKalman(fps=self._fps)

    def set_homography(self, homography: CourtHomography) -> None:
        """Update homography (e.g. after camera cut). Clears position history."""
        self._homography = homography
        # Position history is in old coordinate space — discard it
        self._history.clear()

    def update(
        self,
        detections: List[Detection],
        frame: np.ndarray,
        frame_number: int,
        timestamp_ms: float,
    ) -> List[TrackedObject]:
        """Update tracker with detections for the current frame."""
        player_dets = [d for d in detections if d.class_label == "player"]
        ball_dets   = [d for d in detections if d.class_label == "ball"]

        # ── Player tracking ───────────────────────────────────────────────────
        raw = [
            ([d.bbox[0], d.bbox[1], d.bbox[2]-d.bbox[0], d.bbox[3]-d.bbox[1]],
             d.confidence, d.class_label)
            for d in player_dets
        ]
        tracks = self._deepsort.update_tracks(raw, frame=frame)

        self._frame_count += 1
        results: List[TrackedObject] = []
        active_non_ref_ids: List[int] = []

        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id = int(track.track_id)
            ltwh = track.to_ltwh()
            cx = float(ltwh[0] + ltwh[2] / 2)
            cy = float(ltwh[1] + ltwh[3] / 2)
            x_ft, y_ft = self._to_feet(cx, cy)

            # Drop players outside court bounds (crowd, bench)
            if self._homography and self._homography.is_calibrated:
                if not self._homography.on_court(x_ft, y_ft, margin=8.0):
                    continue

            bbox = (
                float(ltwh[0]), float(ltwh[1]),
                float(ltwh[0] + ltwh[2]), float(ltwh[1] + ltwh[3]),
            )

            # Sample jersey color for team classification and ref detection
            hsv = self._sample_jersey_hsv(frame, bbox)
            if hsv is not None:
                self._color_history[track_id].append(hsv)

            # Filter referees (gray/white/black jerseys = low saturation)
            if self._is_referee(track_id):
                continue

            active_non_ref_ids.append(track_id)

            # Velocity in ft/s (position history stored in feet)
            vx, vy, speed, direction = self._compute_velocity(track_id, x_ft, y_ft)

            conf = self._match_confidence(cx, cy, player_dets, track)
            team = self._get_team(track_id, x_ft)

            results.append(TrackedObject(
                track_id=track_id,
                object_type="player",
                cx=cx, cy=cy,
                x_ft=x_ft, y_ft=y_ft,
                bbox=bbox,
                confidence=conf,
                frame_number=frame_number,
                timestamp_ms=timestamp_ms,
                velocity_x=vx, velocity_y=vy,
                speed=speed,
                direction_degrees=direction,
                team=team,
            ))

        # Re-cluster teams from jersey colors periodically
        if self._frame_count % _RECLUSTER_INTERVAL == 0 and active_non_ref_ids:
            self._recluster_teams(active_non_ref_ids)

        # ── Ball tracking via Kalman ──────────────────────────────────────────
        ball_det = max(ball_dets, key=lambda d: d.confidence) if ball_dets else None

        ball_obs = None
        if ball_det is not None:
            bx_ft, by_ft = self._to_feet(ball_det.cx, ball_det.cy)
            ball_obs = (bx_ft, by_ft)

        ball_state = self._ball_kalman.update(ball_obs)

        if ball_state is not None:
            bx_ft, by_ft, bvx, bvy = ball_state
            bx_px, by_px = self._to_pixels(bx_ft, by_ft)
            bspeed = math.sqrt(bvx**2 + bvy**2)
            bdir   = math.degrees(math.atan2(bvy, bvx)) % 360.0

            raw_cx   = ball_det.cx        if ball_det else bx_px
            raw_cy   = ball_det.cy        if ball_det else by_px
            raw_conf = ball_det.confidence if ball_det else 0.0

            results.append(TrackedObject(
                track_id=0,
                object_type="ball",
                cx=raw_cx, cy=raw_cy,
                x_ft=bx_ft, y_ft=by_ft,
                bbox=(raw_cx-10, raw_cy-10, raw_cx+10, raw_cy+10),
                confidence=raw_conf,
                frame_number=frame_number,
                timestamp_ms=timestamp_ms,
                velocity_x=bvx, velocity_y=bvy,
                speed=bspeed,
                direction_degrees=bdir,
                team="ball",
            ))

        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    def _to_feet(self, cx: float, cy: float) -> Tuple[float, float]:
        if self._homography and self._homography.is_calibrated:
            return self._homography.to_feet(cx, cy)
        return cx, cy

    def _to_pixels(self, x_ft: float, y_ft: float) -> Tuple[float, float]:
        if self._homography and self._homography.is_calibrated:
            return self._homography.to_pixels(x_ft, y_ft)
        return x_ft, y_ft

    def _compute_velocity(
        self, track_id: int, x: float, y: float
    ) -> Tuple[float, float, float, float]:
        """Velocity over rolling window. x/y should be in feet for ft/s output."""
        history = self._history[track_id]
        history.append((x, y))

        if len(history) < 2:
            return 0.0, 0.0, 0.0, 0.0

        oldest_x, oldest_y = history[0]
        dt = (len(history) - 1) / self._fps

        vx    = (x - oldest_x) / dt
        vy    = (y - oldest_y) / dt
        speed = math.sqrt(vx * vx + vy * vy)
        direction = math.degrees(math.atan2(vy, vx)) % 360.0

        return vx, vy, speed, direction

    def _sample_jersey_hsv(
        self, frame: np.ndarray, bbox: tuple
    ) -> Optional[np.ndarray]:
        """Return median HSV of the player's torso region, or None if too small."""
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        bh, bw = y2 - y1, x2 - x1
        if bh < 20 or bw < 10:
            return None

        # Torso: 25%–65% vertical, 25%–75% horizontal (avoids head and shorts)
        ry1 = max(0, y1 + int(bh * 0.25))
        ry2 = min(frame.shape[0], y1 + int(bh * 0.65))
        rx1 = max(0, x1 + int(bw * 0.25))
        rx2 = min(frame.shape[1], x1 + int(bw * 0.75))

        if ry2 <= ry1 or rx2 <= rx1:
            return None

        region = frame[ry1:ry2, rx1:rx2]
        if region.size == 0:
            return None

        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        return np.median(hsv.reshape(-1, 3), axis=0).astype(np.float32)

    def _is_referee(self, track_id: int) -> bool:
        """True if track's jersey is consistently low-saturation (ref/official)."""
        history = list(self._color_history.get(track_id, []))
        if len(history) < 3:
            return False
        mean_sat = float(np.mean([s[1] for s in history]))
        return mean_sat < _REF_SAT_THRESHOLD

    def _get_team(self, track_id: int, x_ft: float) -> str:
        """Return team label from k-means assignment, falling back to court half."""
        if track_id in self._team_assignment:
            return self._team_assignment[track_id]
        # Fallback until enough color data: left half = team_a, right = team_b
        return "team_a" if x_ft < 47.0 else "team_b"

    def _recluster_teams(self, active_ids: List[int]) -> None:
        """K-means (k=2) on jersey hue/saturation to assign team_a / team_b."""
        eligible_ids: List[int] = []
        features: List[np.ndarray] = []

        for tid in active_ids:
            hist = list(self._color_history.get(tid, []))
            if len(hist) < 3:
                continue
            mean_hsv = np.mean(hist, axis=0)
            if float(mean_hsv[1]) < _REF_SAT_THRESHOLD:
                continue  # ref — skip
            eligible_ids.append(tid)
            # Use hue and saturation (not value — varies with lighting)
            features.append(mean_hsv[:2])

        if len(eligible_ids) < _MIN_CLUSTER_TRACKS:
            return

        data = np.array(features, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
        _, labels, centers = cv2.kmeans(data, 2, None, criteria, 5, cv2.KMEANS_RANDOM_CENTERS)
        labels = labels.flatten()

        # Require clusters to be meaningfully separated in hue/saturation space.
        # If they're too similar the jersey colors are ambiguous — don't update.
        inter_dist = float(np.linalg.norm(centers[0] - centers[1]))
        if inter_dist < 8.0:
            return

        # Stabilize labels: if previous centers exist, check whether the new clusters
        # are swapped relative to the previous run.  If new cluster-0 is closer to
        # the old cluster-1 center, flip all labels so team_a stays team_a.
        if self._cluster_centers is not None:
            d00 = float(np.linalg.norm(centers[0] - self._cluster_centers[0]))
            d01 = float(np.linalg.norm(centers[0] - self._cluster_centers[1]))
            if d01 < d00:
                labels = 1 - labels
                centers = centers[[1, 0]]

        self._cluster_centers = centers

        for tid, label in zip(eligible_ids, labels):
            self._team_assignment[tid] = "team_a" if label == 0 else "team_b"

    def _match_confidence(
        self, cx: float, cy: float, detections: List[Detection], track
    ) -> float:
        if not detections:
            conf = track.get_det_conf()
            return float(conf) if conf is not None else 0.0
        best_dist = float("inf")
        best_conf = 0.0
        for det in detections:
            dist = math.hypot(det.cx - cx, det.cy - cy)
            if dist < best_dist:
                best_dist = dist
                best_conf = det.confidence
        return best_conf
