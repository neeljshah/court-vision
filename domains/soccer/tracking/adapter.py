"""Broadcast soccer tracking projected onto a 105 by 68 metre pitch."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd


SCHEMA = ("frame", "track_id", "cls", "x", "y")
PITCH_METRES = np.float32(((0, 0), (105, 0), (0, 68), (105, 68)))
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write tracking rows in the shared platform schema."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, SCHEMA].to_csv(path, index=False)


class SoccerAdapter:
    """Track broadcast-view players only when the current pitch is calibrated."""

    def __init__(self, detector: Optional[Detector] = None, retirement_frames: int = 30) -> None:
        self.detector = detector if detector is not None else self._load_yolo_detector()
        self.retirement_frames = retirement_frames
        self._tracks: dict[int, tuple[np.ndarray, int]] = {}
        self._next_track_id = 1
        self.last_output = pd.DataFrame(columns=SCHEMA)

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "SoccerAdapter requires ultralytics. Install it with "
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
    def _white_pitch_mask(frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        pitch_neighbourhood = cv2.dilate(green, np.ones((21, 21), np.uint8))
        white = cv2.inRange(hsv, np.array((0, 0, 180)), np.array((180, 75, 255)))
        return cv2.bitwise_and(white, pitch_neighbourhood)

    @staticmethod
    def _line_position(line: np.ndarray, horizontal: bool, shape: tuple[int, int]) -> float:
        x1, y1, x2, y2 = line
        height, width = shape
        if horizontal:
            if abs(x2 - x1) < 1e-6:
                return float((y1 + y2) / 2.0)
            return float(y1 + (width / 2.0 - x1) * (y2 - y1) / (x2 - x1))
        if abs(y2 - y1) < 1e-6:
            return float((x1 + x2) / 2.0)
        return float(x1 + (height / 2.0 - y1) * (x2 - x1) / (y2 - y1))

    @classmethod
    def _cluster_lines(
        cls, lines: list[np.ndarray], horizontal: bool, shape: tuple[int, int]
    ) -> list[list[np.ndarray]]:
        clusters: list[list[np.ndarray]] = []
        for line in sorted(lines, key=lambda item: cls._line_position(item, horizontal, shape)):
            position = cls._line_position(line, horizontal, shape)
            if not clusters or abs(position - np.mean([
                cls._line_position(item, horizontal, shape) for item in clusters[-1]
            ])) > 12.0:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        return clusters

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray(
            [[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines],
            dtype=np.float32,
        )
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return np.array((x0 - 10000 * vx, y0 - 10000 * vy, x0 + 10000 * vx, y0 + 10000 * vy))

    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        a = np.cross((first[0], first[1], 1.0), (first[2], first[3], 1.0))
        b = np.cross((second[0], second[1], 1.0), (second[2], second[3], 1.0))
        point = np.cross(a, b)
        return None if abs(point[2]) < 1e-8 else np.float32(point[:2] / point[2])

    def detect_pitch_lines(self, frame: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Extract candidate touchlines and transverse lines from the green pitch."""
        height, width = frame.shape[:2]
        lines = cv2.HoughLinesP(
            self._white_pitch_mask(frame), 1, np.pi / 180.0, threshold=55,
            minLineLength=max(80, width // 10), maxLineGap=25,
        )
        horizontal: list[np.ndarray] = []
        vertical: list[np.ndarray] = []
        if lines is None:
            return horizontal, vertical
        for raw in lines[:, 0, :]:
            line = raw.astype(float)
            dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
            if dx >= 1.5 * dy:
                horizontal.append(line)
            elif dy >= 1.5 * dx:
                vertical.append(line)
        return horizontal, vertical

    def detect_pitch_markings(self, frame: np.ndarray) -> dict[str, object]:
        """Detect touchline/halfway geometry and the centre circle when visible."""
        height, width = frame.shape[:2]
        horizontal, vertical = self.detect_pitch_lines(frame)
        vertical_clusters = self._cluster_lines(vertical, False, (height, width))
        halfway_x = None
        if len(vertical_clusters) >= 3:
            positions = [self._line_position(cluster[0], False, (height, width)) for cluster in vertical_clusters]
            halfway_x = float(min(positions, key=lambda value: abs(value - width / 2.0)))
        circles = cv2.HoughCircles(
            self._white_pitch_mask(frame), cv2.HOUGH_GRADIENT, 1.2, max(40, height // 5),
            param1=80, param2=18, minRadius=max(15, height // 30), maxRadius=height // 3,
        )
        circle = None if circles is None else tuple(map(float, circles[0, 0]))
        return {"horizontal": horizontal, "vertical": vertical, "halfway_x": halfway_x, "center_circle": circle}

    def detect_pitch_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return near-left, near-right, far-left, far-right pitch corners."""
        height, width = frame.shape[:2]
        horizontal, vertical = self.detect_pitch_lines(frame)
        horizontal_clusters = self._cluster_lines(horizontal, True, (height, width))
        vertical_clusters = self._cluster_lines(vertical, False, (height, width))
        if len(horizontal_clusters) < 2 or len(vertical_clusters) < 2:
            return None
        near, far = self._fit_line(horizontal_clusters[-1]), self._fit_line(horizontal_clusters[0])
        left, right = self._fit_line(vertical_clusters[0]), self._fit_line(vertical_clusters[-1])
        corners = [
            self._intersection(near, left), self._intersection(near, right),
            self._intersection(far, left), self._intersection(far, right),
        ]
        if any(point is None for point in corners):
            return None
        result = np.asarray(corners, dtype=np.float32)
        if np.any(result[:, 0] < -5) or np.any(result[:, 0] > width + 5):
            return None
        if np.any(result[:, 1] < -5) or np.any(result[:, 1] > height + 5):
            return None
        return result

    @staticmethod
    def homography_from_corners(corners: np.ndarray) -> np.ndarray:
        """Map ordered image pitch corners to the 105 by 68 metre plane."""
        homography, _ = cv2.findHomography(np.asarray(corners, dtype=np.float32), PITCH_METRES)
        if homography is None:
            raise ValueError("Could not calculate pitch homography")
        return homography

    @staticmethod
    def _project(point: tuple[float, float], homography: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.float32([[point]]), homography)[0, 0]

    def _assign_tracks(self, centers: list[np.ndarray]) -> list[int]:
        available = set(self._tracks)
        ids: list[int] = []
        for center in centers:
            nearest = min(available, key=lambda track_id: np.linalg.norm(center - self._tracks[track_id][0]), default=None)
            if nearest is None:
                nearest = self._next_track_id
                self._next_track_id += 1
            else:
                available.remove(nearest)
            self._tracks[nearest] = (center, 0)
            ids.append(nearest)
        for track_id in list(available):
            center, lost = self._tracks[track_id]
            self._tracks[track_id] = (center, lost + 1)
            if lost + 1 >= self.retirement_frames:
                del self._tracks[track_id]
        return ids

    def mark_frame_lost(self) -> None:
        """Age tracks for a frame that cannot safely be projected."""
        self._assign_tracks([])

    def detect_players(self, frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Project YOLO person detections and retain nearest-centroid identities."""
        candidates: list[tuple[np.ndarray, np.ndarray]] = []
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 <= x1 or y2 <= y1:
                continue
            point = self._project(((x1 + x2) / 2.0, y2), homography)
            if not (0 <= point[0] <= 105 and 0 <= point[1] <= 68):
                continue
            candidates.append((np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0)), point))
        ids = self._assign_tracks([candidate[0] for candidate in candidates])
        return list(zip(ids, [candidate[1] for candidate in candidates]))

    @staticmethod
    def detect_ball_stub(frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return no ball rows. TODO: add a validated soccer ball detector."""
        del frame, homography
        return []

    def process_video(
        self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1
    ) -> pd.DataFrame:
        """Process a headless stream, recalibrating the panning camera every frame."""
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
                    corners = self.detect_pitch_corners(frame)
                    if corners is None:
                        self.mark_frame_lost()
                    else:
                        homography = self.homography_from_corners(corners)
                        for track_id, point in self.detect_players(frame, homography):
                            rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                        self.detect_ball_stub(frame, homography)
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
