"""Center-field baseball pitch-view tracking in plate-relative feet.

This adapter only emits rows for a calibrated center-field pitch view.  It uses
the visible mound and plate dirt areas to make a local affine projection, not a
full-field homography: a broadcast pitch camera does not reliably show enough
fixed, coplanar field landmarks for an honest full-field calibration.  Therefore
full-field tracking is explicitly out of scope, as is ball tracking until a
validated fast-ball detector is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd


SCHEMA = ("frame", "track_id", "cls", "x", "y")
MOUND_TO_PLATE_FEET = 60.5
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


@dataclass(frozen=True)
class PitchGeometry:
    """Image anchors and scale recovered from one center-field pitch frame."""

    mound: np.ndarray
    plate: np.ndarray
    pixels_per_foot: float


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write rows in the normalized platform tracking schema."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, SCHEMA].to_csv(path, index=False)


class BaseballAdapter:
    """Track pitcher and batter only in calibrated center-field pitch views."""

    def __init__(self, detector: Optional[Detector] = None) -> None:
        self.detector = detector if detector is not None else self._load_yolo_detector()
        self._geometry: Optional[PitchGeometry] = None
        self.last_output = pd.DataFrame(columns=SCHEMA)

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "BaseballAdapter requires ultralytics. Install it with "
                "`pip install ultralytics` or pass a detector for testing."
            ) from exc
        model = YOLO("yolov8n.pt")

        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            if result.boxes is None:
                return []
            return result.boxes.xyxy.cpu().numpy().tolist()

        return detect

    @staticmethod
    def _dirt_blobs(frame: np.ndarray) -> list[tuple[float, np.ndarray]]:
        """Return area and centroids for sufficiently large brown/tan blobs."""
        height, width = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        dirt = cv2.inRange(hsv, np.array((5, 35, 35)), np.array((32, 255, 255)))
        dirt = cv2.morphologyEx(dirt, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        count, _, stats, centers = cv2.connectedComponentsWithStats(dirt)
        minimum_area = max(25, int(height * width * 0.0001))
        return [
            (float(stats[index, cv2.CC_STAT_AREA]), centers[index].astype(np.float32))
            for index in range(1, count)
            if stats[index, cv2.CC_STAT_AREA] >= minimum_area
        ]

    @staticmethod
    def _dominant_green(frame: np.ndarray) -> bool:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        return float(np.count_nonzero(green)) / green.size >= 0.35

    def detect_pitch_geometry(self, frame: np.ndarray) -> Optional[PitchGeometry]:
        """Find mound and plate dirt anchors when the frame is a pitch view."""
        if not self._dominant_green(frame):
            return None
        height, width = frame.shape[:2]
        blobs = self._dirt_blobs(frame)
        mound = [
            center for _, center in blobs
            if 0.30 * width <= center[0] <= 0.70 * width
            and 0.25 * height <= center[1] <= 0.68 * height
        ]
        plate = [
            center for _, center in blobs
            if 0.35 * width <= center[0] <= 0.65 * width
            and 0.60 * height <= center[1] <= 0.95 * height
        ]
        if not mound or not plate:
            return None
        center_x = width / 2.0
        mound_point = min(mound, key=lambda point: abs(point[0] - center_x) + abs(point[1] - height * 0.50))
        plate_point = min(plate, key=lambda point: abs(point[0] - center_x) + abs(point[1] - height * 0.78))
        distance = float(np.linalg.norm(mound_point - plate_point))
        if plate_point[1] <= mound_point[1] or distance < 20.0:
            return None
        return PitchGeometry(mound_point, plate_point, distance / MOUND_TO_PLATE_FEET)

    def is_pitch_view(self, frame: np.ndarray) -> bool:
        """Return whether the frame has the required green field, mound, and plate geometry."""
        return self.detect_pitch_geometry(frame) is not None

    def calibrate_scale(self, frame: np.ndarray) -> Optional[float]:
        """Return the pitch-view linear scale in pixels per foot, when calibratable."""
        geometry = self.detect_pitch_geometry(frame)
        return None if geometry is None else geometry.pixels_per_foot

    @staticmethod
    def _project(foot: np.ndarray, geometry: PitchGeometry) -> np.ndarray:
        """Project an image feet point to plate-relative horizontal and moundward feet."""
        scale = geometry.pixels_per_foot
        return np.array(
            ((foot[0] - geometry.plate[0]) / scale,
             (geometry.plate[1] - foot[1]) / scale),
            dtype=np.float32,
        )

    def detect_players(
        self, frame: np.ndarray, geometry: PitchGeometry
    ) -> list[tuple[int, np.ndarray]]:
        """Return nearest visible pitcher (1) and batter (2) feet points."""
        candidates: list[tuple[np.ndarray, np.ndarray]] = []
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 <= x1 or y2 <= y1:
                continue
            foot = np.array(((x1 + x2) / 2.0, y2), dtype=np.float32)
            point = self._project(foot, geometry)
            if -30.0 <= point[0] <= 30.0 and 0.0 <= point[1] <= 60.0:
                candidates.append((foot, point))
        if len(candidates) < 2:
            return []

        def nearest(anchor: np.ndarray, excluded: Optional[int] = None) -> Optional[int]:
            choices = [index for index in range(len(candidates)) if index != excluded]
            return min(choices, key=lambda index: np.linalg.norm(candidates[index][0] - anchor)) if choices else None

        pitcher = nearest(geometry.mound)
        batter = nearest(geometry.plate, pitcher)
        if pitcher is None or batter is None:
            return []
        return [(1, candidates[pitcher][1]), (2, candidates[batter][1])]

    @staticmethod
    def detect_ball_stub(frame: np.ndarray, geometry: PitchGeometry) -> list[tuple[int, np.ndarray]]:
        """Return no ball rows. TODO: integrate a validated fast-ball detector."""
        del frame, geometry
        return []

    def process_video(
        self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1
    ) -> pd.DataFrame:
        """Process a headless video, emitting only calibrated pitch-view player rows."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        source_frame = processed = 0
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if source_frame % stride == 0:
                    self._geometry = self.detect_pitch_geometry(frame)
                    if self._geometry is not None:
                        for track_id, point in self.detect_players(frame, self._geometry):
                            rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                        self.detect_ball_stub(frame, self._geometry)
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
