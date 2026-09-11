"""G373 phase 1: record the finisher's blind adjudications.

The finisher views each sheet and decides independently -- no detector output, no
v1 label, and without being shown which primary rater produced which box, so the
adjudication is its own observation rather than a vote between two others.

Input lines are `<12-char prefix>,<LABEL>,<x>,<y>,<w>,<h>,<reason>` exactly as the
raters emit, and this expands them to full frame keys and the sealed ratings
schema with rater=ADJUDICATOR.  The same box validation the raters face applies
here: a VISIBLE row needs an in-frame box, ABSENT/UNKNOWN must carry none.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.platformkit.tracking.g373_rate import RATING_FIELDS, neutralise

ADJUDICATOR = "ADJUDICATOR"


def expand(lines: list[str], keys: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Expand adjudication shorthand into sealed-schema rows; reject the malformed."""
    rows: list[dict] = []
    rejected: list[str] = []
    for raw in lines:
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        parts = [item.strip() for item in text.split(",")]
        if len(parts) < 2 or parts[0] not in keys or parts[1] not in ("VISIBLE", "ABSENT",
                                                                     "UNKNOWN"):
            rejected.append(text)
            continue
        label = parts[1]
        box, tail = parts[2:-1], parts[-1] if len(parts) > 2 else ""
        reason, _ = neutralise(tail[:80])
        if label == "VISIBLE":
            try:
                x, y, w, h = (int(round(float(value))) for value in box)
            except (ValueError, TypeError):
                rejected.append(text)
                continue
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > 1920 or y + h > 1080:
                rejected.append(text)
                continue
            values = {"box_x": x, "box_y": y, "box_w": w, "box_h": h,
                      "cx": x + w / 2.0, "cy": y + h / 2.0}
        else:
            if any(value for value in box):
                rejected.append(text)
                continue
            values = {"box_x": "", "box_y": "", "box_w": "", "box_h": "", "cx": "", "cy": ""}
        rows.append({"frame_key": keys[parts[0]], "rater": ADJUDICATOR, "label": label,
                     "pass": "adjudication", "reason": reason, **values})
    return rows, rejected


def run(args) -> int:
    keys = {row["frame_key"][:12]: row["frame_key"]
            for row in csv.DictReader(Path(args.manifest).open(encoding="utf-8", newline=""))}
    rows, rejected = expand(Path(args.decisions).read_text(encoding="ascii").splitlines(), keys)
    out = Path(args.out)
    seen: set[str] = set()
    if out.exists():
        seen = {row["frame_key"]
                for row in csv.DictReader(out.open(encoding="utf-8", newline=""))}
    fresh = [row for row in rows if row["frame_key"] not in seen]
    exists = out.exists() and out.stat().st_size > 0
    with out.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(RATING_FIELDS), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerows(fresh)
    print(f"ADJUDICATED added={len(fresh)} duplicate={len(rows) - len(fresh)} "
          f"rejected={len(rejected)} total={len(seen) + len(fresh)}")
    for item in rejected[:5]:
        print("  REJECTED " + item[:70])
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_adjudicate")
    for flag in ("--manifest", "--decisions", "--out"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
