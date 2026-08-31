"""Synthetic tests for the soccer broadcast tracking adapter.

Run: python -m pytest domains/soccer/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from domains.soccer.tracking.adapter import SoccerAdapter


PITCH = np.float32(((100, 650), (1180, 650), (100, 100), (1180, 100)))


def _pitch_image() -> np.ndarray:
    image = np.full((720, 1280, 3), (40, 140, 40), dtype=np.uint8)
    cv2.line(image, tuple(PITCH[0].astype(int)), tuple(PITCH[1].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[0].astype(int)), tuple(PITCH[2].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[1].astype(int)), tuple(PITCH[3].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[2].astype(int)), tuple(PITCH[3].astype(int)), (255, 255, 255), 5)
    cv2.line(image, (640, 100), (640, 650), (255, 255, 255), 5)
    cv2.circle(image, (640, 375), 85, (255, 255, 255), 5)
    return image


def test_synthetic_markings_and_homography() -> None:
    image = _pitch_image()
    adapter = SoccerAdapter(detector=lambda frame: [])
    markings = adapter.detect_pitch_markings(image)
    assert markings["halfway_x"] is not None
    assert abs(markings["halfway_x"] - 640) < 5.0
    assert markings["center_circle"] is not None
    corners = adapter.detect_pitch_corners(image)
    assert corners is not None
    homography = adapter.homography_from_corners(corners)
    mapped = cv2.perspectiveTransform(PITCH.reshape(1, -1, 2), homography)[0]
    assert np.max(np.abs(mapped - np.float32(((0, 0), (105, 0), (0, 68), (105, 68))))) < 1.0


def test_mock_detector_projects_players_and_tracks_ids() -> None:
    image = _pitch_image()
    base = SoccerAdapter(detector=lambda frame: [])
    homography = base.homography_from_corners(PITCH)
    inverse = np.linalg.inv(homography)

    def box_for(x: float, y: float) -> list[float]:
        pixel = cv2.perspectiveTransform(np.float32([[[x, y]]]), inverse)[0, 0]
        return [pixel[0] - 15, pixel[1] - 60, pixel[0] + 15, pixel[1]]

    adapter = SoccerAdapter(detector=lambda frame: [box_for(20, 12), box_for(80, 52)])
    players = adapter.detect_players(image, homography)
    assert [track_id for track_id, _ in players] == [1, 2]
    points = {track_id: point for track_id, point in players}
    assert np.allclose(points[1], (20, 12), atol=0.5)
    assert np.allclose(points[2], (80, 52), atol=0.5)


def test_write_csv_uses_normalized_schema(tmp_path) -> None:
    adapter = SoccerAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame([[4, 1, "player", 20.0, 6.0]], columns=("frame", "track_id", "cls", "x", "y"))
    output = tmp_path / "tracking.csv"
    adapter.write_csv(output)
    assert list(pd.read_csv(output).columns) == ["frame", "track_id", "cls", "x", "y"]
