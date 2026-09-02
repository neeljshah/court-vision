"""Focused G75 tests for image-only paint role assignment."""

import pytest

from domains.basketball.tracking.line_calibration import (
    ObservedSegment,
    assign_paint_roles,
    candidate_line_group_details,
)


def test_assign_paint_roles_uses_termination_extent_and_declared_side() -> None:
    candidates = candidate_line_group_details([
        ObservedSegment((0, 0, 200, 0)),       # baseline continues beyond lanes
        ObservedSegment((50, 100, 150, 100)),  # free throw terminates at lanes
        ObservedSegment((50, 0, 50, 100)),
        ObservedSegment((150, 0, 150, 100)),
    ], angle_deg=1.0, offset_px=4.0)

    roles = assign_paint_roles(candidates, "ncaa_legacy", "left")

    assert roles is not None
    assert roles["baseline"].length > roles["free_throw"].length
    assert roles["lane_low"].anchor[0] < roles["lane_high"].anchor[0]
    with pytest.raises(ValueError, match="caller-declared league"):
        assign_paint_roles(candidates, "guessed", "left")
