"""Focused tests for normalized tracking-frame liveness metrics."""
import pandas as pd

from scripts.platformkit.liveness_metrics import compute_liveness_metrics, liveness_failures


def _frame(moving: bool) -> pd.DataFrame:
    rows = []
    for frame in range(20):
        for track_id in range(2):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + (frame * 0.1 if moving else 0.0),
                         "y": 20.0})
    return pd.DataFrame(rows)


def test_frozen_tracks_are_detected():
    metrics = compute_liveness_metrics(_frame(moving=False), "basketball")
    assert metrics.zero_step_share == 1.0
    assert metrics.median_step_distance == 0.0
    assert metrics.stationary_track_share == 1.0
    assert metrics.verdict == "FROZEN"


def test_moving_tracks_are_live():
    metrics = compute_liveness_metrics(_frame(moving=True), "basketball")
    assert metrics.zero_step_share == 0.0
    assert round(metrics.median_step_distance, 6) == 0.1
    assert metrics.distinct_position_ratio > 0.5
    assert metrics.stationary_track_share == 0.0
    assert metrics.verdict == "LIVE"


def test_step_held_tracks_are_detected():
    rows = []
    for frame in range(100):
        for track_id in range(2):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + (frame // 20), "y": 20.0})
    metrics = compute_liveness_metrics(pd.DataFrame(rows), "basketball")
    assert metrics.zero_step_share > 0.883869
    assert metrics.distinct_position_ratio < 0.108915
    assert metrics.verdict == "SUSPECT"
    assert any("zero_step_share" in failure for failure in liveness_failures(metrics, "basketball"))


def test_teleporting_tracks_are_detected():
    rows = []
    for frame in range(20):
        for track_id in range(2):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id + frame * 20.0, "y": 20.0})
    metrics = compute_liveness_metrics(pd.DataFrame(rows), "basketball")
    assert metrics.median_step_distance > 8.408436
    assert metrics.verdict == "SUSPECT"
    assert any("median_step_distance" in failure
               for failure in liveness_failures(metrics, "basketball"))
