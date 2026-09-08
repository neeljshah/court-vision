"""Tiny CSV writer shared by shot_router's report output (fix 1d LOC split)."""

from __future__ import annotations

import csv
from pathlib import Path


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0]) if rows else ["section"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
