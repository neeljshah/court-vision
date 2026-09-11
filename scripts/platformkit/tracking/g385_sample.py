"""G385 section and tick sampler: fixed even interior coverage, never a head slice."""

from __future__ import annotations

import math


SEED = 385
SECTIONS = 30
TICKS_PER_SECTION = 12


def interior_indices(frame_count: int, count: int = TICKS_PER_SECTION) -> list[int]:
    """Return unique strict-interior positions spanning one section."""
    if frame_count < count + 2:
        raise ValueError("section cannot supply the sealed interior tick count")
    last = frame_count - 1
    out = [math.floor((position + 1) * last / (count + 1)) for position in range(count)]
    if len(set(out)) != count or out[0] <= 0 or out[-1] >= last:
        raise ValueError("interior ticks are not unique and strict")
    return out


def even_sections(rows: list[dict[str, str]], count: int = SECTIONS) -> list[dict[str, str]]:
    """Select rows across the sorted full eligible set, requiring ten source videos."""
    ordered = sorted(rows, key=lambda row: (row.get("competition", ""), row.get("video_id", ""),
                                             float(row.get("offset_s", "0")), row.get("section_id", "")))
    if len(ordered) < count:
        raise ValueError("insufficient preserved development-disjoint sections")
    positions = [math.floor((index + 0.5) * len(ordered) / count) for index in range(count)]
    selected = [ordered[index] for index in positions]
    if len({row.get("section_id", "") for row in selected}) != count:
        raise ValueError("section draw is not unique")
    if len({row.get("video_id", "") for row in selected}) < 10:
        raise ValueError("sealed draw covers fewer than ten videos")
    return selected


def frame_plan(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand exactly twelve ticks per pinned section with a stable tick key."""
    if len(sections) != SECTIONS:
        raise ValueError("G385 requires exactly thirty sections")
    out: list[dict[str, str]] = []
    for section in sections:
        for index in interior_indices(int(section["frame_count"])):
            key = "%s:%06d" % (section["section_id"], index)
            out.append({**section, "frame_index": str(index), "tick_key": key})
    if len(out) != SECTIONS * TICKS_PER_SECTION or len({row["tick_key"] for row in out}) != len(out):
        raise ValueError("planned tick denominator is not exactly 360 unique keys")
    return sorted(out, key=lambda row: row["tick_key"])
