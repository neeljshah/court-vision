"""Preparation controls for the G406 person-target pixel diagnostic."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

CARDS_PER_KIND = 30
KINDS = ("1080p30", "720p60")
BOUND_FIELDS = ("sealed_start_frame", "sealed_end_frame_exclusive")

__all__ = ["BOUND_FIELDS", "CARDS_PER_KIND", "KINDS", "exact_even", "join_bounds",
           "retain_silence", "seal_valid", "unchanged_masks"]


def _int(value: Any, field: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError("invalid-" + field) from error


def exact_even(items: Iterable[Mapping[str, Any]], count: int = CARDS_PER_KIND) -> list[dict[str, Any]]:
    """Return the sealed exact-even item positions without replacement."""
    values = [dict(item) for item in items]
    if count != CARDS_PER_KIND:
        raise ValueError("card-count-must-remain-30")
    if len(values) < count:
        raise ValueError("insufficient-sealed-ticks")
    return [dict(values[int(index * (len(values) - 1) / (count - 1) + 0.5)],
                 sealed_ordinal=index)
            for index in range(count)]


def _kind(row: Mapping[str, Any]) -> str:
    return str(row.get("draw_kind", row.get("kind", "")))


def join_bounds(mask_rows: Iterable[Mapping[str, Any]], draw_rows: Iterable[Mapping[str, Any]],
                tick_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Attach authoritative window bounds while refusing a conflicting mask value."""
    draw = {(_kind(row), str(row["section_id"])): dict(row) for row in draw_rows}
    ticks = {(str(row["section_id"])): dict(row) for row in tick_rows}
    output = []
    for source in mask_rows:
        row = dict(source)
        key = (_kind(row), str(row["section_id"]))
        if key not in draw or key[1] not in ticks:
            raise ValueError("authoritative-binding-absent")
        bound = ticks[key[1]]
        for field in BOUND_FIELDS:
            expected = _int(bound.get(field), field)
            supplied = str(row.get(field, "")).strip()
            if supplied and _int(supplied, field) != expected:
                raise ValueError("mask-bound-conflicts-authority")
            row[field] = expected
        frame = _int(row.get("frame"), "frame")
        if not row[BOUND_FIELDS[0]] <= frame < row[BOUND_FIELDS[1]]:
            raise ValueError("mask-frame-outside-authoritative-bound")
        output.append(row)
    return output


def retain_silence(selected: Iterable[Mapping[str, Any]], rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Produce one retained accounting record per selected tick, including silence."""
    by_tick: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_tick[(_kind(row), str(row["section_id"]), _int(row["frame"], "frame"))].append(row)
    output = []
    for tick in selected:
        item = dict(tick)
        key = (_kind(item), str(item["section_id"]), _int(item["frame"], "frame"))
        item["all_rows"] = len(by_tick[key])
        item["candidate_rows"] = sum(_int(row.get("target_weight", 0), "target_weight")
                                     for row in by_tick[key])
        item["silence"] = int(not by_tick[key])
        output.append(item)
    return output


def unchanged_masks(before: Iterable[Mapping[str, Any]], after: Iterable[Mapping[str, Any]]) -> bool:
    """Require the frozen provenance and target fields to remain byte-equivalent."""
    fields = ("draw_kind", "section_id", "frame", "player_id", "position_source",
              "target_weight", "mask_reason")
    left = [tuple(str(row.get(field, "")) for field in fields) for row in before]
    right = [tuple(str(row.get(field, "")) for field in fields) for row in after]
    return left == right


def seal_valid(path: Path) -> bool:
    """Validate a preregistration seal after normalizing CRLF to LF."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"(?:^|\n)SEAL sha256 ([0-9a-f]{64})\n?$", text)
    if match is None:
        return False
    start = match.start() + (1 if text[match.start():match.start() + 1] == "\n" else 0)
    return hashlib.sha256(text[:start].encode("utf-8")).hexdigest() == match.group(1)
