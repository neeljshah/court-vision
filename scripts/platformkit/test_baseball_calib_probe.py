"""Test the baseball landmark census arithmetic that carries the fail-closed verdict.

Run: python -m pytest scripts/platformkit/test_baseball_calib_probe.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.baseball_calib_probe import (
    BASE_LATERAL_OFFSET_FEET, landmark_census,
)

GRASS = (45, 130, 45)
DIRT = (70, 76, 120)


def _write_clip(path, mound_half_width: int, frames: int = 6) -> None:
    image = np.full((720, 1280, 3), GRASS, dtype=np.uint8)
    cv2.rectangle(image, (0, 300), (1280, 450), DIRT, -1)
    cv2.ellipse(image, (640, 604), (mound_half_width, 55), 0, 0, 360, DIRT, -1)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 10.0, (1280, 720))
    for _ in range(frames):
        writer.write(image)
    writer.release()


def test_broadcast_framing_cannot_contain_first_and_third_base(tmp_path) -> None:
    """A 912 px mound chord is 18 ft, so 1280 px is ~25 ft -- 1B/3B are 63.64 ft out."""
    clip = tmp_path / "tight.avi"
    _write_clip(clip, mound_half_width=456)

    census = landmark_census(str(clip), 0, 5, 1)

    assert census["pitch_view_frames"] > 0
    assert census["lateral_px_per_foot_p50"] > 40.0
    assert census["lateral_fov_feet_p50"] < 2 * BASE_LATERAL_OFFSET_FEET
    assert census["frames_that_could_contain_1b_and_3b"] == 0


def test_a_wide_enough_framing_is_counted(tmp_path) -> None:
    """The census must be able to falsify itself, or its zero means nothing.

    A 160 px chord is 18 ft, so the frame spans 144 ft and both 1B and 3B fit.
    """
    clip = tmp_path / "wide.avi"
    _write_clip(clip, mound_half_width=80)

    census = landmark_census(str(clip), 0, 5, 1)

    assert census["pitch_view_frames"] > 0
    assert census["lateral_fov_feet_p50"] > 2 * BASE_LATERAL_OFFSET_FEET
    assert census["frames_that_could_contain_1b_and_3b"] == census["pitch_view_frames"]
