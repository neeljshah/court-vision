"""Observational gate trace for the tennis court-line solver."""
from __future__ import annotations

from collections import Counter
from typing import Optional

import cv2
import numpy as np

from domains.tennis.tracking.adapter import CROSS_RATIO, TennisAdapter


GATE_ORDER = (
    "no_hough_lines", "insufficient_oriented_lines", "vertical_cluster_count",
    "cross_ratio", "depth_order", "homography", "skew", "image_bounds",
    "accepted",
)


def rejection_gate(frame: np.ndarray) -> str:
    """Return the first production-solver gate that rejects ``frame``."""
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                            minLineLength=max(40, width // 12), maxLineGap=20)
    if lines is None:
        return "no_hough_lines"
    horizontal, vertical = [], []
    for raw in lines[:, 0, :]:
        line = raw.astype(float)
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        if dx >= 1.5 * dy:
            horizontal.append(line)
        elif dy > dx:
            vertical.append(line)
    if len(horizontal) < 2 or len(vertical) < 2:
        return "insufficient_oriented_lines"
    horizontal_clusters = TennisAdapter._cluster_lines(horizontal, True, (height, width))
    vertical_clusters = TennisAdapter._cluster_lines(vertical, False, (height, width))
    if not horizontal_clusters or len(vertical_clusters) != 5:
        return "vertical_cluster_count"
    across = [TennisAdapter._line_position(TennisAdapter._fit_line(cluster), False, (height, width))
              for cluster in vertical_clusters]
    denominator = (across[2] - across[1]) * (across[4] - across[0])
    ratio = (across[2] - across[0]) * (across[4] - across[1]) / denominator if abs(denominator) >= 1e-6 else np.inf
    if abs(denominator) < 1e-6 or abs(ratio - CROSS_RATIO) > 0.05:
        return "cross_ratio"
    near = TennisAdapter._fit_line(horizontal_clusters[-1])
    left, right = TennisAdapter._fit_line(vertical_clusters[0]), TennisAdapter._fit_line(vertical_clusters[-1])
    centre = TennisAdapter._fit_line(vertical_clusters[2])
    far_left = TennisAdapter._point_at_row(left, TennisAdapter._endpoint_rows(vertical_clusters[0])[0])
    service_t = TennisAdapter._point_at_row(centre, TennisAdapter._endpoint_rows(vertical_clusters[2])[1])
    near_left, near_right = TennisAdapter._intersection(near, left), TennisAdapter._intersection(near, right)
    if near_left is None or near_right is None or not far_left[1] < service_t[1] < near_left[1]:
        return "depth_order"
    anchors = np.float32((near_left, near_right, far_left, service_t))
    to_image, _ = cv2.findHomography(np.float32(((0, 0), (0, 36), (78, 0), (18, 18))), anchors)
    if to_image is None:
        return "homography"
    far_right = TennisAdapter._project((78.0, 36.0), to_image)
    result = np.asarray((near_left, near_right, far_left, far_right), dtype=np.float32)
    depth = float(result[0][1] - result[2][1])
    if depth <= 0.0 or abs(result[2][1] - result[3][1]) > 0.25 * depth:
        return "skew"
    if np.any(result[:, 0] < -5) or np.any(result[:, 0] > width + 5) or np.any(result[:, 1] < -5) or np.any(result[:, 1] > height + 5):
        return "image_bounds"
    return "accepted"


def count_gates(video: str, max_frames: int) -> Counter[str]:
    """Count first-rejection gates across a bounded video prefix."""
    capture = cv2.VideoCapture(video)
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    counts: Counter[str] = Counter()
    try:
        for _ in range(max_frames):
            ok, frame = capture.read()
            if not ok:
                break
            counts[rejection_gate(frame)] += 1
    finally:
        capture.release()
    return counts


def held_out_service_t_error(frame: np.ndarray) -> Optional[float]:
    """Measure the observed opposite service T against four real line anchors."""
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                            minLineLength=max(40, width // 12), maxLineGap=20)
    if lines is None:
        return None
    horizontal, vertical = [], []
    for raw in lines[:, 0, :]:
        line = raw.astype(float)
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        if dx >= 1.5 * dy:
            horizontal.append(line)
        elif dy > dx:
            vertical.append(line)
    if len(horizontal) < 2 or len(vertical) < 2:
        return None
    horizontal_clusters = TennisAdapter._cluster_lines(horizontal, True, (height, width))
    vertical_clusters = TennisAdapter._cluster_lines(vertical, False, (height, width))
    if not horizontal_clusters or len(vertical_clusters) != 5:
        return None
    across = [TennisAdapter._line_position(TennisAdapter._fit_line(cluster), False, (height, width))
              for cluster in vertical_clusters]
    denominator = (across[2] - across[1]) * (across[4] - across[0])
    if abs(denominator) < 1e-6 or abs((across[2] - across[0]) * (across[4] - across[1]) / denominator - CROSS_RATIO) > 0.05:
        return None
    near = TennisAdapter._fit_line(horizontal_clusters[-1])
    left, right = TennisAdapter._fit_line(vertical_clusters[0]), TennisAdapter._fit_line(vertical_clusters[-1])
    centre = TennisAdapter._fit_line(vertical_clusters[2])
    far_left = TennisAdapter._point_at_row(left, TennisAdapter._endpoint_rows(vertical_clusters[0])[0])
    near_left, near_right = TennisAdapter._intersection(near, left), TennisAdapter._intersection(near, right)
    if near_left is None or near_right is None:
        return None
    service_t = TennisAdapter._point_at_row(centre, TennisAdapter._endpoint_rows(vertical_clusters[2])[1])
    opposite_t = TennisAdapter._point_at_row(centre, TennisAdapter._endpoint_rows(vertical_clusters[2])[0])
    if not far_left[1] < service_t[1] < near_left[1]:
        return None
    homography, _ = cv2.findHomography(np.float32((near_left, near_right, far_left, service_t)),
                                       np.float32(((0, 0), (0, 36), (78, 0), (18, 18))))
    if homography is None:
        return None
    predicted = TennisAdapter._project(opposite_t, homography)
    return float(np.linalg.norm(predicted - np.float32((60.0, 18.0))))
