r"""scripts.platformkit.improve.coverage_map -- SI-10 self-improve coverage map.

Crosses tried_families.jsonl against improve_ledger_segmented.jsonl to produce a
(family, aspect) cell map: graded / untried / shipped / frozen / INSUFFICIENT_DATA.

SI-10 CONTRACT: READ-ONLY. No dollar field. cell.status in the five states above.
Shipped cell carries latest_delta. Frozen family flagged. Missing ledger ->
INSUFFICIENT_DATA. vs_close UNPROVEN. Calibration NOT edge. Stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from scripts.platformkit.improve.candidate_families import FAMILIES
from scripts.platformkit.improve.candidate_enum import load_tried_ids, TRIED_PATH
from scripts.platformkit.improve.prioritizer import frozen_families as _frozen_families

# ---------------------------------------------------------------------------
# Paths (defaults; injectable via build_coverage_map kwargs)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO_ROOT / "data" / "frontend" / "improve_ledger_segmented.jsonl"
_DEFAULT_TRIED = TRIED_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_CALIBRATION_NOTE = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)
_VS_CLOSE = "UNPROVEN"


# ---------------------------------------------------------------------------
# Helpers -- all private, pure, never raise on bad data
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file; return [] on missing/unreadable (cold start is valid)."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
    except Exception:  # noqa: BLE001 -- IO failure -> empty (cold start)
        return []
    return rows


def _all_keys(obj: Any) -> List[str]:
    """Recursively collect all dict keys (for banned-key scan)."""
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any) -> None:
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.search(k):
            raise ValueError("Banned key %r violates no-dollar-field contract." % k)


def _extract_brier_delta(row: Dict[str, Any]) -> Optional[float]:
    """Extract raw_brier from a graded ledger row's readout, or None."""
    readout = row.get("readout")
    if not isinstance(readout, dict):
        return None
    v = readout.get("raw_brier")
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN-safe
    except (TypeError, ValueError):
        return None


def _family_from_tried_row(row: Dict[str, Any]) -> Optional[str]:
    """Return the family field from a tried-families row, or None if absent/invalid."""
    fam = row.get("family")
    if isinstance(fam, str) and fam:
        return fam
    return None


def _market_aspect_from_ledger_row(row: Dict[str, Any]) -> str:
    """Return the market aspect from a ledger row (its 'market' key)."""
    mkt = row.get("market", "")
    return str(mkt).lower() if mkt else "unknown"


def _build_prioritizer_ledger(tried_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build prioritizer-ledger dict from tried-family rows (for frozen_families())."""
    ledger: Dict[str, Any] = {}
    for row in tried_rows:
        fam = _family_from_tried_row(row)
        if fam is None:
            continue
        if fam not in ledger:
            ledger[fam] = {"ships": 0, "rejects": 0, "null_shipped": False,
                           "null_ships": 0}
        verdict = str(row.get("verdict", row.get("status", ""))).upper()
        if verdict == "SHIP":
            ledger[fam]["ships"] += 1
        elif verdict in ("REJECT", "REJECTED"):
            ledger[fam]["rejects"] += 1
        if row.get("is_planted_null") and verdict == "SHIP":
            ledger[fam]["null_shipped"] = True
            ledger[fam]["null_ships"] = ledger[fam].get("null_ships", 0) + 1
    return ledger


# ---------------------------------------------------------------------------
# Core: build the coverage map
# ---------------------------------------------------------------------------

def build_coverage_map(
    ledger_path: Optional[Path] = None,
    tried_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build and return the SI-10 coverage map (read-only).

    Returns dict: cells list, summary counts, ledger_present, tried_present, note, vs_close.
    """
    lp = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    tp = Path(tried_path) if tried_path else _DEFAULT_TRIED

    ledger_present: bool = lp.exists()
    tried_present: bool = tp.exists()

    # -- Load inputs (safe; returns [] on missing / parse errors) ----------------
    ledger_rows: List[Dict[str, Any]] = _read_jsonl(lp)
    tried_rows: List[Dict[str, Any]] = _read_jsonl(tp)

    # -- Tried family set (from tried_families.jsonl + candidate_enum.load_tried_ids) --
    tried_ids: Set[str] = load_tried_ids(tp)
    tried_family_names: Set[str] = set()
    for row in tried_rows:
        fam = _family_from_tried_row(row)
        if fam:
            tried_family_names.add(fam)

    # -- Frozen families (from prioritizer logic) --------------------------------
    pri_ledger = _build_prioritizer_ledger(tried_rows)
    frozen: Set[str] = _frozen_families(pri_ledger)

    # Build (family, aspect) cells: family in FAMILIES x unique markets in ledger.
    # Tried family + SHIP ledger -> shipped; tried + other -> graded; not tried -> untried.
    market_latest: Dict[str, Dict[str, Any]] = {}
    for row in ledger_rows:
        aspect = _market_aspect_from_ledger_row(row)
        market_latest[aspect] = row  # last JSONL occurrence wins (append-only log)

    aspects: List[str] = sorted(market_latest.keys()) if market_latest else []

    # If no ledger rows at all, every cell is INSUFFICIENT_DATA
    if not ledger_rows:
        cells: List[Dict[str, Any]] = []
        for fam in FAMILIES:
            cell: Dict[str, Any] = {
                "family": fam,
                "aspect": "all",
                "status": "INSUFFICIENT_DATA",
                "reason": "ledger absent or empty -- no graded data",
                "frozen": fam in frozen,
                "latest_delta": None,
                "vs_close": _VS_CLOSE,
                "note": _CALIBRATION_NOTE,
            }
            _assert_no_banned_keys(cell)
            cells.append(cell)
        summary = {
            "total": len(cells),
            "graded": 0,
            "untried": 0,
            "shipped": 0,
            "frozen": sum(1 for c in cells if c["frozen"]),
            "insufficient_data": len(cells),
        }
        result: Dict[str, Any] = {
            "cells": cells,
            "summary": summary,
            "ledger_present": ledger_present,
            "tried_present": tried_present,
            "note": _CALIBRATION_NOTE,
            "vs_close": _VS_CLOSE,
        }
        _assert_no_banned_keys(result)
        return result

    # -- Build cells for every (family, aspect) pair ----------------------------
    cells = []
    for fam in FAMILIES:
        for aspect in aspects:
            ledger_row = market_latest[aspect]
            row_status = str(ledger_row.get("status", "")).upper()
            is_tried = fam in tried_family_names
            is_frozen = fam in frozen

            if is_frozen:
                cell_status = "frozen"
            elif not is_tried:
                cell_status = "untried"
            elif row_status == "INSUFFICIENT_DATA":
                cell_status = "INSUFFICIENT_DATA"
            elif row_status == "SHIP":
                cell_status = "shipped"
            else:
                cell_status = "graded"

            latest_delta = (
                _extract_brier_delta(ledger_row)
                if cell_status in ("graded", "shipped")
                else None
            )

            cell = {
                "family": fam,
                "aspect": aspect,
                "status": cell_status,
                "frozen": is_frozen,
                "tried": is_tried,
                "ledger_status": row_status,
                "latest_delta": latest_delta,
                "vs_close": _VS_CLOSE,
                "note": _CALIBRATION_NOTE,
            }
            _assert_no_banned_keys(cell)
            cells.append(cell)

    # -- Summary counts ---------------------------------------------------------
    total = len(cells)
    n_graded = sum(1 for c in cells if c["status"] == "graded")
    n_untried = sum(1 for c in cells if c["status"] == "untried")
    n_shipped = sum(1 for c in cells if c["status"] == "shipped")
    n_frozen = sum(1 for c in cells if c["frozen"])
    n_insuff = sum(1 for c in cells if c["status"] == "INSUFFICIENT_DATA")

    summary = {
        "total": total,
        "graded": n_graded,
        "untried": n_untried,
        "shipped": n_shipped,
        "frozen": n_frozen,
        "insufficient_data": n_insuff,
    }

    result = {
        "cells": cells,
        "summary": summary,
        "ledger_present": ledger_present,
        "tried_present": tried_present,
        "note": _CALIBRATION_NOTE,
        "vs_close": _VS_CLOSE,
    }
    _assert_no_banned_keys(result)
    return result


__all__ = [
    "build_coverage_map",
]
