"""Focused regression for G134's immutable-baseline grouping proposal."""
from domains.basketball.tracking.line_calibration import ObservedSegment
from scripts.platformkit.g134_grouping_stability import stable_groups


def test_g134_keeps_baseline_group_fit_when_an_added_segment_is_present() -> None:
    baseline = [ObservedSegment((0.0, 0.0, 20.0, 0.0))]
    enlarged = [*baseline, ObservedSegment((0.0, 9.0, 20.0, 9.0))]
    baseline_group = stable_groups(baseline, baseline)[0]
    stable = stable_groups(baseline, enlarged)
    assert stable[0].segments == baseline_group.segments
    assert stable[0].anchor == baseline_group.anchor
    assert len(stable) == 2
