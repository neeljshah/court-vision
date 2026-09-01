"""Focused tests for baseball broadcast scene-cut detection.

Run: python -m pytest domains/baseball/tracking/test_segmenter.py -q
"""
from __future__ import annotations

import numpy as np

from domains.baseball.tracking.segmenter import detect_cut, small_gray


def test_detect_cut_rejects_a_hard_broadcast_view_change() -> None:
    pitch = np.full((72, 128, 3), (45, 130, 45), dtype=np.uint8)
    replay = np.full((72, 128, 3), (180, 40, 20), dtype=np.uint8)

    assert detect_cut(small_gray(pitch), small_gray(replay))


def test_detect_cut_accepts_small_within_view_luminance_change() -> None:
    previous = np.full((72, 128, 3), (45, 130, 45), dtype=np.uint8)
    current = previous.copy()
    current[20:28, 50:78] = (50, 135, 50)

    assert not detect_cut(small_gray(previous), small_gray(current))
