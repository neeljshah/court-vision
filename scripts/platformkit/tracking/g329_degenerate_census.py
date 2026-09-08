"""G329 census: pod tracking-daemon rows too thin to be real completions.

Read-only. Consumes a snapshot of the pod append log
``data/tracking/track_daemon_ledger.jsonl`` plus a pod facts capture (one line
per clip, produced by a read-only ``ssh`` probe) and writes the census CSV.

Definitions are frozen by ``docs/evidence/tracking/g329_prereg_2026-09-08.md``:
LOW ROW ``rows`` below 50; DEGENERATE also ``seconds`` below 600; RESUME when the
clip data dir holds a file older than the derived start (``finished_at`` minus
``seconds``); SOURCE GONE when the mp4 is in none of corpus, bridge, quarantine.
Timestamp cells use ISO 8601 basic form so no two-digit field stands alone.

Run: ``python -m scripts.platformkit.tracking.g329_degenerate_census
--log snapshot.jsonl --pod-facts facts.txt --out census.csv
[--projection ledger_projection.csv]``
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone

LOW_ROWS = 50
SHORT_SECONDS = 600
PAD = 6
UNKNOWN = "unknown"
FIELDS = ["clip_id", "sport", "status", "rows", "wall_seconds", "started_utc",
          "finished_utc", "resume", "degenerate", "source_state", "guard_named",
          "class"]
PROJECTION_FIELDS = ["game_id", "rows", "seconds", "finished_at"]


def _pad(value) -> str:
    """Zero-pad an integer cell; a missing value stays an explicit marker."""
    try:
        return "%0*d" % (PAD, int(value))
    except (TypeError, ValueError):
        return "none"


def _utc(epoch) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError, OSError, OverflowError):
        return "none"


def read_log(path: str) -> list:
    """Every readable row of the append log, in file order."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                rows.append(entry)
    return rows


def read_pod_facts(path: str) -> dict:
    """Parse the read-only pod capture: ``id|key=value|key=value|...``."""
    facts = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = [part.strip() for part in line.strip().split("|") if part.strip()]
            if len(parts) < 2:
                continue
            record = {}
            for part in parts[1:]:
                key, _, value = part.partition("=")
                record[key] = value
            facts[parts[0]] = record
    return facts


def row_count(entry: dict):
    """The `rows` field as an int, or None when the log recorded none.

    An absent count is UNKNOWN, never zero: a row the log never described is
    not evidence of a thin run, and guessing zero would invent a LOW ROW.
    """
    try:
        return int(entry["rows"])
    except (KeyError, TypeError, ValueError):
        return None


def low_rows(entries: list) -> list:
    """Every LOW ROW, exhaustive over the append log (no sampling).

    A row whose count is UNKNOWN passes through so it is visible in the census,
    but it is never counted as degenerate and never as data loss.
    """
    return [entry for entry in entries
            if row_count(entry) is None or row_count(entry) < LOW_ROWS]


def is_degenerate(entry: dict) -> bool:
    """A LOW ROW whose wall time is also too short to be a real completion."""
    count = row_count(entry)
    if count is None:
        return False
    try:
        return count < LOW_ROWS and int(entry.get("seconds")) < SHORT_SECONDS
    except (TypeError, ValueError):
        return False


def started(entry: dict):
    """Derived start: the two append-log fields, never a wall-clock guess."""
    try:
        return int(entry["finished_at"]) - int(entry["seconds"])
    except (KeyError, TypeError, ValueError):
        return None


def resume_state(entry: dict, fact: dict) -> str:
    """RESUME when a data-dir file predates the derived start of this run."""
    begin = started(entry)
    stamp = (fact or {}).get("minmtime", "none")
    if stamp in ("none", "", None):
        return "no_data_dir"
    if begin is None:
        return "unknown_start"
    try:
        return "resume" if float(stamp) < begin else "fresh_dir"
    except ValueError:
        return "unknown_start"


def source_state(fact: dict) -> str:
    """GONE only when all three holding places were read and all say absent.

    A clip with no pod facts at all is UNKNOWN, never GONE: an unread holding
    place is not an absent mp4, and UNKNOWN is never counted as data loss.
    """
    fact = fact or {}
    for key, name in (("corpus", "corpus"), ("bridge", "bridge"),
                      ("quar", "quarantine")):
        if fact.get(key) == "yes":
            return name
    if all(fact.get(key) == "no" for key in ("corpus", "bridge", "quar")):
        return "gone"
    return UNKNOWN


def classify(entry: dict) -> str:
    """The failure family, read from the tail the daemon stored on the row."""
    tail = entry.get("tail") or ""
    if not tail:
        return "no_tail_recorded"
    if "No such file or directory" in tail:
        return "runner_absent"
    if "PREFLIGHT FAIL" in tail:
        return "preflight_reject"
    if "Stage 1 produced 0 rows" in tail:
        return "stage1_empty"
    if "Frame " in tail:
        return "killed_midrun"
    return "other"


def build(entries: list, facts: dict) -> list:
    """One census record per LOW ROW, ordered as the append log wrote them."""
    census = []
    for entry in low_rows(entries):
        clip = entry.get("game_id")
        fact = facts.get(clip, {})
        count = row_count(entry)
        census.append({
            "clip_id": clip,
            "sport": entry.get("sport"),
            "status": entry.get("status"),
            "rows": _pad(count) if count is not None else UNKNOWN,
            "wall_seconds": _pad(entry.get("seconds")),
            "started_utc": _utc(started(entry)),
            "finished_utc": _utc(entry.get("finished_at")),
            "resume": resume_state(entry, fact),
            "degenerate": UNKNOWN if count is None
                          else ("true" if is_degenerate(entry) else "false"),
            "source_state": source_state(fact),
            "guard_named": "true" if (fact.get("guardhits") or "0") != "0" else "false",
            "class": classify(entry),
        })
    return census


def table(census: list) -> list:
    """The grouped counts the memo prints, every cell carrying its own n."""
    lines = ["LOW ROWS n=%d" % len(census)]
    for state in ("resume", "fresh_dir", "no_data_dir", "unknown_start"):
        group = [row for row in census if row["resume"] == state]
        if not group:
            continue
        thin = [row for row in group if row["degenerate"] == "true"]
        lost = [row for row in thin if row["source_state"] == "gone"]
        lines.append("  %-13s n=%d  degenerate %d/%d  source gone %d/%d"
                     % (state, len(group), len(thin), len(group),
                        len(lost), len(thin)))
    degenerate = [row for row in census if row["degenerate"] == "true"]
    lines.append("DEGENERATE n=%d of %d LOW ROWS" % (len(degenerate), len(census)))
    families: dict = {}
    for row in degenerate:
        families[row["class"]] = families.get(row["class"], 0) + 1
    for name in sorted(families):
        lines.append("  class %-18s %d/%d" % (name, families[name], len(degenerate)))
    lost = [row for row in degenerate if row["source_state"] == "gone"]
    lines.append("DATA LOSS n=%d of %d degenerate rows (source in no holding place)"
                 % (len(lost), len(degenerate)))
    named = [row for row in lost if row["guard_named"] == "true"]
    lines.append("  volume guard names %d/%d of them as pruned" % (len(named), len(lost)))
    return lines


def projection(entries: list) -> list:
    """Every append-log row, four fields, so the denominator is checkable.

    The census filters; this does not. It is the exhaustiveness receipt (Q7):
    anyone can recount the LOW ROWS from it without the snapshot.
    """
    return [{"game_id": entry.get("game_id"),
             "rows": _pad(row_count(entry)) if row_count(entry) is not None
                     else UNKNOWN,
             "seconds": _pad(entry.get("seconds")),
             "finished_at": _pad(entry.get("finished_at"))}
            for entry in entries]


def _write(path: str, fields: list, records: list) -> None:
    with open(path, "w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--pod-facts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--projection")
    args = parser.parse_args(argv[1:])

    entries = read_log(args.log)
    census = build(entries, read_pod_facts(args.pod_facts))
    _write(args.out, FIELDS, census)
    if args.projection:
        _write(args.projection, PROJECTION_FIELDS, projection(entries))
    print("append-log rows n=%d" % len(entries))
    for line in table(census):
        print(line)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))
