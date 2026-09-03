"""Focused tests for the G188 evidence helper."""

from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking.g188_player_selection_defect import (
    draw_dual_boxes,
    evenly_spaced_frames,
)


def test_even_positions_include_declared_endpoints() -> None:
    assert evenly_spaced_frames(range(180, 1378, 3), 20) == list(range(180, 1378, 63))


def test_dual_render_keeps_raw_and_survivor_colours_distinct() -> None:
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    raw = [{"x1": 4.0, "y1": 8.0, "x2": 30.0, "y2": 44.0, "confidence": 0.9, "class": "person"}]
    survivor = [{"x1": 42.0, "y1": 8.0, "x2": 70.0, "y2": 44.0, "confidence": 1.0, "class": "person"}]
    rendered = draw_dual_boxes(image, raw, survivor, "f1")
    assert tuple(rendered[8, 4]) == (0, 0, 255)
    assert tuple(rendered[8, 42]) == (0, 255, 0)
