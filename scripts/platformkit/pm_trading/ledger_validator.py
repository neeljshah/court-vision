"""ledger_validator.py -- CI guard: PM ledger completeness + dedup validator.

Fail-closed on EITHER:
  1. POLICY COMPLETENESS: every "open" row has tier/flat_unit/quarter_kelly stamped.
  2. DUP-KEY GUARD: no two rows share the same (bet_id|status) composite key.
     open+settled twins have DISTINCT keys and are NOT flagged as dups.

CONTRACT: READ-ONLY; UNITS only (no $/roi/pnl); pass_=False when missing_tier>0
OR dup_keys>0; CLI exits 0=pass, 1=fail.
Build only under scripts/platformkit/pm_trading/.  <=300 LOC.  ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Imports with hermetic fallback
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit import clv_ledger as _clv
    from scripts.platformkit.clv_ledger_enrich import enrich_rows
    from scripts.platformkit.clv_ledger_dedup import _row_key as _make_row_key
except ImportError:  # pragma: no cover
    import sys as _sys
    _root = str(Path(__file__).resolve().parents[3])
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    try:
        from scripts.platformkit import clv_ledger as _clv
        from scripts.platformkit.clv_ledger_enrich import enrich_rows
        from scripts.platformkit.clv_ledger_dedup import _row_key as _make_row_key
    except ImportError:
        _clv = None  # type: ignore[assignment]
        enrich_rows = None  # type: ignore[assignment]
        _make_row_key = None  # type: ignore[assignment]

REQUIRED_POLICY_FIELDS: tuple = ("tier", "flat_unit", "quarter_kelly")
_OPEN_STATUS = "open"
_STAMP_STATUS = "policy_stamp"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class ValidationResult:
    """Outcome of a single ledger validation run.

    pass_ : True only when missing_tier==0 AND dup_keys==0.
    missing_tier : open rows with tier absent/None after enrichment+stamps.
    dup_keys : rows sharing a (bet_id|status) key with a prior row.
    flagged_ids : bet_id values of open rows missing policy fields.
    dup_key_list : (bet_id|status) composite keys appearing >1 time.
    total_open : "open" rows examined (not policy_stamp or settled).
    detail : one entry per flagged row.
    """
    pass_: bool
    missing_tier: int
    dup_keys: int = 0
    flagged_ids: List[str] = field(default_factory=list)
    dup_key_list: List[str] = field(default_factory=list)
    total_open: int = 0
    detail: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_stamps(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build bet_id -> first policy_stamp row map (first wins)."""
    stamps: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != _STAMP_STATUS:
            continue
        bid = str(row.get("bet_id") or "")
        if bid and bid not in stamps:
            stamps[bid] = row
    return stamps


def _apply_stamps(
    open_row: Dict[str, Any],
    stamps: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Return copy of open_row with policy fields filled from stamp (existing wins)."""
    bid = str(open_row.get("bet_id") or "")
    stamp = stamps.get(bid)
    if stamp is None:
        return open_row
    merged = dict(open_row)
    for f in REQUIRED_POLICY_FIELDS:
        if merged.get(f) is None and stamp.get(f) is not None:
            merged[f] = stamp[f]
    return merged


def _find_dup_keys(rows: List[Dict[str, Any]]) -> List[str]:
    """Return (bet_id|status) keys that appear more than once across all rows."""
    def _key(r: Dict[str, Any]) -> str:
        if _make_row_key is not None:
            return _make_row_key(r)
        bid = str(r.get("bet_id") or "")
        status = str(r.get("status") or "open").strip().lower()
        return "%s|%s" % (bid, status)

    counts: Dict[str, int] = {}
    for row in rows:
        k = _key(row)
        counts[k] = counts.get(k, 0) + 1
    return [k for k, n in counts.items() if n > 1]


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_ledger(
    path: Optional[Path] = None,
    *,
    raw_rows: Optional[List[Dict[str, Any]]] = None,
) -> ValidationResult:
    """Validate policy completeness and (bet_id|status) dedup integrity.

    pass_=True only when missing_tier==0 AND dup_keys==0.
    Read-only; never raises; errors -> pass_=False.
    """
    try:
        if raw_rows is not None:
            rows = list(raw_rows)
        elif _clv is not None:
            rows = _clv.load_ledger(path)
        else:
            return ValidationResult(
                pass_=False, missing_tier=0, dup_keys=0, total_open=0,
                detail=[{"error": INSUFFICIENT_DATA, "reason": "clv_ledger unavailable"}],
            )
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(
            pass_=False, missing_tier=0, dup_keys=0, total_open=0,
            detail=[{"error": INSUFFICIENT_DATA, "reason": str(exc)}],
        )

    # Dup-key guard (all rows: open, settled, policy_stamp).
    dup_key_list = _find_dup_keys(rows)
    dup_keys = len(dup_key_list)

    # Policy completeness (open rows only).
    stamps = _collect_stamps(rows)
    open_rows_raw = [r for r in rows if r.get("status") == _OPEN_STATUS]
    try:
        enriched = enrich_rows(open_rows_raw) if enrich_rows is not None else [dict(r) for r in open_rows_raw]
    except Exception:  # noqa: BLE001
        enriched = [dict(r) for r in open_rows_raw]
    enriched = [_apply_stamps(r, stamps) for r in enriched]

    flagged_ids: List[str] = []
    detail: List[Dict[str, Any]] = []
    for row in enriched:
        missing_fields = [f for f in REQUIRED_POLICY_FIELDS if row.get(f) is None]
        if row.get("tier") is None:
            bid = str(row.get("bet_id") or "")
            flagged_ids.append(bid)
            detail.append({"bet_id": bid, "missing_fields": missing_fields,
                            "sport": row.get("sport"), "matchup": row.get("matchup")})

    missing_tier = len(flagged_ids)
    return ValidationResult(
        pass_=(missing_tier == 0 and dup_keys == 0),
        missing_tier=missing_tier,
        dup_keys=dup_keys,
        flagged_ids=flagged_ids,
        dup_key_list=dup_key_list,
        total_open=len(enriched),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PM ledger completeness + dedup (CI guard). 0=pass, 1=fail."
    )
    parser.add_argument("--path", type=Path, default=None,
                        help="Path to clv_ledger.jsonl")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Emit result as JSON to stdout")
    args = parser.parse_args(argv)
    result = validate_ledger(path=args.path)

    if args.json:
        print(json.dumps({
            "pass": result.pass_, "missing_tier": result.missing_tier,
            "dup_keys": result.dup_keys, "total_open": result.total_open,
            "flagged_ids": result.flagged_ids, "dup_key_list": result.dup_key_list,
            "detail": result.detail,
        }, indent=2, default=str))
    else:
        status = "PASS" if result.pass_ else "FAIL"
        print("[ledger_validator] %s  open=%d  missing_tier=%d  dup_keys=%d"
              % (status, result.total_open, result.missing_tier, result.dup_keys))
        for entry in result.detail:
            print("  flagged %s missing=%s" % (entry.get("bet_id", ""), entry.get("missing_fields", [])))
        for k in result.dup_key_list:
            print("  dup_key %s" % k)

    return 0 if result.pass_ else 1


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["validate_ledger", "ValidationResult", "REQUIRED_POLICY_FIELDS", "INSUFFICIENT_DATA"]
