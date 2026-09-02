"""Conservative semantic keypoints for broadcast soccer calibration.

This provider deliberately refuses to convert arbitrary white-line crossings
into pitch corners.  A visible centre circle can be named only when a line
passes through its centre; the evidence is still insufficient for a planar
solve, but it is a genuine semantic landmark rather than an ordinal guess.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np


Detection = tuple[float, float, float]


class SoccerKeypointProvider:
    """Detect only soccer landmarks supported by feature-specific evidence."""

    def _pitch_mask(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((30, 20, 20)), np.array((95, 255, 255)))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(green)
        if count <= 1:
            return np.zeros(frame.shape[:2], dtype=np.uint8)
        label = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        return np.where(labels == label, 255, 0).astype(np.uint8)

    def _markings(self, frame: np.ndarray) -> np.ndarray:
        pitch = self._pitch_mask(frame)
        if not cv2.countNonZero(pitch):
            return pitch
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        white = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            max(31, (min(frame.shape[:2]) // 8) | 1), -4,
        )
        return cv2.bitwise_and(white, cv2.dilate(pitch, np.ones((9, 9), np.uint8)))

    @staticmethod
    def _crossing_line(mask: np.ndarray, center: tuple[float, float], radius: float) -> bool:
        lines = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=30,
                                minLineLength=max(45, int(radius * 1.6)),
                                maxLineGap=max(12, int(radius * 0.35)))
        if lines is None:
            return False
        cx, cy = center
        for x1, y1, x2, y2 in lines.reshape(-1, lines.shape[-1]):
            length = float(np.hypot(x2 - x1, y2 - y1))
            if not length:
                continue
            distance = abs((y2 - y1) * cx - (x2 - x1) * cy + x2 * y1 - y2 * x1) / length
            if distance <= max(4.0, radius * 0.12):
                return True
        return False

    def detect(self, frame: np.ndarray) -> dict[str, Detection]:
        """Return named centre-circle evidence, never position-ordered corners."""
        mask = self._markings(frame)
        height = frame.shape[0]
        circles = cv2.HoughCircles(
            mask, cv2.HOUGH_GRADIENT, 1.2, max(50, height // 4), param1=80,
            param2=18, minRadius=max(18, height // 35), maxRadius=max(24, height // 3),
        )
        if circles is None:
            return {}
        candidates = []
        for x, y, radius in circles[0]:
            if self._crossing_line(mask, (float(x), float(y)), float(radius)):
                candidates.append((float(x), float(y), float(radius)))
        if len(candidates) != 1:
            return {}
        x, y, radius = candidates[0]
        confidence = min(1.0, 0.55 + radius / max(1.0, height))
        return {"center_circle": (x, y, confidence)}

    def diagnostics(self, frame: np.ndarray) -> dict[str, Optional[tuple[float, float, float]]]:
        """Expose the raw circle candidate for inspection without naming it."""
        mask = self._markings(frame)
        circles = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, 1.2, 50,
                                   param1=80, param2=18, minRadius=18,
                                   maxRadius=max(24, frame.shape[0] // 3))
        raw = None if circles is None else tuple(map(float, circles[0, 0]))
        named = self.detect(frame).get("center_circle")
        return {"raw_circle": raw, "center_circle": named}
