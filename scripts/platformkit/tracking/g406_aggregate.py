"""Per-tick and pooled aggregates for the G406 person-target pixel diagnostic."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g406_measure import OUT, read_csv, write_csv, write_json
from scripts.platformkit.tracking.g406_prepare import KINDS

SUPPORTED = ("PERSON", "PERSON_OFFSET")
CLASSES = ("DETECTION", "PREDICTION", "CLAMP", "SUBPIXEL")
PER_TICK_FIELDS = ["card_id", "draw_kind", "section_id", "frame", "actual_pts_s", "native_width",
                   "native_height", "producer_rows", "candidate_rows", "producer_silence",
                   "comparator_boxes", "comparator_silence", "blind_instances", "blind_uncertain",
                   "blind_regions", "blind_region_min_persons", "producer_supported",
                   "producer_no_person", "producer_unknown", "producer_out_of_frame",
                   "producer_matched_comparator", "comparator_matched_producer",
                   "comparator_matched_blind", "blind_matched_producer"]


def _pairs() -> dict[tuple[str, str, str], set[str]]:
    out: dict[tuple[str, str, str], set[str]] = {}
    for row in read_csv(OUT / "associations.csv"):
        key = (row["card_id"], row["left_set"], row["right_set"])
        out.setdefault(key, set()).add(row["left_id"])
        out.setdefault((row["card_id"], row["right_set"], row["left_set"]), set()).add(row["right_id"])
    return out


def _centre(row: dict[str, Any]) -> tuple[float, float]:
    return ((float(row["bbox_x1"]) + float(row["bbox_x2"])) / 2.0,
            (float(row["bbox_y1"]) + float(row["bbox_y2"])) / 2.0)


def geometry() -> dict[str, Any]:
    """Describe producer-versus-comparator geometry for the sealed matched pairs."""
    boxes = {row["box_id"]: row for row in read_csv(OUT / "all_masked_rows.csv")}
    boxes.update({row["det_id"]: row for row in read_csv(OUT / "comparator_detections.csv")
                  if row["status"] == "DETECTION"})
    matched_dx, matched_dy, near_dx, near_dy = [], [], [], []
    for row in read_csv(OUT / "associations.csv"):
        if row["left_set"] == "producer" and row["right_set"] == "comparator":
            left, right = _centre(boxes[row["left_id"]]), _centre(boxes[row["right_id"]])
            matched_dx.append(left[0] - right[0])
            matched_dy.append(left[1] - right[1])
    per_card: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "comparator_detections.csv"):
        if row["status"] == "DETECTION":
            per_card.setdefault(row["card_id"], []).append(row)
    for row in read_csv(OUT / "all_masked_rows.csv"):
        pool = per_card.get(row["card_id"], [])
        if not pool:
            continue
        left = _centre(row)
        best = min(pool, key=lambda item: (left[0] - _centre(item)[0]) ** 2 +
                   (left[1] - _centre(item)[1]) ** 2)
        right = _centre(best)
        near_dx.append(left[0] - right[0])
        near_dy.append(left[1] - right[1])

    def describe(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        return {"n": len(values), "median": round(statistics.median(ordered), 2),
                "p10": round(ordered[int(0.10 * (len(ordered) - 1))], 2),
                "p90": round(ordered[int(0.90 * (len(ordered) - 1))], 2)}
    return {"sealed_matched_pairs_iou_ge_0_50": {"dx": describe(matched_dx), "dy": describe(matched_dy)},
            "nearest_comparator_centre_offset_descriptive_only": {"dx": describe(near_dx),
                                                                  "dy": describe(near_dy)},
            "note": ("the nearest-comparator offset is descriptive and is not an association rule; "
                     "the sealed rule remains one-to-one maximum IoU at 0.50")}


def per_tick() -> list[dict[str, Any]]:
    frames = {row["card_id"]: row for row in read_csv(OUT / "frame_receipts.csv")}
    marks = {json.loads(line)["card_id"]: json.loads(line)
             for line in (OUT / "blind_marks.jsonl").read_text(encoding="utf-8").splitlines()}
    pairs = _pairs()
    rows_by_card: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "all_masked_rows.csv"):
        rows_by_card.setdefault(row["card_id"], []).append(row)
    comp_by_card: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "comparator_detections.csv"):
        comp_by_card.setdefault(row["card_id"], []).append(row)
    verdict = {row["subject_id"]: row["verdict"] for row in read_csv(OUT / "adjudications.csv")}
    out = []
    for card in sorted(frames):
        producer = rows_by_card.get(card, [])
        comparator = [row for row in comp_by_card.get(card, []) if row["status"] == "DETECTION"]
        mark = marks[card]
        verdicts = [verdict[row["box_id"]] for row in producer]
        out.append({
            "card_id": card, "draw_kind": frames[card]["draw_kind"],
            "section_id": frames[card]["section_id"], "frame": frames[card]["frame"],
            "actual_pts_s": frames[card]["actual_pts_s"],
            "native_width": frames[card]["decoded_width"], "native_height": frames[card]["decoded_height"],
            "producer_rows": len(producer),
            "candidate_rows": sum(1 for row in producer if row["target_weight"] == "1"),
            "producer_silence": int(not producer),
            "comparator_boxes": len(comparator), "comparator_silence": int(not comparator),
            "blind_instances": len(mark["marks"]),
            "blind_uncertain": sum(1 for item in mark["marks"] if item["certainty"] == "UNCERTAIN"),
            "blind_regions": len(mark["regions"]),
            "blind_region_min_persons": sum(int(item["approx_count_min"]) for item in mark["regions"]),
            "producer_supported": sum(1 for item in verdicts if item in SUPPORTED),
            "producer_no_person": verdicts.count("NO_PERSON"),
            "producer_unknown": verdicts.count("UNKNOWN"),
            "producer_out_of_frame": verdicts.count("OUT_OF_FRAME"),
            "producer_matched_comparator": len(pairs.get((card, "producer", "comparator"), set())),
            "comparator_matched_producer": len(pairs.get((card, "comparator", "producer"), set())),
            "comparator_matched_blind": len(pairs.get((card, "comparator", "blind"), set())),
            "blind_matched_producer": len(pairs.get((card, "blind", "producer"), set()))})
    return out


def _rate(numerator: int, denominator: int) -> Any:
    return "UNDEFINED" if denominator == 0 else round(numerator / denominator, 6)


def summarise(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    rows = read_csv(OUT / "all_masked_rows.csv")
    verdict = {row["subject_id"]: row["verdict"] for row in read_csv(OUT / "adjudications.csv")}
    accounting = read_csv(OUT / "window_accounting.csv")
    summary: dict[str, Any] = {}
    for kind in list(KINDS) + ["POOLED"]:
        subset = [row for row in ticks if kind in (row["draw_kind"], "POOLED")]
        mask = [row for row in rows if kind in (row["draw_kind"], "POOLED")]
        windows = [row for row in accounting if kind in (row["draw_kind"], "POOLED")]
        candidates = [row for row in mask if row["target_weight"] == "1"]
        supported = sum(1 for row in candidates if verdict[row["box_id"]] in SUPPORTED)
        by_class = {}
        for name in CLASSES:
            group = [row for row in mask if row["position_source"] == name]
            hit = sum(1 for row in group if verdict[row["box_id"]] in SUPPORTED)
            by_class[name] = {"rows": len(group), "supported": hit,
                              "supported_rate": _rate(hit, len(group)),
                              "extent_correct": sum(1 for row in group
                                                    if verdict[row["box_id"]] == "PERSON"),
                              "no_person": sum(1 for row in group
                                               if verdict[row["box_id"]] == "NO_PERSON"),
                              "unknown": sum(1 for row in group
                                             if verdict[row["box_id"]] in ("UNKNOWN", "OUT_OF_FRAME"))}
        summary[kind] = {
            "sampled_ticks": len(subset),
            "sampled_producer_rows": len(mask),
            "candidate_rows": len(candidates), "candidate_supported": supported,
            "candidate_plausibility": _rate(supported, len(candidates)),
            "candidate_extent_correct": sum(1 for row in candidates
                                            if verdict[row["box_id"]] == "PERSON"),
            "masked_rows_by_class": by_class,
            "producer_silent_ticks": sum(row["producer_silence"] for row in subset),
            "comparator_silent_ticks": sum(row["comparator_silence"] for row in subset),
            "comparator_boxes": sum(row["comparator_boxes"] for row in subset),
            "producer_matched_comparator": sum(row["producer_matched_comparator"] for row in subset),
            "producer_matched_comparator_rate": _rate(
                sum(row["producer_matched_comparator"] for row in subset), len(mask)),
            "comparator_matched_producer": sum(row["comparator_matched_producer"] for row in subset),
            "comparator_matched_producer_rate": _rate(
                sum(row["comparator_matched_producer"] for row in subset),
                sum(row["comparator_boxes"] for row in subset)),
            "blind_instances": sum(row["blind_instances"] for row in subset),
            "blind_uncertain_instances": sum(row["blind_uncertain"] for row in subset),
            "blind_matched_producer": sum(row["blind_matched_producer"] for row in subset),
            "blind_missed_by_producer": sum(row["blind_instances"] - row["blind_matched_producer"]
                                            for row in subset),
            "blind_missed_by_producer_rate": _rate(
                sum(row["blind_instances"] - row["blind_matched_producer"] for row in subset),
                sum(row["blind_instances"] for row in subset)),
            "blind_uncertain_regions": sum(row["blind_regions"] for row in subset),
            "blind_region_min_persons_not_instance_marked": sum(row["blind_region_min_persons"]
                                                                for row in subset),
            "full_window_denominators": {
                "windows": len(windows),
                "decoded_frames": sum(int(row["all_decoded_frames"]) for row in windows),
                "evaluated_ticks": sum(int(row["all_evaluated_ticks"]) for row in windows),
                "bounded_rows": sum(int(row["bounded_rows"]) for row in windows),
                "candidate_rows": sum(int(row["candidate_rows"]) for row in windows),
                "zero_candidate_evaluated_ticks_alias_zero_output_evaluated_ticks": sum(
                    int(row["zero_candidate_evaluated_ticks"]) for row in windows),
                "receipt_zero_output_evaluated_ticks": sum(
                    int(row["receipt_zero_output_evaluated_ticks"]) for row in windows
                    if row["receipt_zero_output_evaluated_ticks"] != "UNKNOWN"),
                "receipt_zero_output_unknown_windows": sum(
                    1 for row in windows
                    if row["receipt_zero_output_evaluated_ticks"] == "UNKNOWN")},
            "sampled_denominators": {"decoded_frames": len(subset), "evaluated_ticks": len(subset),
                                     "producer_rows": len(mask)}}
    summary["geometry"] = geometry()
    return summary


if __name__ == "__main__":
    ticks = per_tick()
    write_csv(OUT / "per_tick.csv", ticks, PER_TICK_FIELDS)
    result = summarise(ticks)
    write_json(OUT / "summary.json", result)
    print(json.dumps({kind: result[kind] for kind in ("1080p30", "720p60", "POOLED")},
                     indent=1, sort_keys=True)[:1] and "written", file=sys.stderr)
    print(json.dumps(result["POOLED"], indent=1, sort_keys=True))
