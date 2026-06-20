"""supervisor/test_webapp_build_drift.py -- per-file tests for webapp_build_drift.

Acceptance criteria (from workstream spec):
  1. DRIFT: served build_id != on-disk build_id -> status DRIFT, ok False.
  2. OK:    served build_id == on-disk build_id -> status OK, ok True.
  3. UNAVAILABLE: missing .next/BUILD_ID -> status UNAVAILABLE, ok False (never green).
  4. UNAVAILABLE: server not reachable (HTTP 0) -> status UNAVAILABLE, ok False.
  5. tick() writes the status JSON to disk and returns the doc.
  6. run(max_ticks=2, injected clock/sleep) returns 2, never blocks.
  7. Status doc never contains a $ / PnL key.
  8. schema_version present on every doc.
  9. tick() never raises even with a garbage fetcher.

All I/O is injected:
  - build_id_reader callable (returns on-disk build ID or None).
  - fetcher callable(url, timeout) -> int (returns HTTP status code).
  - clock injected (fixed epoch).
  - sleep_fn injected (records calls, never blocks).
  - status written to tmp paths; no real sockets, no real timers.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from supervisor.webapp_build_drift import (
    STATUS_DRIFT,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    check,
    run,
    tick,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_EPOCH = 1_718_700_000.0


def _fixed_clock(epoch: float = _EPOCH):
    def _c():
        return epoch
    return _c


def _sleep_noop(secs: float) -> None:  # noqa: ARG001
    pass


def _reader(build_id: str | None):
    """Return a callable that yields *build_id* (or None) as the on-disk ID."""
    def _r():
        return build_id
    return _r


def _fetcher_200(_url: str, _timeout: float) -> int:
    """Pretend the server knows this build ID (HTTP 200)."""
    return 200


def _fetcher_404(_url: str, _timeout: float) -> int:
    """Pretend the server returns 404 -- serving a different build."""
    return 404


def _fetcher_0(_url: str, _timeout: float) -> int:
    """Pretend the server is not reachable (connection refused / timeout)."""
    return 0


def _read_status(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test 1: DRIFT -- served build != on-disk build (fetcher returns 404)
# ---------------------------------------------------------------------------

def test_stale_server_returns_drift_not_ok():
    """Core acceptance: when the server doesn't serve the on-disk build manifest,
    status must be DRIFT and ok must be False (stale-never-green)."""
    doc = check(
        build_id_reader=_reader("abc123build"),
        fetcher=_fetcher_404,
        clock=_fixed_clock(),
    )
    assert doc["status"] == STATUS_DRIFT, "stale server must return DRIFT"
    assert doc["ok"] is False, "DRIFT must never set ok=True"
    assert doc["disk_build_id"] == "abc123build"
    assert doc["updated_at"] == pytest.approx(_EPOCH)


def test_drift_detail_mentions_restart():
    """The detail field must hint at a restart being needed."""
    doc = check(
        build_id_reader=_reader("someid"),
        fetcher=_fetcher_404,
        clock=_fixed_clock(),
    )
    assert "restart" in doc["detail"].lower() or "stale" in doc["detail"].lower()


# ---------------------------------------------------------------------------
# Test 2: OK -- server serves the current build manifest (fetcher returns 200)
# ---------------------------------------------------------------------------

def test_matching_build_ids_returns_ok():
    """When the server serves the manifest for the on-disk build ID, status is OK."""
    doc = check(
        build_id_reader=_reader("freshbuild99"),
        fetcher=_fetcher_200,
        clock=_fixed_clock(),
    )
    assert doc["status"] == STATUS_OK
    assert doc["ok"] is True
    assert doc["disk_build_id"] == "freshbuild99"


def test_ok_detail_contains_build_id():
    doc = check(
        build_id_reader=_reader("freshbuild99"),
        fetcher=_fetcher_200,
        clock=_fixed_clock(),
    )
    assert "freshbuild99" in doc["detail"]


# ---------------------------------------------------------------------------
# Test 3: UNAVAILABLE -- missing .next/BUILD_ID (reader returns None)
# ---------------------------------------------------------------------------

def test_missing_build_id_returns_unavailable_not_ok():
    """When on-disk BUILD_ID is absent, status must be UNAVAILABLE, never green."""
    doc = check(
        build_id_reader=_reader(None),
        fetcher=_fetcher_200,   # fetcher would return 200 but we never reach it
        clock=_fixed_clock(),
    )
    assert doc["status"] == STATUS_UNAVAILABLE
    assert doc["ok"] is False, "UNAVAILABLE must never set ok=True"


def test_missing_build_id_disk_field_empty():
    """disk_build_id should be an empty string (not None/undefined) when absent."""
    doc = check(
        build_id_reader=_reader(None),
        fetcher=_fetcher_0,
        clock=_fixed_clock(),
    )
    # Must be a string (empty ok); must not be None (JSON null) to keep UI safe.
    assert isinstance(doc["disk_build_id"], str)


def test_empty_string_reader_returns_unavailable():
    """An empty-string build ID is as bad as None -- must also return UNAVAILABLE."""
    doc = check(
        build_id_reader=_reader(""),
        fetcher=_fetcher_200,
        clock=_fixed_clock(),
    )
    assert doc["status"] == STATUS_UNAVAILABLE
    assert doc["ok"] is False


# ---------------------------------------------------------------------------
# Test 4: UNAVAILABLE -- server not reachable (HTTP 0)
# ---------------------------------------------------------------------------

def test_server_not_reachable_returns_unavailable_not_ok():
    """Connection refused / timeout -> UNAVAILABLE, never DRIFT, never ok."""
    doc = check(
        build_id_reader=_reader("somebuild"),
        fetcher=_fetcher_0,
        clock=_fixed_clock(),
    )
    assert doc["status"] == STATUS_UNAVAILABLE
    assert doc["ok"] is False


# ---------------------------------------------------------------------------
# Test 5: tick() writes status JSON to disk and returns the doc
# ---------------------------------------------------------------------------

def test_tick_writes_status_file_and_returns_doc(tmp_path):
    status_out = tmp_path / "webapp_build_drift.json"

    doc = tick(
        build_id_reader=_reader("tickbuild"),
        fetcher=_fetcher_200,
        clock=_fixed_clock(),
        status_path=status_out,
    )

    assert status_out.exists(), "tick() must write the status file"
    persisted = _read_status(status_out)
    assert persisted["status"] == STATUS_OK
    assert persisted["ok"] is True
    assert persisted["disk_build_id"] == "tickbuild"
    # In-memory return must match persisted
    assert doc["status"] == persisted["status"]
    assert doc["ok"] == persisted["ok"]


def test_tick_drift_file_written(tmp_path):
    status_out = tmp_path / "webapp_build_drift.json"

    doc = tick(
        build_id_reader=_reader("oldbuild"),
        fetcher=_fetcher_404,
        clock=_fixed_clock(),
        status_path=status_out,
    )

    assert status_out.exists()
    persisted = _read_status(status_out)
    assert persisted["status"] == STATUS_DRIFT
    assert persisted["ok"] is False
    assert doc["status"] == STATUS_DRIFT


# ---------------------------------------------------------------------------
# Test 6: run(max_ticks=2, injected) returns 2 and never blocks
# ---------------------------------------------------------------------------

def test_run_max_ticks_returns_count_never_blocks(tmp_path):
    status_out = tmp_path / "webapp_build_drift.json"
    sleep_calls: list = []

    def _recording_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    t0 = time.monotonic()
    result = run(
        interval_sec=0.0,
        build_id_reader=_reader("somebuild"),
        fetcher=_fetcher_200,
        clock=_fixed_clock(),
        sleep_fn=_recording_sleep,
        status_path=status_out,
        max_ticks=2,
    )
    elapsed = time.monotonic() - t0

    assert result == 2, "run() must return the number of ticks completed"
    # sleep called once: between tick 1 and tick 2, NOT after the last tick
    assert len(sleep_calls) == 1
    assert elapsed < 2.0, "run() must complete without real blocking (elapsed %.2fs)" % elapsed

    persisted = _read_status(status_out)
    assert persisted["status"] == STATUS_OK


# ---------------------------------------------------------------------------
# Test 7: status doc never contains a $ / PnL key
# ---------------------------------------------------------------------------

def test_no_dollar_or_pnl_key_in_status():
    _banned = {"dollar", "pnl", "roi", "profit", "loss", "usd", "money"}
    for _fetcher in (_fetcher_200, _fetcher_404, _fetcher_0):
        doc = check(
            build_id_reader=_reader("anybuild"),
            fetcher=_fetcher,
            clock=_fixed_clock(),
        )
        for key in doc:
            assert key.lower() not in _banned, "banned key in doc: %r" % key


# ---------------------------------------------------------------------------
# Test 8: schema_version present on every doc
# ---------------------------------------------------------------------------

def test_schema_version_present_on_all_statuses():
    for reader_val, _fetcher in [
        (None, _fetcher_0),          # UNAVAILABLE (no build ID)
        ("somebuild", _fetcher_0),   # UNAVAILABLE (server down)
        ("somebuild", _fetcher_404), # DRIFT
        ("somebuild", _fetcher_200), # OK
    ]:
        doc = check(
            build_id_reader=_reader(reader_val),
            fetcher=_fetcher,
            clock=_fixed_clock(),
        )
        assert "schema_version" in doc, "schema_version missing for status %s" % doc.get("status")


# ---------------------------------------------------------------------------
# Test 9: tick() never raises even with a garbage fetcher
# ---------------------------------------------------------------------------

def test_tick_never_raises_on_garbage_fetcher(tmp_path):
    status_out = tmp_path / "webapp_build_drift.json"

    def _exploding_fetcher(_url: str, _timeout: float) -> int:
        raise RuntimeError("injected failure")

    # Must not raise
    doc = tick(
        build_id_reader=_reader("somebuild"),
        fetcher=_exploding_fetcher,
        clock=_fixed_clock(),
        status_path=status_out,
    )
    # An exploding fetcher should be treated as server-unreachable -> UNAVAILABLE
    assert doc["status"] == STATUS_UNAVAILABLE
    assert doc["ok"] is False


# ---------------------------------------------------------------------------
# Test 10: real on-disk BUILD_ID path (integration, no network call)
#          Reads the actual webapp/.next/BUILD_ID from disk to confirm the
#          default reader works, but uses an injected fetcher to avoid a
#          live HTTP call.
# ---------------------------------------------------------------------------

def test_real_disk_build_id_reads_correctly(tmp_path):
    """The default build_id_reader can read the real .next/BUILD_ID on disk."""
    from supervisor.webapp_build_drift import _NEXT_BUILD_ID_PATH, _read_disk_build_id

    if not _NEXT_BUILD_ID_PATH.exists():
        pytest.skip("webapp/.next/BUILD_ID not present; run next build first")

    disk_id = _read_disk_build_id(_NEXT_BUILD_ID_PATH)
    assert disk_id is not None
    assert len(disk_id) > 4, "build ID looks suspiciously short: %r" % disk_id
    # It should be the same value the check() function would report in status.
    doc = check(
        fetcher=_fetcher_404,  # inject stale-server -> DRIFT
        clock=_fixed_clock(),
    )
    # DRIFT because we told the fetcher to return 404
    assert doc["status"] == STATUS_DRIFT
    assert doc["disk_build_id"] == disk_id


# ---------------------------------------------------------------------------
# Test 11: DRIFT status -> ok is False (stale-never-green invariant)
#          and UNAVAILABLE status -> ok is False (same invariant)
# ---------------------------------------------------------------------------

def test_stale_never_green_invariant():
    """ok must be False for EVERY non-OK status, without exception."""
    cases = [
        (_reader(None),    _fetcher_0),    # UNAVAILABLE (no build ID)
        (_reader("x"),     _fetcher_0),    # UNAVAILABLE (server down)
        (_reader("x"),     _fetcher_404),  # DRIFT
    ]
    for reader, _fetcher in cases:
        doc = check(build_id_reader=reader, fetcher=_fetcher, clock=_fixed_clock())
        assert doc["status"] != STATUS_OK
        assert doc["ok"] is False, (
            "ok must be False for status=%s (stale-never-green)" % doc["status"]
        )
