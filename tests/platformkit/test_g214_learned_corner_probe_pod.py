"""Focused G214 scorer-contract tests."""
import numpy as np

from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame
from scripts.platformkit.tracking.g214_learned_corner_probe_pod import intersections


def test_native_support_intersections_feed_g205_scorer_unchanged():
    segments = np.array([[0.0, 10.0, 20.0, 10.0], [10.0, 0.0, 10.0, 20.0]])
    proposals = intersections(segments, width=30, height=30)
    target_rows, proposal_rows, all_four = score_frame(
        [{"audit_id": "frame", "role": "corner", "x_px": "10", "y_px": "10"}], proposals
    )

    assert proposals == [(10.0, 10.0)]
    assert target_rows[0]["available"] is True
    assert proposal_rows[0]["on_any_target"] is True
    assert all_four is True
