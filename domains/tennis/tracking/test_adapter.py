"""Synthetic tests for the tennis broadcast tracking adapter.

Run: python -m pytest domains/tennis/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd
import sys
from types import SimpleNamespace

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.segmenter import detect_cut, small_gray


COURT = np.float32(((120, 650), (1160, 650), (430, 120), (850, 120)))


def _court_image() -> np.ndarray:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:] = (40, 120, 40)
    cv2.polylines(image, [COURT.astype(np.int32)], True, (255, 255, 255), 5)
    cv2.line(image, tuple(COURT[0].astype(int)), tuple(COURT[2].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(COURT[1].astype(int)), tuple(COURT[3].astype(int)), (255, 255, 255), 5)
    return image


class _FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self._frames = iter(frames)

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        try:
            return True, next(self._frames)
        except StopIteration:
            return False, None

    def release(self) -> None:
        pass


def _ball_sequence(with_dot: bool) -> list[np.ndarray]:
    frames = []
    for index in range(14):
        frame = _court_image()
        if with_dot:
            cv2.circle(frame, (560 + index * 3, 260), 2, (255, 255, 255), thickness=-1)
        frames.append(frame)
    return frames


def test_process_video_appends_rectified_ball_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "domains.tennis.tracking.adapter.cv2.VideoCapture",
        lambda path: _FakeCapture(_ball_sequence(with_dot=True)),
    )
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.detect_court_corners = lambda frame: COURT

    output = adapter.process_video("synthetic.avi")

    balls = output.loc[output.cls == "ball"]
    assert not balls.empty
    assert balls.x.between(0.0, 78.0).all()
    assert balls.y.between(0.0, 36.0).all()
    assert set(output.calibration_provenance) == {"solved"}


def test_process_video_returns_rally_metadata_only_when_requested(monkeypatch) -> None:
    monkeypatch.setattr(
        "domains.tennis.tracking.adapter.cv2.VideoCapture",
        lambda path: _FakeCapture(_ball_sequence(with_dot=True)),
    )
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.detect_court_corners = lambda frame: COURT

    rows, metadata = adapter.process_video("synthetic.avi", compute_features=True)

    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y", "calibration_provenance"]
    assert metadata == adapter.last_metadata
    assert set(metadata["rally_features"]) >= {"n_rallies", "players"}


def test_process_video_keeps_no_ball_rows_when_motion_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        "domains.tennis.tracking.adapter.cv2.VideoCapture",
        lambda path: _FakeCapture(_ball_sequence(with_dot=False)),
    )
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.detect_court_corners = lambda frame: COURT

    output = adapter.process_video("synthetic.avi")

    assert output.loc[output.cls == "ball"].empty


def test_synthetic_corners_and_homography() -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    corners = adapter.detect_court_corners(_court_image())
    assert corners is not None
    assert np.max(np.abs(corners - COURT)) < 5.0
    homography = adapter.homography_from_corners(corners)
    mapped = cv2.perspectiveTransform(COURT.reshape(1, -1, 2), homography)[0]
    expected = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))
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


def test_temporal_calibration_limits_noisy_corner_projection_jitter() -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    rng = np.random.default_rng(7)
    projected = []
    for index in range(45):
        noise = np.zeros_like(COURT) if index < 9 else rng.normal(0, 100, COURT.shape)
        adapter.detect_court_corners = lambda frame, corners=COURT + noise: corners
        homography = adapter._stable_homography(np.zeros((720, 1280, 3), dtype=np.uint8))
        if homography is not None:
            projected.append(adapter._project((640.0, 375.0), homography))
    jumps = np.linalg.norm(np.diff(np.asarray(projected), axis=0), axis=1)
    assert np.percentile(jumps, 95) < 8.0


def test_lost_corners_mark_reused_homography_propagated() -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    frame = _court_image()
    adapter.detect_court_corners = lambda _: COURT
    for _ in range(8):
        adapter._stable_homography(frame)
    assert adapter._stable_homography(frame) is not None
    adapter.detect_court_corners = lambda _: None
    assert adapter._stable_homography(frame) is not None
    assert adapter._calibration_provenance == "propagated"


def test_scene_cut_resets_homography_smoothing(monkeypatch) -> None:
    first_court = COURT.copy()
    second_court = np.float32(((180, 640), (1100, 610), (340, 100), (950, 150)))
    first_frames = [np.full((720, 1280, 3), (30, 100, 30), dtype=np.uint8) for _ in range(12)]
    second_frames = [np.full((720, 1280, 3), (220, 180, 180), dtype=np.uint8) for _ in range(12)]
    frames = first_frames + second_frames
    assert detect_cut(small_gray(first_frames[-1]), small_gray(second_frames[0]))

    class FakeCapture:
        def __init__(self, stream: list[np.ndarray]) -> None:
            self._stream = iter(stream)

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, np.ndarray | None]:
            try:
                return True, next(self._stream)
            except StopIteration:
                return False, None

        def release(self) -> None:
            pass

    monkeypatch.setattr(
        "domains.tennis.tracking.adapter.cv2.VideoCapture",
        lambda path: FakeCapture(frames),
    )
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.detect_court_corners = lambda frame: (
        first_court if frame[0, 0, 0] < 100 else second_court
    )
    seen: list[tuple[str, np.ndarray]] = []

    def record_projection(frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        segment = "first" if frame[0, 0, 0] < 100 else "second"
        seen.append((segment, adapter._project((640.0, 375.0), homography)))
        return []

    adapter.detect_players = record_projection
    adapter.process_video("synthetic.avi")

    expected_second = adapter._project(
        (640.0, 375.0), adapter.homography_from_corners(second_court)
    )
    first_points = np.asarray([point for segment, point in seen if segment == "first"])
    second_points = np.asarray([point for segment, point in seen if segment == "second"])
    assert len(first_points) > 0
    assert np.allclose(second_points, expected_second, atol=0.5)
    for points in (first_points, second_points):
        jumps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        assert np.percentile(jumps, 95) < 8.0


def test_write_csv_uses_normalized_schema(tmp_path) -> None:
    adapter = TennisAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame(
        [[4, 1, "player", 20.0, 6.0, "solved"]], columns=("frame", "track_id", "cls", "x", "y", "calibration_provenance")
    )
    output = tmp_path / "tracking.csv"
    adapter.write_csv(output)
    assert list(pd.read_csv(output).columns) == ["frame", "track_id", "cls", "x", "y", "calibration_provenance"]


def test_yolo_detector_receives_configured_imgsz_and_conf(monkeypatch, capsys) -> None:
    calls: list[dict[str, object]] = []

    class Model:
        def __call__(self, frame, **kwargs):
            calls.append(kwargs)
            boxes = SimpleNamespace(
                xyxy=SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array([[1, 2, 3, 4]]))),
                conf=SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array([0.8]))),
            )
            return [SimpleNamespace(boxes=boxes)]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda _: Model()))
    detector = TennisAdapter._load_yolo_detector(1280, 0.15)
    assert detector(np.zeros((4, 4, 3), dtype=np.uint8)) == [[1, 2, 3, 4, 0.8]]
    assert calls == [{"classes": [0], "imgsz": 1280, "conf": 0.15, "verbose": False}]
    assert "TENNIS_INFERENCE imgsz=1280 conf=0.150" in capsys.readouterr().out
