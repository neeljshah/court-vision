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


def test_detect_cut_ignores_pitcher_motion_on_a_static_camera() -> None:
    """A body translating across a held pitch view is never a shot boundary.

    Measured 2026-09-01 (docs/evidence/tracking/baseball_cut_detector_2026-09-01.md):
    the real broadcast cut rate is 0.37-2.75 pct of processed frames and the
    correlation p05 is 0.87-0.98 against the 0.60 threshold, so the detector was
    NOT over-triggering on motion. This locks that in: the histogram is
    translation-invariant, so lowering the threshold toward the noise floor is the
    only way to break it, and that would fail here.
    """
    field = np.full((72, 128, 3), (45, 130, 45), dtype=np.uint8)
    field[55:70, :] = (78, 88, 139)  # measured infield dirt band
    previous, current = field.copy(), field.copy()
    previous[30:52, 40:52] = (200, 200, 210)  # pitcher, mid-windup
    current[30:52, 62:74] = (200, 200, 210)   # same body, 22 px down-mound

    assert not detect_cut(small_gray(previous), small_gray(current))
