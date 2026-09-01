"""Tests for the fit-free football field gates.

Run: python -m pytest domains/football/tracking/test_field_gates.py -q
"""
from __future__ import annotations

import numpy as np

from domains.football.tracking.field_gates import (MIN_FIELD_VIEW_GREEN,
                                                   field_view_fraction,
                                                   pencil_is_uniform,
                                                   pencil_positions)

SHAPE = (360, 640, 3)
# A deliberately oblique image-to-field homography: the gate must survive real
# perspective, which is exactly what a parallelism test cannot do.
IMAGE_TO_FIELD = np.array(((1.0, 0.2, -30.0), (0.0, 1.5, -20.0), (0.0, 0.0015, 1.0)))


def _image_lines(field_x: list[float]) -> list[np.ndarray]:
    """Project field lines x = c into the image under IMAGE_TO_FIELD."""
    lines = []
    for value in field_x:
        line = IMAGE_TO_FIELD.T @ np.array((1.0, 0.0, -float(value)))
        lines.append(line / np.hypot(line[0], line[1]))
    return lines


def test_equally_spaced_pencil_holds_the_cross_ratio_under_perspective() -> None:
    assert pencil_is_uniform(_image_lines([0.0, 15.0, 30.0, 45.0, 60.0]), SHAPE)


def test_a_gap_in_the_family_is_rejected() -> None:
    """A missed five-yard line makes the ordinal x = index * 15 ft labelling false."""
    assert not pencil_is_uniform(_image_lines([0.0, 15.0, 45.0, 60.0, 75.0]), SHAPE)


def test_contaminating_line_between_yard_lines_is_rejected() -> None:
    """A hash-mark or logo edge landing inside the family breaks a quadruple."""
    assert not pencil_is_uniform(_image_lines([0.0, 15.0, 22.0, 30.0, 45.0]), SHAPE)


def test_three_lines_cannot_be_tested_so_they_are_rejected() -> None:
    assert not pencil_is_uniform(_image_lines([0.0, 15.0, 30.0]), SHAPE)


def test_pencil_positions_are_ordered_and_finite() -> None:
    positions = pencil_positions(_image_lines([0.0, 15.0, 30.0, 45.0]), SHAPE)
    assert len(positions) == 4
    assert positions == sorted(positions)
    assert np.isfinite(positions).all()


def test_field_view_fraction_separates_grass_from_a_studio_frame() -> None:
    grass = np.zeros((90, 160, 3), dtype=np.uint8)
    grass[:, :] = (45, 145, 45)
    studio = np.full((90, 160, 3), 30, dtype=np.uint8)

    assert field_view_fraction(grass) > MIN_FIELD_VIEW_GREEN
    assert field_view_fraction(studio) < MIN_FIELD_VIEW_GREEN
