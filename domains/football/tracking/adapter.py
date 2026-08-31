"""American-football broadcast adapter for field geometry and pre-snap rows.

This intentionally does not claim full-play TV tracking. Broadcast cuts, camera
pans and zooms, heavy occlusion at the line, and a frequently invisible ball
make player identity and continuous full-play trajectories unreliable without
multi-view calibration and play-specific validation. The adapter therefore
emits only low-motion, pre-snap formation frames; ball rows are a named stub.

Yard-line coordinates are offset-relative until an OCR integration identifies
the painted yard number: the first ordered detected five-yard line is x=0 and
each following line is x=15 feet. y=0 and y=160 are the estimated sidelines.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator


SCHEMA = ("frame", "track_id", "cls", "x", "y")
FIELD_WIDTH_FT = 160.0
YARD_LINE_SPACING_FT = 15.0
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write normalized tracking rows."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, SCHEMA].to_csv(path, index=False)


class FootballAdapter:
    """Estimate an offset-relative field plane and pre-snap player formations."""

    def __init__(self, detector: Optional[Detector] = None, motion_threshold: float = 3.0) -> None:
        self.detector = detector
        self.motion_threshold = motion_threshold
        self._homography: Optional[np.ndarray] = None
        self._h_params: list[np.ndarray] = []
        self._centroids: dict[int, np.ndarray] = {}
        self._next_track_id = 1
        self.last_output = pd.DataFrame(columns=SCHEMA)

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("FootballAdapter requires ultralytics or a test detector.") from exc
        model = YOLO("yolov8n.pt")

        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            return [] if result.boxes is None else result.boxes.xyxy.cpu().numpy().tolist()
        return detect

    def _detect(self, frame: np.ndarray) -> Sequence[Sequence[float]]:
        if self.detector is None:
            self.detector = self._load_yolo_detector()
        return self.detector(frame)

    @staticmethod
    def _line_coefficients(line: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = map(float, line)
        result = np.array((y1 - y2, x2 - x1, x1 * y2 - x2 * y1), dtype=float)
        return result / np.hypot(result[0], result[1])

    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        point = np.cross(first, second)
        return None if abs(point[2]) < 1e-8 else (point[:2] / point[2]).astype(np.float32)

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return FootballAdapter._line_coefficients(np.array((x0 - 9999 * vx, y0 - 9999 * vy, x0 + 9999 * vx, y0 + 9999 * vy)))

    @staticmethod
    def _white_field_mask(frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        white = cv2.inRange(hsv, np.array((0, 0, 150)), np.array((180, 100, 255)))
        return cv2.bitwise_and(white, cv2.dilate(green, np.ones((5, 5), np.uint8)))

    def _line_groups(self, frame: np.ndarray) -> list[list[np.ndarray]]:
        mask = self._white_field_mask(frame)
        raw = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=35, minLineLength=max(30, frame.shape[1] // 12), maxLineGap=18)
        if raw is None:
            return []
        groups: list[list[np.ndarray]] = []
        for item in raw[:, 0, :].astype(float):
            angle = np.arctan2(item[3] - item[1], item[2] - item[0]) % np.pi
            for group in groups:
                ref = group[0]
                ref_angle = np.arctan2(ref[3] - ref[1], ref[2] - ref[0]) % np.pi
                if abs(((angle - ref_angle + np.pi / 2) % np.pi) - np.pi / 2) < np.deg2rad(10):
                    group.append(item)
                    break
            else:
                groups.append([item])
        return groups

    def detect_yard_line_family(self, frame: np.ndarray) -> list[np.ndarray]:
        """Return fitted, ordered parallel five-yard-line image lines."""
        groups = self._line_groups(frame)
        if not groups:
            return []
        group = max(groups, key=len)
        direction = np.mean([np.arctan2(line[3] - line[1], line[2] - line[0]) % np.pi for line in group])
        normal = np.array((-np.sin(direction), np.cos(direction)))
        clusters: list[list[np.ndarray]] = []
        for line in sorted(group, key=lambda value: np.dot(((value[:2] + value[2:]) / 2), normal)):
            offset = np.dot(((line[:2] + line[2:]) / 2), normal)
            if not clusters or abs(offset - np.mean([np.dot(((x[:2] + x[2:]) / 2), normal) for x in clusters[-1]])) > 8:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        return [self._fit_line(cluster) for cluster in clusters if len(cluster) >= 1]

    def estimate_absolute_yardline_stub(self, frame: np.ndarray) -> Optional[int]:
        """Return no yard number until an OCR model validates a painted numeral."""
        del frame
        return None

    def homography_from_yard_lines(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Fit pixel-to-feet H from yard-line/sideline intersections."""
        yard_lines = self.detect_yard_line_family(frame)
        if len(yard_lines) < 2:
            return None
        groups = self._line_groups(frame)
        yard_angle = np.arctan2(-yard_lines[0][0], yard_lines[0][1]) % np.pi
        candidates = [group for group in groups if abs(((np.arctan2(group[0][3] - group[0][1], group[0][2] - group[0][0]) % np.pi - yard_angle + np.pi / 2) % np.pi) - np.pi / 2) > np.deg2rad(35)]
        if candidates:
            side_group = max(candidates, key=len)
            side_lines = [self._fit_line([line]) for line in side_group]
            anchor = yard_lines[len(yard_lines) // 2]
            side_lines.sort(
                key=lambda line: self._intersection(anchor, line)[1]
                if self._intersection(anchor, line) is not None else float("inf")
            )
            bounds = (side_lines[0], side_lines[-1])
        else:
            green = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), np.array((35, 35, 25)), np.array((95, 255, 255)))
            points = cv2.findNonZero(green)
            if points is None:
                return None
            x, y, width, height = cv2.boundingRect(points)
            bounds = (np.array((0.0, 1.0, -float(y))), np.array((0.0, 1.0, -float(y + height))))
        pixels: list[np.ndarray] = []
        field: list[tuple[float, float]] = []
        for index, yard in enumerate(yard_lines):
            for side_index, side in enumerate(bounds):
                point = self._intersection(yard, side)
                if point is not None:
                    pixels.append(point)
                    field.append((index * YARD_LINE_SPACING_FT, side_index * FIELD_WIDTH_FT))
        if len(pixels) < 4:
            return None
        homography, _ = cv2.findHomography(np.float32(pixels), np.float32(field), cv2.RANSAC, 3.0)
        return None if homography is None else homography / homography[2, 2]

    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        raw = self.homography_from_yard_lines(frame)
        if raw is None:
            return self._homography
        self._h_params.append(TemporalCalibrator._parameters(raw))
        params = np.median(np.vstack(self._h_params[-5:]), axis=0)
        self._homography = TemporalCalibrator._from_parameters(params)
        return self._homography

    @staticmethod
    def motion_magnitude(previous: np.ndarray, current: np.ndarray) -> float:
        """Return median gray-frame difference for a conservative stillness test."""
        first = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        second = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        return float(np.median(cv2.absdiff(first, second)))

    def is_pre_snap(self, previous: np.ndarray, current: np.ndarray, detections: Optional[Sequence[Sequence[float]]] = None) -> bool:
        """Classify a low-motion frame with at least 14 people as pre-snap."""
        boxes = self._detect(current) if detections is None else detections
        return self.motion_magnitude(previous, current) <= self.motion_threshold and len(boxes) >= 14

    def _track_players(self, boxes: Sequence[Sequence[float]], homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        result: list[tuple[int, np.ndarray]] = []
        unused = set(self._centroids)
        for box in boxes:
            x1, y1, x2, y2 = map(float, box[:4])
            center = np.array(((x1 + x2) / 2, (y1 + y2) / 2))
            foot = cv2.perspectiveTransform(np.float32([[[center[0], y2]]]), homography)[0, 0]
            choices = [(np.linalg.norm(center - self._centroids[item]), item) for item in unused]
            track_id = min(choices)[1] if choices else self._next_track_id
            if not choices:
                self._next_track_id += 1
            unused.discard(track_id)
            self._centroids[track_id] = center
            result.append((track_id, foot))
        return result

    @staticmethod
    def detect_ball_stub(frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return no ball rows; a broadcast ball detector is intentionally out of scope."""
        del frame, homography
        return []

    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1) -> pd.DataFrame:
        """Process headless video and emit only pre-snap player rows."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        previous: Optional[np.ndarray] = None
        frame_index = processed = 0
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % stride == 0:
                    homography, boxes = self._stable_homography(frame), self._detect(frame)
                    if previous is not None and homography is not None and self.is_pre_snap(previous, frame, boxes):
                        for track_id, point in self._track_players(boxes, homography):
                            rows.append({"frame": frame_index, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                    previous = frame
                    processed += 1
                frame_index += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the latest adapter output in the normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
