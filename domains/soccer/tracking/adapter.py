"""Broadcast soccer tracking projected onto a 105 by 68 metre pitch."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional, Sequence, Union
import cv2
import numpy as np
import pandas as pd
from scripts.platformkit.calibration.keypoint_calib import (
    CANONICAL_LANDMARKS,
    TemporalCalibrator,
    project_points,
    solve_homography,
)
from domains.soccer.tracking.segmenter import is_pitch_view
from domains.soccer.tracking.pressing import aggregate_pressing, pressure_index
SCHEMA = ("frame", "track_id", "cls", "x", "y")
PITCH_METRES = np.float32(((0, 0), (105, 0), (0, 68), (105, 68)))
# Deliberately WIDER than the harness soccer bound (0..105, 0..68): players
# legitimately stand off the playing surface (throw-ins beyond the touchline,
# keepers behind the goal line).  An accept window equal to the harness bound
# makes oob_pct a structural 0.0 that can never fail, which is what this was.
PITCH_ACCEPT = (-5.0, 110.0, -5.0, 73.0)
# A 4-point homography is exactly determined, so its own reprojection error is
# identically 0 and evidences nothing.  Five named landmarks let every one of
# them be predicted by a fit that excluded it.
MIN_LANDMARKS = 5
MAX_HELDOUT_ERROR_M = 2.0
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]
Detections = dict[str, tuple[float, float, float]]


class BallTrackingUnavailableError(RuntimeError):
    """Raised when a caller requests unsupported soccer ball tracking."""


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
        self._homography: Optional[np.ndarray] = None
        self._calibrator = TemporalCalibrator("soccer", drift_threshold=8.0)
        self._calibration_updates = 0
        self.last_output = pd.DataFrame(columns=SCHEMA)
        self.last_metadata: dict[str, object] = {}

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("SoccerAdapter requires ultralytics or a test detector.") from exc
        model = YOLO("yolov8n.pt")

        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            return [] if result.boxes is None else result.boxes.xyxy.cpu().numpy().tolist()

        return detect

    @staticmethod
    def _pitch_mask(frame: np.ndarray) -> np.ndarray:
        """Return the largest green field component using HSV and saturation Otsu."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        otsu, _ = cv2.threshold(saturation, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        green = cv2.inRange(hsv, np.array((30, 0, 20)), np.array((95, 255, 255)))
        saturated = cv2.inRange(saturation, max(20, int(otsu)), 255)
        candidate = cv2.bitwise_and(green, saturated)
        candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate)
        if count <= 1:
            return np.zeros(frame.shape[:2], dtype=np.uint8)
        label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        return np.where(labels == label, 255, 0).astype(np.uint8)

    @staticmethod
    def _thin(binary: np.ndarray) -> np.ndarray:
        """Thin a binary line mask without requiring the contrib OpenCV build."""
        ximgproc = getattr(cv2, "ximgproc", None)
        if ximgproc is not None:
            return ximgproc.thinning(binary)
        skeleton = np.zeros_like(binary)
        current = binary.copy()
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        while cv2.countNonZero(current):
            eroded = cv2.erode(current, element)
            skeleton = cv2.bitwise_or(skeleton, cv2.subtract(current, cv2.dilate(eroded, element)))
            current = eroded
        return skeleton

    @classmethod
    def _white_pitch_mask(cls, frame: np.ndarray) -> np.ndarray:
        """Adaptively extract white markings only from the detected pitch."""
        pitch = cls._pitch_mask(frame)
        if not cv2.countNonZero(pitch):
            return pitch
        luminance = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        smallest = min(frame.shape[:2])
        block = max(31, min(91, (smallest // 8) | 1))
        white = cv2.adaptiveThreshold(
            luminance, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, -4,
        )
        support = cv2.dilate(pitch, np.ones((11, 11), np.uint8))
        white = cv2.bitwise_and(white, support)
        white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        return cls._thin(white)

    @staticmethod
    def _line_position(line: np.ndarray, horizontal: bool, shape: tuple[int, int]) -> float:
        x1, y1, x2, y2 = line
        height, width = shape
        if horizontal:
            return float((y1 + y2) / 2.0) if abs(x2 - x1) < 1e-6 else float(y1 + (width / 2 - x1) * (y2 - y1) / (x2 - x1))
        return float((x1 + x2) / 2.0) if abs(y2 - y1) < 1e-6 else float(x1 + (height / 2 - y1) * (x2 - x1) / (y2 - y1))

    @classmethod
    def _cluster_lines(cls, lines: list[np.ndarray], horizontal: bool, shape: tuple[int, int]) -> list[list[np.ndarray]]:
        clusters: list[list[np.ndarray]] = []
        gap = max(12.0, min(shape) / 60.0)
        for line in sorted(lines, key=lambda item: cls._line_position(item, horizontal, shape)):
            position = cls._line_position(line, horizontal, shape)
            if not clusters or abs(position - np.mean([cls._line_position(item, horizontal, shape) for item in clusters[-1]])) > gap:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        return clusters

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return np.array((x0 - 10000 * vx, y0 - 10000 * vy, x0 + 10000 * vx, y0 + 10000 * vy))

    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        point = np.cross(np.cross((first[0], first[1], 1.0), (first[2], first[3], 1.0)), np.cross((second[0], second[1], 1.0), (second[2], second[3], 1.0)))
        return None if abs(point[2]) < 1e-8 else np.float32(point[:2] / point[2])

    def detect_pitch_lines(self, frame: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Find relaxed, image-space horizontal and vertical pitch-line families."""
        height, width = frame.shape[:2]
        lines = cv2.HoughLinesP(self._white_pitch_mask(frame), 1, np.pi / 180, threshold=24, minLineLength=max(35, width // 18), maxLineGap=max(24, width // 24))
        horizontal: list[np.ndarray] = []
        vertical: list[np.ndarray] = []
        if lines is None:
            return horizontal, vertical
        for raw in lines[:, 0, :]:
            line = raw.astype(float)
            angle = abs(np.degrees(np.arctan2(line[3] - line[1], line[2] - line[0]))) % 180
            angle = min(angle, 180 - angle)
            if angle <= 35:
                horizontal.append(line)
            elif angle >= 55:
                vertical.append(line)
        return horizontal, vertical

    def _landmark_detections(self, frame: np.ndarray) -> Detections:
        """Label the outermost visible line clusters as the pitch boundary.

        ponytail: this is the known ceiling and the reason soccer now emits
        nothing.  Nothing ties the outermost DETECTED lines to the touchline and
        goal line -- in a broadcast view they are usually the halfway line and
        the 18-yard box -- so the same physical lines get a different canonical
        identity every frame.  Measured on data/videos/reference/soccer.mp4:
        consecutive candidate homographies disagree by a median 378 m on a 105 m
        pitch, and only 4.6 percent agree within the adapter's own 8 m
        tolerance.  Only four unevidenced names are ever produced, which is
        below MIN_LANDMARKS, so _validated_homography rejects every frame.
        Upgrade path: emit landmarks whose identity is independently evidenced
        (center circle, halfway line, and penalty-box corners verified by the
        16.5 x 40.32 m box aspect ratio) -- all already in CANONICAL_LANDMARKS.
        """
        height, width = frame.shape[:2]
        horizontal, vertical = self.detect_pitch_lines(frame)
        horizontal_clusters = self._cluster_lines(horizontal, True, (height, width))
        vertical_clusters = self._cluster_lines(vertical, False, (height, width))
        if len(horizontal_clusters) < 2 or len(vertical_clusters) < 2:
            return {}
        near, far = self._fit_line(horizontal_clusters[-1]), self._fit_line(horizontal_clusters[0])
        left, right = self._fit_line(vertical_clusters[0]), self._fit_line(vertical_clusters[-1])
        points = [self._intersection(near, left), self._intersection(near, right), self._intersection(far, left), self._intersection(far, right)]
        if any(point is None for point in points):
            return {}
        corners = np.asarray(points, dtype=np.float32)
        if np.any(corners[:, 0] < -width * 0.25) or np.any(corners[:, 0] > width * 1.25) or np.any(corners[:, 1] < -height * 0.25) or np.any(corners[:, 1] > height * 1.25):
            return {}
        return {name: (float(point[0]), float(point[1]), 1.0) for name, point in zip(("pitch_bl", "pitch_br", "pitch_tl", "pitch_tr"), corners)}

    def detect_pitch_markings(self, frame: np.ndarray) -> dict[str, object]:
        """Expose line families and optional center-circle diagnostics."""
        height, width = frame.shape[:2]
        horizontal, vertical = self.detect_pitch_lines(frame)
        clusters = self._cluster_lines(vertical, False, (height, width))
        halfway_x = None if len(clusters) < 3 else min((self._line_position(cluster[0], False, (height, width)) for cluster in clusters), key=lambda value: abs(value - width / 2))
        circles = cv2.HoughCircles(self._white_pitch_mask(frame), cv2.HOUGH_GRADIENT, 1.2, max(40, height // 5), param1=80, param2=14, minRadius=max(15, height // 30), maxRadius=height // 3)
        circle = None if circles is None else tuple(map(float, circles[0, 0]))
        return {"horizontal": horizontal, "vertical": vertical, "halfway_x": halfway_x, "center_circle": circle}

    def detect_pitch_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return near-left, near-right, far-left, far-right pitch corners."""
        detections = self._landmark_detections(frame)
        if len(detections) < 4:
            return None
        return np.float32([detections[name][:2] for name in ("pitch_bl", "pitch_br", "pitch_tl", "pitch_tr")])

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

    @staticmethod
    def _reprojection_error(homography: np.ndarray, detections: Detections) -> float:
        names = [name for name in CANONICAL_LANDMARKS["soccer"] if name in detections]
        pixels = [(detections[name][0], detections[name][1]) for name in names]
        targets = np.asarray([CANONICAL_LANDMARKS["soccer"][name] for name in names])
        return float(np.max(np.linalg.norm(project_points(homography, pixels) - targets, axis=1)))

    def _stable_homography(self, detections: Union[Detections, np.ndarray], shape: tuple[int, int] = (720, 1280)) -> Optional[np.ndarray]:
        if isinstance(detections, np.ndarray):
            detections = {name: (float(point[0]), float(point[1]), 1.0) for name, point in zip(("pitch_bl", "pitch_br", "pitch_tl", "pitch_tr"), detections)}
        if self._validated_homography(detections) is None:
            return None
        result = self._calibrator.update(detections)
        if result.homography is None or result.recompute or not self._in_tolerance(result.homography, shape):
            return None
        self._calibration_updates += 1
        if self._calibration_updates < 9:
            return None
        self._homography = result.homography
        return self._homography

    def _validated_homography(self, detections: Detections) -> Optional[np.ndarray]:
        """Fit only when landmarks held out of the fit confirm it.

        Leave-one-out is the whole point: scoring a fit on the same four points
        that determined it always returns zero and can never reject anything.
        """
        names = [name for name in CANONICAL_LANDMARKS["soccer"] if name in detections]
        if len(names) < MIN_LANDMARKS:
            return None
        for held in names:
            subset = {name: detections[name] for name in names if name != held}
            partial = solve_homography(subset, "soccer", min_conf=0.5)
            if partial is None:
                return None
            if self._reprojection_error(partial, {held: detections[held]}) > MAX_HELDOUT_ERROR_M:
                return None
        return solve_homography(detections, "soccer", min_conf=0.5)

    def _in_tolerance(self, homography: np.ndarray, shape: tuple[int, int]) -> bool:
        if self._homography is None:
            return True
        height, width = shape
        probes = np.float32(((0, 0), (width / 2, height / 2), (width, height)))
        current = cv2.perspectiveTransform(probes.reshape(1, -1, 2), homography)[0]
        previous = cv2.perspectiveTransform(probes.reshape(1, -1, 2), self._homography)[0]
        return bool(np.max(np.linalg.norm(current - previous, axis=1)) <= 8.0)

    def _assign_tracks(self, centers: list[np.ndarray]) -> list[int]:
        available, ids = set(self._tracks), []
        for center in centers:
            nearest = min(available, key=lambda track_id: np.linalg.norm(center - self._tracks[track_id][0]), default=None)
            if nearest is None:
                nearest, self._next_track_id = self._next_track_id, self._next_track_id + 1
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
        """Project person detections and retain nearest-centroid identities."""
        candidates: list[tuple[np.ndarray, np.ndarray]] = []
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 > x1 and y2 > y1:
                point = self._project(((x1 + x2) / 2, y2), homography)
                low_x, high_x, low_y, high_y = PITCH_ACCEPT
                if low_x <= point[0] <= high_x and low_y <= point[1] <= high_y:
                    candidates.append((np.array(((x1 + x2) / 2, (y1 + y2) / 2)), point))
        ids = self._assign_tracks([candidate[0] for candidate in candidates])
        return list(zip(ids, [candidate[1] for candidate in candidates]))

    def process_video(
        self,
        path: Union[str, Path],
        max_frames: Optional[int] = None,
        stride: int = 1,
        skip_non_pitch: bool = True,
        compute_pressing: bool = True,
        player_only: bool = False,
    ) -> pd.DataFrame:
        """Process a headless stream, emitting rows only for validated pitch frames.

        Callers must opt into player-only output: this adapter runs YOLO person
        class 0 only and has no soccer-ball detector, so it cannot satisfy a
        ball-tracking contract.
        """
        if stride < 1:
            raise ValueError("stride must be at least 1")
        if not player_only:
            raise BallTrackingUnavailableError(
                "Soccer ball tracking is unavailable: this adapter runs YOLO "
                "person class 0 only and has no validated ball detector. Use "
                "player_only=True for player-only output."
            )
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        source_frame = processed = 0
        pitch_frames: list[int] = []
        accepted_homography_frames: list[int] = []
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if source_frame % stride == 0:
                    pitch_view = is_pitch_view(frame)
                    if skip_non_pitch and not pitch_view:
                        self.mark_frame_lost()
                        processed += 1
                        source_frame += 1
                        continue
                    if pitch_view:
                        pitch_frames.append(source_frame)
                    homography = self._stable_homography(self._landmark_detections(frame), frame.shape[:2])
                    if homography is None:
                        self.mark_frame_lost()
                    else:
                        accepted_homography_frames.append(source_frame)
                        for track_id, point in self.detect_players(frame, homography):
                            rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        self.last_metadata = {
            "processed_frames": processed,
            "pitch_view_frames": pitch_frames,
            "accepted_homography_frames": accepted_homography_frames,
        }
        if compute_pressing:
            index = pressure_index(self.last_output, ball_proxy=True)
            self.last_metadata["pressing_proxy"] = {
                "per_frame": index,
                "windows": aggregate_pressing(self.last_output, ball_proxy=True),
                "frame_ids": index["frame"].astype(int).tolist(),
            }
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
