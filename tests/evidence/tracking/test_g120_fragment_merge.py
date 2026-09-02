"""Focused checks for G120's preregistered fragment relation."""
from domains.basketball.tracking.line_calibration import ObservedSegment
from scripts.platformkit.g120_fragment_merge import merge_collinear_fragments


def test_g120_merges_only_nearby_collinear_fragments() -> None:
    segments = [
        ObservedSegment((0.0, 0.0, 30.0, 0.0)),
        ObservedSegment((42.0, 1.0, 72.0, 1.0)),
        ObservedSegment((110.0, 0.0, 140.0, 0.0)),
        ObservedSegment((0.0, 30.0, 30.0, 45.0)),
    ]
    merged = merge_collinear_fragments(segments)
    assert len(merged) == 3
    assert max(segment.length for segment in merged) > 70.0
