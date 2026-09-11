"""Pure G397 table reconstruction, held-pair accounting, and additive joins."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.platformkit.tracking.g376_schedule import integral, reconstructed_schedule

__all__ = ["evaluated_tick_rows", "held_pair_summary", "enrich_ledger"]


def _rows(path: Path) -> tuple[list[dict[str, str]], list[str], str]:
    try:
        with Path(path).open(encoding="utf-8-sig", newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return [], [], "table_no_header"
            return list(reader), list(reader.fieldnames), ""
    except OSError:
        return [], [], "table_unreadable"


def _player_field(names: Iterable[str]) -> str | None:
    for name in ("player_id", "track_id", "id"):
        if name in names:
            return name
    return None


def _coordinate_fields(names: Iterable[str]) -> tuple[str, str] | None:
    """Resolve the producer's own coordinate column pair; never invent a substitute."""
    names = list(names)
    for pair in (("x", "y"), ("x_position", "y_position"), ("ft_x", "ft_y")):
        if pair[0] in names and pair[1] in names:
            return pair
    return None


def evaluated_tick_rows(ball_path: Path, tracking_path: Path) -> tuple[list[dict[str, Any]], str]:
    """Account for every reconstructed tick; no tracking row creates a zero-output tick."""
    schedule = reconstructed_schedule(Path(ball_path))
    if schedule["reason"]:
        return [], schedule["reason"]
    tracking, names, reason = _rows(Path(tracking_path))
    if reason:
        tracking, names = [], []
    player = _player_field(names)
    grouped: dict[int, set[str]] = defaultdict(set)
    raw: dict[int, int] = defaultdict(int)
    for row in tracking:
        frame = integral(row.get("frame"))
        if frame is not None:
            raw[frame] += 1
            if player and row.get(player, ""):
                grouped[frame].add(row[player])
    return ([{"frame": frame, "state": "EVALUATED", "raw_rows": raw[frame],
              "unique_players": len(grouped[frame]), "emitting": int(bool(raw[frame]))}
             for frame in sorted(schedule["evaluated"])] +
            [{"frame": frame, "state": "SUSPENDED", "raw_rows": raw[frame],
              "unique_players": len(grouped[frame]), "emitting": int(bool(raw[frame]))}
             for frame in sorted(schedule["suspended"])]), ""


def held_pair_summary(ball_path: Path, tracking_path: Path) -> dict[str, Any]:
    """Compute held pairs across adjacent reconstructed evaluated ticks only."""
    schedule = reconstructed_schedule(Path(ball_path))
    if schedule["reason"]:
        return {"status": "UNKNOWN", "reason": schedule["reason"]}
    tracking, names, reason = _rows(Path(tracking_path))
    player, coordinates = _player_field(names), _coordinate_fields(names)
    if reason or not player or coordinates is None:
        return {"status": "UNKNOWN", "reason": reason or "tracking_required_column_absent"}
    by_tick: dict[int, dict[str, set[tuple[str, str]]]] = defaultdict(lambda: defaultdict(set))
    for row in tracking:
        frame = integral(row.get("frame"))
        if frame in schedule["evaluated"] and row.get(player, ""):
            by_tick[frame][row[player]].add((row.get(coordinates[0], ""),
                                             row.get(coordinates[1], "")))
    held = shared = no_shared = 0
    ticks = sorted(schedule["evaluated"])
    for left, right in zip(ticks, ticks[1:]):
        names_shared = set(by_tick[left]) & set(by_tick[right])
        if not names_shared:
            no_shared += 1
        for name in names_shared:
            for pair in by_tick[left][name] & by_tick[right][name]:
                held += 1
            shared += len(by_tick[left][name]) * len(by_tick[right][name])
    no_output = sum(not by_tick[frame] for frame in ticks)
    return {"status": "OK", "coordinate_columns": "/".join(coordinates),
            "held_pairs": held, "shared_pairs": shared,
            "held_share": None if not shared else held / shared,
            "no_shared_pairs": no_shared, "adjacent_evaluated_pairs": max(0, len(ticks) - 1),
            "no_output_ticks": no_output, "evaluated_ticks": len(ticks)}


def enrich_ledger(records: Iterable[Mapping[str, Any]], probes: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Add G397 probe fields without changing supplied rows or silently collapsing attempts."""
    seen: set[str] = set()
    enriched: list[dict[str, Any]] = []
    for source in records:
        row, attempt_id = dict(source), str(source.get("attempt_id", ""))
        if attempt_id in seen:
            raise ValueError("duplicate-attempt-id:%s" % attempt_id)
        seen.add(attempt_id)
        probe = probes.get(attempt_id)
        row.update({"g397_join_status": "MATCH" if probe else "UNKNOWN",
                    "g397_probe_width": None if not probe else probe.get("width"),
                    "g397_probe_height": None if not probe else probe.get("height"),
                    "g397_probe_fps": None if not probe else probe.get("fps")})
        enriched.append(row)
    return enriched
