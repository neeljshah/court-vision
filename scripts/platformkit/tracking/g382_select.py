"""G382 sealed section and interior-frame selection from a receipt or census."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SECTIONS = 12
TICKS = 5
MIN_VIDEOS = 6
OUT_FIELDS = ("frame_key", "section_id", "video_id", "native_path", "frame_order",
              "section_rank", "interior_rank", "selection_status")


def _field(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if row.get(name, ""):
            return row[name]
    return ""


def _ordered_indices(size: int, count: int, interior: bool = False) -> list[int]:
    """Fixed, unique quantile positions; interior positions exclude both endpoints."""
    if count < 1 or size < count + (2 if interior else 0):
        raise ValueError("insufficient rows for sealed even selection")
    lo, hi = (1, size - 2) if interior else (0, size - 1)
    picks = [int(round(lo + index * (hi - lo) / (count - 1))) if count > 1 else (lo + hi) // 2
             for index in range(count)]
    if len(set(picks)) != count or picks[0] < lo or picks[-1] > hi:
        raise ValueError("even selection was not unique")
    return picks


def read_source(path: Path) -> list[dict[str, str]]:
    """Read the compact G386-style receipt or census projection, never a source store."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = (("section_id",), ("video_id", "game_id"),
                ("frame_order", "frame_index", "tick_index", "frame_no"),
                ("native_path", "frame_path", "path", "source_path"))
    if not rows or any(not _field(rows[0], names) for names in required):
        raise ValueError("receipt/census lacks a required G382 selection column")
    return rows


def select(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Select 12 even sections and five strictly interior ticks per section."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["section_id"]].append(row)
    sections = []
    for section_id, members in grouped.items():
        ordered = sorted(members, key=lambda row: int(_field(row, ("frame_order", "frame_index",
                                                                     "tick_index", "frame_no"))))
        sections.append((section_id, ordered))
    sections.sort(key=lambda item: (_field(item[1][0], ("video_id", "game_id")), item[0]))
    picked = [sections[index] for index in _ordered_indices(len(sections), SECTIONS)]
    videos = {_field(members[0], ("video_id", "game_id")) for _section, members in picked}
    if len(videos) < MIN_VIDEOS:
        raise ValueError("even section draw has fewer than six video ids")
    out: list[dict[str, str]] = []
    for section_rank, (section_id, members) in enumerate(picked, start=1):
        for interior_rank, index in enumerate(_ordered_indices(len(members), TICKS, interior=True),
                                              start=1):
            row = members[index]
            frame_order = _field(row, ("frame_order", "frame_index", "tick_index", "frame_no"))
            frame_key = _field(row, ("frame_key", "frame_id")) or "%s__%s" % (section_id, frame_order)
            out.append({"frame_key": frame_key, "section_id": section_id,
                        "video_id": _field(row, ("video_id", "game_id")),
                        "native_path": _field(row, ("native_path", "frame_path", "path", "source_path")),
                        "frame_order": frame_order, "section_rank": str(section_rank),
                        "interior_rank": str(interior_rank), "selection_status": "PLANNED"})
    if len(out) != SECTIONS * TICKS or len({row["frame_key"] for row in out}) != len(out):
        raise ValueError("sealed selection did not produce 60 unique frames")
    return out


def receipt(rows: list[dict[str, str]], selected: list[dict[str, str]]) -> dict[str, object]:
    """A stable selection receipt to compare before any frame open."""
    body = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"sections": len({row["section_id"] for row in selected}), "frames": len(selected),
            "videos": len({row["video_id"] for row in selected}),
            "selection_sha256": hashlib.sha256(body).hexdigest()}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    rows = read_source(args.source)
    chosen = select(rows)
    write_csv(args.frames, chosen)
    args.receipt.write_text(json.dumps(receipt(rows, chosen), indent=2) + "\n", encoding="utf-8", newline="\n")
    print("G382_SELECT sections=%d frames=%d" % (SECTIONS, len(chosen)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
