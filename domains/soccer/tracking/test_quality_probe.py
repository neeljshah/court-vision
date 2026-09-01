"""Tests for soccer-specific tracking depth reporting.

Run: python -m pytest domains/soccer/tracking/test_quality_probe.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.tracking.quality_probe import format_depth_report, probe_tracking_depth


def test_reports_soccer_depth_with_accepted_frame_denominator() -> None:
    rows = pd.DataFrame(
        [
            {"frame": frame, "track_id": track_id, "cls": "player", "x": 1.0, "y": 2.0}
            for frame in (0, 1, 2, 3, 4, 5, 6)
            for track_id in range(15)
        ]
    )
    metadata = {
        "processed_frames": 10,
        "pitch_view_frames": list(range(8)),
        "accepted_homography_frames": list(range(7)),
        "pressing_proxy": {"frame_ids": list(range(6))},
    }
    report = probe_tracking_depth(rows, metadata)
    assert report == {
        "pct_frames_accepted_homography": 70.0,
        "median_players_per_accepted_frame": 15.0,
        "pitch_view_segment_coverage": 0.8,
        "pressing_proxy_coverage": 6 / 7,
        "depth_grade": "A",
    }
    assert "grade=A" in format_depth_report(report)


def test_missing_metadata_is_observed_as_no_coverage() -> None:
    report = probe_tracking_depth(pd.DataFrame(columns=("frame", "cls")), {})
    assert report["depth_grade"] == "C"
    assert report["pct_frames_accepted_homography"] == 0.0
