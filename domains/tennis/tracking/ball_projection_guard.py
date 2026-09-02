"""Homography-derived containment guard for tennis ball ground projections."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


COURT_ENVELOPE_FT = (-6.0, 84.0, -4.0, 40.0)


@dataclass(frozen=True)
class ProjectionDecision:
    """Ground-plane projection and its explicit containment decision."""

    raw_x: float
    raw_y: float
    status: str
    rejection_reason: str


def vanishing_line(homography: np.ndarray) -> np.ndarray:
    """Return the normalized image line where the homography denominator is zero."""
    matrix = np.asarray(homography, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("homography must be a finite 3 by 3 matrix")
    line = matrix[2].copy()
    norm = float(np.hypot(line[0], line[1]))
    if norm == 0.0:
        raise ValueError("homography has no finite vanishing line")
    return line / norm


def _ground_side(line: np.ndarray, homography: np.ndarray) -> float:
    """Get the denominator sign of the court centre back-projected by this H."""
    image = np.linalg.inv(homography) @ np.array((39.0, 18.0, 1.0))
    if abs(float(image[2])) < 1e-12:
        raise ValueError("court centre back-projects to infinity")
    pixel = image / image[2]
    return float(line @ pixel)


def guard_ball_projection(point: tuple[float, float, float], homography: np.ndarray) -> ProjectionDecision:
    """Project one pixel and name a sign-flip or physical-envelope rejection."""
    matrix = np.asarray(homography, dtype=np.float64)
    line = vanishing_line(matrix)
    pixel = np.array((float(point[0]), float(point[1]), 1.0))
    denominator = float(line @ pixel)
    ground_denominator = _ground_side(line, matrix)
    if abs(denominator) <= 1e-9:
        return ProjectionDecision(float("nan"), float("nan"), "rejected", "on_vanishing_line")
    projected = matrix @ pixel
    raw_x, raw_y = float(projected[0] / projected[2]), float(projected[1] / projected[2])
    if denominator * ground_denominator < 0.0:
        return ProjectionDecision(raw_x, raw_y, "rejected", "beyond_vanishing_line")
    min_x, max_x, min_y, max_y = COURT_ENVELOPE_FT
    if not (min_x <= raw_x <= max_x and min_y <= raw_y <= max_y):
        return ProjectionDecision(raw_x, raw_y, "rejected", "outside_physical_envelope")
    return ProjectionDecision(raw_x, raw_y, "accepted", "")
