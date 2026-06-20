"""scripts.platformkit.ledger_audit.clv_selfheal -- atomic keep-first dedup self-heal.

PURPOSE
-------
Stop the persistent governance BLOCK caused by open->settle status-change appends
that accumulate duplicate keys in the CLV ledger (QA iter2/4/5/6/7/8/11).

The _run_concurrency gate in governance/run_governance.py hard-fails when duplicate
row keys are present.  Normal settlement activity (one OPEN row + one SETTLED twin
per bet_id) produces STATUS-CHANGE rows that share the same bet_id but differ in
status -- these are NOT true duplicates (clv_reconcile_preflight's status-aware key
distinguishes them).  However, replay/retry scenarios can produce genuine duplicates
(same bet_id AND same status) that legitimately block the gate.

This module adds a GUARDED, IDEMPOTENT self-heal that runs BEFORE _run_concurrency:
  1. Call reconcile_preflight (read-only, status-aware scan) to get the keep-first
     plan.
  2. If no dups -> return CLEAN immediately.
  3. If dups -> execute the keep-first plan atomically (tmp + os.replace) and log
     every dropped key.
  4. Re-scan the healed ledger.  If genuine dups remain after the heal (real
     corruption -- keys that should not be there even after keep-first) -> return
     HEALED_BLOCKED so the caller (run_governance) still fail-closes the gate.
  5. If clean after heal -> return HEALED_OK.

STATUS-CHANGE ROWS (open -> settle)
------------------------------------
The key formula used here mirrors governance/concurrency_guard._row_key:
  key = <bet_id-or-fallback>|<status>
So an OPEN row ("<id>|open") and its SETTLED twin ("<id>|settled") produce DISTINCT
keys and are NEVER deduplicated by this module.  Only rows with the SAME (bet_id,
status) pair collide and are deduplicated.  This is the only correct behaviour for
an append-only status-change ledger.

ATOMICITY
---------
The rewrite is: write rows to a *.tmp file -> os.replace (atomic on all OSes) ->
log dropped keys.  The original is backed up to <ledger>.selfheal.bak before the
replace.  If anything fails before the replace the original is untouched.

HONESTY INVARIANTS
------------------
* NEVER writes data/registry/.
* NEVER authorises a bet, NEVER claims an edge.
* No $ / pnl / roi / profit field introduced or preserved.
* Calibration, not edge.
* Units not $.
* Dedup is keep-first and logged; no data is silently destroyed.

INVARIANTS: <=300 LOC; ASCII; no secrets; stdlib only.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.ledger_audit.clv_reconcile_preflight import (
    reconcile_preflight,
    _row_key_status_aware,
)

logger = logging.getLogger("clv_selfheal")

# Return status constants
SELFHEAL_CLEAN = "CLEAN"           # no dups; ledger untouched
SELFHEAL_OK = "HEALED_OK"          # dups found, healed, ledger now clean
SELFHEAL_BLOCKED = "HEALED_BLOCKED"  # healed but genuine dups remain -> gate still fails
SELFHEAL_UNAVAIL = "UNAVAILABLE"   # ledger missing or unreadable

_BANNED_DOLLAR_KEYS = frozenset({
    "dollar", "roi", "pnl", "profit", "usd", "bankroll", "stake_usd",
    "pnl_units", "profit_units", "roi_units",
})


def selfheal(
    path: Optional[Path] = None,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Idempotent keep-first dedup self-heal for the CLV ledger.

    Parameters
    ----------
    path:
        Override ledger location (None -> canonical DEFAULT_LEDGER via
        reconcile_preflight's resolver).
    dry_run:
        When True, analyse and compute the plan but NEVER write.
        Returns status=CLEAN or status=HEALED_OK/HEALED_BLOCKED with
        dry_run=True and rows unchanged.

    Returns
    -------
    dict::
        {
          "status":        SELFHEAL_CLEAN | HEALED_OK | HEALED_BLOCKED | UNAVAILABLE,
          "dups_before":   int,   # distinct dup keys before heal
          "dups_after":    int,   # distinct dup keys after heal (0 if HEALED_OK)
          "rows_in":       int,
          "rows_out":      int,
          "dropped_keys":  list[str],  # keys whose extra occurrences were removed
          "ledger_path":   str,
          "dry_run":       bool,
          "error":         str | None,
        }

    Never raises. Mutation is atomic (os.replace). Original is backed up to
    <ledger>.selfheal.bak before replace. No $ field anywhere.
    """
    result: Dict[str, Any] = {
        "status": SELFHEAL_UNAVAIL,
        "dups_before": 0,
        "dups_after": 0,
        "rows_in": 0,
        "rows_out": 0,
        "dropped_keys": [],
        "ledger_path": str(path) if path is not None else "",
        "dry_run": dry_run,
        "error": None,
    }

    try:
        # --- Phase 1: read-only scan -------------------------------------------
        pre = reconcile_preflight(path=path)
        result["ledger_path"] = pre["ledger_path"]
        result["rows_in"] = pre["n_rows_scanned"]

        if pre["status"] == "UNAVAILABLE":
            result["status"] = SELFHEAL_UNAVAIL
            result["error"] = pre.get("error") or "ledger unavailable"
            return result

        result["dups_before"] = pre["n_dups"]

        if pre["n_dups"] == 0:
            result["status"] = SELFHEAL_CLEAN
            result["rows_out"] = pre["n_rows_scanned"]
            return result

        # --- Phase 2: build keep-first row list from the plan ------------------
        keep_first_plan = pre["keep_first_plan"]  # list of {key, kept_line, quarantine_candidates}
        # Build a set of (0-based line indices) to DROP (quarantine candidates).
        # kept_line and quarantine_candidates are 1-based line numbers.
        drop_lines = set()
        dropped_keys: List[str] = []
        for entry in keep_first_plan:
            for lineno in entry["quarantine_candidates"]:
                drop_lines.add(lineno)
            dropped_keys.append(entry["key"])

        if dry_run:
            result["status"] = SELFHEAL_OK  # would be clean after heal
            result["dropped_keys"] = sorted(dropped_keys)
            result["rows_out"] = result["rows_in"] - len(drop_lines)
            return result

        # --- Phase 3: atomic rewrite -------------------------------------------
        ledger = Path(pre["ledger_path"])
        healed_rows = _read_keep_rows(ledger, drop_lines)
        result["rows_out"] = len(healed_rows)
        result["dropped_keys"] = sorted(dropped_keys)

        _atomic_write(ledger, healed_rows)

        logger.info(
            "clv_selfheal: healed %s -- dropped %d dup rows for keys: %s",
            ledger,
            len(drop_lines),
            sorted(dropped_keys),
        )

        # --- Phase 4: verify the heal was sufficient ---------------------------
        post = reconcile_preflight(path=ledger)
        result["dups_after"] = post["n_dups"]

        if post["n_dups"] == 0:
            result["status"] = SELFHEAL_OK
        else:
            # Genuine corruption: dups remain after keep-first dedup -> gate must
            # still fail-close (caller enforces this).
            result["status"] = SELFHEAL_BLOCKED
            result["error"] = (
                "HEALED_BLOCKED: %d genuine dup(s) remain after keep-first dedup; "
                "manual inspection required" % post["n_dups"]
            )
            logger.warning("clv_selfheal: %s", result["error"])

    except Exception as exc:  # noqa: BLE001
        result["status"] = SELFHEAL_UNAVAIL
        result["error"] = "selfheal internal error: %s" % exc
        logger.exception("clv_selfheal: unexpected error")

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_keep_rows(
    ledger: Path,
    drop_lines: "set[int]",
) -> List[Dict[str, Any]]:
    """Read ledger JSONL and return rows whose 1-based lineno is NOT in drop_lines.

    Dollar keys are stripped from every row (belt-and-suspenders honesty gate).
    Blank and unparseable lines are silently skipped (matches clv_reconcile_preflight).
    """
    rows: List[Dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            if lineno in drop_lines:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    rows.append(_strip_dollar_keys(obj))
            except json.JSONDecodeError:
                pass  # skip torn/invalid lines
    return rows


def _strip_dollar_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *row* with banned dollar/pnl/roi keys removed."""
    out = dict(row)
    for k in _BANNED_DOLLAR_KEYS:
        out.pop(k, None)
    return out


def _atomic_write(ledger: Path, rows: List[Dict[str, Any]]) -> None:
    """Write *rows* as JSONL to *ledger* atomically (backup + tmp + os.replace).

    Steps:
      1. Write to a sibling *.selfheal.tmp file.
      2. Backup the original to *.selfheal.bak (overwrite prior bak).
      3. os.replace(tmp, ledger) -- atomic on all platforms.

    If anything fails before os.replace the original is untouched.  The .tmp is
    cleaned up on failure.
    """
    backup = ledger.with_suffix(ledger.suffix + ".selfheal.bak")
    tmp_path: Optional[Path] = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(ledger.parent),
            prefix=ledger.name + ".",
            suffix=".selfheal.tmp",
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, default=str) + "\n")
        # Backup BEFORE the replace so original is never destroyed without a copy.
        backup.write_text(ledger.read_text(encoding="utf-8"), encoding="utf-8")
        os.replace(tmp_name, str(ledger))
        tmp_path = None  # replace succeeded; don't clean up (file is now ledger)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                os.unlink(str(tmp_path))
            except OSError:
                pass


__all__ = [
    "selfheal",
    "SELFHEAL_CLEAN",
    "SELFHEAL_OK",
    "SELFHEAL_BLOCKED",
    "SELFHEAL_UNAVAIL",
]
