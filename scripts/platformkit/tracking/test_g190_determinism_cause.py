"""Focused tests for the G190 isolated-detector comparison helper."""

from __future__ import annotations

from scripts.platformkit.tracking.g190_determinism_cause import condition_comparison


def test_condition_comparison_requires_two_records() -> None:
    try:
        condition_comparison([{"box_tensor": [[1, 2, 3, 4, 0.5, 0]]}])
    except ValueError as error:
        assert "at least two" in str(error)
    else:
        raise AssertionError("one record must not be comparable")


def test_condition_comparison_is_bit_exact_and_reports_deltas() -> None:
    same = {"box_tensor": [[1.0, 2.0, 3.0, 4.0, 0.5, 0.0]]}
    moved = {"box_tensor": [[1.25, 2.0, 3.0, 4.0, 0.625, 0.0]]}
    exact = condition_comparison([same, same, same])
    different = condition_comparison([same, moved])
    assert exact["identical_across_runs"] is True
    assert exact["largest_aligned_coordinate_abs_delta"] == 0.0
    assert exact["largest_aligned_confidence_abs_delta"] == 0.0
    assert different["identical_across_runs"] is False
    assert different["largest_aligned_coordinate_abs_delta"] == 0.25
    assert different["largest_aligned_confidence_abs_delta"] == 0.125
