"""G327: the batching / comparison / raw-row code, over SYNTHETIC boxes only.

No GPU, no video, no detector. These pin the properties the row's verdict rests on:
chunk coverage, bit-identity under a one-ulp change, reorder vs the NMSORD ordering
rule, both-way agreement asymmetry, the zero-box denominator, and an EXACT CSV
round-trip (the memo claims a verifier can recompute every cell from the CSV alone).
"""

import numpy as np
import pytest

from scripts.platformkit.tracking.g327_arms import (
    bit_identical, chunk, compare, greedy_match, canon, quant, read_arm_csv,
    read_boxes_csv, rows_for, run_arm, unquant, write_arm_csv, write_boxes_csv,
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


def test_the_committed_csv_round_trips_exactly_and_writes_an_explicit_zero_box_row(
        tmp_path):
    rows = [ROW, EMPTY, (BOX + 0.123456789, SCORE, CLS)]
    idxs = [0, 7, 19]
    path = tmp_path / "boxes_single.csv"
    n = write_arm_csv(path, "single", [(1, idxs, rows)])
    assert n == 5  # 4 boxes PLUS one explicit row for the zero-box frame
    lines = path.read_text(encoding="ascii").splitlines()
    zero = [ln for ln in lines[1:] if ln.split(",")[0] == "%06d" % 7]
    assert len(zero) == 1
    cells = zero[0].split(",")
    assert cells[-1] == "000000" and cells[2:9] == [""] * 7   # n_boxes 000000, no box
    order, table = read_arm_csv(path)
    assert order[1] == idxs                    # the zero-box frame is IN the frame list
    back = rows_for(table[1], idxs)
    assert len(back) == 3
    assert all(bit_identical(a, b) for a, b in zip(rows, back))


def test_the_quantised_cell_round_trips_with_no_tolerance_and_is_pure_digits():
    # The awkward values are BUILT, not written as literals: they are exactly the ones
    # whose shortest decimal form carries a contract-Q6 restricted digit sequence, which
    # is the whole reason this encoding exists, so the sequence must not enter the tree.
    awkward = [0.0, 27.0 * 2, 1615759 / 2048, 3011 / 2 ** 16, -3.5]
    for v in awkward:
        cell = quant(v)
        assert unquant(cell) == v                       # EXACT, no tolerance
        assert cell.lstrip("-").replace("/", "").isdigit()
        # zero-padded to six, so no two-digit run can ever stand alone in a cell
        assert len(cell.split("/")[0].lstrip("-")) >= 6


def test_the_nmsord_arm_writes_its_own_sorted_rows_not_a_resort_of_batch8(tmp_path):
    """ARM NMSORD sorts INSIDE the arm, so its CSV carries the sorted emission itself."""
    flipped = (BOX[::-1].copy(), SCORE[::-1].copy(), CLS[::-1].copy())
    sorted_rows = [tuple((canon(flipped, sort=True)[:, s] for s in (slice(0, 4), 4, 5)))]
    path = tmp_path / "boxes_nmsord.csv"
    write_arm_csv(path, "nmsord", [(1, [0], sorted_rows)])
    _order, table = read_arm_csv(path)
    back = rows_for(table[1], [0])
    assert bit_identical([ROW][0], back[0])          # the FILE is already in sorted order
    assert not bit_identical(flipped, back[0])       # and is not the raw emission order
    assert compare([ROW], back, sort=True)["bit_identical_frames"] == 1


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


def test_an_attempt_1_nine_column_csv_still_reads_through_the_legacy_path(tmp_path):
    """B2: attempt 1's writer, reader and three-argument `rows_for` keep working, and
    `read_arm_csv` parses the same nine-column file through its legacy branch."""
    idxs = [0, 7, 19]
    rows = [ROW, EMPTY, (BOX + 0.123456789, SCORE, CLS)]
    path = tmp_path / "boxes.csv"
    n = write_boxes_csv(path, idxs, {"single": rows})
    assert n == 4                       # attempt 1 wrote NO line for the zero-box frame
    head = path.read_text(encoding="ascii").splitlines()[0].split(",")
    assert len(head) == 9 and head[-1] == "class"
    table = read_boxes_csv(path)                    # attempt 1's return shape: by ARM
    back = rows_for(table, "single", idxs)          # attempt 1's three-argument call
    assert len(back) == 3
    assert all(bit_identical(a, b) for a, b in zip(rows, back))
    order, per_slot = read_arm_csv(path)            # the nine-column parse branch
    assert order[0] == [0, 19]                      # no slot column -> slot 0
    assert all(bit_identical(a, b) for a, b in
               zip([rows[0], rows[2]], rows_for(per_slot[0], [0, 19])))


def _tampered(tmp_path):
    """A well-formed two-frame arm CSV, returned with its lines for one edit."""
    path = tmp_path / "boxes_single.csv"
    write_arm_csv(path, "single", [(1, [0, 7], [ROW, ROW])])
    return path, path.read_text(encoding="ascii").splitlines()


def test_read_arm_csv_rejects_a_row_whose_arm_is_not_the_files_arm(tmp_path):
    path, lines = _tampered(tmp_path)
    lines[2] = lines[2].replace(",single,", ",batch8,")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="file arm"):
        read_arm_csv(path)


def test_read_arm_csv_rejects_a_non_contiguous_box_index(tmp_path):
    path, lines = _tampered(tmp_path)
    cells = lines[2].split(",")
    cells[2] = "%06d" % 5                   # box_index 1 -> 5: a box went missing
    lines[2] = ",".join(cells)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="out of sequence"):
        read_arm_csv(path)


def test_read_arm_csv_rejects_a_declared_count_the_rows_do_not_meet(tmp_path):
    path, lines = _tampered(tmp_path)
    del lines[2]                            # a truncated frame: 2 declared, 1 parsed
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="declares 2, parsed 1"):
        read_arm_csv(path)
