"""G396 scoring driver over the archived truth and the raw rater responses.

Reuses the G392 per-control scorer unchanged so the coordinate protocol is the
one that qualified sol. It never re-dispatches and never moves a bar.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_score as scorer

SET_RATERS = {"practice": ("astra",), "qualification": ("astra", "sol")}


def score(truth: Path, out_root: Path, control_set: str) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Score one control set for exactly the raters that set was dispatched to."""
    truth_rows = tiles.read_csv(truth)
    rows: list[dict[str, str]] = []
    for rater in SET_RATERS[control_set]:
        directory = out_root / ("%s_%s" % (control_set, rater))
        rows.extend(scorer.score_row(row, directory, rater) for row in truth_rows)
    return rows, scorer.summarise(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--set", dest="control_set", required=True, choices=sorted(SET_RATERS))
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = score(args.truth, args.out_root, args.control_set)
    args.scores.parent.mkdir(parents=True, exist_ok=True)
    tiles.write_csv(args.scores, rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
