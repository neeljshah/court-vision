"""Synthetic tests for the football broadcast adapter.

Run: python -m pytest domains/football/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.football.tracking.adapter import (SANITY_LIMIT_FT, YARD_LINE_SPACING_FT,
                                               FootballAdapter)


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


def test_off_field_projection_is_emitted_so_the_harness_can_count_it() -> None:
    """A 400 ft x is off a 360 ft field but is real output, not a blowup.

    Dropping it here would make the harness oob_pct tautologically zero.
    """
    adapter = FootballAdapter(detector=lambda image: [[0, 0, 10, 20]])
    homography = np.array(((1.0, 0.0, 400.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))

    rows = adapter._track_players(adapter._detect(_field()), homography)
    assert len(rows) == 1 and rows[0][1][0] > 360.0


def test_numerical_blowup_projection_is_dropped() -> None:
    adapter = FootballAdapter(detector=lambda image: [[0, 0, 10, 20]])
    homography = np.array(((1.0, 0.0, 10 * SANITY_LIMIT_FT), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))

    assert adapter._track_players(adapter._detect(_field()), homography) == []


def test_scene_cut_clears_carried_geometry_and_identity_state() -> None:
    first = _field()
    second = np.full_like(first, (0, 0, 255))
    adapter = FootballAdapter(detector=lambda image: [], scene_cut_threshold=0.20)
    adapter._homography = np.eye(3)
    adapter._centroids[7] = np.array((100.0, 100.0))

    assert adapter.is_scene_cut(first, second)
    adapter._reset_segment()
    assert adapter._homography is None
    assert not adapter._centroids


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


def test_contaminated_yard_line_family_is_rejected(monkeypatch) -> None:
    adapter = FootballAdapter(detector=lambda image: [])
    monkeypatch.setattr(adapter, "detect_yard_line_family",
                        lambda image: [np.array((1.0, 0.0, -float(x))) for x in range(30)])

    assert adapter.homography_from_yard_lines(_field()) is None
    assert adapter.last_fit_stats["reject"] == "family_size"


def test_held_homography_is_reused_while_a_fresh_fit_agrees() -> None:
    frame = _field()
    adapter = FootballAdapter(detector=lambda image: [])

    assert adapter._stable_homography(frame) is None, "first fit only anchors the segment"
    held = adapter._homography
    assert held is not None
    assert adapter._stable_homography(frame) is held


def test_disagreeing_fit_starts_a_new_segment_instead_of_sliding_the_origin(monkeypatch) -> None:
    frame = _field()
    adapter = FootballAdapter(detector=lambda image: [])
    adapter._stable_homography(frame)
    assert adapter._stable_homography(frame) is not None
    adapter._centroids[7] = np.array((10.0, 10.0))
    reindexed = adapter._homography.copy()
    reindexed[0, 2] += YARD_LINE_SPACING_FT
    monkeypatch.setattr(adapter, "homography_from_yard_lines", lambda image: reindexed)

    assert adapter._stable_homography(frame) is None
    assert not adapter._centroids
