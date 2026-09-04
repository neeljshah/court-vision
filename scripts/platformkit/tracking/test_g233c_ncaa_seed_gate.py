"""Focused construction checks for the fixed G233c NCAA distance-zero gate."""

from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking.g233c_ncaa_seed_gate import (
    LABEL_POINTS,
    SCALE_FACTOR,
    SOURCE_FRAME,
    SPORT,
    render_seed,
    scaled_image_points,
)


def test_g233c_uses_reindexed_frame_three_x_scale_and_ncaa_lane() -> None:
    assert SOURCE_FRAME == 46154
    assert SCALE_FACTOR == 3.0
    assert scaled_image_points().tolist() == [[114.0, 669.0], [117.0, 867.0], [822.0, 672.0], [819.0, 846.0]]
    assert LABEL_POINTS.tolist() == [[38.0, 223.0], [39.0, 289.0], [274.0, 224.0], [273.0, 282.0]]
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    rendered, homography, court_points = render_seed(image)
    assert SPORT == "ncaa_basketball"
    assert court_points.tolist() == [[19.0, 0.0], [31.0, 0.0], [19.0, 19.0], [31.0, 19.0]]
    assert rendered.shape == image.shape
    assert np.isfinite(homography).all()
