"""Basketball broadcast adapter with honest source-pixel provenance."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from domains.basketball.tracking.geometry import BasketballGeometryMixin
from scripts.platformkit.coordinate_provenance import (
    IMAGE_COORDINATE_SPACE,
    NO_CALIBRATION,
    OBSERVED,
)


SCHEMA = (
    "frame", "track_id", "cls", "x", "y", "calibration_provenance",
    "projection_status", "projection_rejection_reason", "raw_projected_x_ft",
    "raw_projected_y_ft", "coordinate_space", "observation", "calibration",
    "source_fps", "source_height", "source_duration",
)
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


class BallTrackingUnavailableError(RuntimeError):
    """Raised when basketball ball tracking is requested without a detector."""


class CalibrationUnavailableError(RuntimeError):
    """Raised when a caller requests basketball court coordinates without proof."""


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write complete canonical rows, including image-space provenance."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, SCHEMA].to_csv(path, index=False)


class BasketballAdapter(BasketballGeometryMixin):
    """Track player detections without laundering pixels into court coordinates."""

    def __init__(self, detector: Optional[Detector] = None,
                 retirement_frames: int = 30) -> None:
        self.detector = detector if detector is not None else self._load_yolo_detector()
        self.retirement_frames, self._tracks, self._next_track_id = retirement_frames, {}, 1
        self.last_output = pd.DataFrame(columns=SCHEMA)
        self.last_metadata: dict[str, object] = {}

    @staticmethod
    def _load_yolo_detector() -> Detector:
        from scripts.platformkit.detection.shim import get_box_detector
        return get_box_detector(
            model_path=os.environ.get("CV_DETECTOR_MODEL"), sport="basketball"
        )

    def _assign_tracks(self, centers: list[np.ndarray]) -> list[int]:
        available, ids = set(self._tracks), []
        for center in centers:
            track_id = min(
                available,
                key=lambda item: np.linalg.norm(center - self._tracks[item][0]),
                default=None,
            )
            if track_id is None:
                track_id, self._next_track_id = self._next_track_id, self._next_track_id + 1
            else:
                available.remove(track_id)
            self._tracks[track_id] = (center, 0)
            ids.append(track_id)
        for track_id in list(available):
            center, lost = self._tracks[track_id]
            self._tracks[track_id] = (center, lost + 1)
            if lost + 1 >= self.retirement_frames:
                del self._tracks[track_id]
        return ids

    def mark_frame_lost(self) -> None:
        """Age identities for a frame that yields no player detections."""
        self._assign_tracks([])

    def detect_players(self, frame: np.ndarray,
                       homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Refuse court-coordinate output until a validated calibration route exists."""
        del frame, homography
        raise CalibrationUnavailableError(
            "basketball has no validated homography route; request image_space=True"
        )

    def detect_players_image_space(self, frame: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return observed player bottom-centres in source-image pixels."""
        candidates = []
        for raw in self.detector(frame):
            x1, y1, x2, y2 = map(float, raw[:4])
            if x2 > x1 and y2 > y1:
                candidates.append((np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0)),
                                   np.array(((x1 + x2) / 2.0, y2))))
        ids = self._assign_tracks([center for center, _ in candidates])
        return list(zip(ids, [point for _, point in candidates]))

    @staticmethod
    def _image_row(frame: int, track_id: int, point: np.ndarray,
                   fps: float, height: int, duration: float) -> dict[str, object]:
        return {
            "frame": frame, "track_id": track_id, "cls": "player",
            "x": float(point[0]), "y": float(point[1]),
            "calibration_provenance": "unavailable",
            "projection_status": "not_projected",
            "projection_rejection_reason": "calibration_unavailable",
            "raw_projected_x_ft": None, "raw_projected_y_ft": None,
            "coordinate_space": IMAGE_COORDINATE_SPACE,
            "observation": OBSERVED, "calibration": NO_CALIBRATION,
            "source_fps": fps, "source_height": height, "source_duration": duration,
        }

    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None,
                      stride: int = 1, player_only: bool = False,
                      image_space: bool = True) -> pd.DataFrame:
        """Process a headless video and emit only declared source-pixel rows."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        if not player_only:
            raise BallTrackingUnavailableError(
                "Basketball ball tracking is unavailable; use player_only=True"
            )
        if not image_space:
            raise CalibrationUnavailableError(
                "basketball court output is unavailable without a validated homography"
            )
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0.0 else float("nan")
        rows, source_frame, processed, source_height = [], 0, 0, None
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if source_frame % stride == 0:
                    source_height = int(frame.shape[0])
                    for track_id, point in self.detect_players_image_space(frame):
                        rows.append(self._image_row(
                            source_frame, track_id, point, fps, source_height, duration
                        ))
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        self.last_metadata = {
            "processed_frames": processed, "coordinate_space": IMAGE_COORDINATE_SPACE,
            "source_fps": fps, "source_height": source_height,
            "source_duration": duration,
        }
        return self.last_output

    def write_csv(self, path: Union[str, Path],
                  rows: Optional[pd.DataFrame] = None) -> None:
        """Write the latest complete canonical tracking table."""
        write_csv(self.last_output if rows is None else rows, path)
