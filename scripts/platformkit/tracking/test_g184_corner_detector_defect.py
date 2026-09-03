"""Focused checks for the additive G184 observer."""
from __future__ import annotations

import cv2

from scripts.platformkit.tracking.g184_corner_detector_defect import (
    evenly_spaced_positions,
    inspect_frame,
)


def test_even_positions_and_demo_parity() -> None:
    assert evenly_spaced_positions(26113, 5) == [0, 6528, 13056, 19584, 26112]
    capture = cv2.VideoCapture("docs/evidence/demo/tennis.mp4")
    frame = None
    for _ in range(150):
        ok, frame = capture.read()
        assert ok
    capture.release()
    record = inspect_frame(frame)
    assert record["accepted"] is False
    assert record["terminal_gate"] == "horizontal_roles"
    assert record["attempts"][-1]["gate"] == record["terminal_gate"]
