"""Construct controls for G402 preparation-only helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g402_mask import coverage, held_pairs, mask_target
from scripts.platformkit.tracking.g402_prepare import even_draw
from scripts.platformkit.tracking.g402_receipts import select_pts_window


def test_prereg_seal_normalizes_file_crlf_to_lf() -> None:
    prereg = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
              "g402_mixed_provenance_target_mask_2026-09-11" / "prereg.md")
    text = prereg.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"\nSEAL sha256 ([0-9a-f]{64})\n?$", text)
    assert match is not None
    above = text[:match.start() + 1]
    assert hashlib.sha256(above.encode("utf-8")).hexdigest() == match.group(1)


def test_repeated_detection_remains_masked_and_label_stays_distinct() -> None:
    repeated = mask_target({"position_source": "DETECTION", "repeated_coordinate": True,
                            "matched_event_id": "e1", "matched_event_valid": True,
                            "matched_box_id": "b1"})
    held = mask_target({"position_source": "HELD", "repeated_coordinate": False,
                        "matched_event_id": "e1", "matched_event_valid": True,
                        "matched_box_id": "b1"})
    assert repeated["target_weight"] == 0 and "REPEATED_COORDINATE" in repeated["mask_reason"]
    assert held["target_weight"] == 0 and "PROVENANCE_MASKED" in held["mask_reason"]


def test_missing_event_id_is_never_admitted() -> None:
    result = mask_target({"position_source": "DETECTION", "matched_box_id": "b1"})
    assert result["target_weight"] == 0
    assert "MATCHED_EVENT_ABSENT" in result["mask_reason"]


def test_held_pairs_do_not_bridge_a_missing_evaluated_tick() -> None:
    result = held_pairs([0, 3, 6], [{"frame": 0, "track_id": "p1", "x": "1", "y": "2"},
                                    {"frame": 6, "track_id": "p1", "x": "1", "y": "2"}])
    assert result["held_pairs"] == 0 and result["shared_pairs"] == 0
    assert result["zero_output_evaluated_ticks"] == 1


def test_empty_candidate_output_keeps_both_denominators() -> None:
    result = coverage([0, 1, 2], [0, 2], [])
    assert result == {"all_decoded_frames": 3, "decoded_frames_with_candidate": 0,
                      "all_evaluated_ticks": 2, "evaluated_ticks_with_candidate": 0,
                      "zero_output_evaluated_ticks": 2}


def test_source_to_window_mapping_keeps_exact_decoded_frame_ids() -> None:
    rows = [{"source_frame": "100", "pts_s": "0.0"},
            {"source_frame": "103", "pts_s": "0.1"},
            {"source_frame": "106", "pts_s": "0.2"}]
    selected = select_pts_window(rows, 0.1, 0.1)
    assert selected == [{"source_frame": "103", "pts_s": "0.1"}]


def test_insufficient_per_kind_population_is_refused() -> None:
    rows = [{"competition": "nba", "game": "g%d" % index, "section_id": "s%d" % index,
             "source_sha256": "%064x" % index} for index in range(29)]
    with pytest.raises(ValueError, match="source-quota-insufficient"):
        even_draw(rows)


# --- measurement controls added by the G402 finisher ---------------------------

from scripts.platformkit.tracking.g402_census import classify, identity_of, rate
from scripts.platformkit.tracking.g402_audit import exact_even, sealed_pool
from scripts.platformkit.tracking.g402_prepare import window_start
from scripts.platformkit.tracking.g402_tables import (
    box_id, event_valid, repeats_flags, trace_attempts,
)


def _row(frame, x, y, player="1", source="DETECTION"):
    return {"frame": str(frame), "player_id": player, "x_position": x, "y_position": y,
            "position_source": source, "bbox_x1": "10", "bbox_y1": "20",
            "bbox_x2": "30", "bbox_y2": "40"}


def test_matched_event_id_must_reproduce_the_emitted_box() -> None:
    good = dict(_row(7, "1", "2"), matched_event_id="7_20_10_40_30")
    assert event_valid(good) is True
    assert event_valid(dict(good, matched_event_id="8_20_10_40_30")) is False
    assert event_valid(dict(good, matched_event_id="7_20_10_40")) is False
    assert event_valid(dict(good, matched_event_id="")) is False
    assert box_id(good) == "10_20_30_40"
    assert box_id({"bbox_x1": ""}) == ""


def test_repeat_flag_never_bridges_a_missing_evaluated_tick() -> None:
    rows = [_row(0, "5", "5"), _row(3, "5", "5"), _row(9, "5", "5")]
    flags = repeats_flags(rows, [0, 3, 9])
    assert flags[0] is False   # no prior evaluated tick
    assert flags[1] is True    # byte-equal on the adjacent evaluated tick
    assert flags[2] is True    # 9 follows 3 in the EVALUATED order, gap unbridged
    assert repeats_flags(rows, [0, 3])[2] is False  # a tick outside the schedule


def test_repeat_flag_is_byte_equality_not_numeric_equality() -> None:
    rows = [_row(0, "5", "5"), _row(3, "5.0", "5")]
    assert repeats_flags(rows, [0, 3])[1] is False


def test_trace_attempts_reads_only_the_attempt_records(tmp_path) -> None:
    path = tmp_path / "one.trace"
    path.write_text("A,4\nS,0,4,DETECTION,b,\nA,7\nL,0,7,HELD,b,\nA,4\n", encoding="ascii")
    assert trace_attempts(path) == [4, 7]
    assert trace_attempts(tmp_path / "absent.trace") == []


def test_census_classifies_only_the_two_target_kinds() -> None:
    assert classify(1920, 1080, 29.97) == "1080p30"
    assert classify(1280, 720, 59.94) == "720p60"
    assert classify(1920, 1080, 59.94).startswith("OTHER")
    assert classify(1280, 720, 30.0).startswith("OTHER")
    assert rate("60000/1001") > 59.9 and rate("bad") == 0.0
    assert identity_of("nba__abc_s90.mp4") == ("nba", "abc", "abc_s90")
    assert identity_of("abc_s90.mp4") == ("UNDECLARED", "abc", "abc_s90")


def test_window_start_walks_the_sealed_interior_without_touching_the_edges() -> None:
    starts = [window_start(0.0, 130.0, j) for j in range(30)]
    assert starts == sorted(starts)
    assert starts[0] > 0.0 and starts[-1] + 10.0 < 130.0


def test_overrun_ticks_are_excluded_from_the_sealed_denominator(tmp_path) -> None:
    """The producer cap is after stride; derived tables retain only sealed ticks."""
    from scripts.platformkit.tracking.g402_tables import section_tables
    raw = tmp_path / "raw_tables" / "1080p30" / "sec_s90"
    raw.mkdir(parents=True)
    (raw / "evaluated_tick_receipt.json").write_text(
        '{"evaluated_tick_ids": [100, 105, 112], "attempted_frames_capped": 3}',
        encoding="ascii")
    (raw / "tracking_data.csv").write_text(
        "frame,player_id,x_position,y_position,position_source,bbox_x1,bbox_y1,bbox_x2,"
        "bbox_y2,matched_event_id,homography_valid\n"
        "100,1,5,6,DETECTION,10,20,30,40,100_20_10_40_30,1\n"
        "105,1,5,6,CLAMP,10,20,30,40,105_20_10_40_30,1\n", encoding="ascii")
    tick_row, _held, cover_row, masked, _prov = section_tables(
        {"draw_kind": "1080p30", "section_id": "sec_s90", "start_frame": "100",
         "frames": "10", "status": "COMPLETE"}, tmp_path)
    assert tick_row["sealed_window_source_frames"] == 10
    assert tick_row["source_decoded_frames_in_window"] == 10
    assert tick_row["window_overrun_frames"] == 0
    assert tick_row["receipt_evaluated_ticks"] == 2
    assert tick_row["excluded_overrun_evaluated_ticks"] == 1
    assert tick_row["trace_attempt_ticks"] == "NOT_TRACED"
    assert tick_row["emitting_ticks"] == 2 and tick_row["zero_output_evaluated_ticks"] == 0
    assert cover_row["all_decoded_frames"] == 10 and cover_row["candidate_rows"] == 1
    assert [item["target_weight"] for item in masked] == [1, 0]


def test_summary_carries_failed_windows_and_flags_any_masked_admission() -> None:
    from scripts.platformkit.tracking.g402_tables import summarize
    launches = [{"draw_kind": "1080p30", "section_id": "a_s90", "status": "COMPLETE"},
                {"draw_kind": "1080p30", "section_id": "b_s90", "status": "INCOMPLETE"}]
    good = {"draw_kind": "1080p30", "position_source": "DETECTION", "repeated_coordinate": 0,
            "matched_event_valid": 1, "target_weight": 1}
    clean = summarize(launches, [], [], [], [good])
    assert clean["per_kind"]["1080p30"]["planned"] == 2
    assert clean["per_kind"]["1080p30"]["complete"] == 1
    assert clean["per_kind"]["1080p30"]["status"]["INCOMPLETE"] == 1
    assert clean["masked_classes_admitted"] == 0
    dirty = summarize(launches, [], [], [], [dict(good, repeated_coordinate=1)])
    assert dirty["masked_classes_admitted"] == 1


def test_derived_rows_stay_sealed_and_coverage_keeps_unknown_failure() -> None:
    evidence = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
                "g402_mixed_provenance_target_mask_2026-09-11")
    import csv
    with (evidence / "launch_receipts.csv").open(newline="", encoding="ascii") as handle:
        launches = {row["section_id"]: row for row in csv.DictReader(handle)}
    with (evidence / "target_mask.csv").open(newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            launch = launches[row["section_id"]]
            assert int(launch["start_frame"]) <= int(row["frame"]) < (
                int(launch["start_frame"]) + int(launch["frames"]))
    with (evidence / "eye_index.csv").open(newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            launch = launches[row["section_id"]]
            assert int(launch["start_frame"]) <= int(row["frame"]) < (
                int(launch["start_frame"]) + int(launch["frames"]))
    with (evidence / "coverage_per_section.csv").open(newline="", encoding="ascii") as handle:
        coverage_rows = list(csv.DictReader(handle))
    assert len(coverage_rows) == 60
    assert [(row["section_id"], row["coverage_status"]) for row in coverage_rows
            if row["coverage_status"] == "UNKNOWN"] == [("RIrGQJ_jsGQ_s90", "UNKNOWN")]


def test_eye_cards_are_exact_sealed_even_draws_with_real_boxes() -> None:
    evidence = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
                "g402_mixed_provenance_target_mask_2026-09-11")
    import csv
    with (evidence / "eye_index.csv").open(newline="", encoding="ascii") as handle:
        index = list(csv.DictReader(handle))
    with (evidence / "pixel_audit.csv").open(newline="", encoding="ascii") as handle:
        audit = list(csv.DictReader(handle))
    for kind in ("1080p30", "720p60"):
        expected = exact_even(sealed_pool(evidence, kind))
        actual = [row for row in index if row["draw_kind"] == kind]
        assert [(row["section_id"], int(row["frame"])) for row in actual] == [
            pair for _ordinal, pair in expected]
        assert [int(row["sealed_ordinal"]) for row in actual] == [
            ordinal for ordinal, _pair in expected]
    by_card = {}
    for row in audit:
        assert int(row["bbox_x1"]) < int(row["bbox_x2"])
        assert int(row["bbox_y1"]) < int(row["bbox_y2"])
        by_card[row["card_id"]] = by_card.get(row["card_id"], 0) + 1
    assert len(index) == 60
    for row in index:
        assert int(row["bbox_count"]) == int(row["nondegenerate_bbox_count"])
        assert by_card.get(row["card_id"], 0) == int(row["bbox_count"])
