"""Fail-closed NFL numeral OCR and point-registration measurement.

This is deliberately a probe, not an adapter fallback.  It never uses the
yard-family cross-ratio and never emits court coordinates.  A caller may use a
reported homography only after its held-out and independent-scale gates pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

import cv2
import numpy as np

from domains.football.tracking.field_gates import field_roi_mask
from domains.football.tracking.geometry import NFL_FIELD_NUMERAL_HEIGHT_FT

VALID_NUMERALS = frozenset((10, 20, 30, 40, 50))
NUMERAL_SIDELINE_OFFSET_FT = 27.0
FIELD_WIDTH_FT = 160.0


class TextReader(Protocol):
    """The small EasyOCR surface used here, enabling deterministic tests."""

    def readtext(self, image: np.ndarray, **kwargs: object) -> list[object]: ...


@dataclass(frozen=True)
class NumeralRead:
    """One confidence-filtered painted numeral crop and its closest field line."""

    value: int
    confidence: float
    box: tuple[float, float, float, float]
    line: np.ndarray


@dataclass(frozen=True)
class RegistrationResult:
    """A point solve plus held-out and NFL numeral-height measurements."""

    homography: Optional[np.ndarray]
    used: int
    held_out_error_ft: Optional[float]
    scale_error_pct: Optional[float]


def _reader_or_load(reader: Optional[TextReader]) -> TextReader:
    if reader is not None:
        return reader
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _white_candidates(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return joined digit crops on field paint, never scoreboard graphics."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, np.array((0, 0, 165)), np.array((180, 100, 255)))
    paint = cv2.bitwise_and(white, field_roi_mask(frame))
    contours, _ = cv2.findContours(paint, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if 18 <= height <= frame.shape[0] // 3 and 0.12 <= width / max(height, 1) <= 2.5:
            raw.append((x, y, width, height))
    result = []
    for first in raw:
        close = [second for second in raw
                 if abs((first[1] + first[3] / 2) - (second[1] + second[3] / 2)) <= max(first[3], second[3]) * .5
                 and abs((first[0] + first[2] / 2) - (second[0] + second[2] / 2)) <= 3 * max(first[3], second[3])]
        left, top = min(item[0] for item in close), min(item[1] for item in close)
        right = max(item[0] + item[2] for item in close)
        bottom = max(item[1] + item[3] for item in close)
        box = (left, top, right - left, bottom - top)
        if box not in result:
            result.append(box)
    # Paint fragmentation can produce dozens of overlapping versions of a
    # single numeral. Keep the largest candidate, the same first-pass evidence
    # unit counted by the earlier numeral funnel, to bound OCR per frame.
    return sorted(result, key=lambda item: item[2] * item[3], reverse=True)[:1]


def _value(text: object) -> Optional[int]:
    digits = "".join(character for character in str(text) if character.isdigit())
    if digits in {"1", "2", "3", "4", "5"}:
        return int(digits) * 10
    value = int(digits) if digits else -1
    return value if value in VALID_NUMERALS else None


def _line_distance(line: np.ndarray, point: tuple[float, float]) -> float:
    a, b, c = np.asarray(line, dtype=float)
    return abs(a * point[0] + b * point[1] + c) / max(float(np.hypot(a, b)), 1e-12)


def recognize(frame: np.ndarray, lines: Sequence[np.ndarray], reader: Optional[TextReader] = None) -> list[NumeralRead]:
    """OCR candidate crops with digits-only EasyOCR and attach their nearest line."""
    if not lines:
        return []
    ocr = _reader_or_load(reader)
    result = []
    for x, y, width, height in _white_candidates(frame):
        margin = max(8, int(round(height * .35)))
        crop = frame[max(0, y - margin):min(frame.shape[0], y + height + margin),
                     max(0, x - margin):min(frame.shape[1], x + width + margin)]
        for reading in ocr.readtext(crop, allowlist="0123456789", detail=1):
            if len(reading) < 3 or float(reading[2]) < .60:
                continue
            value = _value(reading[1])
            if value is None:
                continue
            centre = (x + width / 2.0, y + height / 2.0)
            line = min(lines, key=lambda item: _line_distance(item, centre))
            result.append(NumeralRead(value, float(reading[2]), (float(x), float(y), float(width), float(height)), line))
            break
    return result


def _line_intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
    point = np.cross(np.asarray(first, dtype=float), np.asarray(second, dtype=float))
    if abs(point[2]) < 1e-9:
        return None
    return point[:2] / point[2]


def _box_lines(box: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    x, y, width, height = box
    return np.array((1.0, 0.0, -(x + width / 2.0))), np.array((0.0, 1.0, -(y + height / 2.0)))


def _points(reading: NumeralRead, side: int) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Make two image/field points from numeral line intersection and 6-ft height.

    ``side`` is observed image ordering (-1 upper, +1 lower), not inferred
    from OCR.  The numeral centre is 27 ft inboard of that sideline.  Its box
    height contributes the independent 6-ft painted-height direction.
    """
    _vertical, horizontal = _box_lines(reading.box)
    crossing = _line_intersection(reading.line, horizontal)
    if crossing is None:
        return None
    longitudinal = float(reading.value * 3)
    lateral = NUMERAL_SIDELINE_OFFSET_FT if side < 0 else FIELD_WIDTH_FT - NUMERAL_SIDELINE_OFFSET_FT
    image = np.array((crossing, (reading.box[0] + reading.box[2] / 2.0, reading.box[1] + reading.box[3])))
    field = np.array(((longitudinal, lateral),
                      (longitudinal, lateral + side * NFL_FIELD_NUMERAL_HEIGHT_FT / 2.0)))
    return image, field


def solve(readings: Sequence[NumeralRead], side: int) -> RegistrationResult:
    """Fit a point H and leave one numeral out for an ungameable error check."""
    points = [(reading, _points(reading, side)) for reading in readings]
    points = [(reading, pair) for reading, pair in points if pair is not None]
    if len(points) < 3:
        return RegistrationResult(None, 0, None, None)
    held, fit = points[-1], points[:-1]
    image = np.concatenate([pair[0] for _, pair in fit]).astype(np.float32)
    field = np.concatenate([pair[1] for _, pair in fit]).astype(np.float32)
    homography, _ = cv2.findHomography(image, field, method=0)
    if homography is None or not np.isfinite(homography).all():
        return RegistrationResult(None, len(fit), None, None)
    held_image, held_field = held[1]
    projected = cv2.perspectiveTransform(held_image.reshape(1, -1, 2).astype(np.float32), homography)[0]
    error = float(np.linalg.norm(projected[0] - held_field[0]))
    source = np.float32([[[held[0].box[0] + held[0].box[2] / 2.0, held[0].box[1]],
                          [held[0].box[0] + held[0].box[2] / 2.0, held[0].box[1] + held[0].box[3]]]])
    mapped = cv2.perspectiveTransform(source, homography)[0]
    scale = abs(float(np.linalg.norm(mapped[1] - mapped[0])) / NFL_FIELD_NUMERAL_HEIGHT_FT - 1.0) * 100.0
    return RegistrationResult(homography, len(fit), error, scale)
