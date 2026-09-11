"""Deterministic review controls for the G406 pixel-diagnostic finisher."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

OPAQUE_FIELDS = frozenset({"id", "path", "sha256", "digest", "render_path", "section_id"})

__all__ = ["associate", "blind_before_overlay", "field_scan", "preserve_repeat_parent"]


def _box(row: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return tuple(float(row[field]) for field in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))


def _iou(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    lx1, ly1, lx2, ly2 = _box(left)
    rx1, ry1, rx2, ry2 = _box(right)
    width, height = max(0.0, min(lx2, rx2) - max(lx1, rx1)), max(0.0, min(ly2, ry2) - max(ly1, ry1))
    union = (lx2 - lx1) * (ly2 - ly1) + (rx2 - rx1) * (ry2 - ry1) - width * height
    return 0.0 if union <= 0 else width * height / union


def associate(candidates: Iterable[Mapping[str, Any]], blind: Iterable[Mapping[str, Any]],
              minimum_iou: float = 0.50) -> dict[str, Any]:
    """Greedily retain the lexicographically tied maximum-IoU one-to-one pairs."""
    if minimum_iou != 0.50:
        raise ValueError("iou-threshold-must-remain-0.50")
    left, right = [dict(row) for row in candidates], [dict(row) for row in blind]
    pairs = []
    for candidate in left:
        for person in right:
            value = _iou(candidate, person)
            if value >= minimum_iou:
                pairs.append((value, str(candidate["box_id"]), str(person["person_id"])))
    pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_left, used_right, accepted = set(), set(), []
    for value, candidate_id, person_id in pairs:
        if candidate_id not in used_left and person_id not in used_right:
            used_left.add(candidate_id)
            used_right.add(person_id)
            accepted.append({"box_id": candidate_id, "person_id": person_id, "iou": value})
    return {"matches": accepted,
            "unmatched_boxes": sorted(str(row["box_id"]) for row in left if str(row["box_id"]) not in used_left),
            "unmatched_persons": sorted(str(row["person_id"]) for row in right if str(row["person_id"]) not in used_right),
            "eligible_pairs": [{"box_id": box_id, "person_id": person_id, "iou": value}
                               for value, box_id, person_id in pairs]}


def _time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def blind_before_overlay(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Check that each blind review completion precedes its overlay exposure."""
    for row in rows:
        if _time(str(row["blind_completed_utc"])) >= _time(str(row["overlay_opened_utc"])):
            return False
    return True


def _terms() -> list[str]:
    return ["".join(chr(code) for code in values) for values in
            ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))]


def _scan_value(value: Any, field: str, positions: list[int], offset: int = 0) -> None:
    if field in OPAQUE_FIELDS or isinstance(value, (int, float, bool)) or value is None:
        return
    if isinstance(value, Mapping):
        for child_field, child in value.items():
            _scan_value(child, str(child_field), positions, offset)
        return
    if isinstance(value, list):
        for child in value:
            _scan_value(child, field, positions, offset)
        return
    text = str(value).lower()
    for term in _terms():
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            end = index + len(term)
            left_ok = index == 0 or not text[index - 1].isalnum()
            right_ok = end == len(text) or not text[end].isalnum()
            if left_ok and right_ok:
                positions.append(offset + index)
            start = end


def field_scan(path: Path) -> dict[str, Any]:
    """Scan prose and semantic fields, reporting indices but never matched text."""
    body = path.read_text(encoding="utf-8", errors="replace")
    positions: list[int] = []
    if path.suffix == ".csv":
        for row in csv.DictReader(body.splitlines()):
            for field, value in row.items():
                _scan_value(value, field, positions)
    elif path.suffix in {".json", ".jsonl"}:
        values = [json.loads(line) for line in body.splitlines() if line.strip()] if path.suffix == ".jsonl" else [json.loads(body)]
        for value in values:
            _scan_value(value, "prose", positions)
    else:
        _scan_value(body, "prose", positions)
    return {"path": str(path).replace("\\", "/"), "count": len(positions), "indices": positions}


def preserve_repeat_parent(parent: Mapping[str, Any], additions: Mapping[str, Any]) -> dict[str, Any]:
    """Add G406 repeat fields without removing the parent receipt shape."""
    if "identical" not in parent or "runs" not in parent:
        raise ValueError("repeat-parent-fields-absent")
    result = dict(parent)
    result.update(additions)
    result["identical"] = parent["identical"]
    result["runs"] = parent["runs"]
    return result
