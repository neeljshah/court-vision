"""Court-line evidence and model-consistent line selection for the tennis solver.

Two measured defects of the previous solver live here, fixed at the root:

1. Evidence. The absolute brightness mask (200..255) never contained a court
   line lying in the hard shadow that covers half of many main-camera frames,
   so the right doubles sideline and the near baseline vanished from Hough
   entirely (docs/evidence/tracking/tennis_vertical_lever_2026-09-01). A white
   top-hat keeps "thin and brighter than its surroundings", which a line is in
   sun or shade, and removes shirts and banners, which are not thin.
2. Selection. Requiring EXACTLY five vertical clusters meant better evidence
   produced more rejections, and taking the first/last horizontal clusters made
   the scoreboard the "far baseline". Both roles are now chosen by the court's
   own projective invariants: cross ratios of the line positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import cv2
import numpy as np

# Measured on nyYk 720p (docs/evidence/tracking/tennis_vertical_lever_2026-09-01):
# kernel 11 beat 15; contrast 45 accepted the most court-view frames overall
# and 60 won on the brightest shots, so the solver is run on the richer
# evidence first and the cleaner evidence second. Every pass faces the same
# thresholds; the subset search cannot loosen any of them. What DID change is
# the cluster-count gate: "exactly five" became "at least five, and the five
# in the court's cross ratios" (probed: 60 clutter frames, 0 accepts).
TOPHAT_KERNEL_720P_PX = 11
TOPHAT_CONTRASTS = (45, 60)
CROSS_RATIO_TOLERANCE = 0.05
# Court lines across the width (feet from the left doubles sideline) and along
# the length (feet from the near baseline), in image order.
_ACROSS = (0.0, 4.5, 18.0, 31.5, 36.0)
_ALONG = {"far": 78.0, "far_service": 60.0, "net": 39.0, "near_service": 18.0, "near": 0.0}
_ALONG_TEMPLATES = (
    ("far", "far_service", "net", "near_service", "near"),
    ("far", "far_service", "near_service", "near"),
    ("far", "net", "near_service", "near"),
)


def cross_ratio(a: float, b: float, c: float, d: float) -> float:
    denominator = (c - b) * (d - a)
    return float("inf") if abs(denominator) < 1e-9 else (c - a) * (d - b) / denominator


def _invariants(points: tuple[float, ...]) -> tuple[float, ...]:
    """Two independent cross ratios for five points, one for four."""
    if len(points) == 4:
        return (cross_ratio(*points),)
    return (cross_ratio(points[0], points[1], points[2], points[4]),
            cross_ratio(points[1], points[2], points[3], points[4]))


_ACROSS_TARGET = _invariants(_ACROSS)
_ALONG_TARGETS = {roles: _invariants(tuple(_ALONG[r] for r in roles)) for roles in _ALONG_TEMPLATES}


def _match(positions: list[float], size: int, target: tuple[float, ...],
           windows: Optional[list[tuple[float, float]]] = None) -> Optional[tuple[int, ...]]:
    """Indices (in ``positions`` order) of the best subset whose invariants hit ``target``.

    ``windows`` optionally bounds each slot's position; a subset with any slot
    outside its window is not a candidate at all.
    """
    if len(positions) < size or len(positions) > 14:
        return None
    best: Optional[tuple[float, tuple[int, ...]]] = None
    for combo in combinations(range(len(positions)), size):
        if windows is not None and any(not low <= positions[i] <= high for i, (low, high) in zip(combo, windows)):
            continue
        deviations = [abs(got - want) for got, want in zip(_invariants(tuple(positions[i] for i in combo)), target)]
        if max(deviations) > CROSS_RATIO_TOLERANCE:
            continue
        if best is None or sum(deviations) < best[0]:
            best = (sum(deviations), combo)
    return None if best is None else best[1]


def court_line_segments(frame: np.ndarray, threshold: int = 45, min_length: Optional[int] = None,
                        max_gap: int = 20, contrast: int = TOPHAT_CONTRASTS[0]) -> list[np.ndarray]:
    """Hough segments over a shadow-invariant thin-bright-structure mask."""
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # A court line is a few pixels wide and that width scales with resolution.
    size = max(5, int(round(TOPHAT_KERNEL_720P_PX * height / 720.0)) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    mask = cv2.inRange(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel), contrast, 255)
    found = cv2.HoughLinesP(mask, 1, np.pi / 180.0, threshold,
                            minLineLength=max(40, width // 12) if min_length is None else min_length,
                            maxLineGap=max_gap)
    return [] if found is None else [segment.astype(float) for segment in found[:, 0, :]]


def split_orientation(segments: list[np.ndarray]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Production orientation classes: horizontal abs(dx) >= 1.5 abs(dy); vertical abs(dy) > abs(dx)."""
    horizontal: list[np.ndarray] = []
    vertical: list[np.ndarray] = []
    for line in segments:
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        if dx >= 1.5 * dy:
            horizontal.append(line)
        elif dy > dx:
            vertical.append(line)
    return horizontal, vertical


@dataclass(frozen=True)
class CourtLines:
    """Fitted image lines (x1, y1, x2, y2) with their court roles."""

    left: np.ndarray
    right: np.ndarray
    centre: np.ndarray
    far: np.ndarray
    near_service: np.ndarray
    near: np.ndarray
    far_service: Optional[np.ndarray]
    vertical_clusters: tuple[list[np.ndarray], ...]


def _row_on(line: np.ndarray, vertical: np.ndarray) -> Optional[float]:
    """Image row where ``line`` crosses ``vertical``."""
    a = np.cross(np.array((line[0], line[1], 1.0)), np.array((line[2], line[3], 1.0)))
    b = np.cross(np.array((vertical[0], vertical[1], 1.0)), np.array((vertical[2], vertical[3], 1.0)))
    point = np.cross(a, b)
    return None if abs(point[2]) < 1e-8 else float(point[1] / point[2])


def select_court_lines(segments: list[np.ndarray], shape: tuple[int, int]) -> tuple[Optional[CourtLines], str]:
    """Return the court's lines and ``"ok"``, or ``(None, gate_name)`` for the first failing gate."""
    from domains.tennis.tracking.adapter import TennisAdapter  # circular at import time only

    horizontal, vertical = split_orientation(segments)
    if len(horizontal) < 2 or len(vertical) < 2:
        return None, "insufficient_oriented_lines"
    horizontal_clusters = TennisAdapter._cluster_lines(horizontal, True, shape)
    vertical_clusters = TennisAdapter._cluster_lines(vertical, False, shape)
    if len(horizontal_clusters) < 4 or len(vertical_clusters) < 5:
        return None, "vertical_cluster_count"
    fitted_vertical = [TennisAdapter._fit_line(cluster) for cluster in vertical_clusters]
    across = [TennisAdapter._line_position(line, False, shape) for line in fitted_vertical]
    chosen = _match(across, 5, _ACROSS_TARGET)
    if chosen is None:
        return None, "cross_ratio"
    five = [vertical_clusters[i] for i in chosen]
    left, centre, right = fitted_vertical[chosen[0]], fitted_vertical[chosen[2]], fitted_vertical[chosen[4]]
    # A court line crosses the centre line inside the sidelines' image extent.
    rows = [line[1] for cluster in five for line in cluster] + [line[3] for cluster in five for line in cluster]
    top, bottom = min(rows), max(rows)
    margin = 0.1 * (bottom - top)
    candidates: list[tuple[float, np.ndarray]] = []
    for cluster in horizontal_clusters:
        fitted = TennisAdapter._fit_line(cluster)
        row = _row_on(fitted, centre)
        if row is not None and top - margin <= row <= bottom + margin:
            candidates.append((row, fitted))
    candidates.sort(key=lambda item: item[0])
    positions = [row for row, _ in candidates]
    # A four-point cross ratio alone is weak: two net-cord clusters plus the
    # near service line and baseline matched it within tolerance. The court
    # pins the roles for free: the sidelines END at the baselines, and the
    # centre service line ENDS at the service lines. A player standing on the
    # centre line only shortens its detected extent, so those two bounds are
    # one-sided: safe against false REJECTION. False acceptance of the
    # symmetric (far, far_service, net, near) subset, whose cross ratio equals
    # the (far, net, near_service, near) template exactly, is held off by the
    # near_service window plus the far-right consistency gate in solve_corners.
    centre_rows = [line[1] for line in five[2]] + [line[3] for line in five[2]]
    centre_top, centre_bottom = min(centre_rows), max(centre_rows)
    span, centre_span = bottom - top, centre_bottom - centre_top
    windows = {
        "far": (top - 0.1 * span, top + 0.1 * span),
        "near": (bottom - 0.1 * span, bottom + 0.1 * span),
        "far_service": (top - 0.1 * span, centre_top + 0.06 * centre_span),
        "near_service": (centre_bottom - 0.1 * centre_span, bottom + 0.1 * span),
        "net": (top, bottom),
    }
    for roles in _ALONG_TEMPLATES:
        picked = _match(positions, len(roles), _ALONG_TARGETS[roles], [windows[role] for role in roles])
        if picked is None:
            continue
        by_role = {role: candidates[index][1] for role, index in zip(roles, picked)}
        return CourtLines(left=left, right=right, centre=centre, far=by_role["far"],
                          near_service=by_role["near_service"], near=by_role["near"],
                          far_service=by_role.get("far_service"), vertical_clusters=tuple(five)), "ok"
    return None, "horizontal_roles"


ANCHOR_FEET = ((0.0, 0.0), (0.0, 36.0), (78.0, 0.0), (18.0, 18.0))
FAR_RIGHT_TOLERANCE_WIDTH_FRACTION = 0.02


def solve_corners(court: CourtLines, shape: tuple[int, int]) -> tuple[Optional[np.ndarray], str]:
    """Near-left, near-right, far-left, far-right doubles corners from the court lines, or the failing gate."""
    from domains.tennis.tracking.adapter import TennisAdapter  # circular at import time only

    height, width = shape
    near_left = TennisAdapter._intersection(court.near, court.left)
    near_right = TennisAdapter._intersection(court.near, court.right)
    far_left = TennisAdapter._intersection(court.far, court.left)
    service_t = TennisAdapter._intersection(court.near_service, court.centre)
    # The camera sits behind the near baseline, so depth decreases up the frame.
    if (near_left is None or near_right is None or far_left is None or service_t is None or
            not far_left[1] < service_t[1] < near_left[1]):
        return None, "depth_order"
    anchors = np.float32((near_left, near_right, far_left, service_t))
    to_image, _ = cv2.findHomography(np.float32(ANCHOR_FEET), anchors)
    if to_image is None:
        return None, "homography"
    far_right = cv2.perspectiveTransform(np.float32([[(78.0, 36.0)]]), to_image)[0, 0]
    result = np.asarray((near_left, near_right, far_left, far_right), dtype=np.float32)
    # Both baselines are seen near-parallel from behind the near baseline.
    depth = float(result[0][1] - result[2][1])
    if depth <= 0.0 or abs(result[2][1] - result[3][1]) > 0.25 * depth:
        return None, "skew"
    if np.any(result[:, 0] < -5) or np.any(result[:, 0] > width + 5) or np.any(result[:, 1] < -5) or np.any(result[:, 1] > height + 5):
        return None, "image_bounds"
    # Independent fifth correspondence: the corner the four-anchor fit predicts
    # must land on the far/right intersection the image actually shows.
    observed = TennisAdapter._intersection(court.far, court.right)
    if observed is None or float(np.linalg.norm(observed - far_right)) > FAR_RIGHT_TOLERANCE_WIDTH_FRACTION * width:
        return None, "far_right_consistency"
    return result, "ok"


def detect_court(frame: np.ndarray) -> tuple[Optional[CourtLines], Optional[np.ndarray], str]:
    """Run the strict solver on each evidence contrast in turn; first accept wins.

    Returns ``(court, corners, "accepted")`` or ``(None, None, gate)`` with the
    gate the LAST pass failed at.
    """
    shape = frame.shape[:2]
    gate = "no_hough_lines"
    for contrast in TOPHAT_CONTRASTS:
        segments = court_line_segments(frame, contrast=contrast)
        if not segments:
            gate = "no_hough_lines"
            continue
        court, gate = select_court_lines(segments, shape)
        if court is None:
            continue
        corners, gate = solve_corners(court, shape)
        if corners is not None:
            return court, corners, "accepted"
    return None, None, gate
