"""Construct-only checks for the G410 prepare-only observer helpers."""
from __future__ import annotations

import hashlib
import csv
import re
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g410_contract import (
    box_foot, classify, native_to_cropped, project_homogeneous, serialize_coordinate,
)
from scripts.platformkit.tracking.g410_prepare import (
    draw_by_class, draw_orders_from_launches, exact_even, retain_selected_rows,
)
from scripts.platformkit.tracking.g410_q6_scan import scan_text


def test_prereg_seal_normalizes_file_crlf_to_lf() -> None:
    prereg = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
              "g410_position_box_frame_consistency_2026-09-12" / "prereg.md")
    text = prereg.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"\nSEAL sha256 ([0-9a-f]{64})\n?$", text)
    assert match is not None
    above = text[:match.start() + 1]
    assert hashlib.sha256(above.encode("utf-8")).hexdigest() == match.group(1)


def test_cropped_and_native_projection_follow_declared_origin() -> None:
    matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    native_foot = box_foot((20, 30, 40, 60))
    cropped_foot = native_to_cropped(native_foot, (10, 20))
    assert native_foot == (30.0, 60.0)
    assert project_homogeneous(matrix, native_foot, "native").x == 30.0
    assert project_homogeneous(matrix, cropped_foot, "cropped").y == 40.0


def test_retained_clamp_point_with_moving_box_is_stale_box_not_auto_defect() -> None:
    result = classify("CLAMP", "CLAMP", (5, 6), (7, 8), (10, 20, 30, 40),
                      (10, 20, 30, 40), retained_position_age=1)
    assert result == "STALE_BOX"


def test_subpixel_rounding_requires_the_declared_writer_operation() -> None:
    assert serialize_coordinate(3.5, "ROUND_HALF_UP") == 4
    assert serialize_coordinate(-3.5, "ROUND_HALF_UP") == -4
    assert serialize_coordinate(3.9, "FLOOR") == 3
    with pytest.raises(ValueError, match="rounding-not-declared"):
        serialize_coordinate(3.5, "GUESS")


def test_missing_history_is_unknown_and_never_bridged_across_window() -> None:
    rows = [{"draw_kind": "a", "section_id": "s", "frame": "10", "player_id": "p",
             "matched_event_id": "", "position_source": "CLAMP"}]
    kept, unknowns = retain_selected_rows(rows, [("a", "s", 10)], {("a", "s"): (10, 20)})
    assert kept == rows
    assert [item["reason"] for item in unknowns] == ["MISSING_INITIAL_HISTORY"]


def test_duplicate_keys_and_window_bounds_are_rejected_or_preserved() -> None:
    row = {"draw_kind": "a", "section_id": "s", "frame": "11", "player_id": "p",
           "matched_event_id": "e", "position_source": "CLAMP"}
    with pytest.raises(ValueError, match="duplicate-observation-key"):
        retain_selected_rows([row, dict(row)], [("a", "s", 11)], {("a", "s"): (10, 20)})
    earlier = dict(row, frame="9", matched_event_id="old")
    kept, _unknowns = retain_selected_rows([earlier, row], [("a", "s", 11)],
                                            {("a", "s"): (10, 20)})
    assert kept == [row]


def test_exact_even_draws_are_stable_and_class_specific() -> None:
    clamp = [("a", "s", index) for index in range(30)]
    subpixel = [("a", "s", index + 100) for index in range(30)]
    rows = []
    for label, ticks in (("CLAMP", clamp), ("SUBPIXEL", subpixel)):
        for _kind, _section, frame in ticks:
            rows.append({"draw_kind": "a", "section_id": "s", "frame": str(frame),
                         "player_id": "p", "position_source": label,
                         "source_branch": "route", "matched_event_id": ""})
    assert exact_even(clamp) == clamp
    assert draw_by_class(rows, {("a", "s"): 0}) == {"CLAMP": clamp, "SUBPIXEL": subpixel}


def test_whole_parent_draw_orders_measure_lexical_prereg_overlap() -> None:
    root = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking"
    parent = root / "g402_mixed_provenance_target_mask_2026-09-11"
    with (parent / "target_mask.csv").open(newline="", encoding="ascii") as handle:
        mask_rows = list(csv.DictReader(handle))
    with (parent / "launch_receipts.csv").open(newline="", encoding="ascii") as handle:
        launch_rows = list(csv.DictReader(handle))
    executed = draw_by_class(mask_rows, draw_orders_from_launches(launch_rows))
    lexical = {}
    for label in ("CLAMP", "SUBPIXEL"):
        population = {(row["draw_kind"], row["section_id"], int(row["frame"]))
                      for row in mask_rows if row["position_source"] == label}
        lexical[label] = exact_even(sorted(population))
    delivered = {}
    draw_path = root / "g410_position_box_frame_consistency_2026-09-12" / "draw.csv"
    with draw_path.open(newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            delivered.setdefault(row["class"], []).append(
                (row["draw_kind"], row["section_id"], int(row["frame"])))
    assert delivered == executed
    assert len(set(lexical["CLAMP"]) & set(executed["CLAMP"])) == 3
    assert len(set(lexical["SUBPIXEL"]) & set(executed["SUBPIXEL"])) == 2


def test_character_code_scanner_fixture_reports_indices_not_tokens() -> None:
    text = "".join(chr(value) for value in (114, 111, 105))
    counts = scan_text(text)
    assert counts[1] == 1
    assert set(counts) == {0, 1, 2, 3}


# --- measured additions (Claude finisher) ------------------------------------

from scripts.platformkit.tracking.g410_finalize import consistency_table, staleness_table
from scripts.platformkit.tracking.g410_measure import PAD, TOPCUT, archived_foot
from scripts.platformkit.tracking.g410_report import (
    archived_projection, derive_branch, parse_trace,
)


def test_archived_foot_sits_exactly_pad_above_the_stored_box_bottom() -> None:
    head_x, foot_y, clipped = archived_foot((285.0, 185.0, 415.0, 457.0), 1920, 1020)
    assert foot_y == 457 - PAD
    assert head_x == (285 + PAD + 415 - PAD) // 2
    assert clipped == 0


def test_archived_foot_records_the_clip_that_the_producer_applied() -> None:
    _hx, foot_y, clipped = archived_foot((285.0, 185.0, 415.0, 1100.0), 1920, 1020)
    assert foot_y == 1020 and clipped == 1
    _hx2, _fy2, clipped_left = archived_foot((-40.0, 185.0, 120.0, 457.0), 1920, 1020)
    assert clipped_left == 1


def test_stored_box_is_cropped_pixels_so_native_needs_the_topcut_origin() -> None:
    assert TOPCUT == 60
    cropped_bottom = 457.0
    assert cropped_bottom + TOPCUT == 517.0


def test_archived_projection_truncates_the_homogeneous_quotient() -> None:
    mat = {"M": [1, 0, 0.6, 0, 1, 0.6, 0, 0, 1], "M1": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
    out = archived_projection((185, 285, 457, 415), 1920, 1020, mat)
    assert out["projected_x"] == int(out["head_x"] + 0.6)
    assert out["projected_y"] == int(out["foot_y"] + 0.6)
    assert out["foot_y"] == 457 - PAD


def test_derive_branch_separates_the_clamp_guard_from_a_subpixel_hold() -> None:
    assert derive_branch([10, 20], [10, 20], None, 750) == "DETECTION_FRESH_BOX"
    assert derive_branch([10, 20], [10, 20], [10, 20], 750) == "SUBPIXEL_UNMOVED_FRESH_WRITE"
    assert derive_branch([10, 20], [900, 900], [10, 20], 750) == "CLAMP_GUARD_REPRODUCED"
    assert derive_branch([10, 20], [30, 20], [10, 20], 750) == "RETAINED_WITHOUT_GUARD"
    assert derive_branch([10, 20], [30, 20], [99, 99], 750) == "NON_BOX_WRITE"


def test_parse_trace_reads_matrices_and_pre_post_state(tmp_path) -> None:
    path = tmp_path / "t.trace.txt"
    path.write_text(
        "B,9,0,1,green,185,285,457,415,,\n"
        "M,9," + ",".join(["1", "0", "0", "0", "1", "0", "0", "0", "1"]) + "," +
        ",".join(["1", "0", "0", "0", "1", "0", "0", "0", "1"]) +
        ",1920,1020,3404,1711\n"
        "P,9,0,1,green,185,285,457,415,300,400\n", encoding="ascii", newline="")
    trace = parse_trace(path)
    assert trace["matrices"][9]["frame_h"] == 1020
    assert trace["pre"][(9, 0)]["pos"] is None
    assert trace["post"][(9, 0)]["pos"] == [300.0, 400.0]


def test_class_tables_keep_full_denominators_and_missing_history() -> None:
    rows = [
        {"role": "SELECTED", "position_source": "CLAMP", "draw_kind": "a",
         "section_id": "s", "frame": "3", "predecessor_status": "PRESENT",
         "position_retained": "1", "box_moved": "1", "box_l2_px": "12.0",
         "retained_position_age": "4"},
        {"role": "SELECTED", "position_source": "CLAMP", "draw_kind": "a",
         "section_id": "s", "frame": "6",
         "predecessor_status": "MISSING_INITIAL_HISTORY",
         "position_retained": "", "box_moved": "", "box_l2_px": "",
         "retained_position_age": ""},
    ]
    table = {r["class"]: r for r in staleness_table(rows)}
    assert table["CLAMP"]["selected_rows"] == 2
    assert table["CLAMP"]["rows_with_predecessor"] == 1
    assert table["CLAMP"]["rows_missing_initial_history"] == 1
    assert table["CLAMP"]["position_retained_and_box_moved"] == 1
    assert table["SUBPIXEL"]["selected_rows"] == 0
    checks = [{"derived_branch": "CLAMP_GUARD_REPRODUCED", "draw_kind": "a",
               "section_id": "s", "frame": "3",
               "position_equals_current_box_projection": "0",
               "classification": "STALE_BOX",
               "backprojection_inside_stored_box": "1",
               "backprojected_minus_archived_foot_y": "2.5"}]
    assert consistency_table(checks)[0]["n"] == 1
    assert consistency_table(checks)[0]["classification_stale_box"] == 1


def test_construct_control_separates_cropped_and_native_origins() -> None:
    from scripts.platformkit.tracking.g410_report import construct_cases
    cases = construct_cases()
    assert cases
    for case in cases:
        assert case["topcut_origin_y"] == TOPCUT
        assert case["native_to_cropped_round_trip_ok"] == 1
        assert case["native_frame_foot_y"] == case["archived_foot_y"] + TOPCUT
        if case["matrix"] == "identity":
            assert (case["projected_from_native_foot_y"]
                    == case["archived_projected_y"] + TOPCUT)
        if case["box"] == "interior":
            assert case["stored_bottom_minus_archived_foot_px"] == PAD
            assert (case["stored_box_foot_projected_y"]
                    != case["archived_projected_y"])
