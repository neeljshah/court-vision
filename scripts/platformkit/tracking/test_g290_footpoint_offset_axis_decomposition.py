"""G290 reproduction and direction tests, run this file only."""
import math

import pytest

from scripts.platformkit.tracking.g290_footpoint_offset_axis_decomposition import (
    pair_offsets, reproduce, sign_test, summarize,
)
from scripts.platformkit.tracking.verifier_footpoint_analyses import (
    CROP_HALF_H, CROP_HALF_W, load_detections, load_located,
)


def test_committed_79_pair_reproduction() -> None:
    records, located = load_detections(), load_located()
    check = reproduce(records, located)
    pairs, excluded = pair_offsets(records, located)
    assert check["n"] == 112
    assert len(pairs) == check["in_box"] == 79
    assert len(excluded) == 33
    assert check["in_box_fraction"] == pytest.approx(79 / 112)
    assert check["no_player_fraction"] == pytest.approx(33 / 112)
    assert sorted(r["distance_px"] for r in pairs)[39] == pytest.approx(172.35954426720906)
    assert len({(r["source_frame"], r["detection_index"]) for r in pairs + excluded}) == 112
    assert all(math.hypot(r["dx_px"], r["dy_px"]) == r["distance_px"] for r in pairs)
    summary = summarize(pairs)
    assert summary["squared_offset_share_sum"] == pytest.approx(1)
    assert sum(c["eligible_in_box_pairs"] for c in summary["terciles"]) == 79
    altered = dict(located)
    altered.pop(next(iter(altered)))
    with pytest.raises(ValueError, match="STOP"):
        reproduce(records, altered)


def test_below_positive_dy_and_nearest_inclusive_box() -> None:
    located = {1: [(100.0, 200.0), (101.0, 200.0)]}
    records = [{"source_frame": 1, "detections": [
        {"finite": True, "track_id": 1, "foot_x_px": 101.0, "foot_y_px": 225.0},
        {"finite": True, "track_id": 2, "foot_x_px": 99.0, "foot_y_px": 180.0},
        {"finite": True, "track_id": 3,
         "foot_x_px": 101.0 + CROP_HALF_W, "foot_y_px": 200.0 + CROP_HALF_H},
        {"finite": True, "track_id": 4,
         "foot_x_px": 101.0 + CROP_HALF_W + 0.01, "foot_y_px": 200.0 + CROP_HALF_H},
        {"finite": False, "track_id": 5, "foot_x_px": 101.0, "foot_y_px": 200.0},
    ]}]
    pairs, excluded = pair_offsets(records, located)
    assert (pairs[0]["dx_px"], pairs[0]["dy_px"]) == (0.0, 25.0)
    assert pairs[0]["located_index"] == 1
    assert pairs[0]["located_feet_in_box"] == 2
    assert (pairs[1]["dx_px"], pairs[1]["dy_px"]) == (-1.0, -20.0)
    assert (pairs[2]["dx_px"], pairs[2]["dy_px"]) == (CROP_HALF_W, CROP_HALF_H)
    assert len(excluded) == 1


def test_nominal_two_sided_sign_test_keeps_zeros_separate() -> None:
    result = sign_test([1.0] * 5 + [-1.0] + [0.0])
    assert result["eligible_nonzero_pairs"] == 6
    assert result["zero"] == 1
    assert result["positive_fraction_of_all_pairs"] == 5 / 7
    assert result["nominal_two_sided_p"] == pytest.approx(0.21875)
    assert sign_test([-1.0, 1.0])["nominal_two_sided_p"] == 1.0
