"""
ObjectTracker: DeepSORT wrapper for persistent player and ball tracking.

Wraps deep_sort_realtime.DeepSort to assign persistent integer IDs across
video frames. Computes per-frame velocity, speed, and direction for each
confirmed track. Results are returned as TrackedObject dataclass instances
ready for database insertion by CoordinateWriter.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

from pipelines.detector import Detection


@dataclass
class TrackedObject:
    """A single tracked object (player or ball) at a specific video frame."""
    track_id: int
    object_type: str          # 'player' or 'ball'
    cx: float                 # center x in pixels
    cy: float                 # center y in pixels
    bbox: tuple               # (x1, y1, x2, y2)
    confidence: float
    frame_number: int
    timestamp_ms: float
    velocity_x: float         # pixels per second along x axis
    velocity_y: float         # pixels per second along y axis
    speed: float              # sqrt(vx^2 + vy^2) in pixels per second
    direction_degrees: float  # atan2(vy, vx) normalized to [0, 360)


class ObjectTracker:
    """Wraps DeepSORT to provide persistent track IDs with velocity computation.

    Usage::

        tracker = ObjectTracker()
        tracker.set_fps(ingestor.fps)
        for frame_num, frame, ts_ms in ingestor.frames():
            detections = detector.detect(frame)
            tracked = tracker.update(detections, frame, frame_num, ts_ms)
            writer.write_batch(tracked)
    """

    def __init__(self, max_age: int = 30, n_init: int = 3) -> None:
        """
        Initialize the tracker.

        Args:
            max_age: Maximum number of frames to keep a track alive without
                     a matching detection.
            n_init: Number of consecutive frames required before a track is
                    confirmed (visible in results).
        """
        self.deepsort = DeepSort(max_age=max_age, n_init=n_init)
        self.previous_positions: Dict[int, Tuple[float, float]] = {}
        self.fps: float = 30.0

    def set_fps(self, fps: float) -> None:
        """Update frames-per-second used for velocity computation."""
        self.fps = fps

    def update(
        self,
        detections: List[Detection],
        frame: np.ndarray,
        frame_number: int,
        timestamp_ms: float,
    ) -> List[TrackedObject]:
        """
        Update tracker with new detections and return confirmed tracked objects.

        Args:
            detections: Detection results from ObjectDetector for this frame.
            frame: The raw BGR frame array (required by DeepSORT's embedder).
            frame_number: Zero-based frame index.
            timestamp_ms: Frame timestamp in milliseconds.

        Returns:
            List of TrackedObject for each confirmed DeepSORT track this frame.
        """
        # Convert Detection list to DeepSORT input: ([l,t,w,h], conf, class)
        raw_detections = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            w = x2 - x1
            h = y2 - y1
            raw_detections.append(([x1, y1, w, h], det.confidence, det.class_label))

        tracks = self.deepsort.update_tracks(raw_detections, frame=frame)

        results: List[TrackedObject] = []
        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id: int = int(track.track_id)

            # Derive centroid from ltwh bounding box
            ltwh = track.to_ltwh()
            cx = float(ltwh[0] + ltwh[2] / 2)
            cy = float(ltwh[1] + ltwh[3] / 2)

            # Match object_type by nearest centroid to original detections.
            # get_det_class() can be unreliable across versions, so prefer
            # distance-based matching; fall back to track's stored class.
            object_type, confidence = self._match_detection(
                cx, cy, detections, track
            )

            # Reconstruct bbox from ltwh
            bbox = (
                float(ltwh[0]),
                float(ltwh[1]),
                float(ltwh[0] + ltwh[2]),
                float(ltwh[1] + ltwh[3]),
            )

            # Compute velocity from previous centroid
            velocity_x, velocity_y, speed, direction = self._compute_velocity(
                track_id, cx, cy
            )

            # Update history
            self.previous_positions[track_id] = (cx, cy)

            results.append(
                TrackedObject(
                    track_id=track_id,
                    object_type=object_type,
                    cx=cx,
                    cy=cy,
                    bbox=bbox,
                    confidence=confidence,
                    frame_number=frame_number,
                    timestamp_ms=timestamp_ms,
                    velocity_x=velocity_x,
                    velocity_y=velocity_y,
                    speed=speed,
                    direction_degrees=direction,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _match_detection(
        self,
        cx: float,
        cy: float,
        detections: List[Detection],
        track,
    ) -> Tuple[str, float]:
        """Return (object_type, confidence) for the nearest original detection.

        Falls back to track.get_det_class() / track.get_det_conf() if no
        detections are provided or the track carries its own class info.
        """
        if not detections:
            # No original detections — use stored track class
            cls = track.get_det_class() or "player"
            conf = track.get_det_conf() or 0.0
            return str(cls), float(conf) if conf is not None else 0.0

        best: Optional[Detection] = None
        best_dist = float("inf")
        for det in detections:
            dist = math.hypot(det.cx - cx, det.cy - cy)
            if dist < best_dist:
                best_dist = dist
                best = det

        if best is None:
            cls = track.get_det_class() or "player"
            conf = track.get_det_conf() or 0.0
            return str(cls), float(conf) if conf is not None else 0.0

        return best.class_label, best.confidence

    def _compute_velocity(
        self, track_id: int, cx: float, cy: float
    ) -> Tuple[float, float, float, float]:
        """Compute velocity, speed, and direction from previous position.

        On first appearance of a track_id, all values are 0.0.

        Returns:
            (velocity_x, velocity_y, speed, direction_degrees)
        """
        prev = self.previous_positions.get(track_id)
        if prev is None:
            return 0.0, 0.0, 0.0, 0.0

        prev_cx, prev_cy = prev
        vx = (cx - prev_cx) * self.fps
        vy = (cy - prev_cy) * self.fps
        spd = math.sqrt(vx * vx + vy * vy)
        angle = math.degrees(math.atan2(vy, vx)) % 360.0
        return vx, vy, spd, angle
