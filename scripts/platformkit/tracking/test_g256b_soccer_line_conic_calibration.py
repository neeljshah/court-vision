"""Focused tests for the G256b pod-stream and evidence-crop utility."""

from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g256b_soccer_line_conic_calibration import (
    SOURCE,
    exact_frame_command,
    crop_image,
    survey_command,
)


def test_g256b_survey_is_whole_clip_and_no_seek() -> None:
    command = survey_command(60)
    assert SOURCE in command
    assert "fps=1/60" in command
    assert " -ss " not in command


def test_g256b_exact_frame_uses_zero_based_select_without_input_seek() -> None:
    command = exact_frame_command(179249)
    assert "select=eq(n\\,179249)" in command
    assert " -ss " not in command


def test_g256b_rejects_invalid_selection_values() -> None:
    for callable_, value in ((survey_command, 0), (exact_frame_command, -1)):
        try:
            callable_(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid selection must fail")


def test_g256b_crop_writes_only_a_valid_requested_region(tmp_path: Path) -> None:
    source, output = tmp_path / "source.jpg", tmp_path / "crop.jpg"
    assert cv2.imwrite(str(source), np.zeros((30, 40, 3), dtype=np.uint8))
    crop_image(source, output, 5, 6, 35, 26)
    assert cv2.imread(str(output)).shape[:2] == (20, 30)
