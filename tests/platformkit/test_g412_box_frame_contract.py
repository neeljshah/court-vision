"""Constructive controls and measured-table checks for the G412 box-frame contract."""
import csv
import json
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g412_contract import (
    CROP_ORIGIN_Y_PX, PADDING_PX, Box, LEGACY_FIELDS, additive_receipt, construct_cases,
    native_boxes, proposed_writer_row, valid_prereg_seal, valid_repeat_shape,
)
from scripts.platformkit.tracking.g412_q6_scan import scan_rows
from scripts.platformkit.tracking.g412_tables import (
    DIFF, diff_receipt_fixture, fixture_matches_helper,
)


ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs/evidence/tracking/g412_box_frame_contract_2026-09-12"
PREREG = EVID / "prereg.md"


def _rows(name):
    with (EVID / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _legacy_row():
    return {"player_id": 7, "team": "home", "bbox": (2, 1, 4, 3), "x2d": 10,
            "y2d": 11, "confidence": 0.9}


def _inline_oracle(stored, width, height):
    """Third independent derivation, written only inside this test."""
    def clamp(value, limit):
        return min(max(value, 0), limit)
    padded = (clamp(stored[0], width), clamp(stored[1], height) + CROP_ORIGIN_Y_PX,
              clamp(stored[2], width), clamp(stored[3], height) + CROP_ORIGIN_Y_PX)
    detector = (clamp(stored[0] + PADDING_PX, width),
                clamp(stored[1] + PADDING_PX, height) + CROP_ORIGIN_Y_PX,
                clamp(stored[2] - PADDING_PX, width),
                clamp(stored[3] - PADDING_PX, height) + CROP_ORIGIN_Y_PX)
    return padded, detector


def test_sealed_preregistration_reads_the_file_with_lf_normalization():
    assert valid_prereg_seal(PREREG)


def test_construct_matrix_is_exhaustive_and_legacy_serialization_is_unchanged():
    cases = construct_cases()
    assert len(cases) == 32
    assert len({case["case_id"] for case in cases}) == 32
    for case in cases:
        box = None if case["stored_xyxy"] is None else Box(*case["stored_xyxy"])
        row = proposed_writer_row(_legacy_row(), "fresh_box", box, case["crop_width"],
                                  case["crop_height"], 10 if box else None)
        assert tuple(row[field] for field in LEGACY_FIELDS) == tuple(
            _legacy_row()[field] for field in LEGACY_FIELDS)
        assert row["box_receipt_status"] == ("EMPTY" if box is None else "BOUND")


def test_all_thirty_two_controls_match_a_third_independent_oracle():
    rows = _rows("construct_cases.csv")
    assert len(rows) == 32
    nonempty = 0
    for row in rows:
        assert row["oracle_agrees"] == "1"
        if not row["stored_xyxy"]:
            assert row["receipt_status"] == "EMPTY"
            continue
        nonempty += 1
        stored = tuple(float(v) for v in row["stored_xyxy"].split(" "))
        padded, detector = _inline_oracle(stored, int(row["crop_width"]),
                                          int(row["crop_height"]))
        assert row["helper_native_padded"] == " ".join(str(v) for v in padded)
        assert row["helper_native_detector"] == " ".join(str(v) for v in detector)
        assert row["box_frame"] == "topcut60_pad15"
    assert nonempty == 16


def test_sign_tuple_and_clip_order_errors_are_detected():
    stored = Box(-20, -10, 1990, 1050)
    padded, detector = native_boxes(stored, 1920, 1020)
    assert padded.as_tuple() == (0, 60, 1920, 1080)
    assert detector.as_tuple() == (0, 65, 1920, 1080)
    wrong_sign = (padded.x1, padded.y1 - 2 * CROP_ORIGIN_Y_PX, padded.x2,
                  padded.y2 - 2 * CROP_ORIGIN_Y_PX)
    assert wrong_sign != padded.as_tuple()
    swapped = (padded.y1, padded.x1, padded.y2, padded.x2)
    assert swapped != padded.as_tuple()
    origin_first = (min(max(stored.x1, 0), 1920),
                    min(max(stored.y1 + CROP_ORIGIN_Y_PX, 0), 1020),
                    min(max(stored.x2, 0), 1920),
                    min(max(stored.y2 + CROP_ORIGIN_Y_PX, 0), 1020))
    assert origin_first != padded.as_tuple()
    assert native_boxes(Box(1, 2, 3, 4), 10, 10)[0].as_tuple()[1] == 62


def test_missing_boxes_unknown_routes_and_source_frame_are_explicit():
    assert additive_receipt("fresh_box", None, 100, 100, None)["box_receipt_status"] == "EMPTY"
    unknown = additive_receipt("prediction", Box(1, 2, 3, 4), 100, 100, 5)
    assert unknown["box_receipt_status"] == "UNKNOWN"
    assert unknown["box_receipt_reason"] == "unbound-prediction"
    with pytest.raises(ValueError, match="source-frame-required"):
        additive_receipt("fresh_box", Box(1, 2, 3, 4), 100, 100, None)
    with pytest.raises(ValueError, match="invalid-cropped-dimensions"):
        native_boxes(Box(1, 2, 3, 4), 0, 10)


def test_every_real_row_keeps_its_legacy_columns_and_declares_one_route():
    rows = _rows("writer_compatibility.csv")
    assert len(rows) == 206
    assert all(row["legacy_identical"] == "1" for row in rows)
    bound = [r for r in rows if r["box_receipt_status"] == "BOUND"]
    unknown = [r for r in rows if r["box_receipt_status"] == "UNKNOWN"]
    assert len(bound) + len(unknown) == 206
    assert len(bound) == 34
    assert all(r["box_frame"] == "topcut60_pad15" for r in bound)
    assert all(r["box_crop_origin_y_px"] == "60" and r["box_padding_px"] == "15"
               for r in bound)
    assert all(r["box_frame"] == "UNKNOWN" for r in unknown)


def test_all_sixty_frames_are_accounted_and_bound_to_a_decoded_source():
    frames = _rows("per_frame.csv")
    assert len(frames) == 60
    silent = [f for f in frames if f["status"] == "UNKNOWN_SILENT"]
    assert len(silent) == 5
    assert all(f["stored_boxes"] == "0" for f in silent)
    assert len([f for f in frames if f["status"] == "MEASURED"]) == 55
    assert len({(f["section_id"], f["frame"]) for f in frames}) == 60
    assert all(len(f["decoded_sha256"]) == 64 for f in frames)
    for frame in frames:
        assert int(frame["crop_height"]) == int(frame["native_height"]) - CROP_ORIGIN_Y_PX
        assert int(frame["crop_width"]) == int(frame["native_width"])


def test_eye_index_covers_every_card_with_a_render_and_a_crop_digest():
    index = _rows("eye_index.csv")
    assert len(index) == 60
    assert sum(1 for r in index if r["status"] == "UNKNOWN_SILENT") == 5
    assert all(len(r["render_sha256"]) == 64 and len(r["crop_sha256"]) == 64 for r in index)
    assert sum(int(r["boxes_drawn"]) for r in index) == 206


def test_paired_residuals_shift_by_exactly_sixty_with_no_fitted_constant():
    pairs = _rows("paired_residuals.csv")
    assert len(pairs) == 51
    assert len({p["card_id"] for p in pairs}) == 28
    for pair in pairs:
        delta = float(pair["dy_plus_origin_unclipped"]) - float(pair["dy_old_signed"])
        assert abs(delta - CROP_ORIGIN_Y_PX) < 1e-9
    summary = json.loads((EVID / "summary.json").read_bytes().decode("utf-8"))
    paired = summary["tables"]["paired"]
    assert paired["dy_old_median"] == -58.203
    assert paired["dy_plus_origin_median"] == 1.797
    assert paired["fitted_constants"] == []


def test_proposed_diff_is_additive_and_its_expression_matches_the_helper():
    fixture = diff_receipt_fixture(DIFF)
    assert fixture_matches_helper(fixture)
    text = DIFF.read_bytes().decode("utf-8")
    removed = [l for l in text.split(chr(10))
               if l.startswith("-") and not l.startswith("---")]
    assert removed == []
    assert (EVID / "PROPOSED_g412_box_frame_contract.diff").read_bytes() == DIFF.read_bytes()


def test_repeat_shape_and_character_code_scanner_fixture():
    assert valid_repeat_shape({"identical": True,
                               "runs": [{"stdout": "", "returncode": 0, "command": "x"}]})
    receipt = json.loads((EVID / "repeats.json").read_bytes().decode("utf-8"))
    assert valid_repeat_shape(receipt)
    assert receipt["identical"] is True
    assert receipt["nonzero_returncodes"] == []
    prohibited = "".join(chr(value) for value in (112, 114, 111, 102, 105, 116))
    scanned = scan_rows([{"claim": prohibited, "numeric": 12.34}])
    assert scanned["pattern_indices"] == [1]
    assert scan_rows([{"claim": "calibration only", "numeric": 1}])["pattern_indices"] == []
