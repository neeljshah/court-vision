"""Synthetic-frame proof of landmark detection and the two-reference scale gate."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from domains.baseball.tracking.field_mask import mound_chord
from domains.baseball.tracking.plate_landmark import (
    UNVALIDATED, VALIDATED, detect_plate_landmarks, segment_status, validate_scale,
)

GRASS = (40, 120, 40)
DIRT = (78, 88, 139)
WHITE = (240, 240, 240)
WIDTH, HEIGHT = 1280, 720
MOUND_CENTER, MOUND_ROW = 640, 600
MOUND_HALF_WIDTH = 200
# The drawn chord is 400 px for 18 ft, so a truthful 2 ft rubber is 44.4 px and a
# truthful 17 in plate at a 1.2x deeper row is 26 px.
TRUE_MOUND_PX_PER_FT = 2.0 * MOUND_HALF_WIDTH / 18.0


def _frame(rubber_px: int = 44, plate_px: int = 26) -> np.ndarray:
    frame = np.full((HEIGHT, WIDTH, 3), GRASS, np.uint8)
    cv2.rectangle(frame, (0, 300), (WIDTH, 420), DIRT, -1)
    cv2.ellipse(frame, (MOUND_CENTER, MOUND_ROW), (MOUND_HALF_WIDTH, 60), 0, 0, 360, DIRT, -1)
    if plate_px:
        cv2.rectangle(frame, (MOUND_CENTER - plate_px // 2, 376),
                      (MOUND_CENTER + plate_px // 2, 380), WHITE, -1)
    for offset in (-80, 80):  # batter's-box chalk: too blocky to be read as a plate
        cv2.rectangle(frame, (MOUND_CENTER + offset - 5, 360),
                      (MOUND_CENTER + offset + 5, 400), WHITE, -1)
    if rubber_px:
        cv2.rectangle(frame, (MOUND_CENTER - rubber_px // 2, 580),
                      (MOUND_CENTER + rubber_px // 2, 584), WHITE, -1)
    return frame


def test_chord_and_rubber_are_found_at_the_drawn_pixels():
    frame = _frame()
    chord = mound_chord(frame)
    assert chord is not None and chord.row == pytest.approx(MOUND_ROW, abs=6)
    assert chord.width == pytest.approx(2 * MOUND_HALF_WIDTH, abs=4)
    landmarks = detect_plate_landmarks(frame, chord)
    assert landmarks.rubber is not None
    assert landmarks.rubber.width == pytest.approx(44, abs=2)
    assert landmarks.rubber_px[0] == pytest.approx(MOUND_CENTER, abs=2)
    assert landmarks.plate is not None
    assert landmarks.plate_center_px[0] == pytest.approx(MOUND_CENTER, abs=2)
    assert landmarks.plate.width == pytest.approx(26, abs=2)
    assert landmarks.box_corners  # the flanking chalk is reported, not silently dropped


def test_truthful_rubber_validates_within_ten_percent():
    frame = _frame()
    chord = mound_chord(frame)
    report = validate_scale(chord, detect_plate_landmarks(frame, chord))
    assert report.scale_status == VALIDATED
    assert report.scale_px_per_ft == pytest.approx(TRUE_MOUND_PX_PER_FT, rel=0.02)
    assert report.rubber_px_per_ft == pytest.approx(TRUE_MOUND_PX_PER_FT, rel=0.05)
    assert report.disagreement < 0.10
    assert 1.0 <= report.perspective_ratio <= 1.6


def test_disagreeing_rubber_yields_unvalidated():
    frame = _frame(rubber_px=70)  # 35.0 px/ft against a 22.2 px/ft chord
    chord = mound_chord(frame)
    report = validate_scale(chord, detect_plate_landmarks(frame, chord))
    assert report.scale_status == UNVALIDATED
    assert report.disagreement > 0.10
    assert "disagree" in report.reason
    # The gate ADDS a column: the reported scale itself is untouched.
    assert report.scale_px_per_ft == pytest.approx(TRUE_MOUND_PX_PER_FT, rel=0.02)


def test_missing_rubber_yields_unvalidated():
    frame = _frame(rubber_px=0)
    chord = mound_chord(frame)
    report = validate_scale(chord, detect_plate_landmarks(frame, chord))
    assert report.scale_status == UNVALIDATED
    assert report.rubber_px_per_ft is None
    assert "no pitching rubber" in report.reason


def test_plate_reference_is_diagnostic_and_never_vetoes():
    """A bad plate read must not overturn a rubber the mound already matched.

    The plate sits ~60.5 ft further from the camera than the mound, so its
    px/ft is legitimately different and cannot be differenced against the mound
    scale; it is also the noisier detection of the two.
    """
    frame = _frame(plate_px=60)  # a plate scale ABOVE the mound scale
    chord = mound_chord(frame)
    report = validate_scale(chord, detect_plate_landmarks(frame, chord))
    assert report.perspective_ratio < 1.0
    assert report.scale_status == VALIDATED


def test_tolerance_must_be_a_fraction():
    frame = _frame()
    chord = mound_chord(frame)
    with pytest.raises(ValueError):
        validate_scale(chord, detect_plate_landmarks(frame, chord), tolerance=0.0)


def test_segment_status_needs_one_validated_frame():
    frame, bad = _frame(), _frame(rubber_px=70)
    chord, bad_chord = mound_chord(frame), mound_chord(bad)
    good = validate_scale(chord, detect_plate_landmarks(frame, chord))
    poor = validate_scale(bad_chord, detect_plate_landmarks(bad, bad_chord))
    assert segment_status([poor, good]) == VALIDATED
    assert segment_status([poor, poor]) == UNVALIDATED
    assert segment_status([]) == UNVALIDATED
