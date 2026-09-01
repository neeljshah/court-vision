"""Tests for baseball tracking-depth reporting.

Run: python -m pytest domains/baseball/tracking/test_quality_probe.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.baseball.tracking.quality_probe import probe_quality


def test_probe_reports_baseball_depth_metrics_and_grade_a() -> None:
    metadata = {
        "frames_processed": 100,
        "pitch_view_frames": 80,
        "pitch_segments": 5,
        "raw_calibrations": [{"frame": index} for index in range(80)],
        "calibrations": [{"frame": index} for index in range(72)],
        "command_series": pd.DataFrame({"pitch": range(4)}),
    }

    report = probe_quality(metadata)

    assert report.pitch_view_frame_pct == 0.80
    assert report.pitches_detected == 5
    assert report.scale_stability_rate == 0.90
    assert report.command_meter_coverage == 0.80
    assert report.depth_grade == "A"


def test_probe_grades_missing_or_unstable_pitch_view_as_c() -> None:
    report = probe_quality({"frames_processed": 10, "pitch_view_frames": 2})

    assert report.pitches_detected == 0
    assert report.scale_stability_rate == 0.0
    assert report.command_meter_coverage == 0.0
    assert report.depth_grade == "C"
