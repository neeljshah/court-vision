"""G370 blind usable-court cards and the rating merge.

A card carries only table-derived occupancy evidence: no section id, no gate name,
no threshold, no arm, no admission score. The card-to-section map stays beside the
cards and is never handed to a rater. Cards are ASCII text so a rater reads exactly
what is written.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

GRID_W, GRID_H = 32, 14
RAMP = " .:-=+*#%@"
CARD_MAX_BYTES = 200 * 1024
VERDICTS = ("USABLE", "NOT_USABLE", "UNSURE")


def _positions(table: pd.DataFrame) -> pd.DataFrame:
    if {"x_norm", "y_norm"}.issubset(table.columns):
        frame = table[["x_norm", "y_norm"]].rename(columns={"x_norm": "x", "y_norm": "y"})
    else:
        frame = table[["x_position", "y_position"]].rename(
            columns={"x_position": "x", "y_position": "y"})
        for axis in ("x", "y"):
            span = frame[axis].max() - frame[axis].min()
            frame[axis] = (frame[axis] - frame[axis].min()) / (span if span else 1.0)
    return frame.dropna()


def occupancy(table: pd.DataFrame) -> list[str]:
    """A coarse density map of where the tracked people are over the whole section."""
    frame = _positions(table)
    grid = [[0] * GRID_W for _ in range(GRID_H)]
    for x, y in zip(frame["x"], frame["y"]):
        column = min(max(int(x * GRID_W), 0), GRID_W - 1)
        row = min(max(int(y * GRID_H), 0), GRID_H - 1)
        grid[row][column] += 1
    top = max((value for row in grid for value in row), default=0)
    return ["|" + "".join(RAMP[min(int(value / top * (len(RAMP) - 1)), len(RAMP) - 1)]
                          if top else " " for value in row) + "|" for row in grid]


def card_text(card_id: str, table: pd.DataFrame) -> str:
    """One blind card: counts, per-frame crowd sizes and the occupancy map."""
    per_frame = table.groupby("frame").size()
    counts = table.groupby("player_id").size().sort_values(ascending=False)
    lines = ["CARD {}".format(card_id), "",
             "rows {}".format(len(table)),
             "distinct tracked identities {}".format(len(counts)),
             "frames carrying rows {}".format(int(per_frame.size)),
             "frame index range {} to {}".format(int(table["frame"].min()),
                                                 int(table["frame"].max())),
             "rows per frame min/median/max {}/{}/{}".format(
                 int(per_frame.min()), int(per_frame.median()), int(per_frame.max())),
             "rows per identity (largest first) " + " ".join(
                 str(int(value)) for value in counts.head(12)), "",
             "position spread (producer position field, uncalibrated):"]
    lines.extend(occupancy(table))
    lines.extend(["", "Question: does this card show a sustained stretch of multi-person",
                  "court play -- several distinct tracked identities present together",
                  "across most of the section's frames -- rather than a near-empty,",
                  "single-person, or momentary clip? Answer USABLE, NOT_USABLE or",
                  "UNSURE."])
    return "\n".join(lines) + "\n"


def build(manifest: Path, out_dir: Path, mapping: Path, limit: int) -> None:
    """Write one card per manifest section, evenly spanning the set, plus the map."""
    sections = json.loads(manifest.read_text(encoding="utf-8"))["sections"]
    step = max(len(sections) // limit, 1) if limit else 1
    chosen = [sections[index] for index in range(0, len(sections), step)][:limit or None]
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for order, section in enumerate(chosen):
        card_id = "card_{:04d}".format(order)
        table = pd.read_csv(section["tracking_path"],
                            usecols=["frame", "player_id", "x_norm", "y_norm"])
        payload = card_text(card_id, table).encode("ascii", "replace")
        if len(payload) > CARD_MAX_BYTES:
            raise ValueError("{} is {} bytes".format(card_id, len(payload)))
        (out_dir / (card_id + ".txt")).write_bytes(payload)
        rows.append({"card_id": card_id, "section_id": section["section_id"],
                     "game_id": section["game_id"]})
    with mapping.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("card_id", "section_id", "game_id"))
        writer.writeheader()
        writer.writerows(rows)
    print("cards n={} dir={}".format(len(rows), out_dir))


def _read(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["card_id"].strip(): row["verdict"].strip().upper()
                for row in csv.DictReader(handle) if row.get("card_id")}


def merge(mapping: Path, raters: list[tuple[str, Path]], adjudication: Path | None,
          out: Path) -> None:
    """Join the blind verdicts; a disagreement stays UNRESOLVED until adjudicated."""
    with mapping.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    verdicts = {name: _read(path) for name, path in raters}
    fixed = _read(adjudication) if adjudication and adjudication.exists() else {}
    fields = ("card_id", "section_id", "game_id", *sorted(verdicts), "agreed", "verdict")
    merged = []
    for row in rows:
        cell = {name: verdicts[name].get(row["card_id"], "") for name in verdicts}
        bad = sorted(value for value in cell.values() if value and value not in VERDICTS)
        if bad:
            raise ValueError("{} carries invalid verdict(s) {}".format(row["card_id"], bad))
        values = {value for value in cell.values() if value}
        agreed = bool(cell) and all(cell.values()) and len(values) == 1
        verdict = next(iter(values)) if agreed else fixed.get(row["card_id"], "UNRESOLVED")
        merged.append({**row, **cell, "agreed": int(bool(agreed)), "verdict": verdict})
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(merged)
    tally: dict[str, int] = {}
    for row in merged:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    print("ratings n={} agreed={} {}".format(
        len(merged), sum(row["agreed"] for row in merged), json.dumps(tally, sort_keys=True)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 blind usable-court cards")
    parser.add_argument("command", choices=("build", "merge"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rater", action="append", default=[],
                        help="name=path of a blind verdict csv")
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.manifest, args.out_dir, args.mapping, args.limit)
    else:
        raters = [(item.split("=", 1)[0], Path(item.split("=", 1)[1])) for item in args.rater]
        merge(args.mapping, raters, args.adjudication, args.out)


if __name__ == "__main__":
    main()
