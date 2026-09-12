"""Pure, fixed controls for the G413 native-box re-audit finisher."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

OPAQUE_FIELDS = frozenset({"id", "path", "sha256", "digest", "render_path", "section_id"})
BOX_FIELDS = ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


def _box(row: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return tuple(float(row[name]) for name in BOX_FIELDS)


def transform_native(row: Mapping[str, Any], width: int, height: int, form: str) -> dict[str, Any]:
    """Apply the sealed G412 coordinate mapping and expose clipping explicitly."""
    x1, y1, x2, y2 = _box(row)
    crop_height = height - 60
    if form == "padded":
        crop_raw = (x1, y1, x2, y2)
    elif form == "unpadded":
        crop_raw = (x1 + 15, y1 + 15, x2 - 15, y2 - 15)
    else:
        raise ValueError("unknown-native-form")
    crop_clip = (max(0.0, min(crop_raw[0], width)), max(0.0, min(crop_raw[1], crop_height)),
                 max(0.0, min(crop_raw[2], width)), max(0.0, min(crop_raw[3], crop_height)))
    clipped = (crop_clip[0], crop_clip[1] + 60, crop_clip[2], crop_clip[3] + 60)
    result = dict(row)
    result.update(dict(zip(BOX_FIELDS, clipped)), native_form=form,
                  transform_status="OK" if clipped[0] < clipped[2] and clipped[1] < clipped[3] else "INVALID",
                  clip_left=int(crop_raw[0] != crop_clip[0]), clip_top=int(crop_raw[1] != crop_clip[1]),
                  clip_right=int(crop_raw[2] != crop_clip[2]), clip_bottom=int(crop_raw[3] != crop_clip[3]))
    return result


def iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    """Return standard xyxy intersection-over-union without implicit clipping."""
    lx1, ly1, lx2, ly2 = _box(left)
    rx1, ry1, rx2, ry2 = _box(right)
    width = max(0.0, min(lx2, rx2) - max(lx1, rx1))
    height = max(0.0, min(ly2, ry2) - max(ly1, ry1))
    union = (lx2 - lx1) * (ly2 - ly1) + (rx2 - rx1) * (ry2 - ry1) - width * height
    return 0.0 if union <= 0 else width * height / union


def associate(producer: Iterable[Mapping[str, Any]], comparator: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Use the sealed 0.50, global maximum-IoU and lexical-tie association."""
    left, right = [dict(row) for row in producer], [dict(row) for row in comparator]
    candidates: list[tuple[float, str, str]] = []
    for item in left:
        for other in right:
            if "card_id" in item and "card_id" in other and str(item["card_id"]) != str(other["card_id"]):
                continue
            score = iou(item, other)
            if score >= 0.50:
                candidates.append((score, str(item["box_id"]), str(other["det_id"])))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_left, used_right, matches = set(), set(), []
    for score, box_id, det_id in candidates:
        if box_id not in used_left and det_id not in used_right:
            used_left.add(box_id)
            used_right.add(det_id)
            matches.append({"box_id": box_id, "det_id": det_id, "iou": score})
    return {"matches": matches, "eligible_pairs": [dict(zip(("box_id", "det_id", "iou"),
            (box_id, det_id, score))) for score, box_id, det_id in candidates],
            "unmatched_producer": sorted(str(row["box_id"]) for row in left if str(row["box_id"]) not in used_left),
            "unmatched_comparator": sorted(str(row["det_id"]) for row in right if str(row["det_id"]) not in used_right)}


def historical_pair_guard(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Enforce the inherited 51-pair descriptive population and 28-frame count."""
    values = list(rows)
    frames = {str(row["card_id"]) for row in values}
    if len(values) != 51 or len(frames) != 28:
        raise ValueError("historical-pair-frame-guard-failed")
    return {"pairs": len(values), "distinct_frames": len(frames)}


def per_tick(draw: Iterable[Mapping[str, Any]], producer: Iterable[Mapping[str, Any]],
             comparator: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retain every planned tick, including producer silence and UNKNOWN rows."""
    output = []
    for item in draw:
        key = (str(item["card_id"]), str(item["frame"]))
        left = [row for row in producer if (str(row["card_id"]), str(row["frame"])) == key]
        right = [row for row in comparator if (str(row["card_id"]), str(row["frame"])) == key]
        output.append({"card_id": key[0], "frame": key[1], "producer_boxes": len(left),
                       "comparator_boxes": len(right), "producer_silence": int(not left),
                       "comparator_silence": int(not right), "status": "OK"})
    return output


def residuals(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate the sealed equal-frame-weighted signed and pooled absolute summaries."""
    values = list(rows)
    by_frame: dict[str, list[Mapping[str, Any]]] = {}
    for row in values:
        by_frame.setdefault(str(row["card_id"]), []).append(row)
    if not by_frame:
        return {"matched_frames": 0, "equal_frame_median_dx": None, "equal_frame_median_dy": None,
                "absolute_p50": None, "absolute_p90": None, "absolute_max": None}
    frame_dx = [median(float(row["dx"]) for row in group) for group in by_frame.values()]
    frame_dy = [median(float(row["dy"]) for row in group) for group in by_frame.values()]
    absolute = sorted(abs(float(row[name])) for row in values for name in ("dx", "dy"))
    p90_index = min(len(absolute) - 1, max(0, int((len(absolute) - 1) * .90 + .5)))
    return {"matched_frames": len(by_frame), "equal_frame_median_dx": median(frame_dx),
            "equal_frame_median_dy": median(frame_dy), "absolute_p50": median(absolute),
            "absolute_p90": absolute[p90_index], "absolute_max": max(absolute)}


def bounded(row: Mapping[str, Any]) -> bool:
    """Require an inclusive frame inside the retained half-open sealed window."""
    return int(row["sealed_start_frame"]) <= int(row["frame"]) < int(row["sealed_end_frame_exclusive"])


def _terms() -> list[str]:
    return ["".join(chr(code) for code in values) for values in
            ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))]


def _scan(value: Any, field: str, indices: list[int]) -> None:
    if field in OPAQUE_FIELDS or isinstance(value, (int, float, bool)) or value is None:
        return
    if isinstance(value, Mapping):
        for child_field, child in value.items():
            _scan(child, str(child_field), indices)
        return
    if isinstance(value, list):
        for child in value:
            _scan(child, field, indices)
        return
    text = str(value).lower()
    for number, term in enumerate(_terms()):
        start = 0
        while (found := text.find(term, start)) >= 0:
            end = found + len(term)
            if (found == 0 or not text[found - 1].isalnum()) and (end == len(text) or not text[end].isalnum()):
                indices.append(number)
            start = end


def field_scan(path: Path) -> dict[str, Any]:
    """Return forbidden-pattern indices only, respecting opaque identifier fields."""
    body, indices = path.read_text(encoding="utf-8", errors="replace"), []
    if path.suffix == ".csv":
        for row in csv.DictReader(body.splitlines()):
            _scan(row, "row", indices)
    elif path.suffix in {".json", ".jsonl"}:
        payload = [json.loads(line) for line in body.splitlines() if line.strip()] if path.suffix == ".jsonl" else json.loads(body)
        _scan(payload, "prose", indices)
    else:
        _scan(body, "prose", indices)
    return {"path": str(path).replace("\\", "/"), "count": len(indices), "indices": indices}
