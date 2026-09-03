"""Focused synthetic tests for the G182 non-production measurement harness."""
from __future__ import annotations

from scripts.platformkit.tracking.g182_calibration_funnel import (
    FunnelRecorder,
    _stage_summary,
    evenly_spaced_frames,
)


def test_stage_denominators_and_even_sampling() -> None:
    recorder = FunnelRecorder()
    for frame in range(10):
        recorder.begin_frame(frame)
        record = recorder.current()
        record.corner_detection = True
        record.enough_corners = frame < 5
        record.candidate_homography = frame < 5
        record.homography = frame < 4
        record.lock_drift_pass = frame < 3
        record.emitted = frame < 2
    assert recorder.count("decoded") == 10
    assert recorder.count("corner_detection") == 10
    assert recorder.count("enough_corners") == 5
    summary, loss_stage, loss_frames = _stage_summary(recorder)
    assert summary["lock_drift_pass"]["eligible_denominator"] == 10
    assert summary["emitted"]["eligible_denominator"] == 3
    assert loss_stage == "enough_corners"
    assert loss_frames == [5, 6, 7, 8, 9]
    assert evenly_spaced_frames([10, 20, 30, 40, 50]) == [10, 20, 30, 40, 50]
