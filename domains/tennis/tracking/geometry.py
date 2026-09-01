"""Tennis court geometry and temporal calibration helpers."""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator


COURT_FEET = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))


class TennisGeometryMixin:
    @staticmethod
    def _line_position(line: np.ndarray, horizontal: bool, shape: tuple[int, int]) -> float:
        x1, y1, x2, y2 = line
        height, width = shape
        if horizontal:
            return float((y1 + y2) / 2.0) if abs(x2 - x1) < 1e-6 else float(y1 + (width / 2.0 - x1) * (y2 - y1) / (x2 - x1))
        return float((x1 + x2) / 2.0) if abs(y2 - y1) < 1e-6 else float(x1 + (height / 2.0 - y1) * (x2 - x1) / (y2 - y1))

    @classmethod
    def _cluster_lines(cls, lines: list[np.ndarray], horizontal: bool, shape: tuple[int, int]) -> list[list[np.ndarray]]:
        clusters: list[list[np.ndarray]] = []
        for line in sorted(lines, key=lambda item: cls._line_position(item, horizontal, shape)):
            if not clusters:
                clusters.append([line])
                continue
            position = cls._line_position(line, horizontal, shape)
            previous = np.mean([cls._line_position(item, horizontal, shape) for item in clusters[-1]])
            (clusters[-1] if abs(position - previous) <= 12.0 else clusters).append(line if abs(position - previous) <= 12.0 else [line])
        return clusters

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return np.array((x0 - 10000 * vx, y0 - 10000 * vy, x0 + 10000 * vx, y0 + 10000 * vy))

    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        point = np.cross(np.cross(np.array((first[0], first[1], 1.0)), np.array((first[2], first[3], 1.0))), np.cross(np.array((second[0], second[1], 1.0)), np.array((second[2], second[3], 1.0))))
        return None if abs(point[2]) < 1e-8 else np.float32(point[:2] / point[2])

    def detect_court_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return near-left, near-right, far-left, far-right doubles corners."""
        height, width = frame.shape[:2]
        bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
        lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45, minLineLength=max(40, width // 12), maxLineGap=20)
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
        far, near = self._fit_line(horizontal_clusters[0]), self._fit_line(horizontal_clusters[-1])
        left, right = self._fit_line(vertical_clusters[0]), self._fit_line(vertical_clusters[-1])
        corners = [self._intersection(near, left), self._intersection(near, right), self._intersection(far, left), self._intersection(far, right)]
        if any(point is None for point in corners):
            return None
        result = np.asarray(corners, dtype=np.float32)
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
        detections = {name: (float(point[0]), float(point[1]), 1.0) for name, point in zip(("doubles_bl", "doubles_tl", "doubles_br", "doubles_tr"), corners)}
        result = self._calibrator.update(detections)
        if result.homography is None or result.recompute or not self._in_tolerance(result.homography, frame.shape[:2]):
            self._calibration_provenance = "propagated" if self._homography is not None else "unavailable"
            return self._homography
        self._calibration_updates += 1
        if self._calibration_updates < 9 and not self._force_homography_recompute:
            return None
        self._corners, self._homography = corners, result.homography
        self._calibration_provenance = "solved"
        self._force_homography_recompute = False
        return self._homography
