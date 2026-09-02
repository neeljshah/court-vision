"""Focused checks for the G111 seeded all-clip sample."""
import random

from scripts.platformkit.g111_basketball_reachability import (
    STRATA,
    _feature_count,
    seeded_stratified_indices,
)


def test_g111_samples_one_unique_frame_from_every_temporal_stratum() -> None:
    frame_count = 28_861
    indices = seeded_stratified_indices(frame_count, random.Random(1112026))

    assert len(indices) == STRATA
    assert len(set(indices)) == STRATA
    for slot, index in enumerate(indices):
        assert frame_count * slot // STRATA <= index < frame_count * (slot + 1) // STRATA


def test_g111_point_feature_count_rejects_recycled_landmarks() -> None:
    assert _feature_count("paint_near_baseline_left_corner;three_point_near_apex") == 2
    try:
        _feature_count("paint_near_baseline_left_corner;paint_near_baseline_left_corner")
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("recycled point landmark was accepted")
