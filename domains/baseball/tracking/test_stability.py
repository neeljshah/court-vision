"""Tests for pitch-view scale stabilization.

Run: python -m pytest domains/baseball/tracking/test_stability.py -q
"""
from __future__ import annotations

import numpy as np

from domains.baseball.tracking.stability import ScaleStabilizer, stabilize_rows


def test_jittered_scale_is_smoothed_by_at_least_five_times() -> None:
    jittered = [4.0 + (-1.0 if index % 2 else 1.0) * 0.45 for index in range(80)]
    stabilizer = ScaleStabilizer()
    smoothed = [stabilizer.update(scale, 640.0)[0] for scale in jittered]
    assert np.var(smoothed[10:]) <= np.var(jittered[10:]) / 5.0


def test_reset_freezes_state_within_a_segment_and_clears_on_boundary() -> None:
    stabilizer = ScaleStabilizer()
    stabilizer.reset("top-1")
    first = stabilizer.update(4.0, 640.0)
    stabilizer.reset("top-1")
    second = stabilizer.update(6.0, 660.0)
    assert first != second
    assert second[0] < 6.0
    stabilizer.reset("bottom-1")
    assert stabilizer.pixels_per_foot is None
    assert stabilizer.update(6.0, 660.0) == (6.0, 660.0)


def test_stabilize_rows_drops_unstable_warmup_and_jitter() -> None:
    rows = [
        {"frame": index, "segment_id": "top-1", "pixels_per_foot": 4.0, "plate_centerline": 640.0}
        for index in range(12)
    ]
    rows.extend(
        {"frame": index, "segment_id": "bottom-1", "pixels_per_foot": 4.0 + (-1.0) ** index, "plate_centerline": 640.0}
        for index in range(12, 22)
    )
    emitted = stabilize_rows(rows, ScaleStabilizer())
    assert [row["frame"] for row in emitted] == [9, 10, 11]
