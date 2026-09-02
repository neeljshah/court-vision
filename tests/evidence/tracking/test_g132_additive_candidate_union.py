"""Focused regression for G132's preregistered segment-union boundary."""
from domains.basketball.tracking.line_calibration import ObservedSegment
from scripts.platformkit.g132_additive_candidate_union import union_segments


def test_g132_keeps_baseline_and_drops_only_one_pixel_endpoint_duplicates() -> None:
    baseline = ObservedSegment((1.0, 2.0, 20.0, 2.0))
    duplicate = ObservedSegment((20.5, 2.0, 1.5, 2.0))
    distinct = ObservedSegment((1.0, 5.0, 20.0, 5.0))
    assert union_segments([baseline], [duplicate, distinct]) == [baseline, distinct]
