"""Synthetic tests for the baseball pitch-view adapter.

The synthetic pitch view mirrors the MEASURED broadcast layout (2026-09-01, two
corpora): the pitcher's mound images BELOW the home-plate/base-path dirt band,
is bounded by live grass on both sides, and its horizontal chord is the known
18 feet.  The old adapter assumed the opposite ordering.

Run: python -m pytest domains/baseball/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd
import pytest

from domains.baseball.tracking.adapter import (
    BallTrackingUnavailableError, BaseballAdapter, PitchGeometry,
)
from domains.baseball.tracking.field_mask import MOUND_DIAMETER_FEET
from scripts.platformkit.tracking_harness import evaluate

GRASS = (45, 130, 45)
DIRT = (70, 76, 120)          # measured park dirt: BGR ~ (75, 76, 120), hue 1
MOUND_CENTER = (506, 604)
MOUND_HALF_WIDTH = 456
INFIELD_BAND_ROWS = (300, 450)


def _pitch_view() -> np.ndarray:
    """Green field, a full-width infield dirt band, and a grass-bounded mound."""
    image = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    top, bottom = INFIELD_BAND_ROWS
    cv2.rectangle(image, (0, top), (1280, bottom), DIRT, -1)
    cv2.ellipse(image, MOUND_CENTER, (MOUND_HALF_WIDTH, 55), 0, 0, 360, DIRT, -1)
    return image


def _geometry(scale: float = 50.0) -> PitchGeometry:
    return PitchGeometry(np.array(MOUND_CENTER, dtype=np.float32),
                         scale * MOUND_DIAMETER_FEET, scale, True)


class _FakeCapture:
    def __init__(self, frames):
        self._frames = list(frames)

    def isOpened(self) -> bool:
        return True

    def read(self):
        return (True, self._frames.pop(0)) if self._frames else (False, None)

    def release(self) -> None:
        pass


def test_pitch_view_scale_comes_from_the_known_mound_chord() -> None:
    adapter = BaseballAdapter(detector=lambda frame: [])
    geometry = adapter.detect_pitch_geometry(_pitch_view())

    assert geometry is not None
    assert abs(geometry.mound_chord_px - 2 * MOUND_HALF_WIDTH) <= 6
    assert abs(geometry.pixels_per_foot
               - geometry.mound_chord_px / MOUND_DIAMETER_FEET) < 1e-6


def test_mound_is_found_below_the_infield_band_not_above_it() -> None:
    """Regression for the label inversion: the mound images BELOW home plate."""
    adapter = BaseballAdapter(detector=lambda frame: [])
    geometry = adapter.detect_pitch_geometry(_pitch_view())

    assert geometry is not None
    assert geometry.mound[1] > INFIELD_BAND_ROWS[1]
    assert abs(float(geometry.mound[0]) - MOUND_CENTER[0]) <= 6


def test_all_green_frame_is_not_a_pitch_view() -> None:
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(frame)


def test_outfield_wide_shot_is_rejected() -> None:
    """Measured false positive: warning-track dirt running off the frame edge."""
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.rectangle(frame, (0, 560), (1280, 640), DIRT, -1)

    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(frame)


def test_single_fielder_close_up_is_rejected() -> None:
    """Measured false positive: an isolated dirt patch far too small to be a mound."""
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.rectangle(frame, (0, 300), (1280, 380), DIRT, -1)
    cv2.ellipse(frame, (620, 560), (90, 40), 0, 0, 360, DIRT, -1)

    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(frame)


def test_replay_dissolve_is_rejected() -> None:
    """Measured false positive: a washed-out dissolve loses the dominant green."""
    dissolved = cv2.addWeighted(_pitch_view(), 0.35,
                                np.full((720, 1280, 3), 210, dtype=np.uint8), 0.65, 0)

    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(dissolved)


def test_mound_without_an_infield_band_above_it_is_rejected() -> None:
    frame = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.ellipse(frame, MOUND_CENTER, (MOUND_HALF_WIDTH, 55), 0, 0, 360, DIRT, -1)

    assert not BaseballAdapter(detector=lambda frame: []).is_pitch_view(frame)


def test_process_video_emits_no_coordinate_rows(monkeypatch) -> None:
    monkeypatch.setattr(cv2, "VideoCapture",
                        lambda path: _FakeCapture([_pitch_view() for _ in range(5)]))
    adapter = BaseballAdapter(detector=lambda frame: [[600, 500, 660, 604]])

    rows, metadata = adapter.process_video(
        "synthetic.mp4", compute_command=True, player_only=True)

    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y"]
    assert rows.empty
    assert metadata["coordinate_calibration"] == "unavailable"
    assert "no validated ground-plane homography" in \
        str(metadata["coordinate_calibration_reason"]).lower()
    # The refusal is a calibration limit, not a detection failure.
    assert metadata["pitch_view_frames"] == 5
    assert metadata["players_detected_but_unplaced"] > 0


def test_image_space_rows_are_observed_and_fail_coordinate_contract(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cv2, "VideoCapture",
                        lambda path: _FakeCapture([_pitch_view() for _ in range(5)]))
    adapter = BaseballAdapter(detector=lambda frame: [[600, 500, 660, 604]])

    rows = adapter.process_video("synthetic.mp4", image_space=True, player_only=True)
    output = tmp_path / "image_rows.csv"
    adapter.write_csv(output, rows)
    saved = pd.read_csv(output)
    report = evaluate(saved, "baseball")

    assert len(rows) == 5
    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y",
                                  "coordinate_space", "observation", "calibration"]
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert list(saved.columns) == list(rows.columns)
    assert not report.passed
    assert any(failure.startswith("coordinate_contract:") for failure in report.failures)


def test_process_video_fails_closed_when_ball_tracking_is_requested() -> None:
    adapter = BaseballAdapter(detector=lambda frame: [])

    with pytest.raises(BallTrackingUnavailableError, match="no validated fast-ball detector"):
        adapter.process_video("unused.mp4")


def test_process_video_splits_pitch_segments_at_scene_cuts(monkeypatch) -> None:
    frames = [np.full((72, 128, 3), GRASS, dtype=np.uint8) for _ in range(12)]
    frames.append(np.full((72, 128, 3), (180, 40, 20), dtype=np.uint8))
    frames.extend(np.full((72, 128, 3), GRASS, dtype=np.uint8) for _ in range(12))
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: _FakeCapture(frames))
    adapter = BaseballAdapter(detector=lambda frame: [])
    monkeypatch.setattr(adapter, "detect_pitch_geometry", lambda frame: _geometry())

    _, metadata = adapter.process_video(
        "synthetic.mp4", compute_command=True, player_only=True)

    raw = metadata["raw_calibrations"]
    assert {row["segment_id"] for row in raw} == {1, 2}
    assert {12, 13}.isdisjoint({row["frame"] for row in raw})
