"""Opt-in lighting-robust evidence for a center-field baseball pitch view.

The legacy ``dominant_green`` mode preserves the current gate exactly.  The
``hue_geometry`` mode deliberately removes HSV value from its grass and dirt
tests: stadium lights dim value but retain their hue/saturation separation.
It also requires the broad upper dirt band and lower mound-side dirt evidence
that distinguish a field view from a grass close-up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import cv2
import numpy as np

from domains.baseball.tracking.field_mask import MoundChord, mound_chord
from domains.baseball.tracking.plate_landmark import WhiteRun, detect_plate_landmarks

GateMode = Literal["dominant_green", "hue_geometry", "geometry_only"]
DEFAULT_MODE: GateMode = "dominant_green"


@dataclass(frozen=True)
class PitchViewGateResult:
    """One gate decision and its normalized evidence score."""

    is_pitch_view: bool
    score: float
    geometry: Optional["GeometryOnlyEvidence"] = None


@dataclass(frozen=True)
class GeometryOnlyEvidence:
    """The independent witnesses used by the opt-in geometry-only gate."""

    chord: Optional[MoundChord]
    rubber: Optional[WhiteRun]
    plate: Optional[WhiteRun]
    box_corners: tuple[tuple[float, float], ...]
    landmark_witness: bool
    vertical_order_correct: bool


def _center_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    crop_height, crop_width = int(height * 0.70), int(width * 0.70)
    y0, x0 = (height - crop_height) // 2, (width - crop_width) // 2
    return frame[y0:y0 + crop_height, x0:x0 + crop_width]


def _legacy_score(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(_center_crop(frame), cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
    return float(np.count_nonzero(green)) / green.size


def _wide_dirt_rows(dirt: np.ndarray, start: int, stop: int) -> float:
    """Return the largest horizontal dirt fraction in a bounded row band."""
    if stop <= start:
        return 0.0
    return float(np.max(np.mean(dirt[start:stop] > 0, axis=1)))


def _hue_geometry_score(frame: np.ndarray) -> float:
    """Score hue/saturation grass plus the pitch-view dirt layout, no value."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, saturation = hsv[:, :, 0], hsv[:, :, 1]
    grass = (hue >= 35) & (hue <= 95) & (saturation >= 35)
    dirt = (((hue <= 25) | (hue >= 165)) & (saturation >= 40)).astype(np.uint8)
    height, width = dirt.shape
    x0, x1 = int(width * 0.20), int(width * 0.80)
    grass_fraction = float(np.mean(grass[int(height * 0.25):int(height * 0.88), x0:x1]))
    upper = _wide_dirt_rows(dirt[:, x0:x1], int(height * 0.17), int(height * 0.62))
    lower = _wide_dirt_rows(dirt[:, x0:x1], int(height * 0.55), int(height * 0.86))
    # Each term is 0..1.  Dirt is capped at its structural floor so a giant dirt
    # frame cannot compensate for absent grass.
    return 0.60 * min(1.0, grass_fraction / 0.35) + 0.25 * min(1.0, upper / 0.25) + 0.15 * min(1.0, lower / 0.20)


def _flip_chord(chord: MoundChord, height: int) -> MoundChord:
    return MoundChord(height - 1 - chord.row, chord.left, chord.right,
                      chord.near_edge_occluded)


def _unflip_run(run: Optional[WhiteRun], height: int) -> Optional[WhiteRun]:
    if run is None:
        return None
    return WhiteRun(height - 1 - run.row, run.left, run.right, run.thickness)


def _geometry_only(frame: np.ndarray) -> PitchViewGateResult:
    """Use mound and white landmark layout only, with no color precondition.

    The existing landmark detector looks for a plate above the mound because it
    serves the current scale-validation camera convention. G11c requires the
    opposite image ordering, so its lower-center search runs that unchanged
    detector on a vertically flipped copy and restores its pixel coordinates.
    """
    chord = mound_chord(frame)
    if chord is None:
        evidence = GeometryOnlyEvidence(None, None, None, (), False, False)
        return PitchViewGateResult(False, 0.0, evidence)
    normal = detect_plate_landmarks(frame, chord)
    height = frame.shape[0]
    flipped = detect_plate_landmarks(cv2.flip(frame, 0), _flip_chord(chord, height))
    plate = _unflip_run(flipped.plate, height)
    boxes = tuple((x, float(height - 1 - y)) for x, y in flipped.box_corners)
    lower_landmark_y = (plate.center[1] if plate is not None else
                        (min(y for _, y in boxes) if boxes else None))
    landmark_witness = normal.rubber is not None or lower_landmark_y is not None
    vertical_order = (lower_landmark_y is not None and chord.row < lower_landmark_y)
    evidence = GeometryOnlyEvidence(chord, normal.rubber, plate, boxes,
                                    landmark_witness, vertical_order)
    score = (1.0 + float(landmark_witness) + float(vertical_order)) / 3.0
    return PitchViewGateResult(landmark_witness and vertical_order, score, evidence)


def classify_pitch_view(frame: np.ndarray, mode: GateMode = DEFAULT_MODE) -> PitchViewGateResult:
    """Return pitch-view decision and score for an explicitly selected mode.

    ``dominant_green`` is byte-for-byte equivalent in thresholds and crop to
    the old gate.  ``hue_geometry`` is an opt-in lighting-invariant candidate;
    callers must still apply their existing mound/infield evidence downstream.
    """
    if mode == "dominant_green":
        score = _legacy_score(frame)
        return PitchViewGateResult(score >= 0.35, score)
    if mode == "hue_geometry":
        score = _hue_geometry_score(frame)
        return PitchViewGateResult(score >= 0.80, score)
    if mode == "geometry_only":
        return _geometry_only(frame)
    raise ValueError("unknown pitch-view gate mode: %s" % mode)
