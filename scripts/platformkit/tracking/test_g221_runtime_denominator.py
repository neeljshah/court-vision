"""Focused unit tests for G221 measurement-only helper rules."""

from scripts.platformkit.tracking.g221_runtime_denominator import (
    BASE_STRIDE,
    FRAME_STRIDE_THRESHOLD,
    implied_stride,
    selected_count_source,
)


def test_stride_and_production_source_selection_follow_the_unchanged_rule() -> None:
    assert implied_stride(FRAME_STRIDE_THRESHOLD) == 1
    assert implied_stride(FRAME_STRIDE_THRESHOLD + 1) == BASE_STRIDE
    assert selected_count_source(12, 99) == "cv2"
    assert selected_count_source(0, 99) == "pyav"
    assert selected_count_source(0, 0) == "file_size"
    assert selected_count_source(0, None) == "file_size"
