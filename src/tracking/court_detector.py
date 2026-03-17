"""
court_detector.py — Per-clip homography detection from broadcast frames.

Detects NBA court line geometry from broadcast frame samples and computes
a perspective homography M1 mapping image coordinates to 2D court coordinates.

Used by unified_pipeline._build_court() to replace the static Rectify1.npy
calibration with a clip-specific matrix.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np


def _line_intersection(
    l1: Tuple[int, int, int, int],
    l2: Tuple[int, int, int, int],
) -> Optional[Tuple[float, float]]:
    """
    Compute intersection of two line segments using parametric form.

    Args:
        l1: First line segment as (x1, y1, x2, y2).
        l2: Second line segment as (x3, y3, x4, y4).

    Returns:
        (ix, iy) intersection point, or None if lines are nearly parallel
        (|denom| < 1e-6).
    """
    x1, y1, x2, y2 = l1
    x3, y3, x4, y4 = l2

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)
    return (ix, iy)


def _classify_lines(
    lines: np.ndarray,
    img_w: int,
    img_h: int,
) -> Tuple[List, List]:
    """
    Split HoughLinesP output into horizontal and vertical lines.

    Args:
        lines: Shape (N, 1, 4) from cv2.HoughLinesP, each row (x1, y1, x2, y2).
        img_w: Frame width in pixels.
        img_h: Frame height in pixels.

    Returns:
        Tuple of (horizontal_lines, vertical_lines) as lists of
        (x1, y1, x2, y2) tuples.
    """
    import math

    horizontal_lines: List[Tuple[int, int, int, int]] = []
    vertical_lines: List[Tuple[int, int, int, int]] = []

    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        if angle < 15 or angle > 165:
            horizontal_lines.append((x1, y1, x2, y2))
        elif 75 < angle < 105:
            vertical_lines.append((x1, y1, x2, y2))

    return horizontal_lines, vertical_lines


def detect_court_homography(
    frames: List[np.ndarray],
) -> Optional[np.ndarray]:
    """Detect NBA court line homography from a list of BGR frames.

    Samples up to 10 evenly-spaced frames, accumulates a hardwood floor mask,
    detects white court lines via HoughLinesP, computes line intersections,
    bins into 4 quadrant corners, and returns a 3x3 perspective transform.

    Args:
        frames: List of BGR numpy arrays (any resolution, consistent dims).
                Typically the first 60 frames of a broadcast clip.

    Returns:
        3x3 float64 homography matrix mapping frame coords to 2D court space
        (940x500 px), or None if detection fails (< 4 valid corners found).
    """
    # STEP 1 — Guard: empty input
    if not frames:
        return None

    try:
        # STEP 2 — Sample frames: up to 10 evenly spaced
        sample = frames[::max(1, len(frames) // 10)][:10]
        if not sample:
            return None

        # STEP 3 — Accumulate floor mask across sampled frames
        floor_mask = np.zeros(sample[0].shape[:2], dtype=np.uint8)
        for frame in sample:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (10, 40, 100), (30, 160, 230))
            floor_mask = cv2.bitwise_or(floor_mask, mask)

        # STEP 4 — Build white-line mask from first frame
        h, w = sample[0].shape[:2]
        gray = cv2.cvtColor(sample[0], cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, bright = cv2.threshold(blurred, 200, 255, cv2.THRESH_BINARY)
        line_mask = cv2.bitwise_and(bright, floor_mask)

        # STEP 5 — Hough line detection
        lines = cv2.HoughLinesP(
            line_mask, rho=1, theta=np.pi / 180,
            threshold=50, minLineLength=60, maxLineGap=20,
        )
        if lines is None or len(lines) < 4:
            return None

        # STEP 6 — Classify lines into horizontal and vertical
        h_lines, v_lines = _classify_lines(lines, w, h)
        if len(h_lines) < 2 or len(v_lines) < 2:
            return None

        # STEP 7 — Compute all h x v intersections, keep those within frame bounds
        intersections = []
        for hl in h_lines:
            for vl in v_lines:
                pt = _line_intersection(hl, vl)
                if pt is not None:
                    ix, iy = pt
                    if 0 <= ix <= w and 0 <= iy <= h:
                        intersections.append((ix, iy))

        if len(intersections) < 4:
            return None

        # STEP 8 — Bin intersections into 4 quadrants (TL, TR, BL, BR)
        mid_x, mid_y = w / 2, h / 2
        quadrants: dict = {"TL": [], "TR": [], "BL": [], "BR": []}
        for ix, iy in intersections:
            key = ("T" if iy < mid_y else "B") + ("L" if ix < mid_x else "R")
            quadrants[key].append((ix, iy))

        # STEP 9 — Pick one representative per quadrant (closest to its frame corner)
        corners_map = {"TL": (0, 0), "TR": (w, 0), "BL": (0, h), "BR": (w, h)}
        src_pts = []
        for quad, corner in corners_map.items():
            pts = quadrants[quad]
            if not pts:
                return None
            cx, cy = corner
            best = min(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            src_pts.append(best)
        # src_pts is ordered [TL, TR, BL, BR]

        # STEP 10 — Compute perspective transform to 940x500 court space
        dst_pts = np.float32([[0, 0], [940, 0], [0, 500], [940, 500]])
        src_np = np.float32(src_pts)
        M1 = cv2.getPerspectiveTransform(src_np, dst_pts)
        print(f"[court_detector] detected per-clip homography from {len(frames)} frames")
        return M1.astype(np.float64)

    except Exception:
        print("[court_detector] detection failed — fallback to Rectify1.npy")
        return None
