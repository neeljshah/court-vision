"""scripts.platformkit.clv_ledger_guarded_append -- idempotent status-aware append.

WORKSTREAM BE8-1.

ROOT CAUSE (P1 governance blocker, QA iter 2/4/5/6/7/8/9/11)
-------------------------------------------------------------
record_bet and append_settlement both write directly to the ledger without a
status-aware dedup check.  On every settlement cycle (auto_loop, grade_paper,
or any daemon that fires a concurrent tick) the same (bet_id, status) row can
be written two or more times:

  * A duplicate "open" row:     governance._row_key sees it as the same key ->
    concurrency_guard halts with EXIT 1 (BLOCKED).
  * A duplicate "settled" row:  same halt.
  * An "open" row followed by its intended "settled" twin via the OLD
    clv_ledger_dedup.append_if_new (which keys on bet_id alone):
    the settled row shares the same bet_id as the open twin -> append_if_new
    returns False and silently DROPS the settlement.

All three cases are instances of the same missing abstraction: a SINGLE
status-aware guarded append that callers can substitute for the raw
record_bet / append_settlement pair.

THIS MODULE
-----------
Provides append_if_new_status_aware -- a thread-safe, idempotent status-aware
guarded append that every in-lane writer calls instead of the raw ledger write.

The dedup key is status_key(row) = "<bet_id>|<status>" from
clv_ledger_status_dedup.  The scan + write is protected by a per-path
threading.Lock so that two threads firing the same (bet_id, status) row
simultaneously cannot both see the ledger as empty and both write.

    open row written first       -> status_key = "<id>|open"     -> appended
    settled row written later    -> status_key = "<id>|settled"  -> appended
    open row replayed (tick/dup) -> status_key = "<id>|open"     -> BLOCKED
    settled row replayed         -> status_key = "<id>|settled"  -> BLOCKED
    concurrent double-fire same  -> second thread blocked by lock  -> 1 line

Missing ledger path: parent directory is created and the first row is written.
No existing lines are ever mutated.

HONESTY CONTRACT (binding)
--------------------------
  * UNITS ONLY -- no dollar/bankroll/pnl/roi/profit key is introduced.
    BANNED_KEYS (from clv_ledger_migrate) stripped before every write.
  * Append-only: existing ledger lines are NEVER mutated.
  * Never claims a money edge.
  * Never places a real bet.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; per-file
test at scripts/platformkit/test_clv_ledger_guarded_append.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_guarded_append.py -q
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id as _bet_id
from scripts.platformkit.clv_ledger import load_ledger as _load_ledger
from scripts.platformkit.clv_ledger_io import append_row as _io_append
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.clv_ledger_status_dedup import status_key

# ---------------------------------------------------------------------------
# Per-path threading locks: serialise the scan+write critical section so that
# two threads firing the same (bet_id, status) row cannot both pass the dedup
# check simultaneously.  We key on the resolved absolute path string so
# different ledger files get independent locks.
# ---------------------------------------------------------------------------
_LOCK_REGISTRY: Dict[str, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    """Return (creating if needed) the threading.Lock for *path*."""
    key = str(path.resolve())
    with _REGISTRY_LOCK:
        if key not in _LOCK_REGISTRY:
            _LOCK_REGISTRY[key] = threading.Lock()
        return _LOCK_REGISTRY[key]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


def _seen_keys(path: Path) -> Set[str]:
    """Read existing status_keys from *path*.  Missing file -> empty set."""
    try:
        rows = _load_ledger(path)
        return {status_key(r) for r in rows}
    except Exception:  # noqa: BLE001 -- tolerate missing/corrupt file
        return set()


def _write_row(clean: Dict[str, Any], target: Path) -> None:
    """Append *clean* to *target*, ensuring parent dirs exist."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _io_append(clean, path=target)
    except Exception:  # noqa: BLE001 -- fall back to direct write, never lose the row
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(clean, default=str) + "\n")


# ---------------------------------------------------------------------------
# Core: thread-safe scan + conditional write
# ---------------------------------------------------------------------------

def _guarded_append(
    record: Dict[str, Any],
    target: Path,
    seen: Optional[Set[str]],
) -> Dict[str, Any]:
    """Inner implementation: acquire path lock then scan + conditional write.

    When *seen* is supplied it is used as the source of truth for the pre-check
    (avoiding a disk scan in batch sessions).  When None the ledger is scanned
    while holding the lock for correctness under concurrent callers.
    """
    skey = status_key(record)
    lock = _path_lock(target)

    with lock:
        # Inside the lock: compute or re-verify the existing-keys set.
        if seen is not None:
            # Caller-managed set: trust it as-is; they are responsible for not
            # sharing the set across threads without external synchronisation.
            existing = seen
        else:
            existing = _seen_keys(target)

        if skey in existing:
            return {"appended": False, "key": skey}

        # Strip banned keys and ensure bet_id is present.
        clean = _strip_dollar_keys(record)
        if not clean.get("bet_id"):
            clean["bet_id"] = str(record.get("bet_id") or _bet_id(record))

        _write_row(clean, target)

        if seen is not None:
            seen.add(skey)

    return {"appended": True, "key": skey}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def append_if_new_status_aware(
    record: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Idempotent status-aware guarded append for the CLV ledger.

    Thread-safe: a per-path threading.Lock serialises the scan + write critical
    section so that two concurrent calls with the same (bet_id, status) produce
    exactly one written row.

    The dedup key is status_key(record) = "<bet_id>|<status>":

      * Two writes of the same (bet_id, "open") -> 1 line in ledger.
      * An open row followed by its settled twin (same bet_id, "settled")
        -> 2 lines (distinct status_key, both retained).
      * Concurrent double-fire of identical row -> lock ensures second write
        is blocked, 1 line total.
      * Missing ledger path -> parent directory created, first row written.

    Parameters
    ----------
    record:
        Row dict.  Must carry ``bet_id`` (or enough fields to compute one) and
        ``status`` ("open"/"settled"; "open" assumed when absent).
        BANNED_KEYS stripped before write (units-only contract).
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional mutable set of existing status_key strings shared across a
        batch session.  Must NOT be shared between threads.  When None the
        ledger is scanned while holding the lock on each call.

    Returns
    -------
    dict
        {"appended": True,  "key": <status_key>}  -- row written
        {"appended": False, "key": <status_key>}  -- already present (no-op)
        {"appended": False, "error": <str>}        -- unexpected failure

    Never raises.  Existing lines never mutated.  No dollar key written.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    try:
        return _guarded_append(record, target, _seen)
    except Exception as exc:  # noqa: BLE001 -- guard must NEVER raise
        return {"appended": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def record_open_guarded(
    record: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Guarded append for an OPEN bet row; defaults status to "open".

    Thin convenience wrapper around append_if_new_status_aware.  The row must
    be fully shaped (as returned by clv_ledger.record_bet or built manually).
    This function does NOT re-call record_bet; it only guards the write.

    Returns same dict shape as append_if_new_status_aware.  Never raises.
    """
    row = dict(record)
    if not row.get("status"):
        row["status"] = "open"
    return append_if_new_status_aware(row, path, _seen=_seen)


def record_settlement_guarded(
    settled: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Guarded append for a SETTLED twin row; forces status="settled".

    A duplicate settlement write (grader running twice) is silently blocked.
    An intentional settled twin whose open counterpart is already in the ledger
    is always written (distinct status_key = "<id>|settled").

    Returns same dict shape as append_if_new_status_aware.  Never raises.
    """
    row = dict(settled)
    row["status"] = "settled"
    return append_if_new_status_aware(row, path, _seen=_seen)


def make_session_seen(path: Optional[Path] = None) -> Set[str]:
    """Build the initial _seen set from existing ledger content.

    Call once at the start of a batch session and pass the returned set to
    every append_if_new_status_aware call in that session to avoid per-call
    disk scans.  The set is updated in-place as rows are appended.

    IMPORTANT: do NOT share the returned set across threads.  Each thread
    should build its own seen set.

    Missing ledger -> empty set.  Never raises.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    return _seen_keys(target)


__all__ = [
    "append_if_new_status_aware",
    "record_open_guarded",
    "record_settlement_guarded",
    "make_session_seen",
    "status_key",
    "DEFAULT_LEDGER",
]
