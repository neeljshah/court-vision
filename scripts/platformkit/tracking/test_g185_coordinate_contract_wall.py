"""Focused tests for the G185 diagnostic sampling helpers."""
from scripts.platformkit.tracking.g185_coordinate_contract_wall import (
    FrameRecord,
    even_positions,
    failure_eye_positions,
)


def test_even_positions_and_failure_eye_selection_are_inclusive() -> None:
    assert even_positions(11, 5) == [0, 2, 5, 7, 10]
    records = [FrameRecord(frame, True, frame in {1, 6}, None, "test") for frame in range(11)]
    positions, frames = failure_eye_positions(records)
    assert positions == [0, 2, 4, 6, 8]
    assert frames == [0, 3, 5, 8, 10]
