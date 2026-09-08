"""Merge the twelve per-(section, arm) G334 job outputs into the two committed CSV artifacts.

Each section is scored by two processes, one per sealed arm, and BOTH write the ROUTE baseline arm
from their own independent decode of the same sealed bytes. Those two ROUTE runs are NOT one cell:
metric (a) is measured against the HELD-OUT segments, and each arm's own LSD_MIN_LEN produces a
different held-out set, so the route's forward and reverse columns differ between them by
construction. They are therefore kept as ROUTEA and ROUTEB, labelled from the job directory, so
every G334 arm is compared against the route on the SAME held-out evidence. Metrics (b), (c) and
(d) do not depend on that set and agree exactly across the pair, which is the determinism check.

Usage:
    python -m scripts.platformkit.tracking.g334_merge <out_root> <evidence_dir>
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ORDER = ("S1", "S2", "S3", "S4", "S5", "S6")


def _label(line: str, arm: str, arm_column: int) -> str:
    """Tag a ROUTE row with the job's arm letter so the two route runs stay distinguishable."""
    parts = line.split(",")
    if parts[arm_column] == "ROUTE":
        parts[arm_column] = "ROUTE" + arm
    return ",".join(parts)


def _rows(paths, arm_column: int):
    """One row per (section, arm, key); a true duplicate is counted and any clash is printed."""
    header, seen, out, clashes, duplicates = None, {}, [], [], 0
    for path in sorted(paths):
        arm = path.parent.name.rsplit("_", 1)[-1]
        lines = path.read_text(encoding="ascii").rstrip("\n").split("\n")
        if not lines or not lines[0]:
            continue
        header = header or lines[0]
        if lines[0] != header:
            raise SystemExit("header mismatch in %s" % path)
        for raw in lines[1:]:
            line = _label(raw, arm, arm_column)
            key = tuple(line.split(",")[:3])
            if key in seen:
                duplicates += 1
                if seen[key] != line:
                    clashes.append((key, seen[key], line))
                continue
            seen[key] = line
            out.append(line)
    for key, first, second in clashes:
        print("CLASH %s\n    kept %s\n    drop %s" % (key, first, second))
    return header, out, clashes, duplicates


def _sort_key(line: str):
    parts = line.split(",")
    section = parts[0]
    return (ORDER.index(section) if section in ORDER else len(ORDER), parts[2] if len(parts) > 2
            else "", parts[1])


def merge(out_root: Path, evidence: Path) -> int:
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "renders").mkdir(exist_ok=True)
    total_dupes = total_clashes = 0
    for name, arm_column in (("metrics.csv", 2), ("perframe.csv", 1)):
        header, rows, clashes, duplicates = _rows(out_root.glob("*/%s" % name), arm_column)
        if header is None:
            raise SystemExit("no %s under %s" % (name, out_root))
        total = sum(len(path.read_text(encoding="ascii").rstrip("\n").split("\n")) - 1
                    for path in sorted(out_root.glob("*/%s" % name)))
        total_dupes += duplicates
        total_clashes += len(clashes)
        if name == "metrics.csv":
            rows.sort(key=lambda line: (ORDER.index(line.split(",")[0]), line.split(",")[2]))
        else:
            rows.sort(key=_sort_key)
        (evidence / name).write_text("\n".join([header] + rows) + "\n", encoding="ascii")
        print("MERGED %s rows=%d from %d job rows" % (name, len(rows), total))
    print("DUPLICATE KEYS n=%d CLASHES n=%d after labelling the two route runs ROUTEA / ROUTEB"
          % (total_dupes, total_clashes))
    for render in sorted(out_root.glob("*/renders/*.jpg")):
        shutil.copyfile(render, evidence / "renders" / render.name)
    print("RENDERS %d" % len(list((evidence / "renders").glob("*.jpg"))))
    return 0


if __name__ == "__main__":
    sys.exit(merge(Path(sys.argv[1]), Path(sys.argv[2])))
