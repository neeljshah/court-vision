"""G385 blind rating: batch files, batch parsing, kappa and blind adjudication.

Sealed by `docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10/
g385_prereg_2026-09-10.md` (SEAL sha256
1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589). Raters see
opaque sheet ids only -- no probability, no proposed decision, no section id.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from scripts.platformkit.tracking.g375_census import read_csv, write_csv
from scripts.platformkit.tracking.g375_rate import (ADJ_FIELDS, FIELDS, LABELS,
                                                    disagreements, final_labels, kappa)

LINE = re.compile(r"(g385_\d{4})\.jpg\s*,\s*([A-Za-z_]+)\s*,\s*([A-Za-z ]*?)\s*,\s*(\d+)\s*$")
BATCH = re.compile(r"g385_rater_([a-z]+)_(\d+)")
BATCH_SIZE = 72


def write_batches(sheet_ids: list[str], sheets: Path, out: Path,
                  size: int = BATCH_SIZE) -> list[Path]:
    """Split the blind sheet list into fixed batches of image paths, in id order."""
    out.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sheet_ids)
    written = []
    for number in range((len(ordered) + size - 1) // size):
        chunk = ordered[number * size:(number + 1) * size]
        path = out / ("batch_%02d.txt" % (number + 1))
        path.write_text("\n".join(str(sheets / (name + ".jpg")) for name in chunk) + "\n",
                        encoding="ascii", newline="\n")
        written.append(path)
    return written


def parse_batch(text: str, rater: str) -> dict[str, dict[str, str]]:
    """Take the last well-formed line per sheet; a token outside the five labels is UNKNOWN."""
    found: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = LINE.search(line.strip())
        if match is None:
            continue
        raw = match.group(2).upper()
        found[match.group(1)] = {
            "sheet_id": match.group(1), "rater": rater,
            "label": raw if raw in LABELS else "UNKNOWN",
            "other_sport": match.group(3).strip().lower(),
            "confidence_permille": match.group(4), "raw_label": match.group(2)}
    return found


def collect(raw_dir: Path) -> list[dict[str, str]]:
    """Read every archived rater log and return one row per rater and sheet."""
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for path in sorted(set(raw_dir.glob("*.log")) | set(raw_dir.glob("*.txt"))):
        match = BATCH.search(path.name)
        if match is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for sheet_id, row in parse_batch(text, match.group(1)).items():
            rows[(match.group(1), sheet_id)] = row
    return [rows[key] for key in sorted(rows)]


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 blind rating parser")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--adjudication", type=Path)
    args = parser.parse_args()
    rows = collect(args.raw)
    write_csv(args.ratings, rows, FIELDS)
    split, pairs = disagreements(rows)
    print("ratings=%d sheets=%d raters=%d joint=%d disagreements=%d" % (
        len(rows), len({row["sheet_id"] for row in rows}),
        len({row["rater"] for row in rows}), len(pairs), len(split)))
    if pairs:
        print("agreement=%.6f kappa=%.6f" % (
            sum(left == right for left, right in pairs) / len(pairs), kappa(pairs)))
    print("DISAGREEMENTS " + " ".join(split))
    if args.labels is not None:
        adjudicated = {row["sheet_id"]: row["final_label"]
                       for row in (read_csv(args.adjudication)
                                   if args.adjudication and args.adjudication.exists() else [])}
        write_csv(args.labels, final_labels(rows, adjudicated), ADJ_FIELDS)


if __name__ == "__main__":
    main()
