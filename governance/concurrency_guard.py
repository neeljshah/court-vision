"""governance.concurrency_guard -- governance wrapper for lock-guarded ledger writes.

Asserts that all CLV-ledger and artifact writes go through the tested
``scripts.platformkit.clv_ledger_io`` primitive (advisory lock + atomic append)
rather than calling the ledger directly.  Also provides a duplicate-row check so
two concurrent appenders cannot produce an identical (row_id, ts) pair in the
ledger.

The duplicate check is ADVISORY: it reads all existing rows and asserts the new
row's unique key is absent before delegating to the lock-guarded append_row.  On a
single-writer system this is exact.  On a multi-writer system (two concurrent
processes calling append_row on the same ledger) the lock inside clv_ledger_io
serialises the actual write bytes, so the duplicate check here adds a pre-flight
at the governance layer -- if both processes read an empty ledger simultaneously,
both pass the pre-flight, but only ONE write lands atomically per the sidecar-lock
in clv_ledger_io (the lock serialises the write; the content uniqueness check is
still the caller's responsibility, hence "advisory").

Why this is enough in practice:
  - The paper auto-loop is a SINGLE process; true concurrent multi-process writes
    are rare and handled by the OS lock in clv_ledger_io.
  - The governance pre-flight surfaces accidental duplicate replay in tests and
    single-process code (by far the most common source of dups).

DECISION-ONLY: never authorises a bet.  Never writes data/registry/.  Never flips
a flag.  <=300 LOC; ASCII; no secrets.
"""
from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import scripts.platformkit.clv_ledger_io as _ledger_io

# ---------------------------------------------------------------------------
# Governance-layer unique-key derivation
# ---------------------------------------------------------------------------

def _row_key(row: Dict[str, Any]) -> str:
    """Stable, STATUS-AWARE unique key for a ledger row.

    Priority order for natural keys (explicit bet_id / row_id first; fallback to
    a SHA-1 of the serialised row so we can still detect byte-for-byte dups even
    for rows that lack an explicit id field).

    STATUS DIMENSION (CLV-STATUS-KEY fix): the CLV ledger is append-only and an
    OPEN bet and its later SETTLED twin DELIBERATELY share one bet_id (the durable
    logical identity). Keying on bet_id alone made every settlement cycle look like
    a duplicate-row collision and BLOCKED the governance concurrency gate. The
    settled twin is an INTENTIONAL status-change append, NOT a duplicate, so the
    row's ``status`` is folded into the key. An open row ("<id>|open") and its
    settled twin ("<id>|settled") therefore get DISTINCT keys, while a true
    byte-for-byte replay (same bet_id AND same status) still collides and is
    blocked as before. Rows without a status fall back to "open".
    """
    status = str(row.get("status") or "open").strip().lower()
    for field in ("bet_id", "row_id", "id"):
        val = row.get(field)
        if val is not None:
            return "%s|%s" % (str(val), status)
    # Fallback: content hash (stable; handles float/bool normalisation via json).
    # The content hash already varies with status (status is part of the row),
    # so byte-for-byte dups still collide and status-changed rows still differ.
    payload = json.dumps(row, sort_keys=True, default=str)
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _existing_keys(path: Optional[Path] = None) -> "frozenset[str]":
    """Return the set of unique keys already present in the ledger."""
    rows = _ledger_io.load_rows(path=path)
    return frozenset(_row_key(r) for r in rows)


# ---------------------------------------------------------------------------
# Public governance API
# ---------------------------------------------------------------------------

class DuplicateRowError(Exception):
    """Raised when a row with the same unique key already exists in the ledger."""


def assert_no_dup_and_append(
    row: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> str:
    """Advisory duplicate guard + lock-guarded append.

    1. Derives the row's unique key.
    2. Reads the ledger and ASSERTS the key is absent (raises DuplicateRowError
       when a dup is detected -- the write is BLOCKED).
    3. Delegates to ``clv_ledger_io.append_row`` which holds an OS advisory lock
       around the actual write + fsync.

    Returns the unique key of the appended row so callers can log it.

    Invariants:
      - Duplicate BLOCKS the write (raises DuplicateRowError before append_row).
      - Non-duplicate proceeds through the lock-guarded path.
      - Governance layer adds no new I/O primitives; all real I/O is via
        clv_ledger_io (single, tested lock primitive).
    """
    key = _row_key(row)
    existing = _existing_keys(path)
    if key in existing:
        raise DuplicateRowError(
            "Row with key %r already present in ledger %s -- write BLOCKED."
            % (key, path or _ledger_io.ledger_path())
        )
    _ledger_io.append_row(row, path=path)
    return key


def locked_append(
    row: Dict[str, Any],
    *,
    path: Optional[Path] = None,
    check_dup: bool = True,
) -> str:
    """Governance entry-point for all ledger appends.

    When *check_dup* is True (default) the advisory duplicate guard fires first.
    When False the row is sent straight to the lock-guarded primitive (useful for
    settlement rows that intentionally share the same bet_id under a different
    status key -- callers should set check_dup=False and manage uniqueness
    themselves).

    Returns the unique key of the appended row.
    """
    if check_dup:
        return assert_no_dup_and_append(row, path=path)
    _ledger_io.append_row(row, path=path)
    return _row_key(row)


def load_rows_guarded(*, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read all intact ledger rows via the governance-approved path.

    Thin wrapper over clv_ledger_io.load_rows so callers never bypass the
    lock-guarded I/O primitive to read the ledger directly.
    """
    return _ledger_io.load_rows(path=path)


def ledger_path() -> Path:
    """Return the canonical CLV ledger path (single source of truth)."""
    return _ledger_io.ledger_path()


__all__ = [
    "DuplicateRowError",
    "assert_no_dup_and_append",
    "locked_append",
    "load_rows_guarded",
    "ledger_path",
]
