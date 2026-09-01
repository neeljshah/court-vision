"""Synthetic tests for the center-field baseball tracking adapter.

Run: python -m pytest domains/baseball/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.baseball.tracking.adapter import BaseballAdapter, MOUND_TO_PLATE_FEET, PitchGeometry


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


def test_abs_overlay_does_not_change_pitch_view_scale() -> None:
    adapter = BaseballAdapter(detector=lambda frame: [])
    frame = _pitch_view()
    baseline = adapter.calibrate_scale(frame)
    dirt = (70, 135, 190)
    cv2.rectangle(frame, (550, 500), (730, 552), dirt, 6)

    assert adapter.is_pitch_view(frame)
    scale = adapter.calibrate_scale(frame)
    assert scale is not None and baseline is not None
    assert abs(scale - baseline) < baseline * 0.01


def test_corner_scorebug_is_excluded_from_dirt_detection() -> None:
    adapter = BaseballAdapter(detector=lambda frame: [])
    frame = _pitch_view()
    cv2.rectangle(frame, (0, 0), (180, 90), (70, 135, 190), -1)

    assert len(adapter._dirt_blobs(frame)) == 2
    assert adapter.is_pitch_view(frame)


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


def test_process_video_stabilizes_jittered_pitch_view_projection(monkeypatch) -> None:
    scales = [4.0 + (0.8 if index % 2 else -0.8) for index in range(40)]
    geometries = iter([
        PitchGeometry(
            np.array((640.0, 600.0 - scale * MOUND_TO_PLATE_FEET), dtype=np.float32),
            PLATE.copy(),
            scale,
        )
        for scale in scales
    ])

    class FakeCapture:
        def __init__(self) -> None:
            self.index = 0

        def isOpened(self) -> bool:
            return True

        def read(self):
            if self.index == len(scales):
                return False, None
            self.index += 1
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self) -> None:
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda path: FakeCapture())
    adapter = BaseballAdapter(detector=lambda frame: [
        [610, 300, 650, 410], [620, 480, 660, 590],
    ])
    monkeypatch.setattr(adapter, "detect_pitch_geometry", lambda frame: next(geometries))

    rows = adapter.process_video("synthetic.mp4")
    pitcher = rows.loc[rows["track_id"] == 1, "y"].to_numpy()
    assert len(pitcher) >= 10
    assert np.percentile(np.abs(np.diff(pitcher)), 95) < 10.0


def test_process_video_command_flag_returns_metadata_without_row_schema_change(monkeypatch) -> None:
    frames = iter([np.zeros((2, 2, 3), dtype=np.uint8) for _ in range(3)])

    class FakeCapture:
        def isOpened(self) -> bool:
            return True

        def read(self):
            try:
                return True, next(frames)
            except StopIteration:
                return False, None

        def release(self) -> None:
            pass

    geometry = PitchGeometry(MOUND.copy(), PLATE.copy(), 4.0)
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: FakeCapture())
    adapter = BaseballAdapter(detector=lambda frame: [])
    monkeypatch.setattr(adapter, "detect_pitch_geometry", lambda frame: geometry)

    rows, metadata = adapter.process_video("synthetic.mp4", compute_command=True)

    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y"]
    assert metadata["pitch_view_frames"] == 3
    assert metadata["pitch_segments"] == 1
    assert list(metadata["command_series"].columns) == [
        "pitch", "inning", "miss_ft", "horizontal_ft", "vertical_ft", "inning_median_ft",
    ]
