"""Build the bounded, CPU-only G413 native-box measurement artifacts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import cv2

from scripts.platformkit.tracking.g413_contract import associate, historical_pair_guard, residuals, transform_native


ROOT = Path(__file__).resolve().parents[3]
G406 = ROOT / "docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11"
RECEIVER = Path("C:/Users/neelj/g402_receiver")
LOGICAL_RENDER_ROOT = "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/renders"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(stream.getvalue().encode("utf-8"))


def center(row: dict[str, Any]) -> tuple[float, float]:
    return ((float(row["bbox_x1"]) + float(row["bbox_x2"])) / 2,
            (float(row["bbox_y1"]) + float(row["bbox_y2"])) / 2)


def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + .5))]


def source_rows(draw: list[dict[str, str]], receipts: list[dict[str, str]], out: Path) -> dict[str, Any]:
    by_section = {row["section_id"]: row for row in receipts}
    g406_frames = {row["card_id"]: row for row in read_csv(G406 / "frame_receipts.csv")}
    saved: dict[str, Any] = {}
    rows = []
    for card in draw:
        parent = by_section[card["section_id"]]
        source = RECEIVER / Path(parent["receiver_path"]).name
        capture = cv2.VideoCapture(str(source))
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(card["frame"]))
        ok, image = capture.read()
        pts = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        capture.release()
        status = "OK" if ok else "UNKNOWN"
        if ok:
            saved[card["card_id"]] = image
            width, height = image.shape[1], image.shape[0]
            image_sha = hashlib.sha256(image.tobytes()).hexdigest()
        else:
            width, height, image_sha = "", "", ""
        parent_frame = g406_frames[card["card_id"]]
        delta = abs(pts - float(parent_frame["actual_pts_s"])) if ok else None
        pts_status = "EXACT" if delta is not None and delta <= .001 else "UNKNOWN"
        status = "OK" if status == "OK" and pts_status == "EXACT" else "UNKNOWN"
        rows.append({"card_id": card["card_id"], "section_id": card["section_id"], "frame": card["frame"],
                     "receiver_path": source.as_posix(), "source_bytes": parent["receiver_bytes"],
                     "source_sha256": parent["receiver_sha256"], "decoded_width": width, "decoded_height": height,
                     "decoded_bgr_sha256": image_sha, "actual_pts_s": "%.6f" % pts if ok else "UNKNOWN",
                     "g406_actual_pts_s": parent_frame["actual_pts_s"], "pts_delta_s": delta, "pts_status": pts_status,
                     "frame_index_equal": int(ok), "dimensions_equal": int(ok and width == int(parent_frame["decoded_width"]) and height == int(parent_frame["decoded_height"])),
                     "status": status})
    write_rows(out / "source_receipts.csv", rows)
    return saved


def transformed_rows(producer: list[dict[str, str]], out: Path) -> list[dict[str, Any]]:
    result = []
    for row in producer:
        native = transform_native(row, int(row["native_width"]), int(row["native_height"]), "padded")
        native.update({"original_bbox_x1": row["bbox_x1"], "original_bbox_y1": row["bbox_y1"],
                       "original_bbox_x2": row["bbox_x2"], "original_bbox_y2": row["bbox_y2"],
                       "native_bbox_x1": native["bbox_x1"], "native_bbox_y1": native["bbox_y1"],
                       "native_bbox_x2": native["bbox_x2"], "native_bbox_y2": native["bbox_y2"],
                       "nominal_detector_form": "yes" if "." in row["bbox_x1"] or row["position_source"] == "PREDICTION" else "no"})
        result.append(native)
    write_rows(out / "transformed_rows.csv", result)
    return result


def old_pairs(producer: list[dict[str, str]], comparator: list[dict[str, str]], links: list[dict[str, str]], out: Path) -> None:
    left, right = {row["box_id"]: row for row in producer}, {row["det_id"]: row for row in comparator}
    chosen = [row for row in links if {row["left_set"], row["right_set"]} == {"producer", "comparator"}]
    rows = []
    for link in chosen:
        box_id = link["left_id"] if link["left_set"] == "producer" else link["right_id"]
        det_id = link["right_id"] if link["right_set"] == "comparator" else link["left_id"]
        px, py = center(left[box_id]); dx, dy = center(right[det_id])
        rows.append({"card_id": left[box_id]["card_id"], "box_id": box_id, "det_id": det_id, "iou": link["iou"],
                     "old_dx": px - dx, "old_dy": py - dy, "after_origin_dx": px - dx,
                     "after_origin_dy": (py + 60.0) - dy})
    historical_pair_guard(rows)
    write_rows(out / "old_pair_residuals.csv", rows)


def new_associations(transformed: list[dict[str, Any]], comparator: list[dict[str, str]], out: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [row for row in transformed if row["transform_status"] == "OK"]
    result = associate(valid, comparator)
    boxes, detections = {row["box_id"]: row for row in transformed}, {row["det_id"]: row for row in comparator}
    prior_review = {row["card_id"]: row for row in read_csv(out / "review.csv")} if (out / "review.csv").exists() else {}
    matches = []
    for match in result["matches"]:
        box, det = boxes[match["box_id"]], detections[match["det_id"]]
        px, py = center(box); dx, dy = center(det)
        review = prior_review.get(box["card_id"], {})
        verdict = review.get("review_status", "UNKNOWN")
        visual_adjudication = verdict if verdict in {"correct_object", "wrong_object"} else "UNKNOWN"
        matches.append({"card_id": box["card_id"], "draw_kind": box["draw_kind"], **match,
                        "dx": px - dx, "dy": py - dy, "association_status": "MATCHED",
                        "visual_adjudication": visual_adjudication})
    unmatched = []
    for box_id in result["unmatched_producer"]:
        box = boxes[box_id]
        unmatched.append({"unit_set": "producer", "unit_id": box_id, "card_id": box["card_id"],
                          "reason": "NO_IOU_0_50_MATCH", "status": "UNKNOWN"})
    for box in transformed:
        if box["transform_status"] != "OK":
            unmatched.append({"unit_set": "producer", "unit_id": box["box_id"], "card_id": box["card_id"],
                              "reason": "INVALID_TRANSFORM", "status": "UNKNOWN"})
    for det_id in result["unmatched_comparator"]:
        det = detections[det_id]
        unmatched.append({"unit_set": "comparator", "unit_id": det_id, "card_id": det["card_id"],
                          "reason": "NO_IOU_0_50_MATCH", "status": "UNKNOWN"})
    write_rows(out / "associations.csv", matches or [{"card_id": "UNKNOWN", "association_status": "UNKNOWN"}])
    write_rows(out / "unmatched_boxes.csv", unmatched or [{"unit_set": "UNKNOWN", "status": "UNKNOWN"}])
    return matches, unmatched


def tick_and_residuals(draw: list[dict[str, str]], transformed: list[dict[str, Any]], comparator: list[dict[str, str]],
                       matches: list[dict[str, Any]], out: Path) -> dict[str, Any]:
    by_card = defaultdict(list)
    source_state = {row["card_id"]: row["status"] for row in read_csv(out / "source_receipts.csv")}
    for match in matches:
        by_card[match["card_id"]].append(match)
    ticks, rows = [], []
    for card in draw:
        card_id = card["card_id"]
        prod = [row for row in transformed if row["card_id"] == card_id]
        comp = [row for row in comparator if row["card_id"] == card_id]
        pair = by_card[card_id]
        source_label = "OK" if source_state[card_id] == "OK" else "UNKNOWN"
        ticks.append({**card, "producer_boxes": len(prod), "comparator_boxes": len(comp), "matched_boxes": len(pair),
                      "producer_silence": int(not prod), "comparator_silence": int(not comp),
                      "status": "source_" + source_label + "&transform_accounted&sealed_association"})
        if pair:
            rows.append({"row_type": "frame", "card_id": card_id, "draw_kind": card["draw_kind"], "matched_boxes": len(pair),
                         "median_dx": median(row["dx"] for row in pair), "median_dy": median(row["dy"] for row in pair)})
    write_rows(out / "per_tick.csv", ticks)
    summary = residuals(matches)
    absolute = [abs(float(row[key])) for row in matches for key in ("dx", "dy")]
    for label, subset in [("POOLED", matches)] + [(kind, [row for row in matches if row["draw_kind"] == kind]) for kind in ("1080p30", "720p60")]:
        part = residuals(subset)
        vals = [abs(float(row[key])) for row in subset for key in ("dx", "dy")]
        rows.append({"row_type": "summary", "card_id": label, "matched_boxes": len(subset), **part,
                      "absolute_p50": residuals(subset)["absolute_p50"], "absolute_p90": percentile(vals, .90),
                     "absolute_max": max(vals) if vals else None,
                     "budget_status": "PASS" if part["matched_frames"] >= 30 and abs(part["equal_frame_median_dx"]) <= 5 and abs(part["equal_frame_median_dy"]) <= 5 else "NOT_VALIDATED"})
    write_rows(out / "residuals.csv", rows)
    return {**summary, "matched_boxes": len(matches), "absolute_p50": residuals(matches)["absolute_p50"],
            "absolute_p90": percentile(absolute, .90), "absolute_max": max(absolute) if absolute else None}


def render_review(draw: list[dict[str, str]], frames: dict[str, Any], transformed: list[dict[str, Any]], comparator: list[dict[str, str]],
                  matches: list[dict[str, Any]], out: Path) -> None:
    folder = out / "renders"; folder.mkdir(exist_ok=True)
    review, index = [], []
    match_ids = {row["box_id"] + ":" + row["det_id"] for row in matches}
    for card in draw:
        card_id, image = card["card_id"], frames.get(card["card_id"])
        prod = [row for row in transformed if row["card_id"] == card_id]
        comp = [row for row in comparator if row["card_id"] == card_id]
        if image is None:
            review.append({"card_id": card_id, "overlay_informed": "yes", "review_status": "UNKNOWN", "silence": "UNKNOWN"})
            continue
        canvas = image.copy()
        for row, color, label in [(row, (0, 0, 255), "P") for row in prod] + [(row, (0, 255, 0), "C") for row in comp]:
            p1, p2 = (int(float(row["bbox_x1"])), int(float(row["bbox_y1"]))), (int(float(row["bbox_x2"])), int(float(row["bbox_y2"])))
            cv2.rectangle(canvas, p1, p2, color, 2); cv2.putText(canvas, label + str(row.get("box_id", row.get("det_id"))), p1, cv2.FONT_HERSHEY_SIMPLEX, .35, color, 1)
        render = folder / (card_id + ".jpg")
        render.write_bytes(cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 92])[1].tobytes())
        index.append({"card_id": card_id, "render_path": LOGICAL_RENDER_ROOT + "/" + card_id + ".jpg", "producer_boxes": len(prod), "comparator_boxes": len(comp), "status": "OK"})
        review.append({"card_id": card_id, "overlay_informed": "yes", "review_status": "UNKNOWN", "silence": "yes" if not prod else "no",
                       "producer_extent": ";".join(row["box_id"] + ":UNKNOWN" for row in prod),
                       "comparator_support": ";".join(row["det_id"] + ":UNKNOWN" for row in comp),
                        "wrong_object_matches": ";".join(pair for pair in sorted(match_ids) if pair.startswith(card_id + "_")) or "UNKNOWN",
                        "wrong_object_matches_note": "all sealed associations; not a visual adjudication"})
    write_rows(out / "eye_index.csv", index); write_rows(out / "review.csv", review)


def measure(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    draw = read_csv(G406 / "draw.csv"); producer = read_csv(G406 / "all_masked_rows.csv")
    comparator = read_csv(G406 / "comparator_detections.csv"); links = read_csv(G406 / "associations.csv")
    (out / "draw.csv").write_bytes((G406 / "draw.csv").read_bytes())
    frames = source_rows(draw, read_csv(G406 / "source_receipts.csv"), out)
    transformed = transformed_rows(producer, out); old_pairs(producer, comparator, links, out)
    matches, unmatched = new_associations(transformed, comparator, out)
    stats = tick_and_residuals(draw, transformed, comparator, matches, out)
    render_review(draw, frames, transformed, comparator, matches, out)
    return {"draw": len(draw), "producer": len(producer), "comparator": len(comparator), "matches": len(matches),
            "unmatched": len(unmatched), **stats}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(); result = measure(args.out)
    print("frames=%d producer=%d comparator=%d matches=%d matched_frames=%d" % (result["draw"], result["producer"], result["comparator"], result["matches"], result["matched_frames"]))
