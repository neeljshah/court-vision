"""G334 court template in feet, the measurement image, and the projection helpers.

Sealed in `docs/evidence/tracking/g334_prereg_2026-09-08.md` section 3. Contract: `x` is the court
WIDTH, 0 to 50; `y` is the court LENGTH, 0 to 94 -- the `g196_homography_from_labelled_corners` and
`g252_projection_accuracy_in_pixels` axis order, NOT the transposed
`keypoint_calib.CANONICAL_LANDMARKS` one. Because a broadcast frame shows one end, the fitted
template is the NEAR HALF with the visible baseline at y = 0; which end that is is not decided here,
and metrics (c) and (d) are invariant under the reflection y -> 94 - y.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

COURT_LENGTH_FT = 94.0
COURT_WIDTH_FT = 50.0
LANE_WIDTH_FT = 16.0
LANE_DEPTH_FT = 19.0
CIRCLE_R_FT = 6.0
THREE_R_FT = 23.75
BASKET_Y_FT = 5.25
CORNER_X_FT = 3.0
HALF_Y_FT = COURT_LENGTH_FT / 2.0
LANE_LO_FT = (COURT_WIDTH_FT - LANE_WIDTH_FT) / 2.0
LANE_HI_FT = (COURT_WIDTH_FT + LANE_WIDTH_FT) / 2.0
TOPCUT = 60
MEASURE_WIDTH = 1280
# Court values a detected line may stand for. W lines have constant y, L lines constant x.
FAMILY_W_VALUES = (0.0, LANE_DEPTH_FT, HALF_Y_FT)
FAMILY_L_VALUES = (0.0, CORNER_X_FT, LANE_LO_FT, LANE_HI_FT,
                   COURT_WIDTH_FT - CORNER_X_FT, COURT_WIDTH_FT)


def _arc(cx, cy, radius, start, end, step=1.0):
    n = max(2, int(round(abs(end - start) * radius / step)))
    angles = np.linspace(start, end, n)
    return np.column_stack((cx + radius * np.cos(angles), cy + radius * np.sin(angles)))


def corner_three_end() -> float:
    """Where the corner-three straight meets the arc: 5.25 + sqrt(23.75^2 - 22^2)."""
    return BASKET_Y_FT + math.sqrt(THREE_R_FT ** 2 - (COURT_WIDTH_FT / 2.0 - CORNER_X_FT) ** 2)


def template_polylines() -> list:
    """The near-half NBA court template, in feet. Arcs are 1 ft chords, never fitted conics."""
    half_w = COURT_WIDTH_FT / 2.0
    end = corner_three_end()
    theta = math.acos((half_w - CORNER_X_FT) / THREE_R_FT)
    lines = [
        np.array([(0.0, 0.0), (COURT_WIDTH_FT, 0.0)]),
        np.array([(0.0, 0.0), (0.0, HALF_Y_FT)]),
        np.array([(COURT_WIDTH_FT, 0.0), (COURT_WIDTH_FT, HALF_Y_FT)]),
        np.array([(0.0, HALF_Y_FT), (COURT_WIDTH_FT, HALF_Y_FT)]),
        np.array([(LANE_LO_FT, 0.0), (LANE_LO_FT, LANE_DEPTH_FT)]),
        np.array([(LANE_HI_FT, 0.0), (LANE_HI_FT, LANE_DEPTH_FT)]),
        np.array([(LANE_LO_FT, LANE_DEPTH_FT), (LANE_HI_FT, LANE_DEPTH_FT)]),
        np.array([(CORNER_X_FT, 0.0), (CORNER_X_FT, end)]),
        np.array([(COURT_WIDTH_FT - CORNER_X_FT, 0.0), (COURT_WIDTH_FT - CORNER_X_FT, end)]),
        _arc(half_w, LANE_DEPTH_FT, CIRCLE_R_FT, 0.0, 2.0 * math.pi),
        _arc(half_w, HALF_Y_FT, CIRCLE_R_FT, math.pi, 2.0 * math.pi),
        _arc(half_w, BASKET_Y_FT, THREE_R_FT, theta, math.pi - theta),
    ]
    return [np.asarray(line, dtype=np.float32) for line in lines]


def template_points(spacing: float = 1.0) -> np.ndarray:
    """Every template polyline resampled at `spacing` feet, concatenated."""
    out = []
    for line in template_polylines():
        for start, stop in zip(line[:-1], line[1:]):
            steps = max(1, int(round(float(np.linalg.norm(stop - start)) / spacing)))
            for i in range(steps):
                out.append(start + (stop - start) * (i / steps))
        out.append(line[-1])
    return np.asarray(out, dtype=np.float32)


TEMPLATE_POINTS = template_points()
HALF_COURT_QUAD = np.array([(0.0, 0.0), (COURT_WIDTH_FT, 0.0),
                            (COURT_WIDTH_FT, HALF_Y_FT), (0.0, HALF_Y_FT)], dtype=np.float32)


def measurement_matrix(height: int, width: int, topcut: int = TOPCUT,
                       out_width: int = MEASURE_WIDTH) -> np.ndarray:
    """Original-frame pixels to measurement-image pixels: the TOPCUT crop then the width scale."""
    scale = float(out_width) / float(width)
    return np.array([[scale, 0.0, 0.0], [0.0, scale, -scale * topcut], [0.0, 0.0, 1.0]])


def measurement_image(frame: np.ndarray, topcut: int = TOPCUT,
                      out_width: int = MEASURE_WIDTH) -> np.ndarray:
    """The route's TOPCUT crop, scaled to a fixed 1280 width so one pixel scale serves every cell."""
    crop = frame[topcut:]
    height, width = crop.shape[:2]
    if width == out_width:
        return crop
    return cv2.resize(crop, (out_width, int(round(height * out_width / width))),
                      interpolation=cv2.INTER_AREA)


def project(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(1, -1, 2), matrix)[0]


def lookup(field: np.ndarray, points: np.ndarray):
    """Field values at the points that fall inside it, and how many those were."""
    height, width = field.shape[:2]
    xs, ys = np.round(points[:, 0]).astype(int), np.round(points[:, 1]).astype(int)
    inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    return field[ys[inside], xs[inside]], int(inside.sum())


def distance_transform(shape, segments: list) -> np.ndarray:
    """Distance in pixels from every pixel to the nearest rasterised segment pixel."""
    mask = np.zeros(shape[:2], dtype=np.uint8)
    for segment in segments:
        x1, y1, x2, y2 = segment.endpoints
        cv2.line(mask, (int(round(x1)), int(round(y1))), (int(round(x2)), int(round(y2))), 255, 1)
    return cv2.distanceTransform(255 - mask, cv2.DIST_L2, 3)
