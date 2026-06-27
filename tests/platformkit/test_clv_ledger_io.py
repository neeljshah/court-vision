"""Tests for scripts.platformkit.clv_ledger_io -- lock-guarded ledger append/load.

Verifies: sequential appends land intact; simulated-concurrent (threaded) appends
all land intact and parse; a torn trailing line is tolerated on load; round-trip
integrity of arbitrary row payloads. Per-file test only (never run the full suite).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from scripts.platformkit import clv_ledger_io as io


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    return tmp_path / "frontend" / "clv_ledger.jsonl"


def test_ledger_path_is_canonical():
    from scripts.platformkit.clv_ledger import DEFAULT_LEDGER

    assert io.ledger_path() == DEFAULT_LEDGER
    assert io.ledger_path().name == "clv_ledger.jsonl"


def test_missing_file_loads_empty(ledger: Path):
    assert io.load_rows(path=ledger) == []


def test_append_creates_parent_and_roundtrips(ledger: Path):
    row = {"matchup": "A@B", "side": "home", "clv_pct": 1.25, "n": 3}
    io.append_row(row, path=ledger)
    assert ledger.exists()
    rows = io.load_rows(path=ledger)
    assert rows == [row]


def test_many_sequential_appends_all_intact(ledger: Path):
    expected = [{"i": i, "side": "home" if i % 2 else "away"} for i in range(200)]
    for r in expected:
        io.append_row(r, path=ledger)
    rows = io.load_rows(path=ledger)
    assert len(rows) == 200
    assert sorted(rows, key=lambda r: r["i"]) == expected


def test_simulated_concurrent_appends_all_land(ledger: Path):
    n_threads = 8
    per_thread = 60
    barrier = threading.Barrier(n_threads)

    def worker(tid: int):
        barrier.wait()  # maximise overlap
        for j in range(per_thread):
            io.append_row({"tid": tid, "j": j}, path=ledger)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = io.load_rows(path=ledger)
    # No torn/lost lines: every (tid, j) pair present exactly once, all parseable.
    assert len(rows) == n_threads * per_thread
    seen = {(r["tid"], r["j"]) for r in rows}
    assert len(seen) == n_threads * per_thread
    # Raw file: every non-blank line is valid JSON (no spliced/corrupt lines).
    raw = ledger.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(ln) for ln in raw if ln.strip()]
    assert len(parsed) == n_threads * per_thread


def test_torn_trailing_line_is_tolerated(ledger: Path):
    io.append_row({"good": 1}, path=ledger)
    io.append_row({"good": 2}, path=ledger)
    # Simulate a writer killed mid-flush: append a partial, unterminated JSON frag.
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"good": 3, "partial"')  # no closing brace, no newline
    rows = io.load_rows(path=ledger)
    assert rows == [{"good": 1}, {"good": 2}]  # torn tail dropped, never raises


def test_torn_line_in_middle_does_not_kill_later_rows(ledger: Path):
    # A corrupt line followed by a valid newline-terminated line: skip the bad one.
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"ok": 1}\n')
        fh.write("not json at all\n")
        fh.write('{"ok": 2}\n')
    rows = io.load_rows(path=ledger)
    assert rows == [{"ok": 1}, {"ok": 2}]


def test_blank_lines_ignored(ledger: Path):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"x": 1}\n\n  \n{"x": 2}\n')
    rows = io.load_rows(path=ledger)
    assert rows == [{"x": 1}, {"x": 2}]


def test_append_serialises_non_json_native_via_default_str(ledger: Path):
    from datetime import datetime, timezone

    ts = datetime(2026, 6, 18, tzinfo=timezone.utc)
    io.append_row({"ts": ts, "v": 1}, path=ledger)
    rows = io.load_rows(path=ledger)
    assert rows[0]["v"] == 1
    assert isinstance(rows[0]["ts"], str)  # datetime stringified, not crashed
