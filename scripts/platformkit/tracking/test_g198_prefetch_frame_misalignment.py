"""Focused tests for G198's evidence-only aggregation helpers."""

from __future__ import annotations

from scripts.platformkit.tracking.g198_prefetch_frame_misalignment import (
    arm_comparison,
    control_comparison,
    summarize_observation,
)


def _record(cache_count: int, self_count: int, digest: str = "same") -> dict[str, object]:
    return {
        "data_dir": "/tmp/ignored",
        "player_rows": 10,
        "distinct_player_row_frames": 4,
        "eligible_denominator_attempted_gameplay_frames": 4,
        "survivors": {"474": [], "1377": []},
        "tracking_data_csv_sha256": digest,
        "ball_tracking_csv_sha256": digest,
        "observation": {
            "cache_served_frames": cache_count,
            "self_inferred_frames": self_count,
            "peek_return_count_histogram": {"7": 1},
            "offset_histogram_served_minus_processed": {"1": cache_count},
        },
    }


def test_summarize_observation_reports_whole_run_histograms() -> None:
    summary = summarize_observation([
        {"processed_frame_idx": 10, "inference_mode": "cache", "served_frame_idx": 11},
        {"processed_frame_idx": 11, "inference_mode": "cache", "served_frame_idx": 13},
        {"processed_frame_idx": 12, "inference_mode": "self_inferred", "served_frame_idx": 12},
    ], [7, 0, 7])
    assert summary["cache_served_frames"] == 2
    assert summary["self_inferred_frames"] == 1
    assert summary["offset_histogram_served_minus_processed"] == {"1": 1, "2": 1}
    assert summary["peek_return_count_histogram"] == {"0": 1, "7": 2}


def test_three_run_comparators_use_cache_counts_and_full_records() -> None:
    equal = [_record(9, 1), _record(9, 1), _record(9, 1)]
    changed_counts = [_record(9, 1), _record(8, 2), _record(9, 1)]
    changed_hash = [_record(9, 1), _record(9, 1, "other"), _record(9, 1)]
    assert control_comparison(equal)["cache_served_counts_identical_across_three_runs"] is True
    assert control_comparison(changed_counts)["cache_served_counts_identical_across_three_runs"] is False
    assert arm_comparison(equal)["identical_across_three_runs"] is True
    assert arm_comparison(changed_counts)["identical_across_three_runs"] is True
    assert arm_comparison(changed_hash)["identical_across_three_runs"] is False
