"""Per-file test for verifier_footpoint_analyses: the step definition and the crop box."""
from scripts.platformkit.tracking.verifier_footpoint_analyses import (
    CROP_HALF_H,
    CROP_HALF_W,
    footpoint_player_split,
    implausible_rate,
    steps,
)


def _rec(frame, dets):
    return {"source_frame": frame, "detections": dets}


def _det(tid, x, y, cx, cy):
    return {
        "track_id": tid,
        "foot_x_px": x,
        "foot_y_px": y,
        "court_x_ft": cx,
        "court_y_ft": cy,
        "finite": True,
    }


def test_steps_use_consecutive_observations_not_unit_frame_gaps():
    # Frames 1 and 4: a 3-frame gap is still ONE step, and the speed is divided by 3.
    # Requiring gap == 1 is what produced the false 0.111966 non-reproduction.
    records = [_rec(1, [_det(7, 0, 0, 0.0, 0.0)]), _rec(4, [_det(7, 0, 0, 3.0, 0.0)])]
    rows = steps(records)
    assert len(rows) == 1
    tid, speed = rows[0]
    assert tid == 7
    assert speed == 30.0  # 3 ft over 3 frames at 30 fps


def test_implausible_rate_uses_the_published_40_ft_per_s_bar_strictly():
    slow = [_rec(1, [_det(1, 0, 0, 0.0, 0.0)]), _rec(2, [_det(1, 0, 0, 1.0, 0.0)])]
    fast = [_rec(1, [_det(2, 0, 0, 0.0, 0.0)]), _rec(2, [_det(2, 0, 0, 2.0, 0.0)])]
    assert implausible_rate(slow) == (0, 1, 0.0)  # 30 ft/s, not above 40
    assert implausible_rate(fast) == (1, 1, 1.0)  # 60 ft/s


def test_crop_box_is_G273s_512x640_and_split_counts_both_sides():
    assert (CROP_HALF_W, CROP_HALF_H) == (256, 320)
    records = [_rec(9, [_det(1, 500, 500, 0.0, 0.0), _det(2, 1500, 500, 0.0, 0.0)])]
    # One player 100 px from the first footpoint; nothing near the second.
    located = {9: [(500.0, 600.0)]}
    out = footpoint_player_split(records, located)
    assert out["n"] == 2
    assert out["in_box"] == 1
    assert out["no_player_fraction"] == 0.5
    assert out["median_px_when_player_present"] == 100.0


def test_axis_null_is_the_box_aspect_not_one_half():
    # The acceptance box is 1.25:1 tall, so a uniform-in-box offset already puts
    # 0.6098 of squared offset on the vertical axis. Reading a vertical share
    # against 0.5 instead of against this null overstates vertical dominance.
    from scripts.platformkit.tracking.verifier_footpoint_analyses import axis_null_check

    out = axis_null_check([], {})
    assert out["uniform_in_box_null"] == CROP_HALF_H**2 / (CROP_HALF_W**2 + CROP_HALF_H**2)
    assert round(out["uniform_in_box_null"], 4) == 0.6098
    assert out["isotropic_null"] == 0.5
