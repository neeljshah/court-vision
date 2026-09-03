"""Focused tests for the G205 generic-proposal scoring contract."""
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame


def test_score_frame_requires_each_named_role_and_scores_each_proposal_once():
    targets = [
        {"audit_id": "frame", "role": role, "x_px": str(x), "y_px": "10"}
        for role, x in (("baseline_left", 10), ("baseline_right", 40), ("free_throw_left", 70), ("free_throw_right", 100))
    ]
    proposals = [(10.0, 10.0), (40.0, 10.0), (70.0, 10.0), (100.0, 10.0), (200.0, 200.0)]

    target_rows, proposal_rows, all_four = score_frame(targets, proposals)

    assert all_four is True
    assert sum(row["available"] for row in target_rows) == 4
    assert sum(row["on_any_target"] for row in proposal_rows) == 4
    assert proposal_rows[-1]["on_any_target"] is False
