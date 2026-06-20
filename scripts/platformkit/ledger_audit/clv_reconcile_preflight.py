"""scripts.platformkit.ledger_audit.clv_reconcile_preflight -- read-only CLV ledger
dup-reconciliation preflight for the boot-preflight supervisor check.

This module surfaces the on-disk duplicate state (the 9-11 dated-2026-06-20 rows
that QA keeps flagging) WITHOUT auto-mutating the ledger.  Iter-7 invariant: human
review is required before any ledger mutation.

STATUS-AWARE key formula
------------------------
The original dup_key_detector._row_key uses bet_id alone, so an OPEN row and its
SETTLED twin for the same bet share the same key -> false dup.  This module uses
a STATUS-AWARE variant:

    key = <bet_id-or-fallback> + "|" + <status>

so open+settled twins emit DIFFERENT keys (they are NOT dups) while two identical
(bet_id|open) rows DO collide and are correctly flagged.

Result shape (dict returned by reconcile_preflight)
----------------------------------------------------
{
    "status":        "DUPS_FOUND" | "CLEAN" | "UNAVAILABLE",
    "n_dups":        int,                   # distinct dup keys (status-aware)
    "dup_keys":      list[str],             # sorted dup keys
    "keep_first_plan": [                    # one entry per dup key
        {
            "key":             str,
            "kept_line":       int,         # 1-based line number to keep
            "quarantine_candidates": [int], # later duplicates to quarantine
        },
        ...
    ],
    "n_rows_scanned": int,
    "ledger_path":   str,
    "error":         str | null,
}

HONESTY INVARIANTS
------------------
* NEVER writes, deletes, or dedupes the ledger (read-only measurement).
* NEVER authorises a real-money bet.
* No dollar / P&L / roi / profit field anywhere.
* Missing ledger -> status=UNAVAILABLE, not an exception.
* Never green (CLEAN) when dups exist.
* CLV data is calibration, not edge.

INVARIANTS: <=300 LOC; ASCII; no secrets; stdlib only (json, hashlib, pathlib).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Status-aware row key  (mirrors concurrency_guard._row_key + appends status)
# ---------------------------------------------------------------------------

def _row_key_status_aware(row: Dict[str, Any]) -> str:
    """Stable, status-aware unique key for a ledger row.

    Priority: bet_id -> row_id -> id -> SHA-1 of sorted JSON content.
    The row's ``status`` field (open / settled / ...) is appended so that an
    open row and its settled twin share the same bet_id but produce DIFFERENT
    keys and are NOT counted as duplicates.

    Missing/None status is normalised to the empty string so the function
    never raises on malformed rows.
    """
    status = str(row.get("status") or "").strip().lower()
    for field in ("bet_id", "row_id", "id"):
        val = row.get(field)
        if val is not None:
            return "%s|%s" % (str(val), status)
    payload = json.dumps(row, sort_keys=True, default=str)
    sha = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return "sha1:%s|%s" % (sha, status)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_DUPS = "DUPS_FOUND"
_STATUS_CLEAN = "CLEAN"
_STATUS_UNAVAIL = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def reconcile_preflight(
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scan the CLV ledger for status-aware duplicate row keys.  Read-only; never raises.

    Parameters
    ----------
    path:
        Override the ledger location.  If None the canonical
        data/frontend/clv_ledger.jsonl path is resolved via
        scripts.platformkit.clv_ledger.DEFAULT_LEDGER (with a filesystem fallback).

    Returns
    -------
    dict -- see module docstring for the shape.  Never raises; missing ledger
    returns status=UNAVAILABLE.  No $ / P&L / roi / profit field ever appears.
    """
    ledger = _resolve_path(path)
    base: Dict[str, Any] = {
        "status": _STATUS_UNAVAIL,
        "n_dups": 0,
        "dup_keys": [],
        "keep_first_plan": [],
        "n_rows_scanned": 0,
        "ledger_path": str(ledger),
        "error": None,
    }

    if not ledger.exists():
        base["error"] = "ledger not found: %s" % ledger
        return base

    try:
        rows, parse_error = _load_rows(ledger)
    except Exception as exc:  # noqa: BLE001
        base["error"] = "read error: %s" % exc
        return base

    if parse_error:
        base["error"] = parse_error

    # --- tally occurrences using the status-aware key ----------------------
    # first_seen[key]     = 1-based line number of the FIRST occurrence
    # all_lines[key]      = all 1-based line numbers seen (first + later)
    first_seen: Dict[str, int] = {}
    all_lines: Dict[str, List[int]] = {}

    for lineno, row in rows:
        key = _row_key_status_aware(row)
        if key not in first_seen:
            first_seen[key] = lineno
            all_lines[key] = [lineno]
        else:
            all_lines[key].append(lineno)

    dup_keys_sorted = sorted(k for k, lines in all_lines.items() if len(lines) > 1)

    # --- build the keep-first quarantine plan ------------------------------
    plan: List[Dict[str, Any]] = []
    for key in dup_keys_sorted:
        lines = all_lines[key]
        plan.append({
            "key": key,
            "kept_line": lines[0],
            "quarantine_candidates": lines[1:],
        })

    base["n_rows_scanned"] = len(rows)
    base["n_dups"] = len(dup_keys_sorted)
    base["dup_keys"] = dup_keys_sorted
    base["keep_first_plan"] = plan
    base["status"] = _STATUS_DUPS if dup_keys_sorted else _STATUS_CLEAN

    return base


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(path: Optional[Path]) -> Path:
    """Resolve the ledger path: explicit arg -> DEFAULT_LEDGER import -> fs fallback."""
    if path is not None:
        return Path(path)
    try:
        from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
        return Path(DEFAULT_LEDGER)
    except Exception:  # noqa: BLE001
        _here = Path(__file__).resolve()
        repo = _here.parents[3]
        return repo / "data" / "frontend" / "clv_ledger.jsonl"


def _load_rows(ledger: Path):
    """Load all valid JSONL rows; skip blank/torn lines; return (rows, error_msg|None)."""
    rows: List[tuple] = []   # (lineno, dict)
    parse_error: Optional[str] = None
    with ledger.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    rows.append((lineno, obj))
                else:
                    parse_error = (
                        parse_error or ("line %d is not a JSON object" % lineno)
                    )
            except json.JSONDecodeError as exc:
                parse_error = (
                    parse_error or ("JSON parse error at line %d: %s" % (lineno, exc))
                )
    return rows, parse_error


__all__ = ["reconcile_preflight", "_row_key_status_aware"]
