"""Synthetic tests for the catcher glove-target command meter.

Run: python -m pytest domains/baseball/tracking/test_command_meter.py -q
"""
from __future__ import annotations

from typing import Optional, Sequence

import cv2
import numpy as np
import pytest

from domains.baseball.tracking.command_meter import (
    MotionStableDetector,
    SERIES_SCHEMA,
    command_series,
    glove_target,
    pre_pitch_window,
    target_vs_actual,
)


HEIGHT, WIDTH = 240, 320
GLOVE = (160, 180)
DECOY = (110, 200)


def _frame(blobs: Sequence[tuple[int, int]] = (GLOVE,), background: int = 120) -> np.ndarray:
    image = np.full((HEIGHT, WIDTH, 3), background, dtype=np.uint8)
    for x, y in blobs:
        cv2.rectangle(image, (x - 5, y - 5), (x + 4, y + 4), (30, 30, 30), -1)
    return image


def test_placed_glove_blob_is_found_within_tolerance() -> None:
    frames = [_frame() for _ in range(5)]
    detection = glove_target(frames, MotionStableDetector())

    assert detection is not None
    px, py, confidence = detection
    assert abs(px - GLOVE[0]) <= 2.0
    assert abs(py - GLOVE[1]) <= 2.0
    assert confidence > 0.5


def test_detector_stays_quiet_until_the_buffer_fills() -> None:
    detector = MotionStableDetector()
    frames = [_frame() for _ in range(3)]

    assert detector.detect(frames[0]) is None
    assert detector.detect(frames[1]) is None
    assert detector.detect(frames[2]) is not None


def test_ambiguous_two_blob_frame_emits_nothing() -> None:
    frames = [_frame((GLOVE, DECOY)) for _ in range(5)]

    assert glove_target(frames, MotionStableDetector()) is None


def test_empty_region_emits_nothing() -> None:
    frames = [_frame(blobs=()) for _ in range(5)]

    assert glove_target(frames, MotionStableDetector()) is None


def test_pre_pitch_window_ends_at_the_motion_spike() -> None:
    still = [_frame() for _ in range(5)]
    moving = [_frame(background=120 + 40 * step) for step in range(1, 4)]

    assert pre_pitch_window(still + moving) == [0, 1, 2, 3, 4]
    assert pre_pitch_window(still) == [0, 1, 2, 3, 4]


def test_release_motion_hides_a_late_glove() -> None:
    """Only pre-pitch frames are scanned, so a post-release blob never counts."""
    frames = [_frame(blobs=()) for _ in range(3)]
    frames += [_frame(background=200) for _ in range(2)]
    frames += [_frame() for _ in range(5)]

    assert glove_target(frames, MotionStableDetector()) is None


def test_miss_distance_math_is_exact() -> None:
    miss = target_vs_actual((100.0, 200.0), (130.0, 160.0), 10.0)

    assert miss.horizontal_ft == pytest.approx(3.0)
    assert miss.vertical_ft == pytest.approx(4.0)
    assert miss.miss_ft == pytest.approx(5.0)


def test_miss_signs_follow_the_adapter_convention() -> None:
    low_and_left = target_vs_actual((100.0, 200.0), (80.0, 210.0), 4.0)

    assert low_and_left.horizontal_ft == pytest.approx(-5.0)
    assert low_and_left.vertical_ft == pytest.approx(-2.5)


def test_zero_scale_is_rejected() -> None:
    with pytest.raises(ValueError):
        target_vs_actual((0.0, 0.0), (1.0, 1.0), 0.0)


def _event(inning: int, miss: Optional[float]) -> dict[str, object]:
    if miss is None:
        return {"inning": inning, "target_px": None, "crossing_px": None,
                "scale_px_per_ft": 1.0}
    return {
        "inning": inning,
        "target_px": (0.0, 0.0),
        "crossing_px": (miss, 0.0),
        "scale_px_per_ft": 1.0,
    }


def test_rolling_per_inning_medians_reset_each_inning() -> None:
    events = [
        _event(1, 2.0), _event(1, 4.0), _event(1, 9.0),
        _event(2, 1.0), _event(2, None), _event(2, 5.0),
    ]
    series = command_series(events)

    assert list(series.columns) == list(SERIES_SCHEMA)
    assert list(series["pitch"]) == [0, 1, 2, 3, 5]
    assert list(series["miss_ft"]) == pytest.approx([2.0, 4.0, 9.0, 1.0, 5.0])
    assert list(series["inning_median_ft"]) == pytest.approx([2.0, 3.0, 4.0, 1.0, 3.0])


def test_command_series_on_no_usable_events_is_empty() -> None:
    series = command_series([_event(1, None), {"inning": 1}])

    assert series.empty
    assert list(series.columns) == list(SERIES_SCHEMA)
