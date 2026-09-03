"""Regression tests for G199's sibling ball-table attempted-frame source."""
from pathlib import Path

import pandas as pd

from scripts.platformkit.attempted_frame_count_source import (
    attempted_frames_from_paired_ball_table,
)
from scripts.platformkit.tracking_harness import evaluate_csv_path


def _tracking_rows(frames: int) -> pd.DataFrame:
    rows = []
    for frame in range(frames):
        for track_id in range(6):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + frame * 0.02, "y": 25.0,
                         "coordinate_space": "court_feet"})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet"})
    return pd.DataFrame(rows)


def _write_pair(tmp_path: Path, tracking_frames: int, ball_frames: int) -> Path:
    tracking_path = tmp_path / "tracking_data.csv"
    _tracking_rows(tracking_frames).to_csv(tracking_path, index=False)
    pd.DataFrame({"frame": range(ball_frames), "detected": 1}).to_csv(
        tmp_path / "ball_tracking.csv", index=False
    )
    return tracking_path


def test_direct_csv_scoring_uses_verified_sibling_ball_frame_count(tmp_path):
    tracking_path = _write_pair(tmp_path, tracking_frames=100, ball_frames=200)

    report = evaluate_csv_path(str(tracking_path), "basketball")

    assert attempted_frames_from_paired_ball_table(tracking_path) == 200
    assert report.attempted_frames == 200
    assert report.coverage_attempted_frames_pct == 0.5
    assert report.ball_valid_attempted_frames_pct == 0.5
    assert not report.passed
    assert any(failure.startswith("coverage_attempted_frames") for failure in report.failures)


def test_non_superset_sibling_ball_table_is_never_used_as_denominator(tmp_path):
    tracking_path = _write_pair(tmp_path, tracking_frames=100, ball_frames=50)

    report = evaluate_csv_path(str(tracking_path), "basketball")

    assert attempted_frames_from_paired_ball_table(tracking_path) is None
    assert report.attempted_frames is None
    assert report.coverage_attempted_frames_pct is None
    assert "attempted_frames unavailable" in report.failures


def test_duplicate_ball_frame_rows_are_not_an_attempt_record(tmp_path):
    tracking_path = _write_pair(tmp_path, tracking_frames=100, ball_frames=100)
    ball_path = tmp_path / "ball_tracking.csv"
    ball = pd.read_csv(ball_path)
    pd.concat([ball, ball.iloc[[0]]], ignore_index=True).to_csv(ball_path, index=False)

    assert attempted_frames_from_paired_ball_table(tracking_path) is None
