"""G387 sealed blind-rater output parser; empty and UNKNOWN observations are retained."""
from __future__ import annotations

import csv
from pathlib import Path

FIELDS = ("rater", "opaque_id", "physical_id", "state", "x", "y", "x2", "y2", "mid_x", "mid_y", "reason")
STATES = {"VISIBLE", "ABSENT", "UNKNOWN"}


def read(path: Path, expected_rater: str, opaque_ids: set[str]) -> list[dict[str, str]]:
    """Read one rater file without dropping empty or uncertain frame observations."""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or tuple(rows[0]) != FIELDS:
        raise ValueError("rating schema differs from the sealed G387 schema")
    output, seen = [], set()
    for row in rows:
        if row["rater"] != expected_rater or row["opaque_id"] not in opaque_ids:
            raise ValueError("rating identity is outside the sealed packet")
        if row["state"] not in STATES:
            raise ValueError("rating state is not retained")
        key = (row["opaque_id"], row["physical_id"])
        if key in seen:
            raise ValueError("duplicate frame and physical id")
        seen.add(key)
        if row["state"] == "VISIBLE":
            if not row["physical_id"] or any(row[name] == "" for name in FIELDS[4:10]):
                raise ValueError("visible rating lacks required native clicks")
            for name in FIELDS[4:10]:
                float(row[name])
        output.append({name: row[name] for name in FIELDS})
    if {row["opaque_id"] for row in output} != opaque_ids:
        raise ValueError("a frame has no retained rater observation")
    return output
