"""Bounded accounting controls for G407 saved trace material."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def bounded_rows(rows: list[dict[str, Any]], start: int, stop: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split sealed rows from raw overruns without dropping either population."""
    sealed, overrun = [], []
    for row in rows:
        frame = int(row["source_frame"])
        (sealed if start <= frame < stop else overrun).append(dict(row))
    return sealed, overrun


def held_pairs(evaluated_tick_ids: list[int], rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count byte-equal coordinate pairs only on adjacent evaluated ticks."""
    schedule = [int(value) for value in evaluated_tick_ids]
    by_frame: dict[int, dict[str, tuple[str, str]]] = defaultdict(dict)
    for row in rows:
        frame = int(row["source_frame"])
        track = str(row["track_id"])
        by_frame[frame][track] = (str(row["x"]), str(row["y"]))
    shared = held = no_output = 0
    for previous, current in zip(schedule, schedule[1:]):
        prior = by_frame.get(previous, {})
        now = by_frame.get(current, {})
        if not now:
            no_output += 1
        for track in sorted(set(prior) & set(now)):
            shared += 1
            held += prior[track] == now[track]
    if schedule and not by_frame.get(schedule[0], {}):
        no_output += 1
    return {"held_pairs": held, "shared_pairs": shared,
            "zero_output_evaluated_ticks": no_output}


def window_counts(decoded_pts: list[float], attempted_ids: list[int],
                  evaluated_ids: list[int], suspension_ids: list[int],
                  rows: list[dict[str, Any]], start: int, stop: int,
                  schedule_status: str = "KNOWN") -> dict[str, Any]:
    """Return named denominators for one sealed source-frame interval."""
    sealed, overrun = bounded_rows(rows, start, stop)
    bounded_attempts = [value for value in attempted_ids if start <= int(value) < stop]
    bounded_evaluated = [value for value in evaluated_ids if start <= int(value) < stop]
    bounded_suspensions = [value for value in suspension_ids if start <= int(value) < stop]
    pair_counts = held_pairs(bounded_evaluated, sealed)
    return {
        "decoded_source_frames": len(decoded_pts),
        "attempted_reads": len(bounded_attempts),
        "evaluated_ticks": len(bounded_evaluated),
        "suspension_ticks": len(bounded_suspensions),
        "raw_overrun_rows": len(overrun),
        "derived_out_of_window_rows": 0,
        "schedule_status": schedule_status,
        **pair_counts,
    }
