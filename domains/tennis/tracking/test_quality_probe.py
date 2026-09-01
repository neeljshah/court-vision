"""Tests for tennis tracking depth reporting.

Run: python -m pytest domains/tennis/tracking/test_quality_probe.py -q
"""
from __future__ import annotations

import math

import pandas as pd

from domains.tennis.tracking.quality_probe import quality_report_csv


def _rows(ball_every_frame: bool = True) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for frame in range(25):
        rows.extend((
            {"frame": frame, "track_id": 1, "cls": "player", "x": frame, "y": frame},
            {"frame": frame, "track_id": 2, "cls": "player", "x": 78 - frame, "y": 36 - frame},
        ))
        if ball_every_frame:
            rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 39, "y": 18})
    return pd.DataFrame(rows)


def test_quality_report_csv_reports_depth_metrics_and_a_grade(tmp_path) -> None:
    path = tmp_path / "tracking.csv"
    _rows().to_csv(path, index=False)

    report = quality_report_csv(path)

    assert report["pct_frames_two_players"] == 100.0
    assert report["pct_frames_ball"] == 100.0
    assert report["median_rally_length_frames"] == 25.0
    assert report["court_coverage_sqft_by_player"] == {1: 576.0, 2: 576.0}
    assert report["depth_grade"] == "A"


def test_quality_report_csv_marks_insufficient_tracking_c(tmp_path) -> None:
    path = tmp_path / "thin.csv"
    rows = _rows(ball_every_frame=False).query("frame < 5 and track_id == 1")
    rows.to_csv(path, index=False)

    report = quality_report_csv(path)

    assert report["pct_frames_two_players"] == 0.0
    assert report["pct_frames_ball"] == 0.0
    assert math.isnan(report["median_rally_length_frames"])
    assert report["depth_grade"] == "C"
