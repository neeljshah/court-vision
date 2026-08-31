"""Tests for WNBA court palette and line detection helpers."""

import cv2
import numpy as np
import pytest

from domains.basketball_wnba.tracking.court_config import (
    WNBA_COURT,
    line_mask,
    sample_court_palette,
    scorebug_exclude,
)


@pytest.mark.parametrize(
    ("background", "line", "dark"),
    [((8, 8, 8), (0, 255, 0), True), ((170, 195, 210), (255, 255, 255), False)],
)
def test_palette_and_line_mask_recover_drawn_lines(background, line, dark):
    frame = np.full((160, 240, 3), background, dtype=np.uint8)
    expected = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.line(frame, (20, 80), (220, 80), line, 4)
    cv2.line(expected, (20, 80), (220, 80), 255, 4)

    palette = sample_court_palette([frame, frame.copy()])
    detected = line_mask(frame, palette)

    assert palette["is_dark_court"] is dark
    assert np.mean(detected[expected > 0] > 0) > 0.80


def test_court_constants_and_scorebug_mask():
    assert WNBA_COURT == {"length_ft": 94.0, "width_ft": 50.0, "three_pt_radius_ft": 22.146}
    mask = scorebug_exclude((100, 200, 3))
    assert mask[90, 10] == 0
    assert mask[90, 190] == 0
    assert mask[20, 100] == 255
