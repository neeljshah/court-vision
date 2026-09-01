"""Synthetic tests for the football broadcast adapter.

Run: python -m pytest domains/football/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from domains.football.tracking.adapter import (SANITY_LIMIT_FT, YARD_LINE_SPACING_FT,
                                               FootballAdapter)
from domains.football.tracking.absolute_anchor import AbsoluteYardAnchor
from scripts.platformkit.tracking_harness import evaluate


def _field() -> np.ndarray:
    image = np.zeros((360, 720, 3), dtype=np.uint8)
    image[40:320, 60:660] = (45, 145, 45)
    for x in range(90, 631, 45):
        cv2.line(image, (x, 40), (x, 319), (255, 255, 255), 3)
    cv2.line(image, (60, 40), (660, 40), (255, 255, 255), 3)
    cv2.line(image, (60, 319), (660, 319), (255, 255, 255), 3)
    return image


class _AnchorProvider:
    def detect(self, frame: np.ndarray) -> AbsoluteYardAnchor:
        del frame
        return AbsoluteYardAnchor(40, 1, (360.0, 180.0), 0.99)


def _adapter(**kwargs: object) -> FootballAdapter:
    adapter = FootballAdapter(**kwargs)
    adapter.absolute_anchor_provider = _AnchorProvider()
    return adapter


class _FakeCapture:
    def __init__(self, frames):
        self._frames = list(frames)

    def isOpened(self) -> bool:
        return True

    def read(self):
        return (True, self._frames.pop(0)) if self._frames else (False, None)

    def release(self) -> None:
        pass


def test_unmeasured_scale_never_promotes_a_grid_to_feet() -> None:
    adapter = _adapter(detector=lambda frame: [])
    frame = _field()
    lines = adapter.detect_yard_line_family(frame)
    assert len(lines) >= 10
    assert adapter.homography_from_yard_lines(frame) is None
    assert adapter.last_fit_stats["reject"] == "independent_scale_unavailable"


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
    homography = np.eye(3)
    boxes = [[90, 150, 100, 180], [135, 160, 145, 190]]
    adapter = _adapter(detector=lambda image: boxes)
    rows = adapter._track_players(adapter._detect(frame), homography)
    assert [row[0] for row in rows] == [1, 2]
    assert abs(rows[1][1][0] - rows[0][1][0]) == 45.0
    assert rows[0][1][1] == 180.0


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
    adapter = _adapter(detector=lambda image: [])

    assert adapter.scene_cut_score(frame, frame) == 0.0
    assert not adapter.is_scene_cut(frame, frame)


def test_degenerate_homography_normalization_is_rejected(monkeypatch) -> None:
    frame = _field()
    adapter = _adapter(detector=lambda image: [])
    monkeypatch.setattr(adapter, "detect_yard_line_family", lambda image: [
        np.array((1.0, 0.0, -10.0)), np.array((1.0, 0.0, -20.0)),
    ])
    monkeypatch.setattr(adapter, "_line_groups", lambda image: [])
    monkeypatch.setattr(cv2, "findHomography", lambda *_args: (np.zeros((3, 3)), None))

    assert adapter.homography_from_yard_lines(frame) is None


def test_contaminated_yard_line_family_is_rejected(monkeypatch) -> None:
    adapter = _adapter(detector=lambda image: [])
    monkeypatch.setattr(adapter, "detect_yard_line_family",
                        lambda image: [np.array((1.0, 0.0, -float(x))) for x in range(30)])

    assert adapter.homography_from_yard_lines(_field()) is None
    assert adapter.last_fit_stats["reject"] == "family_size"


def test_held_homography_is_reused_while_a_fresh_fit_agrees() -> None:
    frame = _field()
    adapter = _adapter(detector=lambda image: [])

    assert adapter._stable_homography(frame) is None
    assert adapter._homography is None


def test_disagreeing_fit_starts_a_new_segment_instead_of_sliding_the_origin(monkeypatch) -> None:
    frame = _field()
    adapter = _adapter(detector=lambda image: [])
    adapter._centroids[7] = np.array((10.0, 10.0))
    assert adapter._stable_homography(frame) is None
    assert not adapter._centroids


def test_image_space_rows_are_observed_and_fail_coordinate_contract(monkeypatch, tmp_path) -> None:
    """Pixels are training observations, never football field coordinates."""
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: _FakeCapture([_field(), _field()]))
    adapter = FootballAdapter(detector=lambda frame: [[90, 150, 100, 180]])
    monkeypatch.setattr(adapter, "homography_from_yard_lines",
                        lambda frame: (_ for _ in ()).throw(AssertionError("must not calibrate")))

    rows = adapter.process_video("synthetic.mp4", image_space=True)
    output = tmp_path / "image_rows.csv"
    adapter.write_csv(output, rows)
    saved = pd.read_csv(output)
    report = evaluate(saved, "football")

    assert len(rows) == 2
    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y",
                                  "coordinate_space", "observation", "calibration"]
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert list(saved.columns) == list(rows.columns)
    assert not report.passed
    assert any(failure.startswith("coordinate_contract:") for failure in report.failures)


def test_default_path_never_mixes_unanchored_pixels_into_court_output(monkeypatch) -> None:
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: _FakeCapture([_field(), _field()]))
    adapter = FootballAdapter(detector=lambda frame: [[90, 150, 100, 180]])
    rows = adapter.process_video("synthetic.mp4")
    assert rows.empty


def test_line_homography_lands_a_held_out_intersection_at_its_named_coordinate() -> None:
    """A fresh line solve maps a non-fit yard/hash intersection in field feet."""
    image_to_court = np.array(((0.18, 0.03, -20.0), (0.01, 0.22, -30.0),
                               (0.0001, 0.0002, 1.0)))
    court_to_image = np.linalg.inv(image_to_court)
    court_lines = [np.array((1.0, 0.0, -value)) for value in (105.0, 120.0, 135.0)]
    court_lines += [np.array((0.0, 1.0, -60.0)), np.array((0.0, 1.0, -100.0))]
    image_lines = [np.linalg.inv(image_to_court).T @ line for line in court_lines]
    solved = FootballAdapter.line_homography(court_lines[:2] + court_lines[3:],
                                             image_lines[:2] + image_lines[3:])
    assert solved is not None
    held_court = np.array((135.0, 100.0, 1.0))
    held_image = court_to_image @ held_court
    held_image /= held_image[2]
    projected = cv2.perspectiveTransform(np.float32([[held_image[:2]]]), solved)[0, 0]
    assert np.linalg.norm(projected - held_court[:2]) < 1e-3


def test_a_thin_pre_snap_frame_is_still_emitted_so_coverage_can_fail() -> None:
    """The sibling of the oob test above, for coverage.

    is_pre_snap ANDed in `len(detections) >= 14` and the emission loop repeated
    `players if len(players) >= 14 else ()`. Football's harness min_players is
    exactly 14 and the coverage denominator is the emitted CSV's frame count,
    so no frame that could fail coverage was ever emitted: coverage was pinned
    at 1.0 by construction. Nine players on a pre-snap frame is a real
    observation and the harness must be allowed to count it.
    """
    frame = _field()
    boxes = [[90 + 10 * i, 150, 100 + 10 * i, 180] for i in range(9)]
    adapter = _adapter(detector=lambda image: boxes, motion_threshold=2.0)

    assert adapter.is_pre_snap(frame, frame), "motion is the snap evidence, not headcount"
    homography = np.eye(3)
    rows = adapter._track_players(adapter._detect(frame), homography)
    assert len(rows) == 9, "a nine-player frame must reach the harness, not vanish"
