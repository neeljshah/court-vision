"""G327: the batching / comparison / raw-row code, over SYNTHETIC boxes only.

No GPU, no video, no detector. These pin the properties the row's verdict rests on:
chunk coverage, bit-identity under a one-ulp change, reorder vs the NMSORD ordering
rule, both-way agreement asymmetry, the zero-box denominator, and an EXACT CSV
round-trip (the memo claims a verifier can recompute every cell from the CSV alone).
"""

import numpy as np

from scripts.platformkit.tracking.g327_arms import (
    bit_identical, chunk, compare, greedy_match, canon, read_boxes_csv, rows_for,
    run_arm, write_boxes_csv,
)

BOX = np.array([[10.0, 10.0, 50.0, 90.0], [200.0, 20.0, 240.0, 100.0]])
SCORE = np.array([0.8, 0.4])
CLS = np.zeros(2)
ROW = (BOX, SCORE, CLS)
EMPTY = (np.zeros((0, 4)), np.zeros(0), np.zeros(0))


def test_chunk_covers_every_frame_with_a_short_last_chunk():
    parts = chunk(list(range(10)), 3)
    assert [len(p) for p in parts] == [3, 3, 3, 1]
    assert [x for p in parts for x in p] == list(range(10))


def test_run_arm_keeps_every_frame_at_every_batch_size():
    rows = [ROW, EMPTY, ROW]
    for bs in (1, 2, 8):
        got, ms = run_arm([0, 1, 2], lambda part: [rows[i] for i in part], bs)
        assert len(got) == 3 and ms is not None
        assert all(bit_identical(a, b) for a, b in zip(rows, got))


def test_bit_identity_is_true_for_an_identical_pair_and_false_for_one_ulp():
    assert bit_identical(ROW, (BOX.copy(), SCORE.copy(), CLS.copy()))
    nudged = BOX.copy()
    nudged[0, 0] = np.nextafter(nudged[0, 0], np.inf)
    assert not bit_identical(ROW, (nudged, SCORE, CLS))


def test_a_reorder_fails_the_baseline_rule_and_passes_the_nmsord_rule():
    flipped = (BOX[::-1].copy(), SCORE[::-1].copy(), CLS[::-1].copy())
    assert not bit_identical(ROW, flipped)          # emission order -- the baseline arm
    assert bit_identical(ROW, flipped, sort=True)   # ARM NMSORD: ordering neutralised
    base = compare([ROW], [flipped])
    nms = compare([ROW], [flipped], sort=True)
    assert base["bit_identical_frames"] == 0 and nms["bit_identical_frames"] == 1
    assert base["ordering"] == "emission" and nms["ordering"] == "sorted"


def test_both_way_agreement_is_asymmetric_when_the_counts_differ():
    extra = np.vstack([BOX, [[400.0, 40.0, 440.0, 120.0]]])
    arm = (extra, np.append(SCORE, 0.5), np.zeros(3))
    out = compare([ROW], [arm])
    assert out["matched"] == 2 and out["boxes_ref"] == 2 and out["boxes_arm"] == 3
    assert out["agree_ref_in_arm"] == 1.0
    assert out["agree_arm_in_ref"] < out["agree_ref_in_arm"]
    assert out["per_frame_count_delta"] == [1] and out["abs_count_delta_total"] == 1


def test_greedy_matching_is_one_to_one_at_the_sealed_threshold():
    near = np.array([[12.0, 12.0, 52.0, 92.0], [11.0, 11.0, 51.0, 91.0]])
    # both candidates overlap the SAME reference box; one-to-one allows only one match
    assert greedy_match(canon((BOX[:1], SCORE[:1], CLS[:1])),
                        canon((near, SCORE, CLS))) == 1
    far = np.array([[10.0, 10.0, 20.0, 20.0]])
    assert greedy_match(canon((BOX[:1], SCORE[:1], CLS[:1])),
                        canon((far, SCORE[:1], CLS[:1]))) == 0


def test_a_zero_box_frame_stays_in_the_denominator_and_matches_another_zero_box_frame():
    assert bit_identical(EMPTY, EMPTY)
    out = compare([ROW, EMPTY], [ROW, EMPTY])
    assert out["frames"] == 2 and out["bit_identical_frames"] == 2
    assert out["zero_box_frames_ref"] == 1 and out["zero_box_frames_arm"] == 1
    assert out["agree_ref_in_arm"] == 1.0


def test_the_committed_csv_round_trips_exactly_and_restores_zero_box_frames(tmp_path):
    rows = [ROW, EMPTY, (BOX + 0.123456789, SCORE, CLS)]
    idxs = [0, 7, 19]
    path = tmp_path / "boxes.csv"
    n = write_boxes_csv(path, idxs, {"single": rows, "batch8": rows})
    assert n == 8  # 4 boxes per arm; the zero-box frame writes no line by design
    table = read_boxes_csv(path)
    back = rows_for(table, "single", idxs)
    assert len(back) == 3  # the zero-box frame is RESTORED, not dropped
    assert all(bit_identical(a, b) for a, b in zip(rows, back))


def test_game_id_strips_only_a_trailing_segment_suffix():
    from scripts.platformkit.tracking.g327_sources import game_id
    assert game_id("nba__0022400909_s1015") == "nba__0022400909"
    assert game_id("nba__0022400909_s1206") == "nba__0022400909"  # same game, other clip
    assert game_id("wnba__wnba_06") == "wnba__wnba_06"            # no suffix to strip
    assert game_id("ncaa__x_s12_y") == "ncaa__x_s12_y"            # not trailing, kept


def test_indices_span_zero_to_the_anchor_with_no_duplicate_and_no_head_slice():
    from scripts.platformkit.tracking.g327_sources import indices
    idx = indices(3994)
    assert len(idx) == 40 and len(set(idx)) == 40   # contract B7/A4: unique, not a slice
    assert idx[0] == 0 and idx[-1] == 3994          # spans to the MEASURED anchor
    assert idx == sorted(idx)
