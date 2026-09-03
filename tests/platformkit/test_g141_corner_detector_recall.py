"""Per-file tests for the additive G141 corner-recall measurement module."""
from scripts.platformkit.g141_corner_detector_recall import score_targets, wilson_interval


def test_scores_unique_targets_and_all_proposals_without_recycling() -> None:
    targets = [
        {"audit_id": "frame-a", "clip": "clip", "source_frame": "1", "role": "left", "x_px": "0", "y_px": "0"},
        {"audit_id": "frame-a", "clip": "clip", "source_frame": "1", "role": "right", "x_px": "40", "y_px": "0"},
    ]
    target_scores, proposal_scores, summary = score_targets(
        targets, {"frame-a": [(0, 0), (100, 100)]}
    )
    assert [row["available"] for row in target_scores] == [True, False]
    assert [row["on_any_target"] for row in proposal_scores] == [True, False]
    assert summary["available_targets"] == 1
    assert summary["targets"] == 2
    assert summary["matched_proposals"] == 1
    assert summary["proposals"] == 2
    assert summary["precision"] == 0.5
    lower, upper = wilson_interval(1, 2)
    assert 0.0 < lower < 0.5 < upper < 1.0
