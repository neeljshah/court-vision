"""Tests for the measured baseball field masks.

Run: python -m pytest domains/baseball/tracking/test_field_mask.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.baseball.tracking.field_mask import (
    MOUND_DIAMETER_FEET, dirt_mask, grass_mask, infield_band_present, mound_chord,
)

GRASS = (45, 130, 45)
# Measured on both corpora 2026-09-01: infield dirt is BGR ~ (75, 76, 120),
# which is HSV hue 1 -- below the old hue floor of 5.
DIRT = (70, 76, 120)


def _field(mound_half_width: int = 456) -> np.ndarray:
    image = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.rectangle(image, (0, 300), (1280, 450), DIRT, -1)
    cv2.ellipse(image, (506, 604), (mound_half_width, 55), 0, 0, 360, DIRT, -1)
    return image


def test_dirt_mask_catches_hue_one_park_dirt() -> None:
    patch = np.full((40, 40, 3), DIRT, dtype=np.uint8)
    assert cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[0, 0, 0] < 5
    assert dirt_mask(patch).mean() > 250


def test_grass_and_dirt_masks_do_not_overlap() -> None:
    frame = _field()
    assert not np.logical_and(dirt_mask(frame) > 0, grass_mask(frame) > 0).any()


def test_mound_chord_measures_the_grass_bounded_island() -> None:
    chord = mound_chord(_field())

    assert chord is not None
    assert abs(chord.width - 912) <= 6
    assert abs(chord.center_x - 506) <= 6
    assert abs(chord.pixels_per_foot_lateral - chord.width / MOUND_DIAMETER_FEET) < 1e-9


def test_mound_chord_ignores_dirt_that_runs_off_the_frame_edge() -> None:
    """The infield band is wider than the mound but is not grass-bounded."""
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.rectangle(frame, (0, 560), (1280, 660), DIRT, -1)

    assert mound_chord(frame) is None


def test_infield_band_is_not_satisfied_by_the_mound_itself() -> None:
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.ellipse(frame, (506, 604), (456, 55), 0, 0, 360, DIRT, -1)

    assert not infield_band_present(frame, 604)
    assert infield_band_present(_field(), 604)
