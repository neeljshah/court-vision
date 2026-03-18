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
        if angle < 25 or angle > 155:
            horizontal_lines.append((x1, y1, x2, y2))
        elif 65 < angle < 115:
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
        h_all, w_all = frames[0].shape[:2]

        # STEP 2 — Filter to frames that actually show the hardwood court.
        # Broadcast clips often begin with pre-game intros, crowd shots, and
        # arena flyovers. We scan all supplied frames and keep only those where
        # the hardwood floor mask covers >12% of the frame, ensuring detection
        # runs on actual gameplay frames rather than intro footage.
        # HSV range covers light and dark hardwood (H:8-35, S:30-200, V:80-240).
        court_frames: List[np.ndarray] = []
        for frame in frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, (8, 30, 80), (35, 200, 240))
            if mask.sum() / 255 > 0.12 * h_all * w_all:
                court_frames.append(frame)

        # Fall back to all frames if none pass the court filter (e.g. non-hardwood arena)
        if len(court_frames) < 3:
            court_frames = frames

        # STEP 3 — Sample up to 10 evenly-spaced court frames
        sample = court_frames[::max(1, len(court_frames) // 10)][:10]
        if not sample:
            return None
        h, w = sample[0].shape[:2]

        # STEP 4 — Build white-line mask using adaptive threshold.
        # Try thresholds from 200 down to 160; use the first that yields
        # enough Hough lines (≥4). Broadcast video compression can reduce
        # white line intensity below 200, so we try progressively lower values.
        gray = cv2.cvtColor(sample[0], cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        lines = None
        for thresh in (200, 180, 160):
            _, bright = cv2.threshold(blurred, thresh, 255, cv2.THRESH_BINARY)
            candidate = cv2.HoughLinesP(
                bright, rho=1, theta=np.pi / 180,
                threshold=40, minLineLength=40, maxLineGap=30,
            )
            if candidate is not None and len(candidate) >= 4:
                lines = candidate
                break

        if lines is None or len(lines) < 4:
            return None

        # STEP 5 — Classify lines into horizontal and vertical.
        # Use wider 25° tolerance (vs original 15°) to handle perspective
        # distortion in broadcast frames where sidelines run slightly angled.
        h_lines, v_lines = _classify_lines(lines, w, h)
        if len(h_lines) < 2 or len(v_lines) < 2:
            return None

        # STEP 6 — Compute all h × v intersections, keep those within frame bounds
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

        # STEP 7 — Bin intersections into 4 quadrants (TL, TR, BL, BR)
        mid_x, mid_y = w / 2, h / 2
        quadrants: dict = {"TL": [], "TR": [], "BL": [], "BR": []}
        for ix, iy in intersections:
            key = ("T" if iy < mid_y else "B") + ("L" if ix < mid_x else "R")
            quadrants[key].append((ix, iy))

        # STEP 8 — Pick one representative per quadrant.
        # Use the point FARTHEST from the image centre in each quadrant — this
        # selects boundary line intersections (sidelines × baselines) rather
        # than interior lines (free-throw × 3-point arc, etc.).
        cx_img, cy_img = w / 2, h / 2
        src_pts = []
        for quad in ("TL", "TR", "BL", "BR"):
            pts = quadrants[quad]
            if not pts:
                return None
            best = max(pts, key=lambda p: (p[0] - cx_img) ** 2 + (p[1] - cy_img) ** 2)
            src_pts.append(best)
        # src_pts ordered [TL, TR, BL, BR]

        # STEP 9 — Validate corners span a reasonable fraction of the frame
        # (at least 30% width and 25% height) before committing.
        xs = [p[0] for p in src_pts]
        ys = [p[1] for p in src_pts]
        if (max(xs) - min(xs)) < 0.30 * w or (max(ys) - min(ys)) < 0.25 * h:
            return None

        # STEP 10 — Compute perspective transform to 940×500 court space
        dst_pts = np.float32([[0, 0], [940, 0], [0, 500], [940, 500]])
        src_np = np.float32(src_pts)
        M1 = cv2.getPerspectiveTransform(src_np, dst_pts)
        print(
            f"[court_detector] detected per-clip homography from "
            f"{len(court_frames)} court frames ({len(frames)} supplied)"
        )
        return M1.astype(np.float64)

    except Exception:
        print("[court_detector] detection failed — fallback to Rectify1.npy")
        return None
