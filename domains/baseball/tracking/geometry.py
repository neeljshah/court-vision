"""Image evidence for baseball pitch-view geometry.

These helpers deliberately measure only the mound's lateral pixel scale. They
do not create a ground-plane coordinate transform.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from domains.baseball.tracking.field_mask import (
    MIN_CHORD_FRACTION,
    infield_band_present,
    mound_chord,
)

_CENTER_CROP_FRACTION = 0.70


@dataclass(frozen=True)
class PitchGeometry:
    """One frame's mound evidence and its lateral pixel scale.

    ``pixels_per_foot`` applies at the mound row across the image x axis only.
    It is deliberately never used to project depth into feet.
    """

    mound: np.ndarray
    mound_chord_px: float
    pixels_per_foot: float
    near_edge_occluded: bool


def center_crop(frame: np.ndarray) -> np.ndarray:
    """Return the central 70 percent of a frame."""
    height, width = frame.shape[:2]
    crop_width = int(width * _CENTER_CROP_FRACTION)
    crop_height = int(height * _CENTER_CROP_FRACTION)
    x0, y0 = (width - crop_width) // 2, (height - crop_height) // 2
    return frame[y0:y0 + crop_height, x0:x0 + crop_width]


def dominant_green(frame: np.ndarray) -> bool:
    """Return whether live grass dominates the image crop."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
    return float(np.count_nonzero(green)) / green.size >= 0.35


def detect_pitch_geometry(
    frame: np.ndarray, min_chord_fraction: float = MIN_CHORD_FRACTION,
) -> Optional[PitchGeometry]:
    """Identify a mound positively and measure its lateral scale."""
    if not dominant_green(center_crop(frame)):
        return None
    chord = mound_chord(frame, min_chord_fraction)
    if chord is None or not infield_band_present(frame, chord.row):
        return None
    mound = np.array((chord.center_x, float(chord.row)), dtype=np.float32)
    return PitchGeometry(mound, chord.width, chord.pixels_per_foot_lateral,
                         chord.near_edge_occluded)
