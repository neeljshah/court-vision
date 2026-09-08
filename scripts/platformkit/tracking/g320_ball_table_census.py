"""G320 -- census of every committed ball table with the hardened G314 reader.

SCOPE RULE (pre-registered, `g320_prereg_2026-09-08.md` section 4): every file
tracked by git under `docs/evidence/tracking/` whose name ends in `.csv` is
header-scanned; a file is a BALL TABLE when its header carries BOTH `ball_x2d`
and `ball_y2d`, the per-row coordinate columns the G314 reader classifies.
Exhaustive -- no head slice, no sampling (contract B7).

A table that is a ball table but carries no `ball_inferred` header makes the
hardened reader STOP.  That stop is the census result for that table, recorded
as a status, NOT as a count of zero.  Integer cells are zero-padded to six
digits; a count that does not exist is left empty rather than written as zero.

Image space only.  Nothing here is recall, precision, accuracy or registration,
and no coordinate counted here has ever been checked against an image.

    python -m scripts.platformkit.tracking.g320_ball_table_census <out_csv> [extra.csv ...]
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys

from scripts.platformkit.tracking.g314_ball_inferred_coords import (
    MissingBallInferredHeader, count_ball_table,
)

EVIDENCE_DIR = "docs/evidence/tracking"
BALL_COORD_COLS = ("ball_x2d", "ball_y2d")
FIELDS = ["scope", "table", "rows", "detected", "inferred", "inferred_no_coord", "status"]


def is_ball_table(header_cols) -> bool:
    """The scope predicate: both per-row ball coordinate columns are present."""
    cols = set(header_cols or ())
    return all(c in cols for c in BALL_COORD_COLS)


def header_of(path: str):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return csv.DictReader(fh).fieldnames or []


def committed_csv_files(repo_root: str):
    """Every git-tracked `.csv` under the evidence tree, in git's own order."""
    out = subprocess.check_output(
        ["git", "-C", repo_root, "ls-files", EVIDENCE_DIR], text=True)
    return [p for p in out.splitlines() if p.lower().endswith(".csv")]


def count_data_rows(path: str) -> int:
    """Data rows excluding the header -- countable whether or not the reader stops."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return max(0, sum(1 for _ in csv.reader(fh)) - 1)


def census_row(scope: str, label: str, path: str) -> dict:
    row = {"scope": scope, "table": label, "rows": "%06d" % count_data_rows(path),
           "detected": "", "inferred": "", "inferred_no_coord": "", "status": ""}
    try:
        c = count_ball_table(path)
    except MissingBallInferredHeader:
        row["status"] = "STOP_MISSING_BALL_INFERRED_HEADER"
        return row
    row["detected"] = "%06d" % c["ball_detected"]
    row["inferred"] = "%06d" % c["ball_inferred"]
    row["inferred_no_coord"] = "%06d" % c["inferred_no_coord"]
    row["status"] = "OK"
    return row


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: g320_ball_table_census.py <out_csv> [extra_ball_table.csv ...]")
        return 2
    out_csv, extras = argv[0], argv[1:]
    root = os.getcwd()
    every = committed_csv_files(root)
    ball, with_flag_col, other = [], [], 0
    for rel in every:
        cols = header_of(os.path.join(root, rel))
        if is_ball_table(cols):
            ball.append(rel)
        elif "ball_inferred" in cols:
            with_flag_col.append(rel)
        else:
            other += 1
    print("committed .csv files scanned under %s: n = %d" % (EVIDENCE_DIR, len(every)))
    print("  ball tables (ball_x2d AND ball_y2d present):        n = %d" % len(ball))
    print("  carry a ball_inferred column but are NOT ball tables: n = %d" % len(with_flag_col))
    for rel in with_flag_col:
        print("    OUT OF SCOPE: %s (no per-row ball coordinate columns)" % rel)
    print("  neither:                                            n = %d" % other)

    rows = [census_row("committed", rel, os.path.join(root, rel)) for rel in ball]
    for extra in extras:
        rows.append(census_row("pod_read_only", os.path.basename(extra), extra))
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("")
    for r in rows:
        print("  %-13s %-58s rows=%s detected=%s inferred=%s inferred_no_coord=%s %s"
              % (r["scope"], r["table"], r["rows"], r["detected"] or "-",
                 r["inferred"] or "-", r["inferred_no_coord"] or "-", r["status"]))
    print("\nwrote %s  (n = %d census rows)" % (out_csv, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
