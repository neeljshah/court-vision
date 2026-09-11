"""G402 native-pixel audit over the exact sealed even evaluated-tick draw."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

import cv2

CARDS_PER_KIND = 30
KINDS = ("1080p30", "720p60")
COLOURS = {1: (0, 200, 0), 0: (0, 0, 220)}
AUDIT_FIELDS = ("card_id", "draw_kind", "section_id", "sealed_start_frame",
                "sealed_end_frame_exclusive", "frame", "player_id", "bbox_x1",
                "bbox_y1", "bbox_x2", "bbox_y2", "native_width", "native_height",
                "box_within_frame", "position_source", "matched_event_id",
                "matched_event_valid", "repeated_coordinate", "target_weight", "mask_reason")
EYE_FIELDS = ("card_id", "draw_kind", "section_id", "sealed_start_frame",
              "sealed_end_frame_exclusive", "frame", "sealed_ordinal", "evaluated_tick",
              "emitted_rows", "candidate_rows", "silent", "bbox_count",
              "nondegenerate_bbox_count", "native_width", "native_height", "render_path",
              "render_sha256", "render_bytes", "status")


def read_rows(path: Path) -> list:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def exact_even(items: list, count: int = CARDS_PER_KIND) -> list:
    """Return preregistered floor(j*(N-1)/(count-1)+0.5) positions."""
    if len(items) < count:
        raise ValueError("sealed-decision-set-insufficient")
    return [(int(index * (len(items) - 1) / (count - 1) + 0.5),
             items[int(index * (len(items) - 1) / (count - 1) + 0.5)])
            for index in range(count)]


def sealed_pool(evidence: Path, kind: str) -> list:
    """Order bounded receipt ticks by preregistered draw order, then tick."""
    plans = [row for row in read_rows(evidence / "draw.csv") if row["draw_kind"] == kind]
    ticks = {row["section_id"]: row for row in read_rows(evidence / "evaluated_ticks.csv")}
    pool = []
    for plan in sorted(plans, key=lambda row: int(row["draw_order"])):
        section = plan["section_id"]
        bounds = ticks.get(section, {})
        if bounds.get("schedule") != "COMPLETE":
            continue
        start, end = int(bounds["sealed_start_frame"]), int(bounds["sealed_end_frame_exclusive"])
        receipt = evidence / "raw_tables" / kind / section / "evaluated_tick_receipt.json"
        values = json.loads(receipt.read_text(encoding="utf-8")).get("evaluated_tick_ids") or []
        pool.extend((section, tick) for tick in sorted(int(value) for value in values)
                    if start <= tick < end)
    return pool


def box(row: dict) -> list[int]:
    """Read an emitted detector box and refuse a degenerate card record."""
    try:
        value = [int(float(row[key])) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("audit-box-missing") from error
    if value[0] >= value[2] or value[1] >= value[3]:
        raise ValueError("audit-box-degenerate")
    return value


def grab(source: Path, frame_index: int):
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return None
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, image = capture.read()
    capture.release()
    return image if ok else None


def draw_card(image, rows: list, label: str):
    for row in rows:
        value = box(row)
        colour = COLOURS[int(row["target_weight"])]
        cv2.rectangle(image, (value[0], value[1]), (value[2], value[3]), colour, 2)
        cv2.putText(image, "%s/%s" % (row["position_source"], row["mask_reason"].split(";")[0]),
                    (value[0], max(14, value[1] - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    colour, 1, cv2.LINE_AA)
    cv2.putText(image, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
                cv2.LINE_AA)
    return image


def write_csv(path: Path, fields: tuple, rows: list) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--quality", type=int, default=50)
    parser.add_argument("--sealed-fix", action="store_true")
    args = parser.parse_args()
    evidence, receiver = Path(args.evidence), Path(args.receiver)
    renders = evidence / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    plan = {row["section_id"]: row for row in read_rows(evidence / "draw.csv")}
    ticks = {row["section_id"]: row for row in read_rows(evidence / "evaluated_ticks.csv")}
    masks = defaultdict(list)
    for row in read_rows(evidence / "target_mask.csv"):
        masks[(row["draw_kind"], row["section_id"], int(row["frame"]))].append(row)
    audit, index = [], []
    for kind in KINDS:
        for card_ordinal, (sealed_ordinal, (section, frame)) in enumerate(
                exact_even(sealed_pool(evidence, kind))):
            card = "%s_%02d" % (kind, card_ordinal)
            prior, out = renders / (card + ".jpg"), renders / (card + ".jpg")
            if args.sealed_fix and prior.is_file():
                archived = evidence / "renders_pre_fix1c" / prior.name
                archived.parent.mkdir(parents=True, exist_ok=True)
                if not archived.exists():
                    shutil.copy2(prior, archived)
            rows, bounds = masks[(kind, section, frame)], ticks[section]
            source = receiver / Path(plan[section]["source_path"]).name
            image = grab(source, frame) if source.is_file() else None
            entry = {"card_id": card, "draw_kind": kind, "section_id": section,
                     "sealed_start_frame": bounds["sealed_start_frame"],
                     "sealed_end_frame_exclusive": bounds["sealed_end_frame_exclusive"],
                     "frame": frame, "sealed_ordinal": sealed_ordinal, "evaluated_tick": 1,
                     "emitted_rows": len(rows), "candidate_rows": sum(int(row["target_weight"])
                     for row in rows), "silent": int(not rows), "bbox_count": len(rows),
                     "nondegenerate_bbox_count": len(rows), "native_width": 0, "native_height": 0,
                     "render_path": "", "render_sha256": "", "render_bytes": 0}
            if image is None:
                entry["status"] = "NATIVE_FRAME_UNAVAILABLE"
                index.append(entry)
                continue
            height, width = image.shape[:2]
            values = [box(row) for row in rows]
            if len(values) != entry["nondegenerate_bbox_count"]:
                raise ValueError("audit-box-count-mismatch")
            entry.update(native_width=width, native_height=height, status="OK")
            label = "%s %s f=%d rows=%d%s" % (kind, section, frame, len(rows),
                                                " SILENT" if not rows else "")
            cv2.imwrite(str(out), draw_card(image, rows, label),
                        [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
            body = out.read_bytes()
            entry.update(render_path="renders/" + out.name, render_bytes=len(body),
                         render_sha256=hashlib.sha256(body).hexdigest())
            index.append(entry)
            for row, value in zip(rows, values):
                inside = int(0 <= value[0] < value[2] <= width and 0 <= value[1] < value[3] <= height)
                audit.append({"card_id": card, "draw_kind": kind, "section_id": section,
                              "sealed_start_frame": bounds["sealed_start_frame"],
                              "sealed_end_frame_exclusive": bounds["sealed_end_frame_exclusive"],
                              "frame": frame, "player_id": row["player_id"],
                              "bbox_x1": value[0], "bbox_y1": value[1], "bbox_x2": value[2],
                              "bbox_y2": value[3], "native_width": width, "native_height": height,
                              "box_within_frame": inside, "position_source": row["position_source"],
                              "matched_event_id": row["matched_event_id"],
                              "matched_event_valid": row["matched_event_valid"],
                              "repeated_coordinate": row["repeated_coordinate"],
                              "target_weight": row["target_weight"], "mask_reason": row["mask_reason"]})
    write_csv(evidence / "pixel_audit.csv", AUDIT_FIELDS, audit)
    write_csv(evidence / "eye_index.csv", EYE_FIELDS, index)
    out = {"cards": len(index), "rendered": sum(item["status"] == "OK" for item in index),
           "silent_cards": sum(int(item["silent"]) for item in index), "audited_boxes": len(audit),
           "boxes_outside_native_frame": sum(not int(item["box_within_frame"]) for item in audit),
           "degenerate_boxes": sum(int(item["bbox_x1"]) >= int(item["bbox_x2"]) or
                                   int(item["bbox_y1"]) >= int(item["bbox_y2"]) for item in audit),
           "per_kind": {kind: sum(item["draw_kind"] == kind for item in index) for kind in KINDS}}
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
