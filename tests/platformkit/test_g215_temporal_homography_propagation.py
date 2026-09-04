"""Focused unit checks for G215's deterministic homography composition helpers."""

import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import court_points_for_sport
from scripts.platformkit.tracking.g215_temporal_homography_propagation import (
    compose_image_to_court,
    project_court_points,
)


def test_composition_projects_the_same_court_points_after_a_pixel_translation():
    seed_image_to_court = np.array(((0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.0, 0.0, 1.0)))
    seed_to_current = np.array(((1.0, 0.0, 25.0), (0.0, 1.0, -10.0), (0.0, 0.0, 1.0)))
    court = court_points_for_sport("wnba")

    seed_projection = project_court_points(seed_image_to_court, court)
    current_projection = project_court_points(
        compose_image_to_court(seed_image_to_court, seed_to_current), court
    )

    np.testing.assert_allclose(current_projection - seed_projection, ((25.0, -10.0),) * 4)
