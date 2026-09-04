import numpy as np

from scripts.platformkit.tracking.g270_implausibility_conditioned_on_position import (
    _horizon_band,
    _partition,
    horizon_distance_px,
    local_scale_at_foot,
)


def test_horizon_distance_and_local_scale_follow_the_image_homography():
    homography = np.array(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 1.0, -10.0)))
    near = {"foot_x_px": 3.0, "foot_y_px": 9.0}
    far = {"foot_x_px": 3.0, "foot_y_px": 20.0}
    assert horizon_distance_px(homography, near) == 1.0
    assert horizon_distance_px(homography, far) == 10.0
    assert local_scale_at_foot(homography, near)[1] > local_scale_at_foot(homography, far)[1]


def test_position_partitions_and_horizon_bands_are_exhaustive():
    assert _partition({"prior_inside_court": True, "current_inside_court": True}) == "both_endpoints_inside_court"
    assert _partition({"prior_inside_court": True, "current_inside_court": False}) == "one_endpoint_inside_court"
    assert _partition({"prior_inside_court": False, "current_inside_court": False}) == "both_endpoints_outside_court"
    assert _horizon_band(1199.9) == "0_to_1200_px"
    assert _horizon_band(1200.0) == "1200_to_1400_px"
    assert _horizon_band(1800.0) == "1800_px_or_more"
