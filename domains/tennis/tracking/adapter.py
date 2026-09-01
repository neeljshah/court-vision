"""Fixed-camera tennis broadcast tracking in normalized court feet."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional, Sequence, Union
import cv2
import numpy as np
import pandas as pd
from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator
from domains.tennis.tracking.geometry import TennisGeometryMixin
from domains.tennis.tracking.ball import MotionDiffDetector, ball_rows, rectify_track
from domains.tennis.tracking.rally_features import match_aggregates
from domains.tennis.tracking.segmenter import detect_cut, small_gray
SCHEMA = ("frame", "track_id", "cls", "x", "y", "calibration_provenance")
# Court x is the 78-foot length; y is the 36-foot width.
COURT_FEET = np.float32(((0, 0), (0, 36), (78, 0), (78, 36))); Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]
# Same physical acceptance region as before the corrected court-axis mapping.
ACCEPT_FEET = (-10.83, 88.83, -2.31, 38.31)
def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write player tracking rows in the normalized platform schema."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing: raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True); rows.loc[:, SCHEMA].to_csv(path, index=False)
class TennisAdapter(TennisGeometryMixin):
    """Track two tennis players from a fixed behind-baseline broadcast feed."""
    def __init__(
        self,
        detector: Optional[Detector] = None,
        corner_stability_px: float = 5.0,
        imgsz: int = 640,
        conf: float = 0.25,
        tracker_conf: Optional[float] = None,
    ) -> None:
        if imgsz <= 0 or not 0.0 <= conf <= 1.0:
            raise ValueError("imgsz must be positive and conf must be in [0, 1]")
        self.imgsz, self.conf = int(imgsz), float(conf)
        self.tracker_conf = float(conf if tracker_conf is None else tracker_conf)
        if not 0.0 <= self.tracker_conf <= 1.0:
            raise ValueError("tracker_conf must be in [0, 1]")
        self.detector = detector if detector is not None else self._load_yolo_detector(self.imgsz, self.conf)
        self.corner_stability_px = corner_stability_px
        self._corners = self._homography = None
        self._calibration_provenance = "unavailable"
        self._calibrator = TemporalCalibrator("tennis", drift_threshold=8.0)
        self._calibration_updates = self._lost_corner_frames = 0
        self._force_homography_recompute = False
        self._centroids: dict[int, np.ndarray] = {}
        self.last_output, self.last_metadata = pd.DataFrame(columns=SCHEMA), {}

    @staticmethod
    def _load_yolo_detector(imgsz: int, conf: float) -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("TennisAdapter requires ultralytics; install it or pass a detector.") from exc
        model = YOLO("yolov8n.pt")
        emitted = False
        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            nonlocal emitted
            if not emitted:
                print("TENNIS_INFERENCE imgsz=%d conf=%.3f" % (imgsz, conf))
                emitted = True
            result = model(frame, classes=[0], imgsz=imgsz, conf=conf, verbose=False)[0]
            if result.boxes is None:
                return []
            return [box + [float(score)] for box, score in zip(result.boxes.xyxy.cpu().numpy().tolist(), result.boxes.conf.cpu().numpy().tolist())]
        return detect
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
    @staticmethod
    def _cluster_lines(
        lines: list[np.ndarray], horizontal: bool, shape: tuple[int, int]
    ) -> list[list[np.ndarray]]:
        ordered = sorted(
            lines, key=lambda line: TennisAdapter._line_position(line, horizontal, shape)
        )
        clusters: list[list[np.ndarray]] = []
        for line in ordered:
            if not clusters:
                clusters.append([line])
                continue
            position = TennisAdapter._line_position(line, horizontal, shape)
            previous = np.mean([
                TennisAdapter._line_position(item, horizontal, shape)
                for item in clusters[-1]
            ])
            if abs(position - previous) <= 12.0:
                clusters[-1].append(line)
            else:
                clusters.append([line])
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
        a = np.cross(
            np.array((first[0], first[1], 1.0)), np.array((first[2], first[3], 1.0))
        )
        b = np.cross(
            np.array((second[0], second[1], 1.0)), np.array((second[2], second[3], 1.0))
        )
        point = np.cross(a, b)
        if abs(point[2]) < 1e-8:
            return None
        return np.float32(point[:2] / point[2])
    def detect_court_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return near-left, near-right, far-left, far-right doubles corners."""
        height, width = frame.shape[:2]
        bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
        lines = cv2.HoughLinesP(
            bright, 1, np.pi / 180.0, threshold=45,
            minLineLength=max(40, width // 12), maxLineGap=20,
        )
        if lines is None:
            return None
        horizontal: list[np.ndarray] = []
        vertical: list[np.ndarray] = []
        for raw_line in lines[:, 0, :]:
            line = raw_line.astype(float)
            dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
            if dx >= 1.5 * dy:
                horizontal.append(line)
            elif dy > dx:
                vertical.append(line)
        if len(horizontal) < 2 or len(vertical) < 2:
            return None
        horizontal_clusters = self._cluster_lines(horizontal, True, (height, width))
        vertical_clusters = self._cluster_lines(vertical, False, (height, width))
        if len(horizontal_clusters) < 2 or len(vertical_clusters) < 2:
            return None
        # Known limitation: the far baseline can be absent from bright-line clusters; treat tennis x as ordinal, not feet.
        far = self._fit_line(horizontal_clusters[0])
        near = self._fit_line(horizontal_clusters[-1])
        left = self._fit_line(vertical_clusters[0])
        right = self._fit_line(vertical_clusters[-1])
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
        """Map ordered image doubles-court corners to a 78 by 36 foot plane."""
        homography, _ = cv2.findHomography(np.asarray(corners, dtype=np.float32), COURT_FEET)
        if homography is None:
            raise ValueError("Could not calculate court homography")
        return homography
    @staticmethod
    def _project(point: tuple[float, float], homography: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.float32([[point]]), homography)[0, 0]
    def _in_tolerance(self, homography: np.ndarray, shape: tuple[int, int]) -> bool:
        if self._homography is None:
            return True
        height, width = shape
        probes = np.float32(((0, 0), (width / 2, height / 2), (width, height)))
        current = cv2.perspectiveTransform(probes.reshape(1, -1, 2), homography)[0]
        previous = cv2.perspectiveTransform(probes.reshape(1, -1, 2), self._homography)[0]
        return bool(np.max(np.linalg.norm(current - previous, axis=1)) <= 8.0)
    def _reset_temporal_calibration(self) -> None:
        """Drop camera-specific calibration history after a cut or prolonged loss."""
        self._corners = self._homography = None
        self._calibrator = TemporalCalibrator("tennis", drift_threshold=8.0)
        self._calibration_updates = self._lost_corner_frames = 0
        self._force_homography_recompute = True

    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        corners = self.detect_court_corners(frame)
        if corners is None:
            self._lost_corner_frames += 1
            if self._lost_corner_frames > 30:
                self._reset_temporal_calibration()
            self._calibration_provenance = "propagated" if self._homography is not None else "unavailable"
            return self._homography
        self._lost_corner_frames = 0
        detections = {
            name: (float(point[0]), float(point[1]), 1.0)
            for name, point in zip(
                ("doubles_bl", "doubles_tl", "doubles_br", "doubles_tr"), corners
            )
        }
        result = self._calibrator.update(detections)
        if result.homography is None or result.recompute or not self._in_tolerance(result.homography, frame.shape[:2]):
            self._calibration_provenance = "propagated" if self._homography is not None else "unavailable"
            return self._homography
        self._calibration_updates += 1
        if self._calibration_updates < 9 and not self._force_homography_recompute:
            return None
        self._corners = corners
        self._homography = result.homography
        self._calibration_provenance = "solved"
        self._force_homography_recompute = False
        return self._homography

    def _track_ids(self, candidates: list[tuple[np.ndarray, np.ndarray]]) -> list[tuple[int, np.ndarray]]:
        centers = [candidate[0] for candidate in candidates]
        if set(self._centroids) != {1, 2}:
            order = sorted(range(2), key=lambda index: (-centers[index][1], centers[index][0]))
        else:
            direct = np.linalg.norm(centers[0] - self._centroids[1]) + np.linalg.norm(centers[1] - self._centroids[2])
            crossed = np.linalg.norm(centers[1] - self._centroids[1]) + np.linalg.norm(centers[0] - self._centroids[2])
            order = [0, 1] if direct <= crossed else [1, 0]
        tracked = [(track_id, candidates[index][1]) for track_id, index in enumerate(order, start=1)]
        self._centroids = {track_id: centers[index] for track_id, index in enumerate(order, start=1)}
        return tracked
    def detect_players(self, frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return two player ids and their court-foot locations, when visible."""
        per_half: dict[int, tuple[float, np.ndarray, np.ndarray]] = {}
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if len(box) >= 5 and float(box[4]) < self.tracker_conf:
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            foot = self._project(((x1 + x2) / 2.0, y2), homography)
            if not (ACCEPT_FEET[0] <= foot[0] <= ACCEPT_FEET[1] and ACCEPT_FEET[2] <= foot[1] <= ACCEPT_FEET[3]):
                continue
            half = 0 if foot[0] < 39.0 else 1
            area = (x2 - x1) * (y2 - y1)
            center = np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
            if half not in per_half or area > per_half[half][0]:
                per_half[half] = (area, center, foot)
        if set(per_half) != {0, 1}:
            return []
        return self._track_ids([(per_half[0][1], per_half[0][2]), (per_half[1][1], per_half[1][2])])
    def process_video(
        self,
        path: Union[str, Path],
        max_frames: Optional[int] = None,
        stride: int = 1,
        compute_features: bool = False,
    ) -> Union[pd.DataFrame, tuple[pd.DataFrame, dict[str, object]]]:
        """Process video into rows, optionally returning descriptive rally metadata."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        ball_detector = MotionDiffDetector()
        ball_points: list[Optional[tuple[float, float, float]]] = []
        ball_frames: list[tuple[int, np.ndarray]] = []
        source_frame = processed = 0
        previous_gray_small: Optional[np.ndarray] = None
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                current_gray_small = small_gray(frame)
                if previous_gray_small is not None and detect_cut(previous_gray_small, current_gray_small):
                    self._reset_temporal_calibration()
                previous_gray_small = current_gray_small
                if source_frame % stride == 0:
                    homography = self._stable_homography(frame)
                    if homography is not None:
                        for track_id, point in self.detect_players(frame, homography):
                            rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1]), "calibration_provenance": self._calibration_provenance})
                        ball_points.append(ball_detector.detect(frame))
                        ball_frames.append((source_frame, homography, self._calibration_provenance))
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        for point, (frame, homography, provenance) in zip(rectify_track(ball_points), ball_frames):
            balls = ball_rows((point,), homography)
            if not balls.empty:
                ball = balls.iloc[0].to_dict()
                ball["frame"] = frame
                ball["calibration_provenance"] = provenance
                rows.append(ball)
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        self.last_metadata = {}
        if compute_features:
            self.last_metadata = {"rally_features": match_aggregates(self.last_output)}
            return self.last_output, self.last_metadata
        return self.last_output
    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
