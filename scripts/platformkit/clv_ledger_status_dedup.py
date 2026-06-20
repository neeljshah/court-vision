"""scripts.platformkit.clv_ledger_status_dedup -- status-aware dedup key + append.

ROOT CAUSE (CLV-STATUS-KEY / QA iter 2/4/5/6):
  clv_ledger.bet_id encodes sport|event|market|side|book|date -- deliberately
  status-agnostic so that the open row and its settled twin share ONE identity.
  The governance concurrency gate mirrors that formula verbatim as its _row_key
  and therefore sees the open row and the settled twin as DUPLICATES.  On every
  settlement cycle run_governance exits 1 (BLOCKED).

THIS MODULE:
  Adds one layer of disambiguation WITHOUT editing the governance/ tree:

    status_key(row) -> "<bet_id>|<status>"

  "open" and "settled" variants of the same logical bet produce DISTINCT keys.
  A true byte-for-byte replay (same bet_id AND same status) produces an identical
  key and is still treated as a duplicate (blocked).

  append_if_new_status_aware(record, path) uses status_key instead of bet_id
  alone.  The caller's settlement writer substitutes this function for the raw
  clv_ledger_dedup.append_if_new to get the correct behaviour:

    * open row written first       -> status_key = "<id>|open"    (appended)
    * settled row written later    -> status_key = "<id>|settled"  (appended)
    * open row replayed again      -> status_key = "<id>|open"    (blocked)
    * settled row replayed again   -> status_key = "<id>|settled"  (blocked)

  Missing ledger -> create and append (inherited from clv_ledger_io).
  Never raises; returns {"appended": bool, ...} on both success and failure.

HONESTY CONTRACT (binding):
  * UNITS ONLY -- no dollar / bankroll / pnl / roi field is introduced.
    BANNED_KEYS (from clv_ledger_migrate) are stripped before every write.
  * append-only: existing ledger lines are never mutated.
  * Never claims an edge; this is a plumbing dedup helper.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no secrets; per-file
test in scripts/platformkit/test_clv_ledger_status_dedup.py.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_status_dedup.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, bet_id as _bet_id
from scripts.platformkit.clv_ledger import load_ledger as _load_ledger
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS

# ---------------------------------------------------------------------------
# Public helper 1: status-aware dedup key
# ---------------------------------------------------------------------------

_DEFAULT_STATUS = "open"


def status_key(row: Dict[str, Any]) -> str:
    """Return the status-aware dedup key for *row*: "<bet_id>|<status>".

    Two rows that share the same bet_id but differ in status ("open" vs
    "settled") produce DISTINCT keys so they are NOT treated as duplicates.
    Two rows that are byte-for-byte identical (same bet_id AND same status)
    produce the SAME key and ARE treated as duplicates (true replay blocked).

    Falls back to _DEFAULT_STATUS ("open") when the row carries no "status"
    field so that a pre-settlement row is always safely classified.

    Mirrors the contract of governance.concurrency_guard._row_key but adds the
    status dimension.  Does NOT edit governance/ (human-gated).
    """
    bid = str(row.get("bet_id") or _bet_id(row))
    status = str(row.get("status") or _DEFAULT_STATUS).strip().lower()
    return "%s|%s" % (bid, status)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with all banned dollar/pnl/roi keys removed."""
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


def _seen_status_keys(path: Path) -> Set[str]:
    """Return the set of status_key values already present in *path*.

    Missing file -> empty set.  Blank lines and malformed JSON are silently
    skipped (mirrors clv_ledger_dedup._seen_bet_ids contract).
    """
    rows = _load_ledger(path)
    return {status_key(r) for r in rows}


# ---------------------------------------------------------------------------
# Public helper 2: status-aware conditional append
# ---------------------------------------------------------------------------

def append_if_new_status_aware(
    record: Dict[str, Any],
    path: Optional[Path] = None,
    *,
    _seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Append *record* to the ledger ONLY when its status_key is not yet present.

    This is the drop-in replacement for clv_ledger_dedup.append_if_new to use
    in settlement writers.  The key difference: the dedup check is on
    status_key(record) = "<bet_id>|<status>" rather than on bet_id alone, so an
    open row and its settled twin are both retained.

    Parameters
    ----------
    record:
        The row dict to append.  A "status" key is required for correct
        behaviour.  "open" is assumed when absent.
    path:
        Override ledger path.  DEFAULT_LEDGER when None.
    _seen:
        Optional pre-computed set of existing status_keys.  Pass a mutable set
        to avoid re-scanning the ledger on every call in a batch session; the
        function adds the new key to the set when a row is appended.  Omit
        (None) for single-call use.

    Returns
    -------
    dict
        {"appended": True,  "key": <status_key>}  -- row was written
        {"appended": False, "key": <status_key>}  -- already present (no-op)
        {"appended": False, "error": <str>}        -- unexpected failure

    Never raises.  Existing ledger lines are never mutated.  BANNED_KEYS are
    stripped before writing (belt-and-suspenders honesty guard).
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    try:
        skey = status_key(record)
        existing: Set[str] = (
            _seen if _seen is not None else _seen_status_keys(target)
        )
        if skey in existing:
            return {"appended": False, "key": skey}

        # Strip any banned dollar keys before writing.
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
        except Exception:  # noqa: BLE001 -- fall through to direct write
            pass

        if not written:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(clean, default=str) + "\n")

        if _seen is not None:
            _seen.add(skey)
        return {"appended": True, "key": skey}

    except Exception as exc:  # noqa: BLE001 -- never crash the caller
        return {"appended": False, "error": "%s: %s" % (type(exc).__name__, exc)}


# ---------------------------------------------------------------------------
# Public helper 3: idempotent status-aware dedup rewrite (keeps LATEST)
# ---------------------------------------------------------------------------

import json as _json
import os as _os
import tempfile as _tempfile


def dedup_status_ledger(
    path: Optional[Path] = None,
    *,
    dry_run: bool = True,
) -> "dict[str, object]":
    """Rewrite the ledger keeping the LATEST occurrence of each (bet_id|status) key.

    This is the status-aware sibling of clv_ledger_dedup.dedup_ledger.  Where that
    function keys on bet_id alone (and would WRONGLY collapse an open+settled twin
    pair into one row), THIS function keys on status_key(row) = "<bet_id>|<status>".

    LATEST wins: if two rows share the same (bet_id, status) the last-written row is
    kept. Open and settled twins of the same logical bet produce DISTINCT keys and are
    BOTH retained untouched.

    READ-SAFE BY DEFAULT: when dry_run=True (the default) the ledger is analysed and
    a report returned but NOTHING is written, replaced, or backed up.  Pass
    dry_run=False to commit the atomic rewrite.

    Idempotent: a ledger with no status-aware duplicates is left unchanged.
    Atomic + backed-up: same tmp+replace+.bak pattern as clv_ledger_dedup.
    Dollar keys are stripped from every row during the pass.

    Returns:
        {status, rows_in, rows_out, dups_removed, path, dry_run}
        status = "ok"         -- rewrite applied (dups_removed > 0, dry_run False)
        status = "dry_run"    -- would remove dups but dry_run=True; file unchanged
        status = "no_change"  -- already clean, file not touched
        status = "no_file"    -- ledger does not exist
        status = "error: X"   -- unexpected failure; original file intact
    """
    target = Path(path) if path is not None else DEFAULT_LEDGER
    result: "dict[str, object]" = {
        "status": "ok",
        "rows_in": 0,
        "rows_out": 0,
        "dups_removed": 0,
        "path": str(target),
        "dry_run": dry_run,
    }
    if not target.exists():
        result["status"] = "no_file"
        return result
    try:
        rows = _load_ledger(target)
        result["rows_in"] = len(rows)

        # Strip dollar keys and compute status-aware dedup keeping LATEST.
        rows_clean = [_strip_dollar_keys(r) for r in rows]
        seen: "dict[str, int]" = {}  # key -> index in rows_clean (last wins)
        for idx, r in enumerate(rows_clean):
            skey = status_key(r)
            seen[skey] = idx  # overwrite -> latest index per key

        deduped = [rows_clean[idx] for idx in sorted(seen.values())]
        dups = len(rows_clean) - len(deduped)
        result["rows_out"] = len(deduped)
        result["dups_removed"] = dups

        if dups == 0:
            result["status"] = "no_change"
            return result
        if dry_run:
            result["status"] = "dry_run"
            return result

        # Backup original (overwrite prior .bak to stay clean on re-runs).
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

        # Atomic rewrite: tmp in same dir, then os.replace.
        fd, tmp_name = _tempfile.mkstemp(
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
        )
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as fh:
                for r in deduped:
                    fh.write(_json.dumps(r, default=str) + "\n")
            _os.replace(tmp_name, str(target))
        finally:
            if Path(tmp_name).exists():
                try:
                    _os.unlink(tmp_name)
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 -- dedup must never crash the box
        result["status"] = "error: %s" % type(exc).__name__
    return result


__all__ = [
    "status_key",
    "append_if_new_status_aware",
    "dedup_status_ledger",
]
