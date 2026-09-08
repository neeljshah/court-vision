"""G310 attempt 2 -- the non-recycled instance key on a hand-pinned construct.

n = 1 CONSTRUCT (Q7): every value below is enumerated by hand, not sampled.
No route is run here, no video is opened and no pod is touched.
"""
from scripts.platformkit.tracking.g310_instance_key import (
    GAP_G, JUMP_J, SENSITIVITY, _milli, _pad, instance_proxies, rows_per_frame,
    split_instances, wall_seconds_from_log,
)
from scripts.platformkit.tracking.g310_native_input_arm import proxies

H = 1000  # source_height, chosen so a normalised step is the pixel step / 1000


def _row(frame, slot, x1, x2, y2):
    return {"frame": str(frame), "player_id": slot, "bbox_x1": str(x1),
            "bbox_y1": "0", "bbox_x2": str(x2), "bbox_y2": str(y2)}


# Deliberately out of frame order: the key must sort each slot by frame first.
# slot "1" -- one slot reused by two players, separated by a frame gap of 393 > G.
# slot "2" -- one slot reused by two players with NO gap: a 600 px jump > J * H.
# slot "3" -- a single row, which is an instance of length 1 with no step.
ROWS = [
    _row(4, "1", 0, 100, 150),      # fp (50, 150)   step from f1  =  50 px
    _row(1, "1", 0, 100, 100),      # fp (50, 100)
    _row(7, "1", 0, 100, 270),      # fp (50, 270)   step from f4  = 120 px
    _row(400, "1", 0, 100, 260),    # fp (50, 260)   gap 393 > G   -> CUT (step 10 px)
    _row(403, "1", 0, 100, 290),    # fp (50, 290)   step          =  30 px
    _row(1, "2", 0, 200, 100),      # fp (100, 100)
    _row(4, "2", 600, 800, 100),    # fp (700, 100)  jump 600 px   -> CUT
    _row(7, "2", 600, 800, 180),    # fp (700, 180)  step          =  80 px
    _row(1, "3", 10, 30, 40),       # fp (20, 40)    single row
]


def test_fixed_parameters_are_the_preregistered_ones():
    assert (GAP_G, JUMP_J) == (270, 0.20)
    assert SENSITIVITY == (90, 0.10)


def test_gap_beyond_g_splits_one_slot_into_two_instances():
    groups = split_instances([r for r in ROWS if r["player_id"] == "1"], H)
    assert [len(g) for g in groups] == [3, 2]
    assert [int(r["frame"]) for r in groups[0]] == [1, 4, 7]
    assert [int(r["frame"]) for r in groups[1]] == [400, 403]


def test_jump_beyond_j_splits_without_any_frame_gap():
    groups = split_instances([r for r in ROWS if r["player_id"] == "2"], H)
    assert [len(g) for g in groups] == [1, 2]
    assert [int(r["frame"]) for r in groups[1]] == [4, 7]


def test_instance_proxies_match_hand_computed_values():
    out = instance_proxies(ROWS, H)
    assert out["instance_key_gap_g"] == 270
    assert out["instance_key_jump_j"] == 0.20
    assert out["distinct_instances"] == 5           # 2 + 2 + 1
    assert out["median_instance_len_rows"] == 2     # lengths 1, 1, 2, 2, 3
    # 4 steps kept: 50, 120, 30 (slot 1) and 80 (slot 2) px.
    # The two CUT boundaries -- 10 px across the gap and 600 px across the jump --
    # are EXCLUDED, because the rows either side of a cut are not one instance.
    assert out["denominator_step_pairs_instance"] == 4
    assert abs(out["p95_norm_step_instance"] - 120.0 / H) < 1e-12


def test_split_boundary_is_what_separates_the_two_units():
    slot = proxies(ROWS, [], evaluated_frames=None, source_height=H)
    inst = instance_proxies(ROWS, H)
    # The attempt-1 slot unit keeps all 6 steps and its p95 IS the 600 px jump.
    assert slot["distinct_track_ids"] == 3
    assert slot["median_track_len_rows"] == 3       # slot lengths 5, 3, 1
    assert slot["denominator_step_pairs"] == 6
    assert abs(slot["p95_norm_footpoint_step"] - 600.0 / H) < 1e-12
    assert inst["denominator_step_pairs_instance"] < slot["denominator_step_pairs"]
    assert inst["p95_norm_step_instance"] < slot["p95_norm_footpoint_step"]


def test_sensitivity_pair_cuts_strictly_more():
    out = instance_proxies(ROWS, H, *SENSITIVITY)
    # G = 90 still cuts the 393 gap; J = 0.10 additionally cuts the 120 px step.
    assert out["distinct_instances"] == 6           # lengths 2, 1, 2, 1, 2, 1
    assert out["median_instance_len_rows"] == 1.5
    assert out["denominator_step_pairs_instance"] == 3   # 50, 30, 80 px
    assert abs(out["p95_norm_step_instance"] - 80.0 / H) < 1e-12


def test_rows_per_frame_prefers_the_sidecar_and_falls_back_by_rule():
    base = {"person_rows": 12, "denominator_evaluated_frames": 4,
            "frames_with_rows": 3, "denominator_reason": "sidecar"}
    out = rows_per_frame(base)
    assert out["person_rows_per_frame"] == 3.0
    assert out["person_rows_per_frame_denominator_source"] == "evaluated_frames"
    base["denominator_evaluated_frames"] = None
    out = rows_per_frame(base)
    assert out["person_rows_per_frame"] == 4.0
    assert out["person_rows_per_frame_denominator_source"] == "frames_with_rows"
    assert out["person_rows_per_frame_denominator_reason"] == "sidecar"


def test_empty_input_is_reported_not_faked():
    out = instance_proxies([], H)
    assert out["distinct_instances"] == 0
    assert out["median_instance_len_rows"] is None
    assert out["p95_norm_step_instance"] is None
    assert out["denominator_step_pairs_instance"] == 0
    assert rows_per_frame({"person_rows": 0, "denominator_evaluated_frames": None,
                           "frames_with_rows": 0})["person_rows_per_frame"] is None


def test_integer_cells_are_zero_padded_to_six_digits():
    assert _pad(90) == "000090"
    assert _pad(1) == "000001"
    assert _milli(1.5) == "001500"      # thousandths of a pixel, no decimal point
    assert _milli(-0.102) == "-00102"


def test_wall_seconds_is_read_off_the_run_log(tmp_path):
    log = tmp_path / "run.log"
    log.write_text('noise\nG310_ARM_SUMMARY {"rc": 0, "wall_seconds": 1668.4}\n')
    assert wall_seconds_from_log(log) == 1668.4
    assert wall_seconds_from_log(tmp_path / "absent.log") is None
