"""G80: insufficient-data reports cannot pass a quality gate."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.coordinate_provenance import METRIC_LOCAL_CALIBRATION
from scripts.platformkit.tracking_harness import (
    MIN_FRAMES_FOR_METRICS,
    _N_DEPENDENT_METRIC_FIELDS,
    evaluate,
)


def _oob_after_frame_ten(n_frames: int) -> pd.DataFrame:
    rows = []
    for frame in range(n_frames):
        for track_id in range(10):
            out_of_bounds = 10 <= frame < 26 and track_id < 6
            rows.append({
                "frame": frame, "track_id": track_id, "cls": "player",
                "x": 100.0 + frame if out_of_bounds else 10.0 + track_id + frame * 0.5,
                "y": 5.0 + frame * 0.5, "coordinate_space": "court_feet",
            })
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet"})
    return pd.DataFrame(rows)


def _metric_local_tiny_table() -> pd.DataFrame:
    rows = []
    for frame in range(3):
        for track_id in range(2):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 20.0 + frame, "y": 10.0, "coordinate_space": "metric_local",
                         "calibration": METRIC_LOCAL_CALIBRATION})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 39.0,
                     "y": 20.0, "coordinate_space": "metric_local",
                     "calibration": METRIC_LOCAL_CALIBRATION})
    return pd.DataFrame(rows)


def test_g80_insufficient_data_is_never_a_pass() -> None:
    for n_frames in (3, 10):
        report = evaluate(_oob_after_frame_ten(n_frames), "basketball")
        assert report.insufficient_data is True
        assert report.passed is False
        assert report.verdict == "INSUFFICIENT_DATA"
        assert report.failures == ["insufficient data: {} frames < {}".format(
            n_frames, MIN_FRAMES_FOR_METRICS)]
        assert all(getattr(report, field) is None for field in _N_DEPENDENT_METRIC_FIELDS)

    adequate = evaluate(_oob_after_frame_ten(40), "basketball")
    assert adequate.insufficient_data is False
    assert adequate.passed is False and adequate.verdict == "FAIL"
    assert adequate.oob_pct == 0.24
    assert adequate.failures == ["oob 0.24 > 0.05"]

    metric_local = evaluate(_metric_local_tiny_table(), "baseball")
    assert metric_local.insufficient_data is True
    assert metric_local.passed is False
    assert metric_local.verdict == "INSUFFICIENT_DATA"
    assert metric_local.failures == ["insufficient data: 3 frames < 30"]
