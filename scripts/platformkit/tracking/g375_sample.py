"""G375 stratified even sampler: floor-10 quotas, seeded even draw, blind sheet ids.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2).
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

from scripts.platformkit.tracking.g375_census import read_csv, write_csv

SEED = 375
OFFSET = SEED / 1000.0
FLOOR = 10
TOTAL = 300
FIELDS = ("sheet_id", "game_id", "prefix", "video_id", "offset_s", "source_duration",
          "target_tick_s", "window_start_s", "window_end_s")


def quotas(sizes: dict[str, int], total: int = TOTAL, floor: int = FLOOR) -> dict[str, int]:
    """Floor min(floor, n_p) per prefix, then largest remainder on the surplus."""
    if sum(sizes.values()) < total:
        raise ValueError("eligible frame is smaller than the sealed sample total")
    picked = {key: min(floor, value) for key, value in sizes.items()}
    remaining = total - sum(picked.values())
    if remaining < 0:
        raise ValueError("sealed floor already exceeds the sealed sample total")
    while remaining > 0:
        room = {key: sizes[key] - picked[key] for key in sizes if sizes[key] > picked[key]}
        if not room:
            raise ValueError("every prefix is capped before the sealed total is reached")
        pool = sum(room.values())
        shares = {key: remaining * value / pool for key, value in room.items()}
        base = {key: min(int(value), room[key]) for key, value in shares.items()}
        for key, value in base.items():
            picked[key] += value
        remaining -= sum(base.values())
        if remaining <= 0:
            break
        order = sorted(room, key=lambda key: (-(shares[key] - int(shares[key])), key))
        for key in order:
            if remaining <= 0:
                break
            if picked[key] < sizes[key]:
                picked[key] += 1
                remaining -= 1
    return picked


def even_pick(count: int, quota: int) -> list[int]:
    """Evenly spaced indices with a seeded start; spans the whole prefix, never a head."""
    if quota > count or quota < 1:
        raise ValueError("quota must be between one and the prefix size")
    if quota == count:
        return list(range(count))
    step = count / quota
    picked = [min(count - 1, int(math.floor((index + OFFSET) * step)))
              for index in range(quota)]
    if len(set(picked)) != quota or sorted(picked) != picked:
        raise ValueError("seeded even draw is not strictly increasing and unique")
    return picked


def draw(eligible: list[dict[str, str]], total: int = TOTAL) -> list[dict[str, str]]:
    """Draw the sealed stratified sample and attach opaque shuffled sheet ids."""
    groups: dict[str, list[dict[str, str]]] = {}
    for row in eligible:
        groups.setdefault(row["prefix"], []).append(row)
    for key in groups:
        groups[key].sort(key=lambda row: row["game_id"])
    sizes = {key: len(value) for key, value in groups.items()}
    picked_quotas = quotas(sizes, total)
    selected: list[dict[str, str]] = []
    for key in sorted(groups):
        quota = picked_quotas[key]
        if quota < 1:
            continue
        for index in even_pick(sizes[key], quota):
            selected.append(groups[key][index])
    if len(selected) != total:
        raise ValueError("stratified draw produced %d rows, not %d" % (len(selected), total))
    selected.sort(key=lambda row: row["game_id"])
    if len({row["game_id"] for row in selected}) != total:
        raise ValueError("stratified draw repeated a game id")
    order = list(range(total))
    random.Random(SEED).shuffle(order)
    out: list[dict[str, str]] = []
    for sheet_index, position in enumerate(order):
        row = selected[position]
        start = int(row["offset_s"])
        tick = start + int(float(row["source_duration"]) // 2)
        window = max(0, tick - 2)
        out.append({"sheet_id": "sheet_%04d" % sheet_index, "game_id": row["game_id"],
                    "prefix": row["prefix"], "video_id": row["video_id"],
                    "offset_s": row["offset_s"], "source_duration": row["source_duration"],
                    "target_tick_s": str(tick), "window_start_s": str(window),
                    "window_end_s": str(window + 5)})
    return sorted(out, key=lambda row: row["sheet_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 stratified even sampler")
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--total", type=int, default=TOTAL)
    args = parser.parse_args()
    eligible = [row for row in read_csv(args.census) if row["eligible"] == "1"]
    rows = draw(eligible, args.total)
    write_csv(args.out, rows, FIELDS)
    per_prefix: dict[str, int] = {}
    for row in rows:
        per_prefix[row["prefix"]] = per_prefix.get(row["prefix"], 0) + 1
    print("sampled=%d prefixes=%d eligible_frame=%d" % (
        len(rows), len(per_prefix), len(eligible)))
    for key in sorted(per_prefix):
        print("  %-20s %4d" % (key, per_prefix[key]))


if __name__ == "__main__":
    main()
