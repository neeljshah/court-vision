"""Regression tests for G197's attempted-frame coverage denominator."""
import pandas as pd

from scripts.platformkit.tracking_harness import evaluate


def _table(emitted_frames: int = 50, attempted_frames: int | None = 100) -> pd.DataFrame:
    rows = []
    for frame in range(emitted_frames):
        for track_id in range(6):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 10.0 + track_id, "y": 25.0, "coordinate_space": "court_feet"})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47.0,
                     "y": 25.0, "coordinate_space": "court_feet"})
    return pd.DataFrame(rows), attempted_frames


def test_emitted_frame_metrics_remain_legacy_but_gate_uses_attempted_frames():
    table, attempted = _table()
    report = evaluate(table, "basketball", attempted_frames=attempted)

    assert report.coverage_pct == 1.0
    assert report.ball_valid_pct == 1.0
    assert report.coverage_pct_denominator == "emitted_frames"
    assert report.ball_valid_pct_denominator == "emitted_frames"
    assert report.attempted_frames == 100
    assert report.coverage_attempted_frames_pct == 0.5
    assert report.ball_valid_attempted_frames_pct == 0.5
    assert report.coverage_attempted_frames_pct_denominator == "attempted_frames"
    assert report.ball_valid_attempted_frames_pct_denominator == "attempted_frames"
    assert not report.passed
    assert any(failure.startswith("coverage_attempted_frames") for failure in report.failures)


def test_missing_attempted_count_is_never_replaced_with_emitted_frame_count():
    table, _ = _table()
    report = evaluate(table, "basketball")

    assert report.coverage_pct == 1.0
    assert report.coverage_attempted_frames_pct is None
    assert report.ball_valid_attempted_frames_pct is None
    assert report.coverage_attempted_frames_pct_denominator == "unavailable"
    assert not report.passed
    assert "attempted_frames unavailable" in report.failures
