"""Focused checks for the G264 evidence-only driver."""

import cv2
import numpy as np

from scripts.platformkit.tracking import g264_line_conic_second_arena as subject


def test_g264_ladder_matches_the_declared_blind_gate() -> None:
    assert subject.LADDER_PX == (5, 10, 20, 40, 100)


def test_g264_survey_command_is_fixed_stride_without_input_seek() -> None:
    command = subject.remote_survey_command(685)
    assert command[:2] == ["ssh", "config.pod"]
    assert "select=not(mod(n\\,685))" in command[2]
    assert " -ss " not in command[2]


def test_g264_frame_command_is_no_seek_and_exact_indexed() -> None:
    command = subject.remote_frame_command(129465)
    assert "select=eq(n\\,129465)" in command[2]
    assert " -ss " not in command[2]


def test_g264_candidate_and_20px_board_maps_are_separated_by_20px() -> None:
    candidate = np.array(((0.04, -0.003, -18.0), (0.006, 0.052, -24.0), (0.00002, 0.0002, 1.0)))
    points = np.float32(((2.0, 3.0), (25.0, 47.0), (48.0, 80.0)))
    first = cv2.perspectiveTransform(points.reshape(1, -1, 2), np.linalg.inv(candidate))[0]
    second = cv2.perspectiveTransform(points.reshape(1, -1, 2), np.linalg.inv(subject.translated_image_to_court(candidate, 20.0)))[0]
    assert np.allclose(second - first, np.array((20.0, 0.0)), atol=1e-4)


def test_g264_ncaacourt_points_are_the_12ft_lane_contract() -> None:
    assert subject.court_points_for_sport("ncaa_basketball").tolist() == [
        [19.0, 0.0], [31.0, 0.0], [19.0, 19.0], [31.0, 19.0]
    ]
