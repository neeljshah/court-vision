"""Blind-mark capture, association and adjudication capture for G406."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g406_audit import associate, blind_before_overlay
from scripts.platformkit.tracking.g406_measure import OUT, read_csv, write_csv, write_json

MARKS = OUT / "blind_marks.jsonl"
ADJUDICATIONS = OUT / "adjudications.csv"
ADJ_FIELDS = ["adjudication_id", "card_id", "draw_kind", "section_id", "frame", "subject_kind",
              "subject_id", "position_source", "target_weight", "bbox_x1", "bbox_y1", "bbox_x2",
              "bbox_y2", "verdict", "certainty", "verdict_source", "note", "overlay_opened_utc",
              "adjudicated_utc"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_marks(batch_path: Path) -> dict[str, Any]:
    """Append one blind batch, stamping completion time before any overlay exists."""
    views = {row["card_id"]: row for row in read_csv(OUT / "blind_view_receipts.csv")}
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    stamp = _now()
    seen = {json.loads(line)["card_id"] for line in MARKS.read_text(encoding="utf-8").splitlines()
            } if MARKS.is_file() else set()
    lines = []
    for card in batch:
        if card["card_id"] in seen:
            raise ValueError("card-already-marked-" + card["card_id"])
        view = views[card["card_id"]]
        lines.append(json.dumps({"card_id": card["card_id"], "blind_completed_utc": stamp,
                                 "view_sha256": view["view_sha256"], "grid_step": int(view["grid_step"]),
                                 "native_width": int(view["native_width"]),
                                 "native_height": int(view["native_height"]),
                                 "scope": card.get("scope", "RESOLVABLE_INSTANCES_PLUS_UNCERTAIN_REGIONS"),
                                 "marks": card.get("marks", []), "regions": card.get("regions", []),
                                 "note": card.get("note", "")}, sort_keys=True))
    MARKS.parent.mkdir(parents=True, exist_ok=True)
    with open(MARKS, "a", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line + "\n")
    return {"appended": len(lines), "blind_completed_utc": stamp,
            "total": len(seen) + len(lines)}


def _subjects() -> dict[str, dict[str, Any]]:
    subjects = {}
    for row in read_csv(OUT / "all_masked_rows.csv"):
        subjects[row["box_id"]] = dict(row, subject_kind="PRODUCER_ROW", subject_id=row["box_id"])
    for row in read_csv(OUT / "comparator_detections.csv"):
        subjects[row["det_id"]] = dict(row, subject_kind="COMPARATOR_BOX", subject_id=row["det_id"],
                                       position_source="", target_weight="")
    return subjects


def _expand(key: str, subjects: dict[str, dict[str, Any]]) -> list[str]:
    """Expand one id or an inclusive id range such as 720p60_03_d05-d12."""
    if key not in subjects or "-" not in key.rsplit("_", 1)[-1]:
        return [key]
    head, span = key.rsplit("_", 1)
    low, high = span.split("-")
    prefix = "".join(character for character in low if character.isalpha())
    start, stop = int(low[len(prefix):]), int(high[len(prefix):])
    return ["%s_%s%02d" % (head, prefix, index) for index in range(start, stop + 1)]


def record_adjudications(batch_path: Path) -> dict[str, Any]:
    """Append per-card adjudications with the overlay-exposure and decision timestamps."""
    batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    subjects = _subjects()
    stamp = _now()
    rows = read_csv(ADJUDICATIONS) if ADJUDICATIONS.is_file() else []
    seen = {row["card_id"] for row in rows}
    added = 0
    for card in batch:
        if card["card_id"] in seen:
            raise ValueError("card-already-adjudicated-" + card["card_id"])
        for key, value in card["verdicts"].items():
            for subject_id in _expand(key, subjects):
                source = subjects.get(subject_id, {"subject_kind": "PRODUCER_SILENCE"})
                rows.append({"adjudication_id": "%s#%s" % (card["card_id"], subject_id),
                             "card_id": card["card_id"], "draw_kind": card["card_id"].split("_")[0],
                             "section_id": source.get("section_id", ""),
                             "frame": source.get("frame", ""),
                             "subject_kind": source["subject_kind"], "subject_id": subject_id,
                             "position_source": source.get("position_source", ""),
                             "target_weight": source.get("target_weight", ""),
                             "bbox_x1": source.get("bbox_x1", ""), "bbox_y1": source.get("bbox_y1", ""),
                             "bbox_x2": source.get("bbox_x2", ""), "bbox_y2": source.get("bbox_y2", ""),
                             "verdict": value[0], "certainty": value[1],
                             "verdict_source": "OVERLAY_ADJUDICATION",
                             "note": value[2] if len(value) > 2 else "",
                             "overlay_opened_utc": card["overlay_opened_utc"],
                             "adjudicated_utc": stamp})
                added += 1
    write_csv(ADJUDICATIONS, rows, ADJ_FIELDS)
    return {"cards": len(batch), "appended": added, "total": len(rows)}


def stage_autofill() -> dict[str, Any]:
    """Carry every blind-corroborated comparator box into the adjudication table.

    These rows are not fresh overlay judgments: the box already matched a person
    instance marked before any overlay existed, so the blind mark is the verdict.
    """
    subjects = _subjects()
    rows = read_csv(ADJUDICATIONS)
    have = {row["subject_id"] for row in rows}
    stamp = _now()
    added = 0
    for pair in read_csv(OUT / "associations.csv"):
        if pair["left_set"] != "comparator" or pair["right_set"] != "blind":
            continue
        if pair["left_id"] in have:
            continue
        source = subjects[pair["left_id"]]
        rows.append({"adjudication_id": "%s#%s" % (pair["card_id"], pair["left_id"]),
                     "card_id": pair["card_id"], "draw_kind": pair["card_id"].split("_")[0],
                     "section_id": "", "frame": "", "subject_kind": "COMPARATOR_BOX",
                     "subject_id": pair["left_id"], "position_source": "", "target_weight": "",
                     "bbox_x1": source["bbox_x1"], "bbox_y1": source["bbox_y1"],
                     "bbox_x2": source["bbox_x2"], "bbox_y2": source["bbox_y2"],
                     "verdict": "PERSON", "certainty": "CERTAIN",
                     "verdict_source": "BLIND_MARK_CORROBORATION",
                     "note": "matched blind mark " + pair["right_id"] + " at IoU " + pair["iou"],
                     "overlay_opened_utc": "", "adjudicated_utc": stamp})
        added += 1
        have.add(pair["left_id"])
    write_csv(ADJUDICATIONS, rows, ADJ_FIELDS)
    return {"appended": added, "total": len(rows)}


def _marks() -> dict[str, dict[str, Any]]:
    return {json.loads(line)["card_id"]: json.loads(line)
            for line in MARKS.read_text(encoding="utf-8").splitlines() if line.strip()}


def stage_associate() -> dict[str, Any]:
    """Publish every producer/comparator/blind association and every unmatched box."""
    marks = _marks()
    producer: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "all_masked_rows.csv"):
        producer.setdefault(row["card_id"], []).append(dict(row, box_id=row["box_id"]))
    comparator: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "comparator_detections.csv"):
        comparator.setdefault(row["card_id"], []).append(dict(row, box_id=row["det_id"]))
    pairs, unmatched = [], []
    for card in sorted(marks):
        blind = [dict(mark, person_id=mark["person_id"]) for mark in marks[card]["marks"]]
        sets = {"producer": producer.get(card, []), "comparator": comparator.get(card, [])}
        for left_name, left in sets.items():
            for right_name, right in (("blind", blind), ("comparator", sets["comparator"])):
                if left_name == right_name:
                    continue
                right_rows = [dict(row, person_id=row.get("person_id", row.get("box_id"))) for row in right]
                result = associate(left, right_rows)
                for match in result["matches"]:
                    pairs.append({"card_id": card, "left_set": left_name, "right_set": right_name,
                                  "left_id": match["box_id"], "right_id": match["person_id"],
                                  "iou": round(match["iou"], 6)})
                for box_id in result["unmatched_boxes"]:
                    unmatched.append({"card_id": card, "set": left_name, "box_id": box_id,
                                      "against": right_name})
                for person_id in result["unmatched_persons"]:
                    unmatched.append({"card_id": card, "set": right_name, "box_id": person_id,
                                      "against": left_name})
    write_csv(OUT / "associations.csv", pairs,
              ["card_id", "left_set", "right_set", "left_id", "right_id", "iou"])
    write_csv(OUT / "unmatched_boxes.csv", unmatched, ["card_id", "set", "box_id", "against"])
    return {"pairs": len(pairs), "unmatched": len(unmatched), "cards": len(marks),
            "blind_instances": sum(len(value["marks"]) for value in marks.values()),
            "uncertain_regions": sum(len(value["regions"]) for value in marks.values())}


def stage_order() -> dict[str, Any]:
    """Prove every blind completion precedes its overlay exposure."""
    marks = _marks()
    rows = []
    for row in read_csv(ADJUDICATIONS):
        if row["verdict_source"] != "OVERLAY_ADJUDICATION":
            continue
        rows.append({"card_id": row["card_id"],
                     "blind_completed_utc": marks[row["card_id"]]["blind_completed_utc"],
                     "overlay_opened_utc": row["overlay_opened_utc"]})
    ordered = blind_before_overlay(rows)
    write_csv(OUT / "blind_order_receipt.csv", rows,
              ["card_id", "blind_completed_utc", "overlay_opened_utc"])
    return {"rows": len(rows), "blind_before_overlay": int(ordered)}


if __name__ == "__main__":
    name = sys.argv[1]
    if name in {"marks", "adjudicate"}:
        outcome = (record_marks if name == "marks" else record_adjudications)(Path(sys.argv[2]))
    else:
        outcome = {"associate": stage_associate, "order": stage_order,
                   "autofill": stage_autofill}[name]()
    write_json(OUT / "runtime_receipts" / ("stage_" + name + ".json"), outcome)
    print(json.dumps(outcome, sort_keys=True))
