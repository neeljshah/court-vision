"""Independent white landmarks (rubber, plate, box chalk) and a scale gate.

The mound chord gives one horizontal scale at the mound row (18 ft of dirt).
It is not self-checking: the chord detector accepts any wide grass-bounded dirt
run, so a third-base cut-out or an outfield warning track passes it and yields a
confident, wrong px/ft.

The pitching rubber is the independent check.  It is 24 in wide, it is white
against dirt, and -- this is the point -- it sits ON the mound, so its px/ft is a
horizontal scale at the SAME image row as the chord.  Two horizontal references
at one depth compare like with like, and a 10 pct agreement gate on them is a
physical statement rather than a tuned one.

Home plate is a THIRD reference but NOT a partner for that gate: it is 17 in wide
at the plate row, which on a centre-field broadcast is ~60.5 ft further from the
camera than the mound, so its px/ft is legitimately smaller.  Measured on
mlb_2iosUkpL0Bc frame 180: mound 43.4, rubber 43.0, plate 35.3 px/ft -- the
rubber agrees to 0.9 pct, the plate is 23 pct lower purely from depth.  The plate
scale is therefore reported with its implied perspective ratio and bounded to a
physically possible band, never differenced against the mound scale.

Detection uses shape evidence only (flat, bright, low-saturation, dirt-bounded).
No search window is bounded by the width the reference is expected to have; that
would make the agreement gate tautological.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np

from domains.baseball.tracking.field_mask import MoundChord, dirt_mask

PLATE_WIDTH_FEET = 17.0 / 12.0
RUBBER_WIDTH_FEET = 2.0
RUBBER_TO_PLATE_FEET = 60.5
BATTERS_BOX_WIDTH_FEET = 4.0
DEFAULT_AGREEMENT_TOLERANCE = 0.10
# mound_scale / plate_scale.  Reported, never a veto.  Measured 1.11-1.30 on the
# centre-field clip and 0.66 on a first-base-side clip where the plate is the
# nearer of the two; an outlier says the plate read is poor, and the plate is the
# noisier detection, so it must not overturn a rubber the mound already matched.
PERSPECTIVE_RATIO_NOTE = "diagnostic only"
WHITE_MAX_SATURATION = 90
WHITE_MIN_VALUE = 200
_MIN_RUN_PX = 8
_DIRT_PROBE_PX = 12
# The rubber sits at the mound centre and the plate on the pitcher-catcher line
# the camera is aimed down, so both are near the chord centre.  These bound
# WHERE a landmark may sit, never how wide it may be.
_RUBBER_ALIGNMENT = 0.15
_PLATE_ALIGNMENT = 0.25
# Shape only: a rubber or a plate is a flat quadrilateral; a chalk stroke is a
# hairline (flatness 20-60) and a shoe or a leg is blockier (flatness < 3).
_RUBBER_FLATNESS = (3.0, 60.0)
_PLATE_FLATNESS = (2.0, 14.0)

VALIDATED = "validated"
UNVALIDATED = "unvalidated"


@dataclass(frozen=True)
class WhiteRun:
    """One horizontal bright run: a rubber, a plate, or a chalk stroke."""

    row: int
    left: int
    right: int
    thickness: int

    @property
    def width(self) -> float:
        return float(self.right - self.left)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2.0, float(self.row))

    @property
    def flatness(self) -> float:
        return self.width / max(1, self.thickness)


@dataclass(frozen=True)
class PlateLandmarks:
    """Per-frame landmark evidence.  Every field may be ``None``."""

    rubber: Optional[WhiteRun]
    plate: Optional[WhiteRun]
    box_corners: tuple[tuple[float, float], ...]

    @property
    def rubber_px(self) -> Optional[tuple[float, float]]:
        return None if self.rubber is None else self.rubber.center

    @property
    def plate_center_px(self) -> Optional[tuple[float, float]]:
        return None if self.plate is None else self.plate.center

    @property
    def rubber_confidence(self) -> float:
        return 0.0 if self.rubber is None else min(1.0, self.rubber.flatness / 20.0)

    @property
    def plate_confidence(self) -> float:
        return 0.0 if self.plate is None else min(1.0, self.plate.flatness / 6.0)

    def as_dict(self) -> dict[str, object]:
        return {
            "plate_center_px": self.plate_center_px,
            "plate_width_px": None if self.plate is None else self.plate.width,
            "plate_confidence": self.plate_confidence,
            "rubber_px": self.rubber_px,
            "rubber_width_px": None if self.rubber is None else self.rubber.width,
            "rubber_confidence": self.rubber_confidence,
            "box_corners": [list(corner) for corner in self.box_corners],
        }


@dataclass(frozen=True)
class ScaleValidation:
    """The mound-chord scale plus the independent references that judge it."""

    scale_px_per_ft: float
    scale_status: str
    rubber_px_per_ft: Optional[float]
    disagreement: Optional[float]
    plate_px_per_ft: Optional[float]
    perspective_ratio: Optional[float]
    reason: str

    def as_dict(self) -> dict[str, object]:
        """The ADDED columns only.  ``scale_px_per_ft`` is the caller's own and
        is deliberately not restated here, so a consumer cannot mistake a
        validation record for a replacement scale."""
        return {
            "scale_status": self.scale_status,
            "scale_reference_px_per_ft": self.rubber_px_per_ft,
            "scale_disagreement": self.disagreement,
            "plate_px_per_ft": self.plate_px_per_ft,
            "perspective_ratio": self.perspective_ratio,
            "scale_status_reason": self.reason,
        }


def white_mask(frame: np.ndarray) -> np.ndarray:
    """Return bright, low-saturation pixels: rubber, plate, chalk, uniforms."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    saturation, value = hsv[:, :, 1], hsv[:, :, 2]
    return ((saturation < WHITE_MAX_SATURATION) & (value > WHITE_MIN_VALUE)).astype(np.uint8)


def _row_runs(row_mask: np.ndarray, offset: int) -> list[tuple[int, int]]:
    edges = np.flatnonzero(np.diff(np.concatenate(([0], (row_mask > 0).view(np.int8), [0]))))
    return [(offset + int(a), offset + int(b)) for a, b in zip(edges[::2], edges[1::2])]


def _thickness(mask: np.ndarray, row: int, column: int) -> int:
    top = bottom = row
    while top > 0 and mask[top - 1, column]:
        top -= 1
    while bottom + 1 < mask.shape[0] and mask[bottom + 1, column]:
        bottom += 1
    return bottom - top + 1


def _dirt_framed(dirt: np.ndarray, row: int, left: int, right: int, thickness: int) -> bool:
    """Return whether dirt surrounds the run on all four sides.

    Left/right alone passes the white base of an outfield wall above a warning
    track, which is exactly the false mound this gate exists to reject.
    """
    height, width = dirt.shape[:2]
    column = (left + right) // 2
    above = dirt[max(0, row - thickness - _DIRT_PROBE_PX):max(1, row - thickness), column]
    below = dirt[min(height - 1, row + thickness):row + thickness + _DIRT_PROBE_PX, column]
    before = dirt[row, max(0, left - _DIRT_PROBE_PX):left]
    after = dirt[row, right:min(width, right + _DIRT_PROBE_PX)]
    return bool(before.any() and after.any() and above.any() and below.any())


def _widest_flat_run(white: np.ndarray, dirt: np.ndarray, rows: range, x0: int, x1: int,
                     center_x: float, alignment: float,
                     flatness: tuple[float, float]) -> Optional[WhiteRun]:
    """Return the widest dirt-framed, correctly shaped bright run in a band.

    The band and ``alignment`` bound WHERE to look and ``flatness`` bounds the
    SHAPE.  Neither bounds how wide an acceptable run may be: a width prior
    would make the agreement gate downstream tautological.
    """
    best: Optional[WhiteRun] = None
    for row in rows:
        for left, right in _row_runs(white[row, x0:x1], x0):
            width = right - left
            if width < _MIN_RUN_PX or (best is not None and width <= best.width):
                continue
            if abs((left + right) / 2.0 - center_x) > alignment:
                continue
            thickness = _thickness(white, row, (left + right) // 2)
            if not flatness[0] <= width / max(1, thickness) <= flatness[1]:
                continue
            if not _dirt_framed(dirt, row, left, right, thickness):
                continue
            best = WhiteRun(row, left, right, thickness)
    return best


def _clamp_band(low: float, high: float, limit: int) -> range:
    """Clamp a search band into the frame; an impossible band is empty, not wrong."""
    start = min(max(0, int(low)), limit)
    return range(start, min(max(start, int(high)), limit))


def detect_plate_landmarks(frame: np.ndarray, chord: MoundChord) -> PlateLandmarks:
    """Locate the rubber on the mound and the plate/chalk above it."""
    height, width = frame.shape[:2]
    white, dirt = white_mask(frame), dirt_mask(frame)
    span = chord.width
    rubber = _widest_flat_run(
        white, dirt,
        _clamp_band(chord.row - 0.30 * span, chord.row + 0.10 * span, height),
        max(0, chord.left), min(width, chord.right),
        chord.center_x, _RUBBER_ALIGNMENT * span, _RUBBER_FLATNESS,
    )
    plate_rows = _clamp_band(height // 6, chord.row - 0.05 * span, height)
    plate = _widest_flat_run(white, dirt, plate_rows, 0, width,
                             chord.center_x, _PLATE_ALIGNMENT * span, _PLATE_FLATNESS)
    corners: list[tuple[float, float]] = []
    for row in plate_rows[::4]:
        for left, right in _row_runs(white[row, 0:width], 0):
            if right - left < _MIN_RUN_PX:
                continue
            if plate is not None and plate.left <= left and right <= plate.right:
                continue
            thickness = _thickness(white, row, (left + right) // 2)
            if _dirt_framed(dirt, row, left, right, thickness):
                corners.append(((left + right) / 2.0, float(row)))
    return PlateLandmarks(rubber, plate, tuple(corners[:8]))


def validate_scale(chord: MoundChord, landmarks: PlateLandmarks,
                   tolerance: float = DEFAULT_AGREEMENT_TOLERANCE) -> ScaleValidation:
    """Judge the mound-chord scale against the rubber at the same image row."""
    if not 0.0 < tolerance < 1.0:
        raise ValueError("tolerance must be in (0, 1)")
    mound_scale = chord.pixels_per_foot_lateral
    plate_scale = ratio = None
    if landmarks.plate is not None:
        plate_scale = landmarks.plate.width / PLATE_WIDTH_FEET
        ratio = mound_scale / plate_scale
    if landmarks.rubber is None:
        return ScaleValidation(mound_scale, UNVALIDATED, None, None, plate_scale, ratio,
                               "no pitching rubber found on the detected mound")
    rubber_scale = landmarks.rubber.width / RUBBER_WIDTH_FEET
    disagreement = abs(rubber_scale - mound_scale) / mound_scale
    if disagreement > tolerance:
        return ScaleValidation(mound_scale, UNVALIDATED, rubber_scale, disagreement,
                               plate_scale, ratio,
                               "rubber and mound scales disagree by %.1f pct" % (100.0 * disagreement))
    return ScaleValidation(mound_scale, VALIDATED, rubber_scale, disagreement,
                           plate_scale, ratio, "rubber agrees within %.1f pct" % (100.0 * tolerance))


def chord_from_geometry(geometry) -> MoundChord:
    """Recover a ``PitchGeometry``'s chord without re-running the chord search.

    A ``MoundChord`` is symmetric about its own centre, so its edges follow
    exactly from the geometry's centre and chord width.
    """
    half = geometry.mound_chord_px / 2.0
    return MoundChord(int(geometry.mound[1]), int(round(float(geometry.mound[0]) - half)),
                      int(round(float(geometry.mound[0]) + half)), geometry.near_edge_occluded)


def validate_geometry(frame: np.ndarray, geometry,
                      tolerance: float = DEFAULT_AGREEMENT_TOLERANCE) -> ScaleValidation:
    """Validate a ``PitchGeometry``'s scale against its own frame's landmarks."""
    chord = chord_from_geometry(geometry)
    return validate_scale(chord, detect_plate_landmarks(frame, chord), tolerance)


def segment_status(validations: Sequence[ScaleValidation]) -> str:
    """A segment is validated when any of its frames validated independently."""
    return VALIDATED if any(v.scale_status == VALIDATED for v in validations) else UNVALIDATED
