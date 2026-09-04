"""Focused unit tests for the G259 streamed-evidence helper."""

from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g259_soccer_penalty_area_seed import (
    SOURCE,
    exact_frame_command,
    survey_command,
    _jpeg_images,
    crop_image,
)


def test_g259_survey_is_whole_clip_and_uses_five_second_stride() -> None:
    command = survey_command()
    assert SOURCE in command
    assert "fps=1/5" in command
    assert " -ss " not in command


def test_g259_exact_frame_is_zero_based_and_rejects_negative_indices() -> None:
    assert "select=eq(n\\,179249)" in exact_frame_command(179249)
    try:
        exact_frame_command(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative source frame must fail")


def test_g259_splits_complete_jpegs_and_rejects_incomplete_tail() -> None:
    one, two = b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"
    assert _jpeg_images(one + two) == [one, two]
    try:
        _jpeg_images(one + b"\xff\xd8bad")
    except ValueError:
        pass
    else:
        raise AssertionError("partial JPEG must fail")


def test_g259_crop_writes_only_a_valid_requested_region(tmp_path: Path) -> None:
    source, output = tmp_path / "source.jpg", tmp_path / "crop.jpg"
    assert cv2.imwrite(str(source), np.zeros((30, 40, 3), dtype=np.uint8))
    crop_image(source, output, (5, 6, 35, 26))
    assert cv2.imread(str(output)).shape[:2] == (20, 30)
