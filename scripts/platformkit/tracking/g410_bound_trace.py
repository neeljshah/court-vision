"""Bound each observer trace to its sealed ticks and archive the overrun digest.

The delivered trace carries only the selected ticks and the one evaluated tick
before each of them, which is all the same-invocation comparison consumes.  The
full trace stays off-tree; its digest, byte count and line count are recorded so
the bounded excerpt can never be mistaken for the whole observation.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g410_measure import write_csv
from scripts.platformkit.tracking.g410_report import parse_trace


def bound_lines(text: str, ticks: set) -> tuple:
    """Return (kept lines, kept tick set) for the sealed ticks plus predecessors."""
    observed = sorted(set(int(line.split(",")[1]) for line in text.splitlines()
                          if line.startswith("M,")))
    keep = set()
    for tick in sorted(ticks):
        if tick not in observed:
            continue
        keep.add(tick)
        position = observed.index(tick)
        if position > 0:
            keep.add(observed[position - 1])
    kept = [line for line in text.splitlines()
            if line and int(line.split(",")[1]) in keep]
    return kept, keep


def emitted_rows(path: Path, keep: set) -> tuple:
    """Return (bounded emitted rows, header) for one replay tracking table."""
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        rows = [r for r in reader if r.get("frame", "").isdigit()
                and int(r["frame"]) in keep]
        return rows, list(reader.fieldnames or [])


def pipeline_clamp_counts(rows: list, post: dict) -> dict:
    """Count emitted positions that differ from the tracker position observed."""
    by_slot = {}
    for (tick, _slot), record in post.items():
        if record["pos"] is not None:
            by_slot[(tick, str(record["player_id"]))] = record["pos"]
    compared = differ = 0
    for row in rows:
        key = (int(row["frame"]), str(row.get("player_id", "")))
        if key not in by_slot:
            continue
        compared += 1
        if (int(float(row["x_position"])), int(float(row["y_position"]))) != (
                int(by_slot[key][0]), int(by_slot[key][1])):
            differ += 1
    return {"emitted_rows_compared": compared,
            "emitted_differs_from_tracker_position": differ}


def main(traces_dir: str, per_row_csv: str, out_dir: str) -> None:
    """Write bounded traces plus one receipt row per full observer trace."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ticks: dict = {}
    with open(per_row_csv, newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            if row.get("role") == "SELECTED":
                ticks.setdefault(row["section_id"], set()).add(int(row["frame"]))
    prior_path = Path(traces_dir).parent / "trace_receipts.csv"
    prior: dict = {}
    if prior_path.exists():
        with prior_path.open(newline="", encoding="ascii") as handle:
            prior = {r["section_id"]: r for r in csv.DictReader(handle)}
    receipts = []
    for path in sorted(Path(traces_dir).glob("*.trace.txt")):
        section = path.name[:-len(".trace.txt")]
        raw = path.read_bytes()
        text = raw.decode("ascii")
        kept, keep = bound_lines(text, ticks.get(section, set()))
        target = out / ("%s.trace.txt" % section)
        target.write_text(chr(10).join(kept) + chr(10), encoding="ascii",
                          newline="")
        emitted_dir = out.parent / "emitted"
        emitted_dir.mkdir(parents=True, exist_ok=True)
        emitted_path = Path(traces_dir) / ("%s.tracking_data.csv" % section)
        if not emitted_path.exists():
            emitted_path = (Path(traces_dir).parent / "emitted"
                            / ("%s.tracking_data.csv" % section))
        rows, _header = emitted_rows(emitted_path, keep)
        write_csv(emitted_dir / ("%s.tracking_data.csv" % section), rows)
        counts = pipeline_clamp_counts(rows, parse_trace(target)["post"])
        receipts.append({
            "section_id": section,
            "full_trace_bytes": prior.get(section, {}).get(
                "full_trace_bytes", len(raw)),
            "full_trace_lines": prior.get(section, {}).get(
                "full_trace_lines", text.count(chr(10))),
            "full_trace_sha256": prior.get(section, {}).get(
                "full_trace_sha256", hashlib.sha256(raw).hexdigest()),
            "sealed_ticks_requested": len(ticks.get(section, set())),
            "sealed_ticks_observed": len(keep),
            "bounded_lines": len(kept),
            "bounded_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "emitted_bounded_sha256": hashlib.sha256(
                (emitted_dir / ("%s.tracking_data.csv" % section)).read_bytes()
            ).hexdigest(),
            **counts,
        })
    write_csv(out.parent / "trace_receipts.csv", receipts)
    print("bounded=%d" % len(receipts))


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])
