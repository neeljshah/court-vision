"""G412 constructive controls, writer compatibility, per-frame and paired-residual tables."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g412_contract import (
    CROP_ORIGIN_Y_PX, LEGACY_FIELDS, PADDING_PX, Box, additive_receipt,
    construct_cases, native_boxes, proposed_writer_row, write_csv_lf, write_lf,
)
from scripts.platformkit.tracking.g412_premise import G406, OUT, ROOT, read_csv

FRESH_BRANCH = "src/tracking/advanced_tracker.py:_activate_slot"
DIFF = ROOT / "docs/research/organization-sprint/PROPOSED_g412_box_frame_contract.diff"


def oracle_native(stored: tuple[float, float, float, float], width: int,
                  height: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Independent corner-loop oracle: clamp each corner, then translate y by the origin."""
    limits = (width, height, width, height)
    offset = (0, CROP_ORIGIN_Y_PX, 0, CROP_ORIGIN_Y_PX)
    inward = (PADDING_PX, PADDING_PX, -PADDING_PX, -PADDING_PX)
    padded, detector = [], []
    for index in range(4):
        limit = limits[index]
        raw = stored[index]
        clamped = limit if raw > limit else (0 if raw < 0 else raw)
        padded.append(clamped + offset[index])
        shrunk = stored[index] + inward[index]
        clamped_in = limit if shrunk > limit else (0 if shrunk < 0 else shrunk)
        detector.append(clamped_in + offset[index])
    return tuple(padded), tuple(detector)


def diff_receipt_fixture(diff_path: Path) -> dict[str, Any]:
    """Evaluate the receipt expression extracted verbatim from the PROPOSED diff."""
    added = [line[1:] for line in diff_path.read_bytes().decode("utf-8").split(chr(10))
             if line.startswith("+") and not line.startswith("+++")]
    helper = [line for line in added
              if line.startswith("def _g412_route") or line.startswith("    return str(")]
    entries = [line.strip().rstrip(",") for line in added
               if line.strip().startswith(chr(34) + "box_") and "_g412_route(" in line]
    carried = [line.strip().rstrip(",") for line in added
               if line.strip().startswith(chr(34) + "box_") and "track.get(" in line]
    if len(entries) != 5 or len(carried) != 5 or len(helper) != 2:
        raise ValueError("unexpected-diff-shape")
    scope: dict[str, Any] = {"getattr": getattr, "str": str}
    exec(chr(10).join(helper), scope)  # noqa: S102
    expression = "{" + ", ".join(entries) + "}"
    results = {}
    for label, previous, route in (("fresh_box", (1.0, 2.0, 3.0, 4.0), "fresh_box"),
                                   ("prediction", (1.0, 2.0, 3.0, 4.0), "prediction"),
                                   ("absent", None, "fresh_box")):
        holder = type("P", (), {"previous_bb": previous, "box_route": route})()
        results[label] = eval(expression, dict(scope), {"p": holder})  # noqa: S307
    return {"expression": expression, "entries": len(entries),
            "carried_columns": len(carried), "helper_lines": helper, "results": results}


def build_construct() -> list[dict[str, Any]]:
    """Enumerate the 32 sealed controls with helper and independent oracle values."""
    rows = []
    for case in construct_cases():
        stored = case["stored_xyxy"]
        row = dict(case)
        row["stored_xyxy"] = "" if stored is None else " ".join(str(v) for v in stored)
        if stored is None:
            row.update({"helper_native_padded": "", "helper_native_detector": "",
                        "oracle_native_padded": "", "oracle_native_detector": "",
                        "oracle_agrees": 1, "receipt_status": "EMPTY",
                        "receipt_reason": "absent-box", "box_frame": ""})
            rows.append(row)
            continue
        padded, detector = native_boxes(Box(*stored), case["crop_width"], case["crop_height"])
        o_pad, o_det = oracle_native(stored, case["crop_width"], case["crop_height"])
        agrees = int(padded.as_tuple() == o_pad and detector.as_tuple() == o_det)
        receipt = additive_receipt("fresh_box", Box(*stored), case["crop_width"],
                                   case["crop_height"], 1)
        row.update({
            "helper_native_padded": " ".join(str(v) for v in padded.as_tuple()),
            "helper_native_detector": " ".join(str(v) for v in detector.as_tuple()),
            "oracle_native_padded": " ".join(str(v) for v in o_pad),
            "oracle_native_detector": " ".join(str(v) for v in o_det),
            "oracle_agrees": agrees, "receipt_status": receipt["box_receipt_status"],
            "receipt_reason": receipt["box_receipt_reason"], "box_frame": receipt["box_frame"],
        })
        rows.append(row)
    return rows


def _route_of(row: dict[str, str]) -> str:
    """Classify a stored row from two independent columns, never one value twice."""
    if row["position_source"] == "DETECTION" and row["source_branch"] == FRESH_BRANCH:
        return "fresh_box"
    if row["position_source"] == "PREDICTION":
        return "prediction"
    return "retained_point"


def build_writer_compatibility(masked: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Apply the proposed additive receipt to all 206 real rows and check legacy parity."""
    rows = []
    for source in masked:
        crop_w = int(source["native_width"])
        crop_h = int(source["native_height"]) - CROP_ORIGIN_Y_PX
        stored = tuple(float(source["bbox_" + key]) for key in ("x1", "y1", "x2", "y2"))
        legacy = {"player_id": source["player_id"], "team": "", "bbox": stored,
                  "x2d": source["x_position"], "y2d": source["y_position"], "confidence": ""}
        route = _route_of(source)
        result = proposed_writer_row(legacy, route, Box(*stored), crop_w, crop_h,
                                     int(source["frame"]))
        padded, detector = native_boxes(Box(*stored), crop_w, crop_h)
        unclipped = (stored[0], stored[1] + CROP_ORIGIN_Y_PX, stored[2],
                     stored[3] + CROP_ORIGIN_Y_PX)
        rows.append({
            "unit": "real_row", "box_id": source["box_id"], "card_id": source["card_id"],
            "section_id": source["section_id"], "frame": source["frame"],
            "position_source": source["position_source"],
            "source_branch": source["source_branch"],
            "route": route, "crop_width": crop_w, "crop_height": crop_h,
            "stored_xyxy": " ".join(str(v) for v in stored),
            "native_padded_xyxy": " ".join(str(v) for v in padded.as_tuple()),
            "native_detector_xyxy": " ".join(str(v) for v in detector.as_tuple()),
            "clipped": int(padded.as_tuple() != unclipped),
            "within_padded_crop_bound": int(stored[3] <= crop_h + PADDING_PX),
            "legacy_identical": int(all(result[f] == legacy[f] for f in LEGACY_FIELDS)),
            "box_frame": result.get("box_frame", ""),
            "box_crop_origin_y_px": result.get("box_crop_origin_y_px", ""),
            "box_padding_px": result.get("box_padding_px", ""),
            "box_receipt_status": result["box_receipt_status"],
            "box_receipt_reason": result["box_receipt_reason"],
        })
    return rows


def build_per_frame(per_tick: list[dict[str, str]], masked: list[dict[str, str]],
                    receipts: list[dict[str, str]]) -> list[dict[str, Any]]:
    """One row per sealed tick; silent ticks are retained as UNKNOWN cards."""
    by_card: dict[str, list[dict[str, str]]] = {}
    for row in masked:
        by_card.setdefault(row["card_id"], []).append(row)
    receipt_by_card = {r["card_id"]: r for r in receipts}
    rows = []
    for tick in per_tick:
        card = tick["card_id"]
        boxes = by_card.get(card, [])
        crop_h = int(tick["native_height"]) - CROP_ORIGIN_Y_PX
        bound = [b for b in boxes if float(b["bbox_y2"]) <= crop_h + PADDING_PX]
        rows.append({
            "card_id": card, "draw_kind": tick["draw_kind"], "section_id": tick["section_id"],
            "frame": tick["frame"], "actual_pts_s": tick["actual_pts_s"],
            "native_width": tick["native_width"], "native_height": tick["native_height"],
            "crop_width": tick["native_width"], "crop_height": crop_h,
            "producer_rows": tick["producer_rows"], "stored_boxes": len(boxes),
            "producer_silence": tick["producer_silence"],
            "comparator_boxes": tick["comparator_boxes"],
            "fresh_box_rows": sum(1 for b in boxes if _route_of(b) == "fresh_box"),
            "prediction_rows": sum(1 for b in boxes if _route_of(b) == "prediction"),
            "retained_point_rows": sum(1 for b in boxes if _route_of(b) == "retained_point"),
            "boxes_within_padded_crop_bound": len(bound),
            "max_stored_y2": max((float(b["bbox_y2"]) for b in boxes), default=""),
            "padded_crop_bound": crop_h + PADDING_PX,
            "decoded_sha256": receipt_by_card[card]["decoded_sha256_rehash"],
            "decoded_bytes": receipt_by_card[card]["decoded_bytes"],
            "status": "UNKNOWN_SILENT" if tick["producer_silence"] == "1" else "MEASURED",
        })
    return rows


def build_paired_residuals(masked):
    """Re-derive G406's 51 producer-comparator pairs and the code-implied +60 shift."""
    by_id = {row["box_id"]: row for row in masked}
    comparators = {row["det_id"]: row for row in read_csv(G406 / "comparator_detections.csv")}
    pairs = [r for r in read_csv(G406 / "associations.csv")
             if {r["left_set"], r["right_set"]} == {"producer", "comparator"}]
    rows, old, shifted, clipped_shift = [], [], [], []
    for pair in pairs:
        prod, comp = by_id[pair["left_id"]], comparators[pair["right_id"]]
        crop_h = int(prod["native_height"]) - CROP_ORIGIN_Y_PX
        stored = tuple(float(prod["bbox_" + k]) for k in ("x1", "y1", "x2", "y2"))
        padded, _ = native_boxes(Box(*stored), int(prod["native_width"]), crop_h)
        prod_cy = (stored[1] + stored[3]) / 2
        comp_cy = (float(comp["bbox_y1"]) + float(comp["bbox_y2"])) / 2
        dy_old = prod_cy - comp_cy
        dy_new = dy_old + CROP_ORIGIN_Y_PX
        dy_clipped = (padded.y1 + padded.y2) / 2 - comp_cy
        old.append(dy_old)
        shifted.append(dy_new)
        clipped_shift.append(dy_clipped)
        rows.append({
            "card_id": pair["card_id"], "producer_box_id": pair["left_id"],
            "comparator_det_id": pair["right_id"], "iou": pair["iou"],
            "producer_centre_y_cropped": prod_cy, "comparator_centre_y_native": comp_cy,
            "dy_old_signed": dy_old, "dy_plus_origin_unclipped": dy_new,
            "dy_after_clipping": dy_clipped, "clipping_delta": dy_clipped - dy_new,
            "dx_old_signed": (stored[0] + stored[2]) / 2
                             - (float(comp["bbox_x1"]) + float(comp["bbox_x2"])) / 2,
        })
    summary = {
        "pairs": len(rows), "frames": len({r["card_id"] for r in rows}),
        "dy_old_median": round(statistics.median(old), 3),
        "dy_plus_origin_median": round(statistics.median(shifted), 3),
        "dy_after_clipping_median": round(statistics.median(clipped_shift), 3),
        "clipping_delta_nonzero_pairs": sum(1 for a, b in zip(clipped_shift, shifted) if a != b),
        "exact_shift_is_sixty": all(abs((b - a) - CROP_ORIGIN_Y_PX) < 1e-9
                                    for a, b in zip(old, shifted)),
        "fitted_constants": [],
        "independence_note": "51 pairs occupy 28 frames; this is descriptive arithmetic",
    }
    return rows, summary


def run() -> dict[str, Any]:
    """Write the four measurement tables and return their headline counts."""
    masked = read_csv(G406 / "all_masked_rows.csv")
    per_tick = read_csv(G406 / "per_tick.csv")
    receipts = read_csv(OUT / "source_receipts.csv")
    construct = build_construct()
    compat = build_writer_compatibility(masked)
    frames = build_per_frame(per_tick, masked, receipts)
    residuals, residual_summary = build_paired_residuals(masked)
    fixture = diff_receipt_fixture(DIFF)
    write_csv_lf(OUT / "construct_cases.csv", list(construct[0]), construct)
    write_csv_lf(OUT / "writer_compatibility.csv", list(compat[0]), compat)
    write_csv_lf(OUT / "per_frame.csv", list(frames[0]), frames)
    write_csv_lf(OUT / "paired_residuals.csv", list(residuals[0]), residuals)
    write_lf(OUT / "diff_fixture.json", json.dumps(fixture, indent=1, sort_keys=True) + chr(10))
    return {
        "construct_cases": len(construct),
        "construct_oracle_agreements": sum(r["oracle_agrees"] for r in construct),
        "real_rows": len(compat),
        "legacy_identical_rows": sum(r["legacy_identical"] for r in compat),
        "bound_rows": sum(1 for r in compat if r["box_receipt_status"] == "BOUND"),
        "unknown_rows": sum(1 for r in compat if r["box_receipt_status"] == "UNKNOWN"),
        "frames": len(frames),
        "silent_frames": sum(1 for r in frames if r["status"] == "UNKNOWN_SILENT"),
        "frames_with_boxes": sum(1 for r in frames if r["stored_boxes"] > 0),
        "boxes_outside_padded_crop_bound": sum(r["stored_boxes"]
                                               - r["boxes_within_padded_crop_bound"]
                                               for r in frames),
        "paired": residual_summary,
        "diff_fixture_entries": fixture["entries"],
        "diff_fixture_matches_helper": fixture_matches_helper(fixture),
    }


def fixture_matches_helper(fixture: dict[str, Any]) -> bool:
    """The diff-extracted expression must agree with the helper on all three states."""
    checks = (("fresh_box", "fresh_box", Box(1.0, 2.0, 3.0, 4.0)),
              ("prediction", "prediction", Box(1.0, 2.0, 3.0, 4.0)),
              ("absent", "fresh_box", None))
    for label, route, box in checks:
        expected = additive_receipt(route, box, 1920, 1020, 1)
        actual = fixture["results"][label]
        for field, value in actual.items():
            if expected[field] != value:
                return False
    return True


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, sort_keys=True))
