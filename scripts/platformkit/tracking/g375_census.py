"""G375 corpus sport-purity census: population, source-tag prefix, eligibility.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2). Reads a ledger
SNAPSHOT only; the live append-only ledger and every table are untouched.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

TAG = re.compile(r"^([a-z][a-z_]{2,})-")
FIELDS = ("game_id", "prefix", "sport", "status", "video_id", "offset_s",
          "source_duration", "source_resolution", "finished_at", "eligible",
          "ineligible_reason")
EXCLUDED_FIELDS = ("game_id", "prefix", "reason")


def prefix_of(game_id: str, sport: str) -> str:
    """Sealed rule: the leading lowercase tag before a hyphen, else the sport field."""
    match = TAG.match(game_id or "")
    return match.group(1) if match else (sport or "UNKNOWN")


def parse_unit(game_id: str) -> tuple[str, str] | None:
    """Landed G364 rule: eleven-character video id plus a numeric section offset."""
    if "_s" not in game_id:
        return None
    stem, _, offset = game_id.rpartition("_s")
    if not offset.isdigit() or len(stem) < 11:
        return None
    return stem[-11:], offset


def population(snapshot: Path) -> list[dict]:
    """Collapse the snapshot to unique game ids, keeping the FIRST row of each."""
    seen: dict[str, dict] = {}
    for line in snapshot.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        seen.setdefault(str(entry.get("game_id") or ""), entry)
    seen.pop("", None)
    return [seen[key] for key in sorted(seen)]


def census(rows: list[dict]) -> list[dict[str, str]]:
    """Enumerate every population key with its prefix and eligibility verdict."""
    out: list[dict[str, str]] = []
    for entry in rows:
        game_id = str(entry["game_id"])
        unit = parse_unit(game_id)
        duration = entry.get("source_duration") or 0.0
        reason = ""
        if unit is None:
            reason = "no_video_id_or_offset"
        elif not float(duration) > 0.0:
            reason = "no_source_duration"
        out.append({
            "game_id": game_id,
            "prefix": prefix_of(game_id, str(entry.get("sport") or "")),
            "sport": str(entry.get("sport") or ""),
            "status": str(entry.get("status")),
            "video_id": unit[0] if unit else "",
            "offset_s": unit[1] if unit else "",
            "source_duration": "%.3f" % float(duration or 0.0),
            "source_resolution": str(entry.get("source_resolution")),
            "finished_at": str(entry.get("finished_at")),
            "eligible": "0" if reason else "1",
            "ineligible_reason": reason,
        })
    return out


def write_csv(path: Path, rows: list[dict[str, str]], fields) -> None:
    """Write one LF manifest, header always present even when empty."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read one bounded manifest CSV."""
    with path.open("r", encoding="ascii", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 corpus census")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, required=True)
    args = parser.parse_args()
    rows = census(population(args.snapshot))
    excluded = [{"game_id": row["game_id"], "prefix": row["prefix"],
                 "reason": row["ineligible_reason"]}
                for row in rows if row["eligible"] == "0"]
    write_csv(args.census, rows, FIELDS)
    write_csv(args.excluded, excluded, EXCLUDED_FIELDS)
    per_sport: dict[str, int] = {}
    per_prefix: dict[str, list[int]] = {}
    for row in rows:
        per_sport[row["sport"]] = per_sport.get(row["sport"], 0) + 1
        seen = per_prefix.setdefault(row["prefix"], [0, 0])
        seen[0] += 1
        seen[1] += int(row["eligible"])
    print("population=%d eligible=%d excluded=%d prefixes=%d" % (
        len(rows), len(rows) - len(excluded), len(excluded), len(per_prefix)))
    print("PER SPORT")
    for key in sorted(per_sport):
        print("  %-20s %d" % (key, per_sport[key]))
    print("PER PREFIX total eligible")
    for key in sorted(per_prefix):
        print("  %-20s %5d %5d" % (key, per_prefix[key][0], per_prefix[key][1]))


if __name__ == "__main__":
    main()
