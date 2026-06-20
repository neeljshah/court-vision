"""scripts.platformkit.pm_unified_browse -- unified PM + prop paper browse surface.

Merges the PM paper-trade trail (Kalshi/Polymarket moneyline) with prop paper
records into ONE paginated list, each row tagged with market_type in
{moneyline, prop}.  Consumers get a single surface for cross-market inspection.

HONESTY CONTRACT (binding):
  * No $ / dollar / roi / profit / pnl field.  UNITS only.
  * executed always False; real-money path DENY.
  * CLV shown honestly: null when no closing line (INSUFFICIENT_DATA).
  * Empty ledgers -> [] not crash.
  * <=300 LOC; ASCII only; no secrets; no network.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.pm_trail_browse import browse_pm_trail
from scripts.platformkit.prop_paper_store import load_ledger

logger = logging.getLogger(__name__)

# Market-type tag constants -- values are the canonical set for the field.
_MT_MONEYLINE = "moneyline"
_MT_PROP = "prop"

_HONEST_NOTE = (
    "Unified PM+prop paper surface. executed=False always; no real orders. "
    "market_type in {moneyline, prop}. "
    "CLV null = no closing line (INSUFFICIENT_DATA). "
    "net_units / stake_units = UNITS only, never $. "
    "No profit/edge claim made."
)

_TIER_RANK: Dict[Optional[str], int] = {"A": 0, "B": 1, "C": 2, None: 3}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _tier_key(row: Dict[str, Any]) -> int:
    tier = row.get("tier")
    return _TIER_RANK.get(str(tier).upper() if tier else None, 3)


def _ts_key(row: Dict[str, Any]) -> str:
    """ISO ts for sort (descending). Empty string sorts last."""
    return str(row.get("ts") or "")


def _shape_moneyline(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one PM trail row into the unified schema."""
    return {
        "market_type": _MT_MONEYLINE,
        "bet_id": raw.get("bet_id"),
        "ts": raw.get("ts"),
        "sport": raw.get("sport"),
        "matchup": raw.get("matchup"),
        "side": raw.get("side"),
        "venue": raw.get("venue"),
        "tier": raw.get("tier"),
        "model_prob": raw.get("model_prob"),
        "stake_units": raw.get("stake_units"),
        "status": raw.get("status"),
        "outcome": raw.get("outcome"),
        "clv_pct": raw.get("clv_pct"),
        "clv_status": raw.get("clv_status"),
        "executed": False,
        "honest_note": None,  # top-level note is sufficient
    }


def _shape_prop(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one prop ledger row into the unified schema."""
    clv_pct = raw.get("clv_pct")
    clv_val: Optional[float] = None
    if clv_pct is not None:
        try:
            clv_val = float(clv_pct)
        except (TypeError, ValueError):
            clv_val = None
    clv_status: Optional[str] = raw.get("clv_status")
    if clv_val is None and raw.get("status") == "settled":
        clv_status = clv_status or "no_close"

    return {
        "market_type": _MT_PROP,
        "bet_id": raw.get("bet_id"),
        "ts": raw.get("as_of") or raw.get("ts"),
        "sport": raw.get("sport"),
        "matchup": raw.get("match"),
        "side": "%s %s %s" % (
            raw.get("player", ""),
            raw.get("stat", ""),
            raw.get("side", ""),
        ),
        "venue": raw.get("book") or raw.get("venue"),
        "tier": raw.get("tier"),
        "model_prob": raw.get("model_p_over"),
        "stake_units": raw.get("stake_units"),
        "status": raw.get("status"),
        "outcome": raw.get("result"),
        "clv_pct": clv_val,
        "clv_status": clv_status,
        "executed": False,
        "honest_note": None,
    }


def _fetch_moneyline_rows(
    pm_ledger_path: Optional[Path],
) -> List[Dict[str, Any]]:
    """Pull PM trail rows and shape them."""
    try:
        result = browse_pm_trail(pm_ledger_path, limit=500)
        raw_trades = result.get("trades") or []
    except Exception:  # noqa: BLE001
        raw_trades = []
    return [_shape_moneyline(r) for r in raw_trades]


def _fetch_prop_rows(
    prop_ledger_path: Optional[Path],
) -> List[Dict[str, Any]]:
    """Pull prop ledger rows and shape them."""
    try:
        raw = load_ledger(prop_ledger_path)
    except Exception:  # noqa: BLE001
        raw = []
    return [_shape_prop(r) for r in raw]


def _apply_filters(
    rows: List[Dict[str, Any]],
    market_type: Optional[str],
    status: Optional[str],
    tier: Optional[str],
) -> List[Dict[str, Any]]:
    out = rows
    if market_type:
        mt = market_type.lower()
        out = [r for r in out if r.get("market_type") == mt]
    if status:
        sl = status.lower()
        out = [r for r in out if str(r.get("status") or "").lower() == sl]
    if tier:
        tu = tier.upper()
        out = [r for r in out if str(r.get("tier") or "").upper() == tu]
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def browse_unified(
    pm_ledger_path: Optional[Path] = None,
    prop_ledger_path: Optional[Path] = None,
    *,
    market_type: Optional[str] = None,
    status: Optional[str] = None,
    tier: Optional[str] = None,
    sort: str = "ts_desc",
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """Merged, paginated PM + prop paper browse surface.

    Args:
        pm_ledger_path: Override path for the CLV/moneyline ledger.
        prop_ledger_path: Override path for the prop JSONL ledger.
        market_type: Optional filter -- "moneyline" or "prop".
        status: Optional filter -- "open" or "settled".
        tier: Optional filter -- "A", "B", or "C".
        sort: "ts_desc" (newest first) or "tier_desc" (tier A first).
        offset: Pagination offset.
        limit: Page size (max 500).

    Returns a dict with keys: status, count, total, offset, limit, rows,
    honest_note.  No $ field anywhere.  executed always False.
    Empty ledgers produce [] not a crash.
    """
    limit = min(max(1, limit), 500)
    offset = max(0, offset)

    ml_rows = _fetch_moneyline_rows(pm_ledger_path)
    prop_rows = _fetch_prop_rows(prop_ledger_path)
    merged = ml_rows + prop_rows

    merged = _apply_filters(merged, market_type, status, tier)

    if sort == "tier_desc":
        merged.sort(key=lambda r: (_tier_key(r), -len(_ts_key(r)), _ts_key(r)))
    else:  # default: ts_desc
        merged.sort(key=_ts_key, reverse=True)

    page = merged[offset: offset + limit]
    return {
        "status": "ok",
        "count": len(page),
        "total": len(merged),
        "offset": offset,
        "limit": limit,
        "rows": page,
        "honest_note": _HONEST_NOTE,
    }


__all__ = ["browse_unified"]
