"""G334 metrics (a) to (d), the route arm's composition, and the overlay render.

Every quantity here is stated in the measurement image of prereg section 2 and in the court feet of
its section 3. Nothing here is accuracy: metrics (a) and (b) are self-consistency and (c) and (d)
are physical plausibility. G233 measured 82.18 pct of projected feet inside 94 x 50 ft on a map that
fails the eye check, and G254 measured that a distance-transform objective walks a correct
homography into a wrong one that scores better. Both limits are carried in the memo.
"""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking.g334_court_template import (
    COURT_LENGTH_FT, COURT_WIDTH_FT, TEMPLATE_POINTS, lookup, project, template_polylines,
)

# The route reports ft_x along the LENGTH and ft_y across the WIDTH; section 3 is the other way up.
SWAP = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def route_court_matrix(homography, m1, map_w: int, map_h: int, resize) -> np.ndarray | None:
    """Measurement-image pixels to court feet through the route's own composition.

    `M1 @ M` is what `unified_pipeline.py:3084` applies to reach map_2d pixels and the feet scale is
    its `:2736-2737`. `resize` is the prereg section 2 crop-and-scale, inverted here.
    """
    if homography is None or m1 is None:
        return None
    scale = np.array([[COURT_LENGTH_FT / max(map_w, 1), 0.0, 0.0],
                      [0.0, COURT_WIDTH_FT / max(map_h, 1), 0.0], [0.0, 0.0, 1.0]])
    try:
        court = SWAP @ scale @ np.asarray(m1, float) @ np.asarray(homography, float) \
            @ np.linalg.inv(np.asarray(resize, float))
    except np.linalg.LinAlgError:
        return None
    if not np.isfinite(court).all() or abs(court[2, 2]) < 1e-12:
        return None
    return court / court[2, 2]


def invert(matrix):
    """The companion feet-to-image matrix, or None when the matrix is singular."""
    if matrix is None:
        return None
    try:
        inverse = np.linalg.inv(np.asarray(matrix, float))
    except np.linalg.LinAlgError:
        return None
    if not np.isfinite(inverse).all() or abs(inverse[2, 2]) < 1e-12:
        return None
    return inverse / inverse[2, 2]


def _median(values) -> float:
    return float(np.median(values)) if len(values) else float("nan")


def forward_error(image_matrix, held_field: np.ndarray):
    """Metric (a), the bar cell: template sample points to the nearest HELD-OUT line pixel."""
    if image_matrix is None:
        return float("nan"), 0
    projected = project(image_matrix, TEMPLATE_POINTS)
    if not np.isfinite(projected).all():
        return float("nan"), 0
    distances, n_scored = lookup(held_field, projected)
    return _median(distances), n_scored


def _segment_pixels(segments: list) -> np.ndarray:
    """One point per pixel along each segment -- the reverse metric's sample set."""
    points = []
    for segment in segments:
        x1, y1, x2, y2 = segment.endpoints
        steps = max(1, int(round(float(np.hypot(x2 - x1, y2 - y1)))))
        fractions = np.linspace(0.0, 1.0, steps + 1)
        points.append(np.column_stack((x1 + (x2 - x1) * fractions, y1 + (y2 - y1) * fractions)))
    return np.vstack(points) if points else np.zeros((0, 2))


def reverse_error(image_matrix, held_segments: list, shape):
    """The companion column: held-out line pixels to the nearest PROJECTED template line."""
    points = _segment_pixels(held_segments)
    if image_matrix is None or not len(points):
        return float("nan"), 0
    mask = np.zeros(shape[:2], dtype=np.uint8)
    drawn = 0
    for polyline in template_polylines():
        projected = project(image_matrix, polyline)
        if not np.isfinite(projected).all() or np.abs(projected).max() > 1e6:
            continue
        cv2.polylines(mask, [np.round(projected).astype(np.int32)], False, 255, 1)
        drawn += 1
    if not drawn or not mask.any():
        return float("nan"), 0
    field = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 3)
    distances, n_scored = lookup(field, points)
    return _median(distances), n_scored


def court_points(court_matrix, feet: list) -> np.ndarray:
    """Foot points in measurement-image pixels, projected to court feet."""
    if court_matrix is None or not feet:
        return np.zeros((0, 2))
    projected = project(court_matrix, np.asarray(feet, dtype=np.float32))
    return projected[np.isfinite(projected).all(axis=1)]


def inside_count(points: np.ndarray) -> int:
    """Metric (c) and the rectangle share of (d): they are the same set under prereg section 8."""
    if not len(points):
        return 0
    return int(((points[:, 0] >= 0.0) & (points[:, 0] <= COURT_WIDTH_FT)
                & (points[:, 1] >= 0.0) & (points[:, 1] <= COURT_LENGTH_FT)).sum())


def nearest_neighbour_ft(points: np.ndarray):
    """Metric (d): each point's nearest-neighbour distance in feet, one value per pair."""
    if len(points) < 2:
        return np.zeros(0)
    gaps = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    np.fill_diagonal(gaps, np.inf)
    return gaps.min(axis=1)


def render_overlay(image: np.ndarray, image_matrix, path, max_bytes: int = 200_000) -> bool:
    """Draw the projected template and write a jpg under `max_bytes`. Renders illustrate only."""
    if image_matrix is None:
        return False
    canvas = image.copy()
    for polyline in template_polylines():
        projected = project(image_matrix, polyline)
        if not np.isfinite(projected).all() or np.abs(projected).max() > 1e6:
            continue
        cv2.polylines(canvas, [np.round(projected).astype(np.int32)], False, (0, 255, 255), 2,
                      cv2.LINE_AA)
    for quality in (70, 50, 35, 20):
        ok, buffer = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok and buffer.nbytes <= max_bytes:
            path.write_bytes(buffer.tobytes())
            return True
    return False


class Cell:
    """One section-by-arm cell: every counter carries its own denominator."""

    def __init__(self, section: str, arm: str):
        self.section, self.arm = section, arm
        self.n_frames = 0
        self.valid = 0
        self.feet_total = 0
        self.feet_eval = 0
        self.feet_in = 0
        self.buckets = {"valid": 0, "too_few_groups": 0, "no_valid_h": 0, "implausible_scale": 0}
        self.forward, self.reverse, self.neighbours = [], [], []
        self.n_forward = self.n_reverse = self.n_held_segments = self.n_hypotheses = 0

    def add(self, reason: str, forward, n_forward, reverse, n_reverse, n_held, feet, inside,
            neighbours, n_hypotheses: int) -> None:
        self.n_frames += 1
        self.buckets[reason] = self.buckets.get(reason, 0) + 1
        self.feet_total += feet
        self.n_held_segments += n_held
        self.n_hypotheses += n_hypotheses
        if reason != "valid":
            return
        self.valid += 1
        self.feet_eval += feet
        self.feet_in += inside
        if np.isfinite(forward):
            self.forward.append(forward)
            self.n_forward += n_forward
        if np.isfinite(reverse):
            self.reverse.append(reverse)
            self.n_reverse += n_reverse
        self.neighbours.extend(float(value) for value in neighbours)

    def summary(self) -> dict:
        return {
            "n_frames": self.n_frames,
            "valid_frames": self.valid,
            "feet_total": self.feet_total,
            "feet_evaluated": self.feet_eval,
            "feet_inside": self.feet_in,
            "heldout_forward_px": _median(self.forward),
            "n_forward_points": self.n_forward,
            "heldout_reverse_px": _median(self.reverse),
            "n_reverse_points": self.n_reverse,
            "n_heldout_segments": self.n_held_segments,
            "nn_median_ft": _median(self.neighbours),
            "n_nn_pairs": len(self.neighbours),
            "n_hypotheses": self.n_hypotheses,
            "bucket_valid": self.buckets["valid"],
            "bucket_too_few_groups": self.buckets["too_few_groups"],
            "bucket_no_valid_h": self.buckets["no_valid_h"],
            "bucket_implausible_scale": self.buckets["implausible_scale"],
        }
