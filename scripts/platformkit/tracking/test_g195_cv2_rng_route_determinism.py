"""Focused tests for the G195 evidence-only route comparator."""

from __future__ import annotations

from scripts.platformkit.tracking.g195_cv2_rng_route_determinism import arm_comparison


def _record(player_rows: int, digest: str = "same") -> dict[str, object]:
    return {
        "data_dir": "/tmp/ignored",
        "player_rows": player_rows,
        "distinct_player_row_frames": 400,
        "eligible_denominator_attempted_gameplay_frames": 400,
        "survivors": {"474": [["5", "green", "1", "2", "3", "4"]], "1377": []},
        "tracking_data_csv_sha256": digest,
        "ball_tracking_csv_sha256": digest,
    }


def test_arm_comparison_requires_exactly_three_runs() -> None:
    try:
        arm_comparison([_record(1), _record(1)])
    except ValueError as error:
        assert "exactly three" in str(error)
    else:
        raise AssertionError("two records must not be comparable")


def test_arm_comparison_uses_all_metrics_and_csv_hashes() -> None:
    identical = arm_comparison([_record(10), _record(10), _record(10)])
    changed_rows = arm_comparison([_record(10), _record(11), _record(10)])
    changed_hash = arm_comparison([_record(10), _record(10, "other"), _record(10)])
    assert identical["identical_across_three_runs"] is True
    assert changed_rows["identical_across_three_runs"] is False
    assert changed_hash["identical_across_three_runs"] is False
