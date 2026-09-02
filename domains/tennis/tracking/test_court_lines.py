"""Synthetic tests for shadow-invariant court-line selection.

Run: python -m pytest domains/tennis/tracking/test_court_lines.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_lines import court_line_segments, select_court_lines

COURT = np.float32(((120, 650), (1160, 650), (430, 120), (850, 120)))
COURT_FEET = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))
_TO_IMAGE = cv2.findHomography(COURT_FEET, COURT)[0]
LINES = {
    "near": ((0, 0), (0, 36)), "far": ((78, 0), (78, 36)),
    "left": ((0, 0), (78, 0)), "right": ((0, 36), (78, 36)),
    "left_singles": ((0, 4.5), (78, 4.5)), "right_singles": ((0, 31.5), (78, 31.5)),
    "near_service": ((18, 4.5), (18, 31.5)), "far_service": ((60, 4.5), (60, 31.5)),
    "centre": ((18, 18), (60, 18)), "net": ((39, -3), (39, 39)),
}


def _image(skip: tuple[str, ...] = (), shadow: bool = True, clutter: bool = True) -> np.ndarray:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:] = (40, 120, 40)
    for name, (start, end) in LINES.items():
        if name in skip:
            continue
        pixels = cv2.perspectiveTransform(np.float32([[start, end]]), _TO_IMAGE)[0]
        cv2.line(image, tuple(pixels[0].astype(int)), tuple(pixels[1].astype(int)), (255, 255, 255), 3)
    if clutter:
        cv2.rectangle(image, (60, 20), (520, 70), (245, 245, 245), -1)   # scoreboard graphic
        cv2.line(image, (0, 95), (1279, 95), (250, 250, 250), 3)         # back wall edge
        cv2.rectangle(image, (600, 300), (700, 480), (255, 255, 255), -1)  # player shirt
    if shadow:
        # A hard shadow over the right half drops court lines below the old 200 mask.
        image[:, 640:] = (image[:, 640:] * 0.45).astype(np.uint8)
    return image


def _pixel(point: tuple[float, float]) -> np.ndarray:
    return cv2.perspectiveTransform(np.float32([[point]]), _TO_IMAGE)[0, 0]


def test_shadowed_court_with_clutter_solves_to_true_corners() -> None:
    corners = TennisAdapter(detector=lambda _: ()).detect_court_corners(_image())
    assert corners is not None
    truth = np.float32(((120, 650), (1160, 650), (430, 120), (850, 120)))
    assert np.max(np.linalg.norm(corners - truth, axis=1)) < 4.0


def test_old_brightness_mask_lost_the_shadowed_half() -> None:
    frame = _image()
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    assert int(bright[:, 640:].sum()) == 0
    court, gate = select_court_lines(court_line_segments(frame), frame.shape[:2])
    assert gate == "ok" and court is not None


def test_horizontal_roles_skip_scoreboard_and_wall() -> None:
    frame = _image()
    court, gate = select_court_lines(court_line_segments(frame), frame.shape[:2])
    assert gate == "ok" and court is not None
    far_left = TennisAdapter._intersection(court.far, court.left)
    service_t = TennisAdapter._intersection(court.near_service, court.centre)
    assert np.linalg.norm(far_left - _pixel((78, 0))) < 4.0
    assert np.linalg.norm(service_t - _pixel((18, 18))) < 4.0
    assert court.far_service is not None


def test_missing_far_service_line_uses_net_template_with_correct_roles() -> None:
    frame = _image(skip=("far_service",))
    court, gate = select_court_lines(court_line_segments(frame), frame.shape[:2])
    assert gate == "ok"
    assert court.far_service is None
    service_t = TennisAdapter._intersection(court.near_service, court.centre)
    assert np.linalg.norm(service_t - _pixel((18, 18))) < 4.0


def test_four_length_lines_fail_closed() -> None:
    frame = _image(skip=("right",))
    court, gate = select_court_lines(court_line_segments(frame), frame.shape[:2])
    assert court is None and gate in ("vertical_cluster_count", "cross_ratio")
