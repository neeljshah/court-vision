"""Synthetic tests for the tennis broadcast tracking adapter.

Run: python -m pytest domains/tennis/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from domains.tennis.tracking.adapter import TennisAdapter


COURT = np.float32(((120, 650), (1160, 650), (430, 120), (850, 120)))


def _court_image() -> np.ndarray:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:] = (40, 120, 40)
    cv2.polylines(image, [COURT.astype(np.int32)], True, (255, 255, 255), 5)
    cv2.line(image, tuple(COURT[0].astype(int)), tuple(COURT[2].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(COURT[1].astype(int)), tuple(COURT[3].astype(int)), (255, 255, 255), 5)
    return image


def test_synthetic_corners_and_homography() -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    corners = adapter.detect_court_corners(_court_image())
    assert corners is not None
    assert np.max(np.abs(corners - COURT)) < 5.0
    homography = adapter.homography_from_corners(corners)
    mapped = cv2.perspectiveTransform(COURT.reshape(1, -1, 2), homography)[0]
    expected = np.float32(((0, 0), (78, 0), (0, 36), (78, 36)))
    assert np.max(np.abs(mapped - expected)) < 0.5


def test_mock_detector_projects_players_on_opposite_halves() -> None:
    image = _court_image()
    base = TennisAdapter(detector=lambda frame: [])
    homography = base.homography_from_corners(COURT)
    inverse = np.linalg.inv(homography)

    def box_for(x: float, y: float) -> list[float]:
        pixel = cv2.perspectiveTransform(np.float32([[[x, y]]]), inverse)[0, 0]
        return [pixel[0] - 20, pixel[1] - 80, pixel[0] + 20, pixel[1]]

    adapter = TennisAdapter(detector=lambda frame: [box_for(20, 6), box_for(58, 30)])
    players = adapter.detect_players(image, homography)
    assert [track_id for track_id, _ in players] == [1, 2]
    points = {track_id: point for track_id, point in players}
    assert np.allclose(points[1], (20, 6), atol=0.5)
    assert np.allclose(points[2], (58, 30), atol=0.5)


def test_write_csv_uses_normalized_schema(tmp_path) -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame(
        [[4, 1, "player", 20.0, 6.0]], columns=("frame", "track_id", "cls", "x", "y")
    )
    output = tmp_path / "tracking.csv"
    adapter.write_csv(output)
    assert list(pd.read_csv(output).columns) == ["frame", "track_id", "cls", "x", "y"]
