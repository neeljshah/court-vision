"""supervisor/test_clv_dup_watch.py -- per-file tests for clv_dup_watch.

Acceptance criteria (from workstream spec):
  1. One tick on a CLEAN ledger writes a status file with verdict CLEAN and
     advances a heartbeat (updated_at).
  2. A ledger with true dups writes DUPS_FOUND with the dup count, and
     overall ok == False (never green).
  3. A missing ledger writes UNAVAILABLE and ok == False (never green).
  4. run(max_ticks=2, injected clock/sleep) returns 2 and never blocks.
  5. No $ field, no real bet placed, no flag flipped, no data/registry write.

All I/O is injected:
  - Ledger files written to tmp paths.
  - Status output written to tmp paths.
  - clock injected (returns a fixed or incrementing epoch).
  - sleep_fn injected (records calls, never blocks).
  - No real sockets, no real timers, no subprocess.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from supervisor.clv_dup_watch import (
    VERDICT_CLEAN,
    VERDICT_DUPS_PREFIX,
    VERDICT_UNAVAILABLE,
    run,
    tick,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ledger(path: Path, rows: list) -> None:
    """Write JSONL rows to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_status(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixed_clock(epoch: float = 1_718_700_000.0):
    """Return a zero-arg callable that always returns *epoch*."""
    def _c():
        return epoch
    return _c


def _sleep_noop(secs: float) -> None:  # noqa: ARG001
    """Injected sleep that never blocks."""


# ---------------------------------------------------------------------------
# Test 1: CLEAN ledger -> verdict CLEAN, ok True, updated_at written
# ---------------------------------------------------------------------------

def test_clean_ledger_writes_clean_verdict(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"
    epoch = 1_718_700_000.0

    # Three rows, each with a unique bet_id -> no dups.
    _write_ledger(ledger, [
        {"bet_id": "A1", "market": "nba_ml", "units": 1.0},
        {"bet_id": "A2", "market": "nba_total", "units": 0.5},
        {"bet_id": "A3", "market": "nba_ml", "units": 1.0},
    ])

    doc = tick(
        ledger_path=ledger,
        status_path=status_out,
        clock=_fixed_clock(epoch),
    )

    # In-memory return value
    assert doc["verdict"] == VERDICT_CLEAN
    assert doc["ok"] is True
    assert doc["n_dups"] == 0
    assert doc["updated_at"] == pytest.approx(epoch)

    # File was written
    assert status_out.exists(), "status file not written"
    persisted = _read_status(status_out)
    assert persisted["verdict"] == VERDICT_CLEAN
    assert persisted["ok"] is True
    assert persisted["n_dups"] == 0
    assert persisted["updated_at"] == pytest.approx(epoch)


# ---------------------------------------------------------------------------
# Test 2: Ledger with true dups -> DUPS_FOUND, ok False, dup count correct
# ---------------------------------------------------------------------------

def test_dup_ledger_writes_dups_found_not_ok(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"

    # Two rows share the same bet_id -> 1 dup key.
    _write_ledger(ledger, [
        {"bet_id": "DUP-1", "market": "nba_ml", "units": 1.0},
        {"bet_id": "DUP-2", "market": "nba_total", "units": 0.5},
        {"bet_id": "DUP-1", "market": "nba_ml", "units": 1.0},   # duplicate of row 0
    ])

    doc = tick(
        ledger_path=ledger,
        status_path=status_out,
        clock=_fixed_clock(),
    )

    assert doc["ok"] is False, "DUPS_FOUND must never set ok=True"
    assert VERDICT_DUPS_PREFIX in doc["verdict"]
    assert "(1)" in doc["verdict"], "expected 1 dup key in verdict string"
    assert doc["n_dups"] == 1

    persisted = _read_status(status_out)
    assert persisted["ok"] is False
    assert VERDICT_DUPS_PREFIX in persisted["verdict"]
    assert persisted["n_dups"] == 1


def test_multiple_dups_counts_correctly(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"

    # 4 rows: 2 distinct dup keys (DUP-A appears twice, DUP-B appears twice).
    _write_ledger(ledger, [
        {"bet_id": "DUP-A"},
        {"bet_id": "DUP-B"},
        {"bet_id": "DUP-A"},
        {"bet_id": "DUP-B"},
    ])

    doc = tick(ledger_path=ledger, status_path=status_out, clock=_fixed_clock())

    assert doc["ok"] is False
    assert doc["n_dups"] == 2
    assert "(2)" in doc["verdict"]


# ---------------------------------------------------------------------------
# Test 3: Missing ledger -> UNAVAILABLE, ok False
# ---------------------------------------------------------------------------

def test_missing_ledger_writes_unavailable_not_ok(tmp_path):
    ledger = tmp_path / "nonexistent_ledger.jsonl"   # does NOT exist
    status_out = tmp_path / "clv_dup_status.json"

    doc = tick(
        ledger_path=ledger,
        status_path=status_out,
        clock=_fixed_clock(),
    )

    assert doc["ok"] is False, "UNAVAILABLE must never set ok=True"
    assert doc["verdict"] == VERDICT_UNAVAILABLE

    persisted = _read_status(status_out)
    assert persisted["ok"] is False
    assert persisted["verdict"] == VERDICT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Test 4: run(max_ticks=2, injected clock/sleep) returns 2, never blocks
# ---------------------------------------------------------------------------

def test_run_max_ticks_returns_count_never_blocks(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"

    # Clean ledger so tick() succeeds
    _write_ledger(ledger, [{"bet_id": "X1"}, {"bet_id": "X2"}])

    sleep_calls: list = []
    def _recording_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    t0 = time.monotonic()
    result = run(
        interval_sec=0.0,
        ledger_path=ledger,
        status_path=status_out,
        clock=_fixed_clock(),
        sleep_fn=_recording_sleep,
        max_ticks=2,
    )
    elapsed = time.monotonic() - t0

    assert result == 2
    # Sleep must have been called once (between tick 1 and tick 2, NOT after last)
    assert len(sleep_calls) == 1
    # Must complete essentially instantly (injected sleep + no I/O blocking)
    assert elapsed < 2.0, "run() must not block: elapsed %.2fs" % elapsed

    # Status file should reflect the latest tick
    persisted = _read_status(status_out)
    assert persisted["verdict"] == VERDICT_CLEAN
    assert persisted["ok"] is True


# ---------------------------------------------------------------------------
# Test 5: status doc NEVER contains a $ / PnL key
# ---------------------------------------------------------------------------

def test_no_dollar_or_pnl_key_in_status(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"
    _write_ledger(ledger, [{"bet_id": "K1"}])

    doc = tick(ledger_path=ledger, status_path=status_out, clock=_fixed_clock())

    banned = {"dollar", "pnl", "roi", "profit", "loss", "usd", "money"}
    for key in doc:
        assert key.lower() not in banned, "banned key in status: %r" % key

    persisted = _read_status(status_out)
    for key in persisted:
        assert key.lower() not in banned, "banned key in persisted status: %r" % key


# ---------------------------------------------------------------------------
# Test 6: heartbeat (updated_at) advances across ticks when clock increments
# ---------------------------------------------------------------------------

def test_heartbeat_advances_across_ticks(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"
    _write_ledger(ledger, [{"bet_id": "Y1"}])

    epoch1 = 1_000_000.0
    epoch2 = 1_000_060.0

    doc1 = tick(ledger_path=ledger, status_path=status_out, clock=_fixed_clock(epoch1))
    doc2 = tick(ledger_path=ledger, status_path=status_out, clock=_fixed_clock(epoch2))

    assert doc1["updated_at"] == pytest.approx(epoch1)
    assert doc2["updated_at"] == pytest.approx(epoch2)
    assert doc2["updated_at"] > doc1["updated_at"]


# ---------------------------------------------------------------------------
# Test 7: schema_version present on every status doc
# ---------------------------------------------------------------------------

def test_schema_version_always_present(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    status_out = tmp_path / "clv_dup_status.json"
    _write_ledger(ledger, [{"bet_id": "Z1"}])

    doc = tick(ledger_path=ledger, status_path=status_out, clock=_fixed_clock())
    assert "schema_version" in doc
    persisted = _read_status(status_out)
    assert "schema_version" in persisted


# ---------------------------------------------------------------------------
# Test 8: tick() never raises even on unreadable ledger path (dir, not file)
# ---------------------------------------------------------------------------

def test_tick_never_raises_on_bad_ledger(tmp_path):
    # Point the ledger path at a DIRECTORY -- scan_ledger should handle gracefully
    bad_ledger = tmp_path / "is_a_dir"
    bad_ledger.mkdir()
    status_out = tmp_path / "clv_dup_status.json"

    # Must not raise
    doc = tick(ledger_path=bad_ledger, status_path=status_out, clock=_fixed_clock())
    assert doc["ok"] is False
    assert doc["verdict"] in (VERDICT_UNAVAILABLE,) or VERDICT_DUPS_PREFIX in doc["verdict"]
