from pathlib import Path

import numpy as np

from scripts.platformkit.soccer_s1_stream_packet import measure_window, select_window_starts


class FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames, self.index = frames, 0

    def isOpened(self) -> bool:
        return True

    def set(self, _prop: int, value: int) -> None:
        self.index = int(value)

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame

    def release(self) -> None:
        pass


class FakeAdapter:
    calibration_stride = 2

    def __init__(self, _detector: object) -> None:
        self.calls = 0
        self._homography = None

    def detect_players_image_space(self, _frame: np.ndarray) -> list[tuple[int, np.ndarray]]:
        values = [[1, 2], [1, 3], [1, 3]][self.calls]
        self.calls += 1
        return [(value, np.array([10.0 + value, 20.0])) for value in values]

    def _landmark_detections(self, _frame: np.ndarray) -> list[object]:
        return []

    def _stable_homography(self, _landmarks: list[object], _shape: tuple[int, int]) -> np.ndarray | None:
        return np.eye(3) if self.calls == 1 else None


def test_window_selection_and_churn_arithmetic(monkeypatch, tmp_path: Path) -> None:
    starts = select_window_starts(1000, 100, 5, 7)
    assert starts == select_window_starts(1000, 100, 5, 7)
    assert len(starts) == 5 and starts == sorted(starts)
    frames = [np.zeros((30, 30, 3), dtype=np.uint8) for _ in range(3)]
    monkeypatch.setattr("scripts.platformkit.soccer_s1_stream_packet.cv2.VideoCapture", lambda _path: FakeCapture(frames))
    monkeypatch.setattr("scripts.platformkit.soccer_s1_stream_packet._render", lambda *_args: None)
    row = measure_window(Path("fake.mp4"), 0, 3, object(), tmp_path, "clip", 1, FakeAdapter)
    assert row["frames_decoded"] == 3
    assert row["mean_raw_person_boxes_per_frame"] == 2.0
    assert row["distinct_track_ids"] == 3
    assert row["new_ids_per_frame"] == 1.0
    assert row["id_churn_ratio"] == 0.5
    assert row["fraction_frames_ge_14_boxes"] == 0.0
    assert row["homography_lock_rate"] == 0.5
