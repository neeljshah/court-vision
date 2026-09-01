"""Tests for soccer S1 packet helpers."""
from scripts.platformkit.soccer_s1_adjudication_packet import _valid_detection_count, select_spread_indices


def test_select_spread_indices_covers_candidate_timeline() -> None:
    assert select_spread_indices([10, 20, 30, 40, 50], 3) == [10, 30, 50]


def test_valid_detection_count_discards_degenerate_boxes() -> None:
    boxes = [[0, 0, 10, 10], [4, 5, 4, 8], [3, 5, 9, 5], [2, 3, 8, 12, 0.9]]
    assert _valid_detection_count(boxes) == 2
