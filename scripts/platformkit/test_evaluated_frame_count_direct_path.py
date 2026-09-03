"""Regression tests for G204's pre-tracking direct-harness denominator."""
from pathlib import Path

import pandas as pd

from scripts.platformkit.attempted_frame_count_source import evaluated_frames_from_metadata
from scripts.platformkit.tracking_harness import evaluate_csv_path


def _tracking_rows(frames: int, decoded: int, fps: float, cap: int) -> pd.DataFrame:
    rows = []
    for frame in range(frames):
        for track_id in range(6):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + frame * 0.02, "y": 25.0,
                         "coordinate_space": "court_feet", "decoded_frames": decoded,
                         "source_fps": fps, "max_frames": cap})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet",
                     "decoded_frames": decoded, "source_fps": fps, "max_frames": cap})
    return pd.DataFrame(rows)


def _score(tmp_path: Path, decoded: int, fps: float, cap: int):
    path = tmp_path / "tracking_data.csv"
    _tracking_rows(50, decoded, fps, cap).to_csv(path, index=False)
    return evaluate_csv_path(str(path), "basketball")


def test_direct_path_derives_uncapped_evaluations_from_source_metadata(tmp_path):
    report = _score(tmp_path, decoded=39035, fps=60.0, cap=30000)

    assert evaluated_frames_from_metadata(39035, 60.0, 30000) == 6506
    assert report.attempted_frames == 6506
    assert report.coverage_attempted_frames_pct == round(50 / 6506, 4)
    assert report.verdict == "FAIL"


def test_direct_path_caps_stride_selected_evaluations(tmp_path):
    report = _score(tmp_path, decoded=426072, fps=30.0, cap=30000)

    assert evaluated_frames_from_metadata(426072, 30.0, 30000) == 30000
    assert report.attempted_frames == 30000
    assert report.coverage_attempted_frames_pct == round(50 / 30000, 4)


def test_direct_path_fails_closed_for_missing_or_unstable_source_metadata(tmp_path):
    path = tmp_path / "tracking_data.csv"
    frame = _tracking_rows(50, decoded=39035, fps=60.0, cap=30000)
    frame.loc[0, "max_frames"] = 29999
    frame.to_csv(path, index=False)

    report = evaluate_csv_path(str(path), "basketball")

    assert report.attempted_frames is None
    assert report.coverage_attempted_frames_pct is None
    assert "attempted_frames unavailable" in report.failures
