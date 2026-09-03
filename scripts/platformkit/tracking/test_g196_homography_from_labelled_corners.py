"""Focused tests for the isolated G196 labelled-homography harness."""

from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    round_trip_residual,
    solve_homography,
)


def test_g196_exact_four_point_homography_round_trips_and_uses_league_widths() -> None:
    ncaa = court_points_for_sport("ncaa_basketball")
    wnba = court_points_for_sport("wnba")
    assert ncaa[1, 0] - ncaa[0, 0] == 12.0
    assert wnba[1, 0] - wnba[0, 0] == 16.0
    image_points = np.float32(((102, 311), (726, 341), (169, 104), (661, 127)))
    homography = solve_homography(image_points, ncaa)
    projected = cv2.perspectiveTransform(image_points.reshape(1, -1, 2), homography)[0]
    assert np.allclose(projected, ncaa, atol=1e-4)
    residual = round_trip_residual(image_points, homography)
    assert residual["max_px"] < 1e-3
