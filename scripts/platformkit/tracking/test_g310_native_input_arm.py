"""G310 -- the proxy computation on a hand-computed synthetic construct.

n = 1 CONSTRUCT (Q7): every value below is enumerated by hand, not sampled.
No route is run here and no video is opened.
"""
from scripts.platformkit.tracking.g310_native_input_arm import footpoint, p95, proxies


def _row(frame, pid, x1, x2, y2):
    return {"frame": str(frame), "player_id": pid, "bbox_x1": str(x1),
            "bbox_y1": "0", "bbox_x2": str(x2), "bbox_y2": str(y2)}


# Deliberately out of frame order: the proxy must sort each track by frame.
ROWS = [
    _row(2, "a", 0, 100, 208),     # footpoint (50, 208)
    _row(1, "a", 0, 100, 100),     # footpoint (50, 100)   step a1->a2 = 108 px
    _row(3, "a", 0, 100, 262),     # footpoint (50, 262)   step a2->a3 =  54 px
    _row(1, "b", 200, 400, 500),   # footpoint (300, 500)
    _row(2, "b", 200, 400, 716),   # footpoint (300, 716)  step b1->b2 = 216 px
    _row(1, "c", 10, 30, 40),      # footpoint (20, 40)    single row, no step
]
BALL = [{"detected": "1"}, {"detected": "0"}, {"detected": "True"}, {"detected": ""}]


def test_footpoint_is_bbox_bottom_centre():
    assert footpoint(_row(1, "c", 10, 30, 40)) == (20.0, 40.0)


def test_p95_is_nearest_rank_and_none_on_empty():
    assert p95([]) is None
    assert p95([0.05, 0.1, 0.2]) == 0.2          # index round(0.95 * 2) = 2
    assert p95([1.0]) == 1.0


def test_proxies_match_hand_computed_values():
    out = proxies(ROWS, BALL, evaluated_frames=10, source_height=1080)
    assert out["person_rows"] == 6
    assert out["denominator_evaluated_frames"] == 10
    assert out["frames_with_rows"] == 3
    assert abs(out["person_rows_per_evaluated_frame"] - 0.6) < 1e-12
    assert out["distinct_track_ids"] == 3
    assert out["median_track_len_rows"] == 2      # track lengths 3, 2, 1
    assert out["ball_rows_total"] == 4
    assert out["ball_rows_detected"] == 2
    assert out["denominator_step_pairs"] == 3     # 2 from a, 1 from b, 0 from c
    assert abs(out["p95_norm_footpoint_step"] - 216.0 / 1080.0) < 1e-12
    assert out["source_height"] == 1080


def test_absent_denominator_yields_none_not_zero():
    out = proxies(ROWS, [], evaluated_frames=None, source_height=1080)
    assert out["person_rows_per_evaluated_frame"] is None
    assert out["ball_rows_total"] == 0
    assert out["ball_rows_detected"] == 0


def test_empty_input_is_reported_not_faked():
    out = proxies([], [], evaluated_frames=10, source_height=1080)
    assert out["person_rows"] == 0
    assert out["distinct_track_ids"] == 0
    assert out["median_track_len_rows"] is None
    assert out["p95_norm_footpoint_step"] is None
    assert out["denominator_step_pairs"] == 0
