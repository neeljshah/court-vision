"""Read-only G410 population selection and same-window predecessor retention."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

TARGET_CLASSES = ("CLAMP", "SUBPIXEL")
REQUIRED_MASK_FIELDS = frozenset({"draw_kind", "section_id", "frame", "player_id",
                                  "position_source", "source_branch", "matched_event_id"})


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV artifact using its committed ASCII-compatible schema."""
    with path.open(newline="", encoding="utf-8", errors="strict") as handle:
        return list(csv.DictReader(handle))


def ordered_ticks(rows: Iterable[Mapping[str, str]], draw_orders: Mapping[tuple[str, str], int],
                  label: str) -> list[tuple[str, str, int]]:
    """Return distinct selected-class ticks in sealed draw-order then frame order."""
    result: set[tuple[str, str, int]] = set()
    for row in rows:
        if row.get("position_source") != label:
            continue
        if not REQUIRED_MASK_FIELDS <= set(row):
            raise ValueError("target-mask-schema-missing-required-field")
        if not str(row["source_branch"]).strip():
            raise ValueError("target-mask-route-missing")
        result.add((str(row["draw_kind"]), str(row["section_id"]), int(row["frame"])))
    return sorted(result, key=lambda item: (item[0], draw_orders[(item[0], item[1])], item[2]))


def exact_even(items: list[tuple[str, str, int]], count: int = 30) -> list[tuple[str, str, int]]:
    """Return the fixed exact-even draw without replacement or replenishment."""
    if len(items) < count:
        raise ValueError("class-tick-supply-insufficient")
    return [items[floor_index(index, len(items), count)] for index in range(count)]


def floor_index(index: int, size: int, count: int) -> int:
    """Implement floor(j*(N-1)/29+0.5) using integer arithmetic."""
    if size < 1 or count < 2 or not 0 <= index < count:
        raise ValueError("exact-even-index-invalid")
    return (2 * index * (size - 1) + (count - 1)) // (2 * (count - 1))


def draw_by_class(rows: Iterable[Mapping[str, str]],
                  draw_orders: Mapping[tuple[str, str], int]) -> dict[str, list[tuple[str, str, int]]]:
    """Draw each target class independently while preserving shared tick identity."""
    materialized = list(rows)
    return {label: exact_even(ordered_ticks(materialized, draw_orders, label))
            for label in TARGET_CLASSES}


def observation_key(row: Mapping[str, str]) -> tuple[str, str, str, str, str]:
    """Return the preserved section, attempt, frame, track, and event identity."""
    section = str(row.get("section_id", ""))
    attempt = str(row.get("attempt_id", row.get("draw_kind", "")))
    frame = str(row.get("frame", ""))
    track = str(row.get("track_id", row.get("player_id", "")))
    event = str(row.get("event_id", row.get("matched_event_id", "")))
    if not all((section, attempt, frame, track)):
        raise ValueError("observation-key-missing")
    return section, attempt, frame, track, event


def retain_selected_rows(rows: Iterable[Mapping[str, str]],
                         selected: Iterable[tuple[str, str, int]],
                         windows: Mapping[tuple[str, str], tuple[int, int]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Keep selected rows plus only their same-track predecessor within the parent window."""
    selected_set = set(selected)
    materialized = [dict(row) for row in rows]
    seen: set[tuple[str, str, str, str, str]] = set()
    prior: dict[tuple[str, str, str], dict[str, str]] = {}
    retained: list[dict[str, str]] = []
    unknowns: list[dict[str, str]] = []
    for row in sorted(materialized, key=lambda item: (
            item.get("draw_kind", ""), item.get("section_id", ""), int(item.get("frame", "0")),
            item.get("player_id", item.get("track_id", "")))):
        key = observation_key(row)
        if key in seen:
            raise ValueError("duplicate-observation-key")
        seen.add(key)
        tick = (row.get("draw_kind", ""), row.get("section_id", ""), int(row["frame"]))
        parent = (str(row.get("draw_kind", "")), str(row.get("section_id", "")))
        start, end = windows[parent]
        track_key = (parent[0], parent[1], key[3])
        if tick in selected_set:
            retained.append(row)
            predecessor = prior.get(track_key)
            if predecessor is None:
                unknowns.append({"reason": "MISSING_INITIAL_HISTORY", **row})
            else:
                retained.append(predecessor)
        if start <= int(row["frame"]) < end:
            prior[track_key] = row
    return retained, unknowns


def draw_orders_from_launches(rows: Iterable[Mapping[str, str]]) -> dict[tuple[str, str], int]:
    """Build the sealed section order from complete G402 launch records."""
    orders: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.get("status") != "COMPLETE":
            continue
        key = (str(row["draw_kind"]), str(row["section_id"]))
        if key in orders:
            raise ValueError("duplicate-launch-section")
        orders[key] = int(row["draw_order"])
    return orders
