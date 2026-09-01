"""Synthetic tests for the football broadcast adapter.

Run: python -m pytest domains/football/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.football.tracking.adapter import FootballAdapter


def _field() -> np.ndarray:
    image = np.zeros((360, 720, 3), dtype=np.uint8)
    image[40:320, 60:660] = (45, 145, 45)
    for x in range(90, 631, 45):
        cv2.line(image, (x, 40), (x, 319), (255, 255, 255), 3)
    cv2.line(image, (60, 40), (660, 40), (255, 255, 255), 3)
    cv2.line(image, (60, 319), (660, 319), (255, 255, 255), 3)
    return image


def test_yard_line_family_maps_spacing_to_fifteen_feet() -> None:
    adapter = FootballAdapter(detector=lambda frame: [])
    frame = _field()
    lines = adapter.detect_yard_line_family(frame)
    assert len(lines) >= 10
    homography = adapter.homography_from_yard_lines(frame)
    assert homography is not None
    points = np.float32([[[90, 180], [135, 180]]])
    mapped = cv2.perspectiveTransform(points, homography)[0]
    assert abs(abs(mapped[1, 0] - mapped[0, 0]) - 15.0) <= 1.5


def test_pre_snap_classifier_separates_still_and_moving_frames() -> None:
    frame = _field()
    moving = frame.copy()
    cv2.rectangle(moving, (0, 0), (719, 359), (0, 0, 255), -1)
    boxes = [[10, 10, 20, 30]] * 14
    adapter = FootballAdapter(detector=lambda image: boxes, motion_threshold=2.0)
    assert adapter.is_pre_snap(frame, frame)
    assert not adapter.is_pre_snap(frame, moving)


def test_mocked_detector_projects_and_tracks_players() -> None:
    frame = _field()
    homography = FootballAdapter(detector=lambda image: []).homography_from_yard_lines(frame)
    assert homography is not None
    boxes = [[90, 150, 100, 180], [135, 160, 145, 190]]
    adapter = FootballAdapter(detector=lambda image: boxes)
    rows = adapter._track_players(adapter._detect(frame), homography)
    assert [row[0] for row in rows] == [1, 2]
    assert abs(abs(rows[1][1][0] - rows[0][1][0]) - 15.0) <= 1.5
    assert 0.0 <= rows[0][1][1] <= 160.0


def test_out_of_field_projection_is_not_emitted() -> None:
    adapter = FootballAdapter(detector=lambda image: [[0, 0, 10, 20]])
    homography = np.array(((1.0, 0.0, 400.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))

    assert adapter._track_players(adapter._detect(_field()), homography) == []


def test_scene_cut_clears_carried_geometry_and_identity_state() -> None:
    first = _field()
    second = np.full_like(first, (0, 0, 255))
    adapter = FootballAdapter(detector=lambda image: [], scene_cut_threshold=0.20)
    adapter._homography = np.eye(3)
    adapter._h_params.append(np.ones(8))
    adapter._centroids[7] = np.array((100.0, 100.0))

    assert adapter.is_scene_cut(first, second)
    adapter._reset_segment()
    assert adapter._homography is None
    assert not adapter._h_params and not adapter._centroids


def test_scene_score_keeps_identical_view_below_cut_threshold() -> None:
    frame = _field()
    adapter = FootballAdapter(detector=lambda image: [])

    assert adapter.scene_cut_score(frame, frame) == 0.0
    assert not adapter.is_scene_cut(frame, frame)


def test_degenerate_homography_normalization_is_rejected(monkeypatch) -> None:
    frame = _field()
    adapter = FootballAdapter(detector=lambda image: [])
    monkeypatch.setattr(adapter, "detect_yard_line_family", lambda image: [
        np.array((1.0, 0.0, -10.0)), np.array((1.0, 0.0, -20.0)),
    ])
    monkeypatch.setattr(adapter, "_line_groups", lambda image: [])
    monkeypatch.setattr(cv2, "findHomography", lambda *_args: (np.zeros((3, 3)), None))

    assert adapter.homography_from_yard_lines(frame) is None
