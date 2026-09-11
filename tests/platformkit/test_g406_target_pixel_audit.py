"""Preparation-only controls for G406's future native-pixel audit."""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g406_audit import (associate, blind_before_overlay,
                                                       field_scan, preserve_repeat_parent)
from scripts.platformkit.tracking.g406_prepare import (exact_even, join_bounds, retain_silence,
                                                         seal_valid, unchanged_masks)


def test_prereg_seal_normalizes_file_crlf_to_lf() -> None:
    path = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
            "g406_masked_target_pixel_audit_2026-09-11" / "prereg.md")
    assert seal_valid(path)
    body = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(body[:body.index("SEAL sha256")].encode("utf-8")).hexdigest() in body


def test_exact_even_keys_have_fixed_endpoints() -> None:
    rows = [{"frame": index} for index in range(60)]
    result = exact_even(rows)
    assert len(result) == 30
    assert result[0]["frame"] == 0 and result[-1]["frame"] == 59
    assert len({row["frame"] for row in result}) == 30


def test_blank_mask_bounds_join_from_authoritative_tick_manifest() -> None:
    masks = [{"draw_kind": "720p60", "section_id": "s1", "frame": "12",
              "sealed_start_frame": "", "sealed_end_frame_exclusive": ""}]
    result = join_bounds(masks, [{"draw_kind": "720p60", "section_id": "s1"}],
                         [{"section_id": "s1", "sealed_start_frame": "10",
                           "sealed_end_frame_exclusive": "14"}])
    assert result[0]["sealed_start_frame"] == 10
    assert result[0]["sealed_end_frame_exclusive"] == 14


def test_silence_is_retained_in_selected_tick_denominator() -> None:
    selected = [{"draw_kind": "720p60", "section_id": "s1", "frame": 12}]
    result = retain_silence(selected, [])
    assert result == [{"draw_kind": "720p60", "section_id": "s1", "frame": 12,
                       "all_rows": 0, "candidate_rows": 0, "silence": 1}]


def test_association_is_one_to_one_with_lexicographic_ties() -> None:
    boxes = [{"box_id": "b2", "bbox_x1": 0, "bbox_y1": 0, "bbox_x2": 10, "bbox_y2": 10},
             {"box_id": "b1", "bbox_x1": 0, "bbox_y1": 0, "bbox_x2": 10, "bbox_y2": 10}]
    people = [{"person_id": "p1", "bbox_x1": 0, "bbox_y1": 0, "bbox_x2": 10, "bbox_y2": 10}]
    result = associate(boxes, people)
    assert result["matches"] == [{"box_id": "b1", "person_id": "p1", "iou": 1.0}]
    assert result["unmatched_boxes"] == ["b2"]


def test_blind_timestamp_precedes_overlay() -> None:
    assert blind_before_overlay([{ "blind_completed_utc": "2026-09-11T00:00:00Z",
                                   "overlay_opened_utc": "2026-09-11T00:00:01Z"}])
    assert not blind_before_overlay([{ "blind_completed_utc": "2026-09-11T00:00:01Z",
                                       "overlay_opened_utc": "2026-09-11T00:00:01Z"}])


def test_masks_remain_immutable() -> None:
    before = [{"draw_kind": "720p60", "section_id": "s1", "frame": 12, "player_id": "p1",
               "position_source": "DETECTION", "target_weight": 1, "mask_reason": "CANDIDATE_ONLY"}]
    assert unchanged_masks(before, [dict(before[0])])
    changed = [dict(before[0], target_weight=0)]
    assert not unchanged_masks(before, changed)


def test_field_aware_scanner_reports_positive_without_matching_text(tmp_path: Path) -> None:
    path = tmp_path / "claims.csv"
    term = "".join(chr(code) for code in (114, 111, 105))
    path.write_text("claim,path\n%s,opaque_identifier\n" % term, encoding="utf-8", newline="\n")
    result = field_scan(path)
    assert result["count"] == 1 and result["indices"]


def test_parent_repeat_fields_are_retained() -> None:
    parent = {"identical": True, "runs": [{"returncode": 0, "stdout": ""}], "other": "keep"}
    result = preserve_repeat_parent(parent, {"g406_tables": {"same": True}})
    assert result["identical"] is True and result["runs"] == parent["runs"]
    assert result["g406_tables"] == {"same": True}


def _out() -> Path:
    return (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
            "g406_masked_target_pixel_audit_2026-09-11")


def _rows(name: str) -> list[dict[str, str]]:
    import csv
    with open(_out() / name, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_sealed_draw_reproduces_the_landed_g402_cards() -> None:
    from scripts.platformkit.tracking.g406_measure import G402, read_csv, sealed_draw
    cards, eye = sealed_draw(), read_csv(G402 / "eye_index.csv")
    assert len(cards) == 60
    assert [(row["card_id"], row["section_id"], row["frame"], row["sealed_ordinal"]) for row in cards] == \
           [(row["card_id"], row["section_id"], int(row["frame"]), int(row["sealed_ordinal"]))
            for row in eye]


def test_selected_masks_are_unchanged_against_the_landed_export() -> None:
    from scripts.platformkit.tracking.g406_measure import G402, read_csv
    selected = {(row["draw_kind"], row["section_id"], row["frame"]) for row in _rows("all_masked_rows.csv")}
    landed = [row for row in read_csv(G402 / "target_mask.csv")
              if (row["draw_kind"], row["section_id"], row["frame"]) in selected]
    assert len(landed) == 206
    key = ("draw_kind", "section_id", "frame", "player_id", "position_source", "target_weight",
           "mask_reason")
    order = lambda row: tuple(str(row[field]) for field in key)
    assert unchanged_masks(sorted(landed, key=order),
                           sorted(_rows("all_masked_rows.csv"), key=order))


def test_every_producer_row_comparator_box_and_silence_tick_is_adjudicated() -> None:
    verdicts = _rows("adjudications.csv")
    judged = {row["subject_id"] for row in verdicts}
    assert {row["box_id"] for row in _rows("all_masked_rows.csv")} <= judged
    assert {row["det_id"] for row in _rows("comparator_detections.csv")} <= judged
    silent = {row["card_id"] for row in _rows("per_tick.csv") if row["producer_silence"] == "1"}
    marked = {row["card_id"] for row in verdicts if row["subject_kind"] == "PRODUCER_SILENCE"}
    assert silent == marked and len(silent) == 5


def test_blind_completion_precedes_every_overlay_exposure() -> None:
    receipt = _rows("blind_order_receipt.csv")
    assert len(receipt) == 482 and blind_before_overlay(receipt)


def test_candidate_rows_keep_their_full_denominator_in_the_summary() -> None:
    import json
    summary = json.loads((_out() / "summary.json").read_text(encoding="utf-8"))
    verdicts = {row["subject_id"]: row["verdict"] for row in _rows("adjudications.csv")}
    candidates = [row for row in _rows("all_masked_rows.csv") if row["target_weight"] == "1"]
    supported = sum(1 for row in candidates if verdicts[row["box_id"]] in ("PERSON", "PERSON_OFFSET"))
    assert summary["POOLED"]["candidate_rows"] == len(candidates) == 34
    assert summary["POOLED"]["candidate_supported"] == supported
    assert summary["POOLED"]["full_window_denominators"]["bounded_rows"] == 19087


def test_field_aware_scan_and_repeats_are_clean() -> None:
    import json
    scan = json.loads((_out() / "q6_scan.json").read_text(encoding="utf-8"))
    assert scan["non_opaque_hits"] == 0
    assert all("indices" in item and "count" in item for item in scan["files"])
    repeats = json.loads((_out() / "repeats.json").read_text(encoding="utf-8"))
    assert repeats["identical"] is True and len(repeats["runs"]) == 2
    assert all("stdout" in run and "returncode" in run for run in repeats["runs"])
