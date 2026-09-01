"""Focused tests for semantic basketball lane keypoint naming."""
from __future__ import annotations

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider


def test_provider_names_a_visible_lane_by_its_outline() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    lane = np.array(((120, 240), (120, 500), (440, 550), (440, 190)), dtype=np.int32)
    cv2.polylines(frame, [lane], True, (255, 255, 255), 6)
    result = BasketballKeypointProvider(min_edge_support=0.05).detect(frame)
    assert set(result) == {"left_paint_bl", "left_paint_tl", "left_paint_tr", "left_paint_br"}
    assert all(value[2] >= 0.05 for value in result.values())


def test_provider_rejects_small_graphics_rectangle() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(frame, (20, 20), (170, 80), (255, 255, 255), 4)
    assert BasketballKeypointProvider(min_edge_support=0.05).detect(frame) == {}
