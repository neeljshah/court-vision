"""Focused geometry checks for G210's label-free court-model fitter."""

import cv2
import numpy as np

from scripts.platformkit.tracking.g210_court_model_fit_to_lines import _court_lines, solve_line_pairs


def test_line_pair_solver_recovers_a_synthetic_league_specific_homography():
    sport = "ncaa_basketball"
    expected = np.array(((0.013, -0.002, -4.0), (0.001, 0.014, -3.0), (0.000002, -0.000001, 1.0)))
    model = _court_lines(sport)
    actual = solve_line_pairs(
        tuple(expected.T @ model[name] for name in ("near_baseline", "near_free_throw")),
        tuple(expected.T @ model[name] for name in ("lane_left", "lane_right")),
        tuple(model[name] for name in ("near_baseline", "near_free_throw")),
        tuple(model[name] for name in ("lane_left", "lane_right")),
    )

    assert actual is not None
    image_points = np.float32(((200, 300), (500, 320), (220, 600), (520, 610))).reshape(1, -1, 2)
    assert np.allclose(cv2.perspectiveTransform(image_points, actual), cv2.perspectiveTransform(image_points, expected), atol=1e-3)
    assert _court_lines("wnba")["lane_right"][2] == -33.0
