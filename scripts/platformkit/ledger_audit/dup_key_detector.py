"""scripts.platformkit.ledger_audit.dup_key_detector -- read-only CLV ledger dup scanner.

Scans the CLV ledger (data/frontend/clv_ledger.jsonl) for duplicate row keys using
a mirrored key formula matching governance/concurrency_guard._row_key:

  priority: bet_id > row_id > id > SHA-1 of sorted JSON
  STATUS DIMENSION: the status field is folded into the key so that an open row
  and its settled twin (same bet_id, different status) produce DISTINCT keys and
  are NOT flagged as duplicates.  This mirrors the fix in concurrency_guard._row_key
  (CLV-STATUS-KEY) and in clv_ledger_status_dedup.status_key.

This module is MEASUREMENT-ONLY.
  - Never writes, dedupes, or mutates the ledger.
  - Never authorises a bet.
  - Never claims a model edge (calibration not edge; units not $).
  - Returns UNAVAILABLE (not an exception) when the ledger is absent.

Result shape (dict):
  {
    "status":        "DUPS_FOUND" | "CLEAN" | "UNAVAILABLE",
    "n_dups":        int,                    # number of distinct dup keys
    "dup_keys":      list[str],              # sorted list of colliding keys
    "first_seen_kept": {key: int},           # line-number of first occurrence
    "n_rows_scanned": int,
    "ledger_path":   str,
    "error":         str | null,
  }

INVARIANTS: <=300 LOC; ASCII; no secrets; stdlib only (json, hashlib, pathlib).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Row-key derivation -- mirrors governance/concurrency_guard._row_key exactly
# ---------------------------------------------------------------------------

def _row_key(row: Dict[str, Any]) -> str:
    """Stable STATUS-AWARE unique key for a ledger row.

    Mirrors governance/concurrency_guard._row_key (CLV-STATUS-KEY fix):
      priority: bet_id -> row_id -> id -> SHA-1 of sorted JSON content.
    The row's ``status`` is folded into the key so that an open row
    ("<id>|open") and its settled twin ("<id>|settled") produce DISTINCT keys
    and are NOT flagged as duplicates.  A true byte-for-byte replay (same id
    AND same status) still collides and is correctly reported as a duplicate.
    Rows without a status default to "open".
    """
    status = str(row.get("status") or "open").strip().lower()
    for field in ("bet_id", "row_id", "id"):
        val = row.get(field)
        if val is not None:
            return "%s|%s" % (str(val), status)
    payload = json.dumps(row, sort_keys=True, default=str)
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

_STATUS_DUPS = "DUPS_FOUND"
_STATUS_CLEAN = "CLEAN"
_STATUS_UNAVAIL = "UNAVAILABLE"


def scan_ledger(
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Scan the CLV ledger for duplicate row keys. Read-only; never raises.

    Parameters
    ----------
    path:
        Override ledger location (defaults to the canonical
        data/frontend/clv_ledger.jsonl from clv_ledger.DEFAULT_LEDGER).

    Returns
    -------
    dict with keys: status, n_dups, dup_keys, first_seen_kept,
                    n_rows_scanned, ledger_path, error.
    """
    ledger = _resolve_path(path)
    base: Dict[str, Any] = {
        "status": _STATUS_UNAVAIL,
        "n_dups": 0,
        "dup_keys": [],
        "first_seen_kept": {},
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

    # --- tally key occurrences -------------------------------------------------
    # first_seen[key] = line number (1-based) of the FIRST occurrence
    # dup_keys = keys seen more than once
    first_seen: Dict[str, int] = {}
    dup_keys_set: set = set()

    for lineno, row in rows:
        key = _row_key(row)
        if key in first_seen:
            dup_keys_set.add(key)
        else:
            first_seen[key] = lineno

    dup_keys_sorted = sorted(dup_keys_set)

    base["n_rows_scanned"] = len(rows)
    base["n_dups"] = len(dup_keys_sorted)
    base["dup_keys"] = dup_keys_sorted
    base["first_seen_kept"] = {k: first_seen[k] for k in dup_keys_sorted}
    base["status"] = _STATUS_DUPS if dup_keys_sorted else _STATUS_CLEAN

    return base


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_path(path: Optional[Path]) -> Path:
    if path is not None:
        return Path(path)
    try:
        from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
        return Path(DEFAULT_LEDGER)
    except Exception:  # noqa: BLE001
        # Fallback to conventional relative path from repo root
        _here = Path(__file__).resolve()
        repo = _here.parents[3]
        return repo / "data" / "frontend" / "clv_ledger.jsonl"


def _load_rows(ledger: Path):
    """Load all valid JSONL rows; skip blank/torn lines; return (rows, error_msg|None)."""
    rows: List[tuple] = []  # (lineno, dict)
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
                    parse_error = parse_error or ("line %d is not a JSON object" % lineno)
            except json.JSONDecodeError as exc:
                parse_error = parse_error or ("JSON parse error at line %d: %s" % (lineno, exc))
    return rows, parse_error


__all__ = ["scan_ledger", "_row_key"]
