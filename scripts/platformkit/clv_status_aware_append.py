"""scripts.platformkit.clv_status_aware_append -- canonical status-aware CLV append.

WORKSTREAM: BE-H-clv-status-rowkey-writer

ROOT CAUSE (governance concurrency-gate FAIL -- QA iter 2/4/5/6/7/8/11)
-----------------------------------------------------------------------
The governance concurrency gate keys on bet_id alone.  When a settlement writer
appends an "open" row and then a "settled" twin for the same logical bet, both
rows share the identical bet_id -> the gate treats the settled row as a duplicate
of the open row -> EXIT 1 (BLOCKED), halting every settlement cycle.

THE FIX (write-path only; governance/ is human-gated and untouched)
-------------------------------------------------------------------
All settlement-path appends must go through a STATUS-AWARE key:

    status_key(row) = bet_id + "|" + status

This ensures "open" and "settled" rows are DISTINCT keys, while a true
byte-for-byte replay of the same (bet_id, status) pair is still caught as a dup.

THIS MODULE
-----------
Provides the SINGLE import surface the settlement writer must call.  It composes
the three already-existing primitives:

  * clv_ledger_status_dedup.status_key           -- the key formula
  * clv_ledger_guarded_append.append_if_new_status_aware  -- thread-safe write
  * clv_settle_write.write_settlement / write_open_bet    -- status-normalised wrappers

None of those modules are modified; this module wires them under one name so that
a settlement writer needs only:

    from scripts.platformkit.clv_status_aware_append import (
        settle_append,
        open_append,
        status_aware_key,
    )

KEY CONTRACT
------------
    open row written first       -> status_key = "<bid>|open"     -> appended
    settled row written later    -> status_key = "<bid>|settled"  -> appended
    open row replayed (tick-dup) -> status_key = "<bid>|open"     -> BLOCKED (dup)
    settled row replayed         -> status_key = "<bid>|settled"  -> BLOCKED (dup)
    concurrent same-status fire  -> lock in guarded_append -> 1 line only

NO LEDGER MUTATION: the module only writes new lines; existing lines are never
altered, deleted, or rewritten.

HONESTY CONTRACT (binding)
--------------------------
  * UNITS ONLY -- no dollar/bankroll/pnl/roi/profit key introduced or passed.
    BANNED_KEYS (from clv_ledger_migrate) are stripped inside the write path.
  * Append-only: existing ledger lines are NEVER mutated.
  * Never claims a money edge; CLV is calibration, not edge.
  * real-money gate: DENY (no bet placement here; this is the ledger write layer).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; per-file
test at tests/platformkit/test_clv_status_aware_append.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      tests/platformkit/test_clv_status_aware_append.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

# ---------------------------------------------------------------------------
# Re-export the core key formula so callers only need this one module.
# ---------------------------------------------------------------------------
from scripts.platformkit.clv_ledger_status_dedup import status_key as status_aware_key

# ---------------------------------------------------------------------------
# Thread-safe guarded-append primitives (scan + write inside a per-path lock).
# ---------------------------------------------------------------------------
from scripts.platformkit.clv_ledger_guarded_append import (
    append_if_new_status_aware as _guarded_append,
    make_session_seen,
)

# ---------------------------------------------------------------------------
# Status-normalised wrappers (ensure "open"/"settled" is on the row before
# the key is computed; both call _guarded_append internally).
# ---------------------------------------------------------------------------
from scripts.platformkit.clv_settle_write import (
    write_open_bet as _write_open,
    write_settlement as _write_settlement,
)


# ---------------------------------------------------------------------------
# Public API: two named helpers the settlement writer calls
# ---------------------------------------------------------------------------

def settle_append(
    settled: Dict[str, Any],
    *,
    path: Optional[Path] = None,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Write a settled-twin row to the CLV ledger; dup-guarded by status_key.

    Replaces a raw ``clv_ledger.append_settlement`` call.  The key is
    ``<bet_id>|settled`` so this write is DISTINCT from the open twin and the
    governance concurrency gate does not see it as a duplicate.

    Parameters
    ----------
    settled:
        Row dict produced by the grader (clv_ledger.grade_one or equivalent).
        Must carry ``bet_id`` and ``status="settled"`` (or status will be set).
        BANNED_KEYS (dollar/pnl/roi) stripped before writing.
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional mutable set of existing status_keys for batch efficiency.
        Do NOT share across threads.

    Returns
    -------
    dict
        ``{"appended": True,  "key": "<bet_id>|settled"}`` -- row written
        ``{"appended": False, "key": "<bet_id>|settled"}`` -- dup; no-op
        ``{"appended": False, "error": <str>}``             -- unexpected failure

    Never raises.  Existing ledger lines never mutated.  No $ key written.
    """
    return _write_settlement(settled, path=path, _seen=_seen)


def open_append(
    record: Dict[str, Any],
    *,
    path: Optional[Path] = None,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Write an open-bet row to the CLV ledger; dup-guarded by status_key.

    Replaces a raw ``clv_ledger.record_bet`` append when the caller may fire
    more than once for the same logical bet (daemon restart, tick overlap).
    The key is ``<bet_id>|open`` -- distinct from the settled twin.

    Parameters
    ----------
    record:
        Open bet row dict.  status will be forced to "open" if absent.
        BANNED_KEYS stripped before writing.
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional mutable set of existing status_keys for batch efficiency.

    Returns
    -------
    dict
        ``{"appended": True,  "key": "<bet_id>|open"}`` -- row written
        ``{"appended": False, "key": "<bet_id>|open"}`` -- dup; no-op
        ``{"appended": False, "error": <str>}``          -- unexpected failure

    Never raises.  Existing ledger lines never mutated.  No $ key written.
    """
    return _write_open(record, path=path, _seen=_seen)


__all__ = [
    # The key formula (re-exported for callers that only need it for inspection)
    "status_aware_key",
    # The two append helpers the settlement writer must call
    "settle_append",
    "open_append",
    # Batch-session helper: build initial seen-set once per session
    "make_session_seen",
]
