"""Focused tests for landmark-anchored baseball calibration scale.

Run: python -m pytest domains/baseball/tracking/test_scale_anchor.py -q
"""
from __future__ import annotations

from domains.baseball.tracking.scale_anchor import anchor_calibrations, anchor_metadata
from scripts.platformkit.tracking_harness import SPORTS


def _row(frame: int, scale: float, segment: str = "top-1") -> dict[str, object]:
    return {"frame": frame, "segment_id": segment, "pixels_per_foot": scale,
            "plate_centerline": 640.0}


def test_thirty_frame_segment_anchors_median_and_marks_two_outliers() -> None:
    raw = [_row(frame, 1.0) for frame in range(28)]
    raw.extend([_row(28, 5.0), _row(29, 5.0)])

    anchored, report = anchor_calibrations(raw, raw, relative_tolerance=0.10)

    assert report.segments == 1
    assert report.frames_accepted == 28
    assert report.frames_rejected == 2
    assert report.scale_p50_per_segment == {"top-1": 1.0}
    assert {row["pixels_per_foot"] for row in anchored} == {1.0}
    assert sum(not bool(row["scale_anchor_accepted"]) for row in anchored) == 2


def test_anchor_preserves_pitch_view_and_pitch_count_while_meeting_harness_bar() -> None:
    raw = []
    for segment, start in (("top-1", 0), ("bottom-1", 40)):
        for offset in range(40):
            # Alternation represents the observed discontinuity band without
            # relying on unavailable archived NPB/KBO rows in this worktree.
            raw.append(_row(start + offset, 50.0 if offset % 3 == 0 else 1.0, segment))
    metadata = {"frames_processed": 100, "pitch_view_frames": 80,
                "pitch_segments": 2, "raw_calibrations": raw,
                "calibrations": raw}

    anchored, report = anchor_metadata(metadata)

    assert report.scale_jump_p95_before >= 46.0
    assert report.scale_jump_p95_after <= SPORTS["baseball"]["jump_p95_max"]
    assert anchored["pitch_view_frames"] == metadata["pitch_view_frames"]
    assert anchored["pitch_segments"] == metadata["pitch_segments"]
    assert len(anchored["calibrations"]) == len(metadata["calibrations"])
