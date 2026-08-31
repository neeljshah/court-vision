"""Synthetic tests for the center-field baseball tracking adapter.

Run: python -m pytest domains/baseball/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.baseball.tracking.adapter import BaseballAdapter, MOUND_TO_PLATE_FEET


MOUND = np.array((640.0, 360.0), dtype=np.float32)
PLATE = np.array((640.0, 600.0), dtype=np.float32)


def _pitch_view() -> np.ndarray:
    image = np.full((720, 1280, 3), (45, 130, 45), dtype=np.uint8)
    dirt = (70, 135, 190)
    cv2.ellipse(image, tuple(MOUND.astype(int)), (55, 28), 0, 0, 360, dirt, -1)
    cv2.ellipse(image, tuple(PLATE.astype(int)), (70, 36), 0, 0, 360, dirt, -1)
    return image


def test_synthetic_pitch_view_and_scale() -> None:
    adapter = BaseballAdapter(detector=lambda frame: [])
    frame = _pitch_view()
    assert adapter.is_pitch_view(frame)
    scale = adapter.calibrate_scale(frame)
    assert scale is not None
    assert abs(scale - np.linalg.norm(MOUND - PLATE) / MOUND_TO_PLATE_FEET) < scale * 0.10


def test_all_green_frame_is_not_pitch_view() -> None:
    frame = np.full((720, 1280, 3), (45, 130, 45), dtype=np.uint8)
    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(frame)


def test_mock_detector_projects_pitcher_and_batter_ids() -> None:
    frame = _pitch_view()
    adapter = BaseballAdapter(detector=lambda frame: [
        [610, 260, 650, 370],
        [620, 480, 660, 590],
        [100, 100, 130, 130],
    ])
    geometry = adapter.detect_pitch_geometry(frame)
    assert geometry is not None
    players = adapter.detect_players(frame, geometry)
    assert [track_id for track_id, _ in players] == [1, 2]
    points = {track_id: point for track_id, point in players}
    assert np.allclose(
        points[1],
        ((630.0 - geometry.plate[0]) / geometry.pixels_per_foot,
         (geometry.plate[1] - 370.0) / geometry.pixels_per_foot),
        atol=1.0,
    )
    assert np.allclose(
        points[2],
        ((640.0 - geometry.plate[0]) / geometry.pixels_per_foot,
         (geometry.plate[1] - 590.0) / geometry.pixels_per_foot),
        atol=1.0,
    )
