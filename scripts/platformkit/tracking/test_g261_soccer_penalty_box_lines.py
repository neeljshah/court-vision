"""Focused tests for the G261 streamed candidate and line-fit helper."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.platformkit.tracking.g261_soccer_penalty_box_lines import (
    SOURCE,
    crop_image,
    jpeg_images,
    line_angle_degrees,
    line_homography,
    native_frames_command,
    split_native_stream,
    vanishing_point,
)


def test_native_frames_command_is_no_seek_and_ordered() -> None:
    command = native_frames_command([0, 150, 300])
    assert SOURCE in command
    assert "eq(n\\,0)+eq(n\\,150)+eq(n\\,300)" in command
    assert " -ss " not in command
    with pytest.raises(ValueError):
        native_frames_command([150, 0])


def test_jpeg_images_rejects_an_incomplete_tail() -> None:
    one, two = b"\xff\xd8one\xff\xd9", b"\xff\xd8two\xff\xd9"
    assert jpeg_images(one + two) == [one, two]
    with pytest.raises(ValueError):
        jpeg_images(one + b"\xff\xd8partial")


def test_split_native_stream_names_each_requested_frame(tmp_path: Path) -> None:
    stream = tmp_path / "stream.mjpg"
    stream.write_bytes(b"\xff\xd8one\xff\xd9\xff\xd8two\xff\xd9")
    paths = split_native_stream(stream, [150, 300], tmp_path / "frames")
    assert [path.name for path in paths] == ["frame_000150.jpg", "frame_000300.jpg"]


def test_crop_image_writes_only_a_valid_requested_region(tmp_path: Path) -> None:
    source, output = tmp_path / "source.jpg", tmp_path / "crop.jpg"
    assert cv2.imwrite(str(source), np.zeros((30, 40, 3), dtype=np.uint8))
    crop_image(source, output, (5, 6, 35, 26))
    assert cv2.imread(str(output)).shape[:2] == (20, 30)


def test_four_line_fit_and_degeneracy_helpers() -> None:
    world = ([0, 1, 0], [0, 1, -16.5], [1, 0, 20.16], [1, 0, -20.16])
    image = ([0, 1, 0], [0, 1, -33], [1, 0, 20.16], [1, 0, -20.16])
    homography, condition = line_homography(world, image)
    assert np.allclose(homography, np.diag([1, 2, 1]), atol=1e-8)
    assert np.isfinite(condition)
    assert line_angle_degrees(image[0], image[2]) == pytest.approx(90.0)
    assert vanishing_point(image[0], image[1])[2] == pytest.approx(0.0)
