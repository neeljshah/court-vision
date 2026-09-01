"""Tests for drift-checked tennis camera locks.

Run: python -m pytest domains/tennis/tracking/test_camera_lock.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.tennis.tracking.camera_lock import (
    CameraLock,
    DRIFT_CEILING_720P_PX,
    detected_intersections,
    drift_from_corners,
    drift_from_frame,
    geometric_median_homography,
)
from domains.tennis.tracking.test_adapter import COURT, COURT_FEET, _court_image


def _homography() -> np.ndarray:
    return cv2.findHomography(COURT, COURT_FEET)[0]


def test_geometric_median_ignores_one_bad_accepted_solve() -> None:
    base = _homography()
    homographies = [base.copy() for _ in range(3)]
    homographies.append(np.array(((1.0, 0.0, 500.0), (0.0, 1.0, 500.0), (0.0, 0.0, 1.0))))
    result = geometric_median_homography(homographies)
    assert np.allclose(result, base / base[2, 2], atol=1e-5)


def test_current_frame_intersections_measure_static_lock_drift() -> None:
    frame, homography = _court_image(), _homography()
    evidence = detected_intersections(frame, homography)
    check = drift_from_frame(homography, frame)
    assert len(evidence) >= 2
    assert check.evidence_count >= 2
    assert check.residual_px is not None and check.residual_px <= DRIFT_CEILING_720P_PX


def test_lock_requires_three_solves_and_full_corner_drift_is_measured() -> None:
    lock, homography = CameraLock(), _homography()
    lock.add_fresh_solve(homography)
    lock.add_fresh_solve(homography)
    assert not lock.ready
    lock.add_fresh_solve(homography)
    assert lock.ready
    check = drift_from_corners(lock.homography, COURT)
    assert lock.accepts(check, 720)
