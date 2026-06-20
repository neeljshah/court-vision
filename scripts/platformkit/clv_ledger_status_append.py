"""scripts.platformkit.clv_ledger_status_append -- (bet_id, status) append guard.

WORKSTREAM BE-R4-2.

ROOT CAUSE / MOTIVATION
  clv_ledger_dedup.append_if_new deduplicates on bet_id alone.
  That correctly blocks replaying the same open row twice.
  BUT it also blocks the intentional settled-twin append:

      record_bet(...)       -> open   row, bet_id = "nba|LAL@BOS|ml|home|FD|2026-06-19"
      append_settlement(...) -> settled row, SAME bet_id (by design; shared identity)

  append_if_new sees "bet_id already present" on the settlement write and
  returns False -- the settled row is silently dropped.

THIS MODULE
  Provides append_if_new_status(record, path, _seen) whose dedup key is the
  (bet_id, status) 2-tuple, encoded as "<bet_id>|<status>":

    open row arrives           -> key "<id>|open"    not seen -> appended (True)
    settled row arrives later  -> key "<id>|settled" not seen -> appended (True)
    open row replayed (tick)   -> key "<id>|open"    seen     -> skipped  (False)
    settled row replayed       -> key "<id>|settled" seen     -> skipped  (False)

  The _seen set carries status_keys (not raw bet_ids), so the fast-path and the
  re-scan path are guaranteed to match: both compute the same key via _status_key().

HONESTY CONTRACT (binding):
  * UNITS ONLY -- no dollar/bankroll/pnl/roi field introduced or preserved.
    BANNED_KEYS (from clv_ledger_migrate) stripped before every write.
  * Append-only: existing ledger lines are never mutated.
  * Never claims a money edge.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; per-file
test at scripts/platformkit/test_clv_ledger_status_append.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_status_append.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id as _bet_id
from scripts.platformkit.clv_ledger import load_ledger as _load_ledger
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_STATUS = "open"


def _status_key(row: Dict[str, Any]) -> str:
    """Dedup key: "<bet_id>|<status>".

    Two rows sharing the same bet_id but differing in status ("open" vs
    "settled") produce DISTINCT keys and are therefore not treated as dups.
    Two rows with the same bet_id AND the same status (e.g., a tick-overlap
    replay) produce the SAME key and ARE treated as dups (blocked).

    Falls back to _DEFAULT_STATUS ("open") when the row has no "status" field.
    """
    bid = str(row.get("bet_id") or _bet_id(row))
    status = str(row.get("status") or _DEFAULT_STATUS).strip().lower()
    return "%s|%s" % (bid, status)


def _seen_status_keys(path: Path) -> Set[str]:
    """Return the set of (bet_id, status) keys present in the ledger at *path*.

    Missing file -> empty set.  Blank lines and malformed JSON are silently
    skipped (same tolerance contract as clv_ledger.load_ledger).
    """
    rows = _load_ledger(path)
    return {_status_key(r) for r in rows}


def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with all banned dollar/pnl/roi keys removed."""
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def append_if_new_status(
    record: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> bool:
    """Append *record* ONLY when (bet_id, status) is not already in the ledger.

    This is the status-aware replacement for clv_ledger_dedup.append_if_new.
    The critical difference: the dedup check is on _status_key(record) =
    "<bet_id>|<status>" rather than bet_id alone, so an open row and its
    settled twin are BOTH written even though they share the same bet_id.

    Parameters
    ----------
    record:
        Row dict to append.  Must carry a "status" field for correct behaviour;
        "open" is assumed when absent.
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional mutable set of existing status_keys (strings "<bet_id>|<status>").
        Pass a set shared across multiple calls in one session to avoid re-scanning
        the ledger on each write.  The function adds the new key to the set when a
        row is appended.  Omit (None) for single-call use -- the ledger is scanned
        once per call in that case.

        INVARIANT: the set stores status_keys (not raw bet_ids).  Both the
        fast-path (checking _seen) and the re-scan path (_seen_status_keys) use
        _status_key(), so they are guaranteed to agree on every key.

    Returns
    -------
    bool
        True  -- row was written (new (bet_id, status) pair).
        False -- row was skipped: (bet_id, status) already present, OR an
                 unexpected error occurred.  Never raises.

    Honesty:
        * BANNED_KEYS stripped before writing (units-only contract).
        * Never writes a dollar / pnl / roi / bankroll field.
        * Never mutates existing rows.
        * Never places a real bet.
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    try:
        skey = _status_key(record)
        existing: Set[str] = (
            _seen if _seen is not None else _seen_status_keys(target)
        )
        if skey in existing:
            return False

        # Strip any dollar/pnl/roi keys before writing (belt-and-suspenders).
        clean = _strip_dollar_keys(record)
        # Ensure bet_id is present on the written row.
        if not clean.get("bet_id"):
            clean["bet_id"] = str(record.get("bet_id") or _bet_id(record))

        # Funnel through the lock-guarded primitive when available.
        written = False
        try:
            from scripts.platformkit.clv_ledger_io import append_row as _append_row
            _append_row(clean, path=target)
            written = True
        except Exception:  # noqa: BLE001 -- lock layer is an aid, never a hard dep
            pass

        if not written:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(clean, default=str) + "\n")

        if _seen is not None:
            _seen.add(skey)
        return True

    except Exception:  # noqa: BLE001 -- never let the guard crash the caller
        return False


__all__ = ["append_if_new_status"]
