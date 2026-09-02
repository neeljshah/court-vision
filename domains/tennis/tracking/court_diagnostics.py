"""Observational gate trace for the tennis court-line solver."""
from __future__ import annotations

from collections import Counter
from typing import Optional

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_lines import CourtLines, detect_court


GATE_ORDER = (
    "no_hough_lines", "insufficient_oriented_lines", "vertical_cluster_count",
    "cross_ratio", "horizontal_roles", "depth_order", "homography", "skew", "image_bounds",
    "far_right_consistency", "accepted",
)


def _anchors(court: CourtLines) -> tuple[Optional[np.ndarray], ...]:
    far_left = TennisAdapter._intersection(court.far, court.left)
    service_t = TennisAdapter._intersection(court.near_service, court.centre)
    near_left = TennisAdapter._intersection(court.near, court.left)
    near_right = TennisAdapter._intersection(court.near, court.right)
    return near_left, near_right, far_left, service_t


def rejection_gate(frame: np.ndarray) -> str:
    """Return the production-solver gate that rejects ``frame`` (last evidence pass), or ``accepted``."""
    return detect_court(frame)[2]


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
    """Measure the observed opposite service T against four real line anchors.

    Needs the far service line, which the solver treats as optional; frames
    solved without it return None rather than a number measured against the net.
    """
    court, corners, _ = detect_court(frame)
    if court is None or corners is None or court.far_service is None:
        return None
    near_left, near_right, far_left, service_t = _anchors(court)
    opposite_t = TennisAdapter._intersection(court.far_service, court.centre)
    if opposite_t is None:
        return None
    homography, _ = cv2.findHomography(np.float32((near_left, near_right, far_left, service_t)),
                                       np.float32(((0, 0), (0, 36), (78, 0), (18, 18))))
    if homography is None:
        return None
    predicted = TennisAdapter._project(opposite_t, homography)
    return float(np.linalg.norm(predicted - np.float32((60.0, 18.0))))
