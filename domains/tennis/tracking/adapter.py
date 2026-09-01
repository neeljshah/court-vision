"""Fixed-camera tennis broadcast tracking in normalized court feet."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable, Optional, Sequence, Union
import cv2
import numpy as np
import pandas as pd
from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator
from domains.tennis.tracking.ball import MotionDiffDetector, ball_rows, rectify_track
from domains.tennis.tracking.frame_manifest import FRAME_MANIFEST_SCHEMA, write_frame_manifest
from domains.tennis.tracking.rally_features import match_aggregates
from domains.tennis.tracking.segmenter import detect_cut, small_gray
from scripts.platformkit.coordinate_provenance import stamp_court_space_rows, write_tracking_csv
SCHEMA = ("frame", "track_id", "cls", "x", "y", "calibration_provenance")
COURT_FEET = np.float32(((0, 0), (0, 36), (78, 0), (78, 36))); Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]
# Projective invariant for the five length-running court lines.
CROSS_RATIO = 567.0 / 486.0
# Near doubles corners, far-left endpoint, and near service T.
ANCHOR_FEET = np.float32(((0, 0), (0, 36), (78, 0), (18, 18)))
def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write player tracking rows in the normalized platform schema."""
    write_tracking_csv(rows, path, SCHEMA)
class TennisAdapter:
    """Track two tennis players from a fixed behind-baseline broadcast feed."""
    def __init__(self, detector: Optional[Detector] = None, corner_stability_px: float = 5.0,
                 imgsz: int = 640, conf: float = 0.25,
                 tracker_conf: Optional[float] = None) -> None:
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
        self._calibration_updates = self._lost_corner_frames = 0; self._force_homography_recompute = False
        self._centroids: dict[int, np.ndarray] = {}
        self.last_output, self.last_metadata = pd.DataFrame(columns=SCHEMA), {}
        self.last_frame_manifest = pd.DataFrame(columns=FRAME_MANIFEST_SCHEMA)
    @staticmethod
    def _load_yolo_detector(imgsz: int, conf: float) -> Detector:
        from scripts.platformkit.detection.shim import get_box_detector
        return get_box_detector(
            model_path=os.environ.get("CV_DETECTOR_MODEL"), sport="tennis"
        )

    @staticmethod
    def _line_position(line: np.ndarray, horizontal: bool, shape: tuple[int, int]) -> float:
        x1, y1, x2, y2 = line
        height, width = shape
        if horizontal:
            return float((y1 + y2) / 2.0) if abs(x2 - x1) < 1e-6 else float(y1 + (width / 2.0 - x1) * (y2 - y1) / (x2 - x1))
        return float((x1 + x2) / 2.0) if abs(y2 - y1) < 1e-6 else float(x1 + (height / 2.0 - y1) * (x2 - x1) / (y2 - y1))
    @staticmethod
    def _cluster_lines(lines: list[np.ndarray], horizontal: bool,
                       shape: tuple[int, int]) -> list[list[np.ndarray]]:
        clusters: list[list[np.ndarray]] = []
        for line in sorted(lines, key=lambda item: TennisAdapter._line_position(item, horizontal, shape)):
            position = TennisAdapter._line_position(line, horizontal, shape)
            previous = np.mean([TennisAdapter._line_position(item, horizontal, shape) for item in clusters[-1]]) if clusters else None
            if previous is not None and abs(position - previous) <= 12.0:
                clusters[-1].append(line)
            else:
                clusters.append([line])
        return clusters
    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return np.array((x0 - 10000 * vx, y0 - 10000 * vy, x0 + 10000 * vx, y0 + 10000 * vy))
    @staticmethod
    def _point_at_row(line: np.ndarray, row: float) -> np.ndarray:
        x1, y1, x2, y2 = line
        return (np.float32((x1, row)) if abs(y2 - y1) < 1e-9
                else np.float32((x1 + (row - y1) * (x2 - x1) / (y2 - y1), row)))
    @staticmethod
    def _endpoint_rows(cluster: list[np.ndarray]) -> tuple[float, float]:
        """Topmost and bottommost image row the cluster's bright pixels reach."""
        rows = [line[1] for line in cluster] + [line[3] for line in cluster]
        return float(min(rows)), float(max(rows))
    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        a = np.cross(np.array((first[0], first[1], 1.0)), np.array((first[2], first[3], 1.0)))
        b = np.cross(np.array((second[0], second[1], 1.0)), np.array((second[2], second[3], 1.0)))
        point = np.cross(a, b)
        return None if abs(point[2]) < 1e-8 else np.float32(point[:2] / point[2])
    def detect_court_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return near-left, near-right, far-left, far-right doubles corners."""
        height, width = frame.shape[:2]
        bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
        lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                                minLineLength=max(40, width // 12), maxLineGap=20)
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
        # Require the court's five length-running lines and their cross ratio.
        if not horizontal_clusters or len(vertical_clusters) != 5:
            return None
        across = [self._line_position(self._fit_line(cluster), False, (height, width))
                  for cluster in vertical_clusters]
        denominator = (across[2] - across[1]) * (across[4] - across[0])
        if abs(denominator) < 1e-6 or abs(
                (across[2] - across[0]) * (across[4] - across[1]) / denominator - CROSS_RATIO) > 0.05:
            return None
        near = self._fit_line(horizontal_clusters[-1])
        left = self._fit_line(vertical_clusters[0])
        right = self._fit_line(vertical_clusters[-1])
        centre = self._fit_line(vertical_clusters[2])
        far_left = self._point_at_row(left, self._endpoint_rows(vertical_clusters[0])[0])
        service_t = self._point_at_row(centre, self._endpoint_rows(vertical_clusters[2])[1])
        near_left, near_right = self._intersection(near, left), self._intersection(near, right)
        # Depth decreases up a behind-baseline broadcast frame.
        if near_left is None or near_right is None or not far_left[1] < service_t[1] < near_left[1]:
            return None
        anchors = np.float32((near_left, near_right, far_left, service_t))
        to_image, _ = cv2.findHomography(ANCHOR_FEET, anchors)
        if to_image is None:
            return None
        far_right = self._project((78.0, 36.0), to_image)
        result = np.asarray((near_left, near_right, far_left, far_right), dtype=np.float32)
        # A camera behind the near baseline sees both baselines near-parallel, so
        # the far edge cannot be steeply skewed against the court's image depth.
        # Rejects a replay frame whose five verticals happened to land in the
        # court's cross ratio (skew 0.62 there, <= 0.09 on every main-camera
        # frame) and then propagated a wrecked homography over 40 frames.
        depth = float(result[0][1] - result[2][1])
        if depth <= 0.0 or abs(result[2][1] - result[3][1]) > 0.25 * depth:
            return None
        if np.any(result[:, 0] < -5) or np.any(result[:, 0] > width + 5) or np.any(result[:, 1] < -5) or np.any(result[:, 1] > height + 5):
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
        self._corners = self._homography = None; self._centroids = {}
        self._calibrator = TemporalCalibrator("tennis", drift_threshold=8.0)
        self._calibration_updates = self._lost_corner_frames = 0; self._force_homography_recompute = True
    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        corners = self.detect_court_corners(frame)
        if corners is None:
            self._lost_corner_frames += 1
            if self._lost_corner_frames > 30:
                self._reset_temporal_calibration()
            # A court-foot row needs a solve from this frame.  Carrying the
            # previous matrix through a close-up or replay made stale geometry
            # look like a contemporaneous calibration.
            self._calibration_provenance = "unavailable"
            return None
        self._lost_corner_frames = 0
        detections = {name: (float(point[0]), float(point[1]), 1.0) for name, point
                      in zip(("doubles_bl", "doubles_tl", "doubles_br", "doubles_tr"), corners)}
        result = self._calibrator.update(detections)
        if result.homography is None or result.recompute or not self._in_tolerance(result.homography, frame.shape[:2]):
            self._calibration_provenance = "unavailable"
            return None
        self._calibration_updates += 1
        self._corners, self._homography = corners, result.homography
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
            # Do not filter coordinates inside the harness bounds.
            half = 0 if foot[0] < 39.0 else 1
            center = np.array(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
            # Prefer centroid continuity over pixel area.
            key = -min(np.linalg.norm(center - prior) for prior in self._centroids.values()) if self._centroids else (x2 - x1) * (y2 - y1)
            if half not in per_half or key > per_half[half][0]:
                per_half[half] = (key, center, foot)
        if set(per_half) != {0, 1}:
            return []
        return self._track_ids([(per_half[0][1], per_half[0][2]), (per_half[1][1], per_half[1][2])])
    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None,
                      stride: int = 1, compute_features: bool = False
                      ) -> Union[pd.DataFrame, tuple[pd.DataFrame, dict[str, object]]]:
        """Process video into rows, optionally returning descriptive rally metadata."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []; manifest: list[dict[str, object]] = []
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
                evaluated = source_frame % stride == 0
                if evaluated:
                    homography = self._stable_homography(frame)
                    player_count = 0
                    if homography is not None:
                        players = self.detect_players(frame, homography)
                        player_count = len(players)
                        for track_id, point in players:
                            rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1]), "calibration_provenance": self._calibration_provenance})
                        ball_points.append(ball_detector.detect(frame))
                        ball_frames.append((source_frame, homography, self._calibration_provenance))
                    status = ("calibration_unavailable" if homography is None else
                              "emitted_players" if player_count else "no_complete_player_pair")
                    processed += 1
                else:
                    status, player_count = "skipped_stride", 0
                manifest.append({"frame": source_frame, "evaluated": evaluated, "status": status,
                                 "calibration_provenance": (self._calibration_provenance if evaluated else "not_evaluated"),
                                 "emitted_player_rows": player_count})
                source_frame += 1
        finally:
            capture.release()
        for point, (frame, homography, provenance) in zip(rectify_track(ball_points), ball_frames):
            balls = ball_rows((point,), homography)
            if not balls.empty:
                ball = balls.iloc[0].to_dict()
                ball["frame"], ball["calibration_provenance"] = frame, provenance
                rows.append(ball)
        # Declare the coordinate space: an omitted declaration is exactly how
        # pixels were laundered into court units elsewhere in this system.
        self.last_output = stamp_court_space_rows(
            pd.DataFrame(rows, columns=SCHEMA), "tennis")
        self.last_frame_manifest = pd.DataFrame(manifest, columns=FRAME_MANIFEST_SCHEMA)
        self.last_metadata = {}
        if not compute_features:
            return self.last_output
        self.last_metadata = {"rally_features": match_aggregates(self.last_output)}
        return self.last_output, self.last_metadata
    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write tracking rows and the required per-decoded-frame manifest."""
        write_csv(self.last_output if rows is None else rows, path)
        write_frame_manifest(self.last_frame_manifest, path)
