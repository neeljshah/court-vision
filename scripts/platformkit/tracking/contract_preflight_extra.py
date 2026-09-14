"""contract_preflight_extra.py -- Q08 correction: two cheap checks split out here to
keep contract_preflight.py under the 300 LOC rail.

removed_artifact catches the G386 class: a tracked evidence/artifact path deleted or
renamed relative to --base without an alias. row_duplication catches the G372 class: a
passed .jsonl/.csv artifact that is mostly duplicate rows, or a column meant to be a
unique key (game_id/section_id/key) that mostly repeats one value.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from collections import Counter
from pathlib import Path

DUP_KEY_COLUMNS = ("game_id", "section_id", "key")
DUP_ROW_SHARE = 0.50
DUP_KEY_SHARE = 0.90


def check_removed_artifact(paths: list[Path], base: str) -> tuple[bool, str, list[dict]]:
    # Merge-base diff (base...HEAD), not base's tip vs the working tree: a worktree
    # branched off an older master and not yet rebased must not see master's OWN later,
    # unrelated commits under docs/evidence as if this lane had deleted them (measured:
    # a 7-commits-behind worktree flagged 10 files other lanes added to master since).
    dirs = {"docs/evidence"}
    for path in paths:
        parent = path.parent.as_posix()
        if parent and parent != ".":
            dirs.add(parent)
    result = subprocess.run(["git", "diff", "--name-status", base + "...HEAD", "--"] + sorted(dirs),
                             capture_output=True, text=True)
    hits = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if fields and fields[0] and fields[0][0] in ("D", "R"):
            hits.append({"status": fields[0], "paths": fields[1:]})
    ok = not hits
    detail = ("no removed/renamed artifacts under %d dir(s)" % len(dirs) if ok else
              "artifact removed or renamed without alias: " + "; ".join(
                  "%s %s" % (h["status"], " -> ".join(h["paths"])) for h in hits))
    return ok, detail, hits


def _rows_of(path: Path) -> list | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".jsonl":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                return None
        return rows
    if path.suffix == ".csv":
        return list(csv.DictReader(io.StringIO(text)))
    return None


def check_row_duplication(paths: list[Path]) -> tuple[bool, str, list[dict]]:
    hits = []
    for path in paths:
        if path.suffix not in (".jsonl", ".csv"):
            continue
        rows = _rows_of(path)
        if not rows:
            continue
        n = len(rows)
        serialized = [json.dumps(row, sort_keys=True) for row in rows]
        dup_share = 1 - (len(set(serialized)) / n)
        if dup_share > DUP_ROW_SHARE:
            hits.append({"path": path.as_posix(), "reason": "duplicate rows",
                         "share": round(dup_share, 4)})
            continue
        if not isinstance(rows[0], dict):
            continue
        for col in DUP_KEY_COLUMNS:
            if col not in rows[0]:
                continue
            counts = Counter(row.get(col) for row in rows if isinstance(row, dict))
            top = counts.most_common(1)[0][1] if counts else 0
            if top / n > DUP_KEY_SHARE:
                hits.append({"path": path.as_posix(), "reason": "column %r repeats" % col,
                             "share": round(top / n, 4)})
                break
    ok = not hits
    detail = "no row duplication over checked artifacts" if ok else "; ".join(
        "%s: %s (%.2f)" % (d["path"], d["reason"], d["share"]) for d in hits)
    return ok, detail, hits
