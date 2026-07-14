"""scripts.platformkit.live_edge.bus -- append-only event bus (LIVE-EDGE A1).

One row per captured event: {source, ts_captured, ts_knowable, payload}.
Written to data/omni/live_edge/bus/<date>.jsonl (date = ts_knowable's UTC date),
via the shared io_atomic.append_jsonl_atomic helper (reused, not reinvented --
same tmp+os.replace crash-safety every other ledger in this repo uses).

ts_knowable is the HONEST report/capture timestamp -- never event time (L-S2
point-in-time rail). Capture-time ingesters (bus_ingest.py) are responsible for
picking the right source field; this module just persists what it's given.

Reader: read_events() takes an as-of cursor (byte-free: line-count offset into
one date file) and an optional asof cutoff on ts_knowable, so a replay can
walk the bus exactly as a live consumer would have seen it. FileCursor persists
{key: line_count} to disk so a resumed process picks up where it left off --
shared by both the bus reader and bus_ingest.py's per-source-file tailing.

INVARIANTS: stdlib + io_atomic only; ASCII stdout; <=300 LOC; no $ fields;
never writes data/registry/.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic, write_text_atomic

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BUS_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "bus"
CURSOR_DIR = BUS_DIR / "_cursors"


def bus_path(date: str, *, bus_dir: pathlib.Path = BUS_DIR) -> pathlib.Path:
    """data/omni/live_edge/bus/<date>.jsonl for a YYYY-MM-DD date string."""
    return bus_dir / f"{date}.jsonl"


def _row(source: str, ts_captured: str, ts_knowable: str, payload: Any) -> Dict[str, Any]:
    return {
        "source": source,
        "ts_captured": ts_captured,
        "ts_knowable": ts_knowable,
        "payload": payload,
    }


def append_event(
    source: str,
    ts_captured: str,
    ts_knowable: str,
    payload: Any,
    *,
    date: Optional[str] = None,
    bus_dir: pathlib.Path = BUS_DIR,
) -> Dict[str, Any]:
    """Append one event row. date defaults to ts_knowable's UTC date (YYYY-MM-DD)."""
    row = _row(source, ts_captured, ts_knowable, payload)
    d = date or ts_knowable[:10]
    append_jsonl_atomic(bus_path(d, bus_dir=bus_dir), row, encoding="utf-8")
    return row


def append_events(
    rows: List[Dict[str, Any]],
    *,
    bus_dir: pathlib.Path = BUS_DIR,
) -> int:
    """Append many rows (each a kwargs dict for append_event). Returns count appended.

    Groups by target date-file and does ONE read + ONE atomic write per file
    (not one append_jsonl_atomic call per row) -- a backfill/replay can hand
    this hundreds of rows for the same date without O(n^2) rewrite cost.
    """
    if not rows:
        return 0
    by_date: Dict[str, List[str]] = {}
    for r in rows:
        d = r.get("date") or str(r["ts_knowable"])[:10]
        line = json.dumps(_row(r["source"], r["ts_captured"], r["ts_knowable"], r["payload"]),
                          ensure_ascii=True, sort_keys=True)
        by_date.setdefault(d, []).append(line)
    n = 0
    for d, lines in by_date.items():
        path = bus_path(d, bus_dir=bus_dir)
        existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        write_text_atomic(path, existing + "\n".join(lines) + "\n")
        n += len(lines)
    return n


def read_events(
    date: str,
    *,
    asof: Optional[str] = None,
    offset: int = 0,
    bus_dir: pathlib.Path = BUS_DIR,
) -> Tuple[List[Dict[str, Any]], int]:
    """Read bus rows for *date* starting at line *offset*.

    Returns (rows, new_offset). new_offset = total lines currently in the file
    (pass it back as *offset* next call to resume). If *asof* is given, only
    rows with ts_knowable <= asof are returned in `rows` -- but new_offset still
    advances past ALL new lines (offset tracks disk position, not the asof
    filter, so a later call with a later asof does not re-scan already-read lines).
    """
    path = bus_path(date, bus_dir=bus_dir)
    if not path.is_file():
        return [], offset
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    new_offset = len(lines)
    out: List[Dict[str, Any]] = []
    for ln in lines[offset:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if asof is None or str(row.get("ts_knowable", "")) <= asof:
            out.append(row)
    return out, new_offset


class FileCursor:
    """Persisted {key: int} offset map, e.g. bus line-offsets or source file line-counts.

    One JSON file per cursor namespace (e.g. one per ingester), written via the
    same atomic helper as everything else here. Keys are caller-chosen strings
    (a date for the bus reader, an absolute source-file path for bus_ingest).
    """

    def __init__(self, name: str, *, cursor_dir: pathlib.Path = CURSOR_DIR):
        self.path = cursor_dir / f"{name}.json"
        self._state: Dict[str, int] = {}
        if self.path.is_file():
            try:
                self._state = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def get(self, key: str, default: int = 0) -> int:
        return int(self._state.get(key, default))

    def set(self, key: str, value: int) -> None:
        self._state[key] = int(value)
        write_json_atomic(self.path, self._state, sort_keys=True)


__all__ = ["append_event", "append_events", "read_events", "bus_path", "FileCursor", "BUS_DIR"]
