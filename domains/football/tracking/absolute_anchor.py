"""Evidence-bearing painted yard-number anchors for football calibration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import cv2
import numpy as np


@dataclass(frozen=True)
class AbsoluteYardAnchor:
    """A painted number and its separately observed longitudinal direction."""

    yard_from_goal: int
    direction: int
    pixel: tuple[float, float]
    confidence: float


class TextReader(Protocol):
    def readtext(self, image: np.ndarray, **kwargs: object) -> list[object]: ...


class PaintedYardAnchorProvider:
    """Find a readable painted number and a nearby, painted direction arrow.

    OCR alone is deliberately insufficient: `40` occurs at both ends of a field.
    The contour test demands a triangular arrow adjacent to the numeral; uncertain
    frames return None instead of guessing a longitudinal orientation.
    """

    def __init__(self, reader: Optional[TextReader] = None) -> None:
        self._reader = reader

    def _reader_or_load(self) -> TextReader:
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self._reader

    @staticmethod
    def _arrow_direction(image: np.ndarray, centre: tuple[float, float]) -> Optional[int]:
        mask = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV),
                           np.array((0, 0, 170)), np.array((180, 110, 255)))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cx, cy = centre
        for contour in contours:
            area = cv2.contourArea(contour)
            if not 20 <= area <= 2500:
                continue
            polygon = cv2.approxPolyDP(contour, 0.08 * cv2.arcLength(contour, True), True)
            x, y, width, height = cv2.boundingRect(contour)
            if len(polygon) != 3 or abs(x + width / 2 - cx) > 180 or abs(y + height / 2 - cy) > 180:
                continue
            points = polygon.reshape(-1, 2)
            tip = points[np.argmax(np.abs(points[:, 0] - points[:, 0].mean()))]
            return 1 if tip[0] >= points[:, 0].mean() else -1
        return None

    def detect(self, frame: np.ndarray) -> Optional[AbsoluteYardAnchor]:
        try:
            readings = self._reader_or_load().readtext(frame, allowlist="0123456789")
        except (ImportError, RuntimeError):
            return None
        for reading in readings:
            box, text, confidence = reading[:3]
            normalized = str(text).strip()
            if normalized not in {"10", "20", "30", "40", "50"} or float(confidence) < 0.70:
                continue
            points = np.asarray(box, dtype=float)
            centre = (float(points[:, 0].mean()), float(points[:, 1].mean()))
            direction = self._arrow_direction(frame, centre)
            if direction is not None:
                return AbsoluteYardAnchor(int(normalized), direction, centre, float(confidence))
        return None
