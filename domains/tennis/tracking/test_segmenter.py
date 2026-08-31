"""Tests for broadcast scene-cut detection.

Run: python -m pytest domains/tennis/tracking/test_segmenter.py -q
"""
from __future__ import annotations

import numpy as np

from domains.tennis.tracking.segmenter import detect_cut, small_gray


def test_detect_cut_uses_downsampled_histogram_correlation() -> None:
    first = np.full((720, 1280, 3), (20, 40, 60), dtype=np.uint8)
    same_shot = first.copy()
    same_shot[250:300, 400:500] = (30, 50, 70)
    second = np.full((720, 1280, 3), (220, 200, 180), dtype=np.uint8)

    first_small = small_gray(first)
    assert first_small.shape == (36, 64)
    assert not detect_cut(first_small, small_gray(same_shot))
    assert detect_cut(first_small, small_gray(second))
