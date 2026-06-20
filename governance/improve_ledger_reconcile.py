"""governance.improve_ledger_reconcile -- read-only parity check between the
self-improve daemon's SHIP/promotion rows and graded CLV/eval rows.

PROBLEM STATEMENT
-----------------
The self-improve daemon records every SHIP verdict in the loop ledger
(.planning/loop/ledger.jsonl).  A separate CLV/eval grading pass independently
produces graded rows in the loop ledger (the same JSONL, keyed by signal name
+ date).  There is currently NO module that reconciles the two sets: a daemon
SHIP with no matching graded row is SILENT.  This module surfaces that gap.

WHAT IT MEASURES
----------------
  n_ship       -- total SHIP-verdict rows in the loop ledger (daemon promotions)
  n_graded     -- rows whose ``clv`` field is not None (graded by the eval pass)
  n_orphan_ship -- SHIP rows with no matching graded row (no clv, no eval grade)
  n_promoted   -- SHIP rows that DO have a matching graded row (clv is not None)

REPORTED, NOT BLOCKING
----------------------
This check is REPORTED in run_governance (like realmoney_authorized) but NEVER
gates ok-ness.  An orphan SHIP is a monitoring signal, not a correctness failure.
The daemon may have SHIPped signals whose CLV grading is pending (offseason,
waiting for live prices).  A missing graded row is therefore INSUFFICIENT_DATA,
not a violation.

HONESTY INVARIANTS
------------------
* PURE / READ-ONLY -- never writes, never mutates the ledger, never raises.
* NEVER authorises a bet; no dollar / pnl / roi / profit field anywhere.
* No edge claim; calibration-not-edge; units not $.
* Missing ledger -> status UNAVAILABLE (never falsely green or falsely blocked).
* n_promoted=0 -> status INSUFFICIENT_DATA / "ratchet has not promoted".

INVARIANTS: build only under governance/; <=300 LOC; ASCII; no secrets;
stdlib only (json, pathlib); per-file tests only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

RECONCILE_VERSION = "governance.improve_ledger_reconcile.v1"

# The loop ledger lives at .planning/loop/ledger.jsonl (same as src/loop/ledger.py
# uses; we re-derive rather than import to keep this module dependency-free).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LEDGER = _REPO_ROOT / ".planning" / "loop" / "ledger.jsonl"

# Verdict string that the daemon writes on a passing signal.
_SHIP_VERDICT = "SHIP"

# Status constants surfaced in the result dict.
STATUS_CLEAN = "CLEAN"              # all SHIPs have a matching graded row
STATUS_ORPHAN = "ORPHAN_SHIPS"      # one or more SHIP rows lack a graded match
STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"  # no SHIPs at all (ratchet not promoted)
STATUS_UNAVAILABLE = "UNAVAILABLE"  # ledger missing or unreadable


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load all valid JSONL rows from *path*.  Returns [] if absent or malformed."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _is_ship(row: Dict[str, Any]) -> bool:
    """True iff *row* has a SHIP verdict (daemon promotion)."""
    verdict = str(row.get("verdict", "")).strip().upper()
    # Handle both the raw string "SHIP" and the enum repr "Verdict.SHIP".
    return verdict in (_SHIP_VERDICT, "VERDICT.SHIP")


def _is_graded(row: Dict[str, Any]) -> bool:
    """True iff *row* has a non-None CLV value (eval/grading pass completed)."""
    return row.get("clv") is not None


def _signal_key(row: Dict[str, Any]) -> str:
    """Stable match key: kind + name + date (mirrors ledger id schema)."""
    kind = str(row.get("kind") or "signal")
    name = str(row.get("name") or "")
    date = str(row.get("date") or "")
    return "%s:%s:%s" % (kind, name, date)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def reconcile(
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only parity check: daemon SHIP rows vs graded CLV/eval rows.

    Parameters
    ----------
    path:
        Override the loop ledger path.  If None the canonical
        .planning/loop/ledger.jsonl location is used.

    Returns
    -------
    dict with keys:
        ``status``         -- CLEAN | ORPHAN_SHIPS | INSUFFICIENT_DATA | UNAVAILABLE
        ``n_ship``         -- total SHIP-verdict rows
        ``n_graded``       -- SHIP rows with a non-None clv (graded)
        ``n_orphan_ship``  -- SHIP rows with no matching graded row
        ``n_promoted``     -- alias for n_graded (for clarity in scoreboard)
        ``orphan_keys``    -- list of signal keys for orphan SHIPs
        ``ledger_path``    -- the resolved ledger path (string)
        ``message``        -- human-readable status summary (ASCII)
        ``version``        -- RECONCILE_VERSION
        ``error``          -- None or a short error string (never raises)

    NEVER raises.  NEVER writes anything.  NEVER gates ok-ness.
    No dollar / pnl / roi / profit / edge field.
    """
    resolved = path if path is not None else _DEFAULT_LEDGER

    base: Dict[str, Any] = {
        "status": STATUS_UNAVAILABLE,
        "n_ship": 0,
        "n_graded": 0,
        "n_orphan_ship": 0,
        "n_promoted": 0,
        "orphan_keys": [],
        "ledger_path": str(resolved),
        "message": "ledger not found or unreadable",
        "version": RECONCILE_VERSION,
        "error": None,
    }

    if not resolved.exists():
        base["error"] = "loop ledger not found: %s" % resolved
        base["message"] = "UNAVAILABLE -- loop ledger absent (ratchet may not have run)"
        return base

    try:
        rows = _load_rows(resolved)
    except Exception as exc:  # noqa: BLE001
        base["error"] = "read error: %s" % str(exc)[:200]
        base["message"] = "UNAVAILABLE -- ledger read error"
        return base

    # Partition rows into SHIP vs rest.
    ship_rows = [r for r in rows if _is_ship(r)]
    n_ship = len(ship_rows)

    if n_ship == 0:
        base["status"] = STATUS_INSUFFICIENT
        base["message"] = ("INSUFFICIENT_DATA -- ratchet has not promoted any signal "
                           "(n_ship=0); CLV grading not yet applicable")
        return base

    # For each SHIP row determine if a graded row (clv not None) exists for the
    # same (kind, name, date) key.  A graded match may be the SHIP row itself
    # (the daemon records clv if the gate returns one) or a separate grading row.
    graded_keys = {_signal_key(r) for r in rows if _is_graded(r)}

    orphan_keys: List[str] = []
    n_graded = 0
    for row in ship_rows:
        key = _signal_key(row)
        if key in graded_keys or _is_graded(row):
            n_graded += 1
        else:
            orphan_keys.append(key)

    n_orphan = len(orphan_keys)

    if n_orphan == 0:
        status = STATUS_CLEAN
        msg = ("CLEAN -- all %d SHIP row(s) have a matching graded CLV row "
               "(n_promoted=%d)" % (n_ship, n_graded))
    else:
        status = STATUS_ORPHAN
        msg = ("ORPHAN_SHIPS -- %d of %d SHIP row(s) lack a graded CLV row "
               "(pending eval or offseason; not a gate failure)" % (n_orphan, n_ship))

    base.update({
        "status": status,
        "n_ship": n_ship,
        "n_graded": n_graded,
        "n_orphan_ship": n_orphan,
        "n_promoted": n_graded,
        "orphan_keys": sorted(orphan_keys),
        "message": msg,
        "error": None,
    })
    return base


__all__ = [
    "reconcile",
    "RECONCILE_VERSION",
    "STATUS_CLEAN",
    "STATUS_ORPHAN",
    "STATUS_INSUFFICIENT",
    "STATUS_UNAVAILABLE",
]
