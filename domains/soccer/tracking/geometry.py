"""Soccer pitch geometry and validated homography helpers."""
from __future__ import annotations

from typing import Optional, Union

import cv2
import numpy as np

from domains.soccer.tracking.keypoints import SoccerKeypointProvider
from scripts.platformkit.calibration.keypoint_calib import CANONICAL_LANDMARKS, project_points, solve_homography


PITCH_METRES = np.float32(((0, 0), (105, 0), (0, 68), (105, 68)))
MIN_LANDMARKS = 5
MAX_HELDOUT_ERROR_M = 2.0
Detections = dict[str, tuple[float, float, float]]


class SoccerGeometryMixin:
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
        skeleton, current = np.zeros_like(binary), binary.copy()
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
        block = max(31, min(91, (min(frame.shape[:2]) // 8) | 1))
        white = cv2.adaptiveThreshold(luminance, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, -4)
        white = cv2.bitwise_and(white, cv2.dilate(pitch, np.ones((11, 11), np.uint8)))
        return cls._thin(cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)))

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
            angle = min(abs(np.degrees(np.arctan2(line[3] - line[1], line[2] - line[0]))) % 180, 180 - (abs(np.degrees(np.arctan2(line[3] - line[1], line[2] - line[0]))) % 180))
            if angle <= 35:
                horizontal.append(line)
            elif angle >= 55:
                vertical.append(line)
        return horizontal, vertical

    def _landmark_detections(self, frame: np.ndarray) -> Detections:
        return self._keypoint_provider.detect(frame)

    def detect_pitch_markings(self, frame: np.ndarray) -> dict[str, object]:
        """Expose line families and optional center-circle diagnostics."""
        height, width = frame.shape[:2]
        horizontal, vertical = self.detect_pitch_lines(frame)
        clusters = self._cluster_lines(vertical, False, (height, width))
        halfway_x = None if len(clusters) < 3 else min((self._line_position(cluster[0], False, (height, width)) for cluster in clusters), key=lambda value: abs(value - width / 2))
        diagnostics = self._keypoint_provider.diagnostics(frame)
        return {"horizontal": horizontal, "vertical": vertical, "halfway_x": halfway_x,
                "center_circle": diagnostics["center_circle"],
                "raw_circle": diagnostics["raw_circle"]}

    def detect_pitch_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return nothing until semantic corner-arc identification is implemented."""
        return None

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
        names = [name for name in CANONICAL_LANDMARKS["soccer"] if name in detections]
        if len(names) < MIN_LANDMARKS:
            return None
        for held in names:
            partial = solve_homography({name: detections[name] for name in names if name != held}, "soccer", min_conf=0.5)
            if partial is None or self._reprojection_error(partial, {held: detections[held]}) > MAX_HELDOUT_ERROR_M:
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
