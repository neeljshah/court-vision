"""Focused coverage for basketball gate-funnel accounting."""
from __future__ import annotations

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider
from scripts.platformkit.basketball_gate_funnel import inspect_frame


def test_funnel_records_named_paint_after_all_provider_gates() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    lane = np.array(((120, 240), (120, 500), (440, 550), (440, 190)), dtype=np.int32)
    cv2.polylines(frame, [lane], True, (255, 255, 255), 6)
    result = inspect_frame(frame, BasketballKeypointProvider(min_edge_support=0.05))
    assert result.outline_quads >= 1
    assert result.physical_quads >= 1
    assert result.supported_quads >= 1
    assert result.first_failure == "4_paint_named"
    assert set(result.landmarks) == {"left_paint_bl", "left_paint_tl", "left_paint_tr", "left_paint_br"}


def test_funnel_separates_outline_failure_from_graphics() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(frame, (20, 20), (170, 80), (255, 255, 255), 4)
    result = inspect_frame(frame, BasketballKeypointProvider(min_edge_support=0.05))
    assert result.physical_quads == 0
    assert result.first_failure in {"1_no_four_corner_outline", "2_no_physically_large_lane"}
