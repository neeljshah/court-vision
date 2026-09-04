import pytest

from scripts.platformkit.tracking.g205_zero_shot_corner_probe import TOLERANCE_PX
from scripts.platformkit.tracking.g217_oracle_error_decomposition import true_line_fit, true_paint_lines


def test_true_paint_lines_follow_the_prescribed_corner_pairs():
    targets = [
        {"role": "paint_near_baseline_left_corner", "x_px": "0", "y_px": "0"},
        {"role": "paint_near_baseline_right_corner", "x_px": "10", "y_px": "0"},
        {"role": "paint_near_free_throw_left_corner", "x_px": "0", "y_px": "20"},
        {"role": "paint_near_free_throw_right_corner", "x_px": "10", "y_px": "20"},
    ]
    lines = true_paint_lines(targets)
    assert set(lines) == {"near_baseline", "near_free_throw", "lane_left", "lane_right"}
    assert abs(float(lines["near_baseline"] @ (0, 0, 1))) < 1e-12
    assert abs(float(lines["near_free_throw"] @ (0, 20, 1))) < 1e-12
    assert abs(float(lines["lane_left"] @ (0, 20, 1))) < 1e-12
    assert abs(float(lines["lane_right"] @ (10, 0, 1))) < 1e-12
    with pytest.raises(ValueError, match="four G140"):
        true_paint_lines(targets[:-1])
    assert TOLERANCE_PX == 12.0
    assert true_line_fit(targets, "ncaa_basketball") is not None
