"""scripts.platformkit.clv_settle_write -- status-aware CLV ledger write wrappers.

ROOT CAUSE (be-r2-w1-clv-writer-dedup):
  A tick-overlap or daemon-restart double-fire on an MLB/NBA moneyline row causes
  grade_paper to call append_settlement (or record_bet) more than once for the same
  (bet_id, status) pair, appending a second IDENTICAL row.  The raw
  clv_ledger.append_settlement has no dedup guard; similarly record_bet's open-row
  append never checks whether that (bet_id|open) pair already exists.

THIS MODULE:
  Provides two thin wrappers that route through the existing
  append_if_new_status_aware primitive (status_key = "<bet_id>|<status>") so that:

    write_settlement(settled)
      -> append_if_new_status_aware with status="settled"
      -> appended exactly ONCE; a second call with the same (bet_id|settled) is
         a no-op; the OPEN row (same bet_id, status="open") is a DISTINCT key and
         remains untouched.

    write_open_bet(record)
      -> append_if_new_status_aware with status="open"
      -> appended exactly ONCE; a replay of the same (bet_id|open) pair is a no-op.

  Both wrappers:
    * Strip BANNED_KEYS (dollar/pnl/roi) before any write (honesty guard).
    * Return {"appended": bool, "key": str} on success or
             {"appended": False, "error": str} on unexpected failure.
    * NEVER raise.
    * NEVER mutate or delete existing ledger lines (append-only preserved).
    * NEVER write a $/pnl/roi/profit key.
    * Use append_if_new_status_aware's _seen param for efficient batch use.

  grade_paper.grade_open_bets substitutes write_settlement for the raw
  clv_ledger.append_settlement call (line 253).

STATUS-KEY / GOVERNANCE ALIGNMENT:
  status_key (from clv_ledger_status_dedup) produces "<bet_id>|<status>".
  governance.concurrency_guard._row_key (READ-ONLY; we do NOT edit it) produces
  the same formula for rows that carry a bet_id.  A ledger written ONLY through
  these wrappers therefore scans CLEAN under ledger_audit.dup_key_detector (which
  mirrors the governance _row_key formula).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets;
per-file test in scripts/platformkit/test_clv_settle_write.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_settle_write.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id as _bet_id
from scripts.platformkit.clv_ledger_status_dedup import append_if_new_status_aware


# ---------------------------------------------------------------------------
# Public wrapper 1: settlement writer (replaces raw append_settlement)
# ---------------------------------------------------------------------------

def write_settlement(
    settled: Dict[str, Any],
    *,
    path: Optional[Path] = None,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Dedup-guarded settlement append; replaces clv_ledger.append_settlement.

    Routes through append_if_new_status_aware so a same (bet_id|settled) replay
    from a tick-overlap or daemon-restart is silently blocked.  The open-row twin
    (same bet_id, status="open") is treated as a DISTINCT key and is never touched.

    Parameters
    ----------
    settled:
        A row dict with status="settled" (produced by clv_ledger.grade_one /
        settle_closing_line).  Missing status is assumed "settled" for forward-
        compat; callers should always set it explicitly.
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional pre-computed set of status_keys (mutable; grows as rows are
        appended).  Pass across calls in a batch settlement loop to avoid repeated
        ledger scans.

    Returns
    -------
    dict
        {"appended": True,  "key": "<bet_id>|settled"}  -- row written
        {"appended": False, "key": "<bet_id>|settled"}  -- duplicate; no-op
        {"appended": False, "error": <str>}              -- unexpected failure
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    row = dict(settled)
    # Normalise status; a settlement row must carry "settled".
    if not row.get("status"):
        row["status"] = "settled"
    # Ensure bet_id is present so status_key is stable.
    if not row.get("bet_id"):
        row["bet_id"] = _bet_id(row)
    return append_if_new_status_aware(row, target, _seen=_seen)


# ---------------------------------------------------------------------------
# Public wrapper 2: open-bet writer (dedup guard for record_bet replay)
# ---------------------------------------------------------------------------

def write_open_bet(
    record: Dict[str, Any],
    *,
    path: Optional[Path] = None,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Dedup-guarded open-bet append; guards against same (bet_id|open) replay.

    record_bet in clv_ledger already builds the open row and calls _append_line
    directly.  Use this wrapper instead when the caller may fire more than once
    for the same logical bet (e.g. a daemon restart re-queuing the same matchup).

    Parameters
    ----------
    record:
        An open bet row dict (status="open" or no status field).
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional mutable set of status_keys already seen (batch efficiency).

    Returns
    -------
    dict
        {"appended": True,  "key": "<bet_id>|open"}  -- row written
        {"appended": False, "key": "<bet_id>|open"}  -- duplicate; no-op
        {"appended": False, "error": <str>}           -- unexpected failure
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    row = dict(record)
    if not row.get("status"):
        row["status"] = "open"
    if not row.get("bet_id"):
        row["bet_id"] = _bet_id(row)
    return append_if_new_status_aware(row, target, _seen=_seen)


__all__ = [
    "write_settlement",
    "write_open_bet",
]
