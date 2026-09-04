"""Focused deterministic checks for G222's direct-reference metric."""

import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import court_points_for_sport
from scripts.platformkit.tracking.g222_direct_to_seed_propagation import _direct_reference_drift


def test_direct_reference_is_zero_under_the_unchanged_g215_paint_drift_measure():
    direct_image_to_court = np.array(((0.1, 0.0, -2.0), (0.0, 0.1, 4.0), (0.0, 0.0, 1.0)))
    median, maximum = _direct_reference_drift(direct_image_to_court, court_points_for_sport("wnba"))

    assert median == 0.0
    assert maximum == 0.0
