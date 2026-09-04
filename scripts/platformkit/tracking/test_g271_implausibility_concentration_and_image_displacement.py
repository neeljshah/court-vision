from scripts.platformkit.tracking.g271_implausibility_concentration_and_image_displacement import (
    _movement_class,
    _per_track,
    _spearman,
)


def test_descriptive_movement_split_keeps_boundaries_indeterminate():
    assert _movement_class(16.9, 40.1) == "projection_amplified"
    assert _movement_class(17.0, 40.1) == "indeterminate"
    assert _movement_class(83.0, 40.1) == "indeterminate"
    assert _movement_class(83.1, 40.1) == "box_jump"
    assert _movement_class(1000.0, 40.0) == "plausible"


def test_per_track_keeps_zero_impossible_ids_and_rank_correlation_direction():
    steps = [
        {"track_id": 1, "strictly_over_40_ft_per_s": True},
        {"track_id": 1, "strictly_over_40_ft_per_s": False},
        {"track_id": 2, "strictly_over_40_ft_per_s": False},
    ]
    rows = _per_track(steps, [1, 2, 3])
    assert rows[2]["on_court_same_id_steps"] == 0
    assert rows[2]["on_court_impossible_fraction"] is None
    assert _spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == -1.0
