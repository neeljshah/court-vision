"""Synthetic tests for conservative tennis ball tracking v1.

Run: python -m pytest domains/tennis/tracking/test_ball.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.tennis.tracking.ball import MotionDiffDetector, ball_rows, rectify_track


def _dot(x: int, y: int) -> np.ndarray:
    frame = np.zeros((90, 140, 3), dtype=np.uint8)
    cv2.circle(frame, (x, y), 2, (255, 255, 255), thickness=-1)
    return frame


def test_motion_diff_detects_a_small_moving_dot() -> None:
    detector = MotionDiffDetector()
    assert detector.detect(_dot(40, 25)) is None
    found = detector.detect(_dot(42, 25))
    assert found is not None
    assert np.allclose(found[:2], (41, 25), atol=1.0)
    assert found[2] >= 0.5


def test_rectify_rejects_teleports_fills_short_gaps_and_drops_singletons() -> None:
    points = [
        (10.0, 10.0, 0.9), (20.0, 10.0, 0.9), None, None,
        (50.0, 10.0, 0.9), (200.0, 10.0, 0.9), None, None,
        None, None, None, None, (40.0, 10.0, 0.9),
    ]
    assert rectify_track(points) == [
        (10.0, 10.0, 0.9), (20.0, 10.0, 0.9),
        (30.0, 10.0, 0.0), (40.0, 10.0, 0.0), (50.0, 10.0, 0.9),
        None, None, None, None, None, None, None, None,
    ]


def test_motion_diff_returns_none_for_two_similar_moving_blobs() -> None:
    detector = MotionDiffDetector()
    first = _dot(30, 20)
    cv2.circle(first, (90, 30), 2, (255, 255, 255), thickness=-1)
    second = _dot(32, 20)
    cv2.circle(second, (92, 30), 2, (255, 255, 255), thickness=-1)
    assert detector.detect(first) is None
    assert detector.detect(second) is None


def test_ball_projection_guard_names_sign_flip_and_envelope_rejections() -> None:
    homography = np.array(((1.0, 0.0, 0.0), (0.0, 0.1, 0.0),
                           (0.0, 0.01, -1.0)))
    rows = ball_rows(((39.0, 200.0, 0.9), (39.0, 50.0, 0.9),
                      (500.0, 200.0, 0.9)), homography)
    assert rows["projection_status"].tolist() == ["accepted", "rejected", "rejected"]
    assert rows["projection_rejection_reason"].tolist() == ["", "beyond_vanishing_line",
                                                               "outside_physical_envelope"]
    assert rows.loc[0, ["x", "y"]].tolist() == [39.0, 20.0]
    assert rows.loc[1:, ["x", "y"]].isna().all().all()


def test_ball_rows_use_the_reserved_negative_track_namespace() -> None:
    homography = np.array(((1.0, 0.0, 0.0), (0.0, 0.1, 0.0),
                           (0.0, 0.01, -1.0)))
    rows = ball_rows(((39.0, 200.0, 0.9),), homography)

    assert rows["track_id"].tolist() == [-1]
    assert rows.loc[0, "track_id"] != 99
