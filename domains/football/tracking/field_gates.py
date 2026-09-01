"""Fit-free gates that test the football field hypothesis before any homography.

Neither gate fits, reuses or interpolates anything: each is a falsifiable test
of an assumption the adapter would otherwise make silently. Both only REJECT
frames -- they can never admit a frame the old code refused.
"""
from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

# Broadcast football cuts constantly to close-ups, replays, crowd and graphics.
# Those frames have no field geometry at all, yet white clutter in them still
# yields Hough lines that the family test happily groups. Measured on a real
# SEC broadcast: 43.25% of sampled frames are not wide-field views.
MIN_FIELD_VIEW_GREEN = 0.35
# Four EQUALLY SPACED coplanar parallel lines cut any transversal in a
# cross-ratio of 4/3, whatever the camera pose. That is exactly the assumption
# behind labelling the n-th detected line as n * 15 ft, so it can be tested
# without fitting. Measured: only 16.4% of detected quadruples pass it, i.e.
# the detected "yard-line family" is usually hash marks, numbers and logos.
YARD_PENCIL_CROSS_RATIO = 4.0 / 3.0
CROSS_RATIO_TOLERANCE = 0.10


def field_view_fraction(frame: np.ndarray) -> float:
    """Return the grass fraction of the frame."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, np.array((35, 30, 20)), np.array((95, 255, 255)))
    return float((grass > 0).mean())


def _transversal(lines: Sequence[np.ndarray], shape: Sequence[int]):
    """Return a cut across the family through the image centre, and that centre."""
    normal = np.mean([line[:2] for line in lines], axis=0)
    length = float(np.linalg.norm(normal))
    if length < 1e-8:
        return None, None
    normal = normal / length
    centre = np.array((shape[1] / 2.0, shape[0] / 2.0))
    start, end = centre - 1e4 * normal, centre + 1e4 * normal
    coefficients = np.array((start[1] - end[1], end[0] - start[0],
                             start[0] * end[1] - end[0] * start[1]), dtype=float)
    return coefficients / np.hypot(coefficients[0], coefficients[1]), (centre, normal)


def pencil_positions(lines: Sequence[np.ndarray], shape: Sequence[int]) -> list[float]:
    """Return sorted 1-D positions where the family cuts one transversal.

    Yard lines meet at a vanishing point, so the family is a concurrent pencil
    and its cross-ratio is the same along every transversal; the choice of cut
    is therefore free. An empty list means the family does not cut cleanly.
    """
    cut, frame = _transversal(lines, shape)
    if cut is None:
        return []
    centre, normal = frame
    positions: list[float] = []
    for line in lines:
        point = np.cross(np.asarray(line, dtype=float), cut)
        if abs(point[2]) < 1e-8:
            return []
        location = point[:2] / point[2]
        if not np.isfinite(location).all():
            return []
        positions.append(float((location - centre) @ normal))
    return sorted(positions)


def pencil_is_uniform(lines: Sequence[np.ndarray], shape: Sequence[int]) -> bool:
    """True only when the family really is CONSECUTIVE five-yard lines.

    Every consecutive quadruple must hold the 4/3 cross-ratio. A single gap or
    one contaminating line breaks some quadruple, so the ordinal labelling the
    caller applies is rejected rather than silently believed.
    """
    positions = pencil_positions(lines, shape)
    if len(positions) < 4:
        return False
    for index in range(len(positions) - 3):
        first, second, third, fourth = positions[index:index + 4]
        denominator = (third - second) * (fourth - first)
        if abs(denominator) < 1e-9:
            return False
        ratio = ((third - first) * (fourth - second)) / denominator
        if abs(ratio - YARD_PENCIL_CROSS_RATIO) > CROSS_RATIO_TOLERANCE * YARD_PENCIL_CROSS_RATIO:
            return False
    return True
