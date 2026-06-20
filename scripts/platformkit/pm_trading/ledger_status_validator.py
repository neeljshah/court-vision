"""ledger_status_validator.py -- CI guard: CLV ledger STATUS-completeness validator.

Distinct from ledger_validator.py (which checks open-row policy-stamp completeness).
THIS module checks the structural twin relationship between open and settled rows:

  1. COLLISION check -- no two rows may share (bet_id, status).
     A collision means the same logical bet was written twice with the same
     lifecycle state; that is the exact governance failure mode caught here
     BEFORE the governance preflight can block.

  2. ORPHAN check -- every settled row must have a matching open twin with
     the same bet_id.  A settled row without an open twin indicates a write
     anomaly (e.g., a settlement was appended but the original open row was
     lost or never written).

CONTRACT (binding):
  * READ-ONLY. Never writes, never appends, never mutates any row or file.
  * UNITS ONLY. No $/dollar/pnl/roi field is introduced, checked, or reported.
  * Fail-closed: any detected collision OR orphan -> pass_=False.
  * Returns a StatusValidationResult dataclass with:
      pass_         bool   -- True iff zero collisions AND zero orphans
      collision_keys list  -- (bet_id, status) tuples that appear more than once
      orphan_ids    list   -- bet_id strings with a settled row but no open twin
      total_rows    int    -- total JSONL rows examined (all statuses)
      total_bets    int    -- distinct bet_ids seen
  * CLI: python ledger_status_validator.py [--path PATH] [--json]
      exits 0 on pass, 1 on fail.

Mirrors the ValidationResult/validate_ledger pattern from ledger_validator.py.
Build only under scripts/platformkit/pm_trading/.  <=300 LOC.  ASCII only.
No secrets.  Per-file test: test_ledger_status_validator.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Imports with flat-sibling fallback for hermetic per-file tests
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit import clv_ledger as _clv
except ImportError:  # pragma: no cover -- hermetic test path
    import importlib as _il  # noqa: F401
    _root = str(Path(__file__).resolve().parents[3])
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from scripts.platformkit import clv_ledger as _clv
    except ImportError:
        _clv = None  # type: ignore[assignment]

# Statuses that carry full lifecycle semantics (not helpers like policy_stamp)
_OPEN_STATUS = "open"
_SETTLED_STATUS = "settled"

# Sentinel for insufficient data (honest; never fabricated)
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class StatusValidationResult:
    """Outcome of a single ledger status-completeness validation run.

    Attributes
    ----------
    pass_ : bool
        True only when zero collisions AND zero orphans are found.
    collision_keys : list of (bet_id, status) tuples
        Every (bet_id, status) pair that appears more than once in the ledger.
        Each entry represents a governance collision failure mode.
    orphan_ids : list of str
        bet_id values that have a settled row but NO matching open twin.
    total_rows : int
        Total rows examined (all statuses combined).
    total_bets : int
        Distinct bet_id values seen across all rows.
    detail : list of dict
        Human-readable detail entries for every finding (collision or orphan).
    """

    pass_: bool
    collision_keys: List[Tuple[str, str]] = field(default_factory=list)
    orphan_ids: List[str] = field(default_factory=list)
    total_rows: int = 0
    total_bets: int = 0
    detail: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_ledger_status(
    path: Optional[Path] = None,
    *,
    raw_rows: Optional[List[Dict[str, Any]]] = None,
) -> StatusValidationResult:
    """Validate (bet_id, status) uniqueness and open/settled twin completeness.

    Parameters
    ----------
    path :
        Path to the JSONL ledger file.  Defaults to clv_ledger.DEFAULT_LEDGER.
        Ignored when raw_rows is provided.
    raw_rows :
        Pre-loaded list of raw ledger dicts.  When provided, bypasses file I/O
        entirely (used by tests for hermetic validation without disk access).

    Returns
    -------
    StatusValidationResult
        pass_=True only when collision_keys==[] AND orphan_ids==[].
        Never raises; on load error returns pass_=False with detail entry.

    Notes
    -----
    * Read-only: no writes, no mutations to the source data.
    * Only "open" and "settled" rows are checked for twin completeness.
      Auxiliary rows (policy_stamp, etc.) are counted in total_rows but
      are excluded from orphan and collision analysis.
    * Collision detection covers ALL status values (including policy_stamp),
      because a duplicate policy_stamp is also a governance anomaly.
    """
    # 1. Load rows --------------------------------------------------------
    try:
        if raw_rows is not None:
            rows = list(raw_rows)
        elif _clv is not None:
            rows = _clv.load_ledger(path)
        else:
            return StatusValidationResult(
                pass_=False,
                total_rows=0,
                total_bets=0,
                detail=[{
                    "error": INSUFFICIENT_DATA,
                    "reason": "clv_ledger module unavailable",
                }],
            )
    except Exception as exc:  # noqa: BLE001
        return StatusValidationResult(
            pass_=False,
            total_rows=0,
            total_bets=0,
            detail=[{"error": INSUFFICIENT_DATA, "reason": str(exc)}],
        )

    total_rows = len(rows)

    # 2. Build (bet_id, status) occurrence map ---------------------------
    # Maps (bet_id, status) -> list of row indices (for reporting)
    key_occurrences: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    # Maps bet_id -> set of statuses seen
    bid_statuses: Dict[str, set] = defaultdict(set)

    for idx, row in enumerate(rows):
        bid = str(row.get("bet_id") or "").strip()
        if not bid:
            continue  # rows without bet_id are ignored (not our domain)
        status = str(row.get("status") or "").strip().lower()
        key_occurrences[(bid, status)].append(idx)
        bid_statuses[bid].add(status)

    total_bets = len(bid_statuses)

    # 3. Detect collisions (any (bet_id, status) with count > 1) ---------
    collision_keys: List[Tuple[str, str]] = []
    detail: List[Dict[str, Any]] = []

    for (bid, status), indices in sorted(key_occurrences.items()):
        if len(indices) > 1:
            collision_keys.append((bid, status))
            detail.append({
                "finding": "collision",
                "bet_id": bid,
                "status": status,
                "count": len(indices),
                "row_indices": indices,
            })

    # 4. Detect orphans (settled with no open twin) ----------------------
    orphan_ids: List[str] = []

    for bid, statuses in sorted(bid_statuses.items()):
        if _SETTLED_STATUS in statuses and _OPEN_STATUS not in statuses:
            orphan_ids.append(bid)
            detail.append({
                "finding": "orphan",
                "bet_id": bid,
                "reason": "settled row has no matching open twin",
                "statuses_found": sorted(statuses),
            })

    pass_ = (len(collision_keys) == 0) and (len(orphan_ids) == 0)

    return StatusValidationResult(
        pass_=pass_,
        collision_keys=collision_keys,
        orphan_ids=orphan_ids,
        total_rows=total_rows,
        total_bets=total_bets,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate CLV ledger status completeness (CI guard). "
            "Exits 0=pass (no collisions, no orphans), 1=fail."
        )
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Path to clv_ledger.jsonl (default: data/frontend/clv_ledger.jsonl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit result as JSON to stdout (for CI parsers)",
    )
    args = parser.parse_args(argv)

    result = validate_ledger_status(path=args.path)

    if args.json:
        out = {
            "pass": result.pass_,
            "total_rows": result.total_rows,
            "total_bets": result.total_bets,
            "collision_keys": [list(k) for k in result.collision_keys],
            "orphan_ids": result.orphan_ids,
            "detail": result.detail,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        status_label = "PASS" if result.pass_ else "FAIL"
        print(
            "[ledger_status_validator] %s  "
            "rows=%d  bets=%d  collisions=%d  orphans=%d"
            % (
                status_label,
                result.total_rows,
                result.total_bets,
                len(result.collision_keys),
                len(result.orphan_ids),
            )
        )
        if not result.pass_:
            for entry in result.detail:
                if entry.get("finding") == "collision":
                    print(
                        "  COLLISION bet_id=%s status=%s count=%d"
                        % (entry["bet_id"], entry["status"], entry["count"])
                    )
                elif entry.get("finding") == "orphan":
                    print(
                        "  ORPHAN    bet_id=%s (settled with no open twin)"
                        % entry["bet_id"]
                    )

    return 0 if result.pass_ else 1


if __name__ == "__main__":
    sys.exit(_main())


__all__ = [
    "validate_ledger_status",
    "StatusValidationResult",
    "INSUFFICIENT_DATA",
]
