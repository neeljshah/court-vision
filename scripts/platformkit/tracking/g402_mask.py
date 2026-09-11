"""Conservative target masking and denominator accounting for G402."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

MASKED_SOURCES = frozenset({"CLAMP", "HELD", "PREDICTION", "SUBPIXEL", "UNKNOWN"})

__all__ = ["MASKED_SOURCES", "coverage", "held_pairs", "mask_target"]


def _truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def mask_target(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return an additive zero/one target decision without inferring supervision."""
    result = dict(row)
    source = str(row.get("position_source", "UNKNOWN"))
    reasons: list[str] = []
    if source in MASKED_SOURCES:
        reasons.append("PROVENANCE_MASKED")
    if _truth(row.get("repeated_coordinate")):
        reasons.append("REPEATED_COORDINATE")
    event = str(row.get("matched_event_id", "")).strip()
    if not event:
        reasons.append("MATCHED_EVENT_ABSENT")
    elif not _truth(row.get("matched_event_valid")):
        reasons.append("MATCHED_EVENT_INVALID")
    if not str(row.get("matched_box_id", "")).strip():
        reasons.append("MATCHED_BOX_ABSENT")
    if source != "DETECTION":
        reasons.append("NOT_DETECTION")
    result["target_weight"] = 0 if reasons else 1
    result["mask_reason"] = ";".join(reasons) if reasons else "CANDIDATE_ONLY"
    return result


def coverage(decoded_frames: Iterable[int], evaluated_ticks: Iterable[int],
             candidate_rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Name decoded and evaluated denominators even when no candidate emits."""
    decoded = list(decoded_frames)
    evaluated = list(evaluated_ticks)
    if len(decoded) != len(set(decoded)) or len(evaluated) != len(set(evaluated)):
        raise ValueError("duplicate-denominator-key")
    decoded_set, evaluated_set = set(decoded), set(evaluated)
    frames = {int(row["frame"]) for row in candidate_rows}
    if not frames <= decoded_set:
        raise ValueError("candidate-frame-outside-decoded-denominator")
    return {"all_decoded_frames": len(decoded),
            "decoded_frames_with_candidate": len(frames),
            "all_evaluated_ticks": len(evaluated),
            "evaluated_ticks_with_candidate": len(frames & evaluated_set),
            "zero_output_evaluated_ticks": len(evaluated_set - frames)}


def held_pairs(evaluated_ticks: Iterable[int], rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count byte-equal coordinates on adjacent evaluated ticks without bridging gaps."""
    ticks = list(evaluated_ticks)
    if ticks != sorted(ticks) or len(ticks) != len(set(ticks)):
        raise ValueError("evaluated-ticks-must-be-sorted-unique")
    by_tick: dict[int, dict[str, set[tuple[str, str]]]] = defaultdict(lambda: defaultdict(set))
    tick_set = set(ticks)
    for row in rows:
        tick = int(row["frame"])
        track = str(row.get("track_id", row.get("player_id", "")))
        if tick in tick_set and track:
            by_tick[tick][track].add((str(row.get("x", row.get("x_position", ""))),
                                      str(row.get("y", row.get("y_position", "")))))
    held = shared = no_shared = 0
    for left, right in zip(ticks, ticks[1:]):
        common = set(by_tick[left]) & set(by_tick[right])
        if not common:
            no_shared += 1
        for track in common:
            left_points, right_points = by_tick[left][track], by_tick[right][track]
            held += len(left_points & right_points)
            shared += len(left_points) * len(right_points)
    return {"held_pairs": held, "shared_pairs": shared,
            "no_shared_pairs": no_shared, "adjacent_evaluated_pairs": max(0, len(ticks) - 1),
            "zero_output_evaluated_ticks": sum(not by_tick[tick] for tick in ticks)}
