"""scripts.platformkit.pm_trail_browse -- rank/paginate the PM paper-trade ledger.

Browse + per-trade-detail logic for the PM paper trail API (W5).
Reads the append-only CLV ledger, enriches via clv_ledger_enrich, exposes:
  browse_pm_trail / best_pm_trades / trade_detail

HONESTY CONTRACT (binding):
  * PM filter = is_pm=True (venue in kalshi|polymarket); sportsbook excluded.
  * CLV shown honestly: null when no closing line (never a 0-fill or fabrication).
  * No $ / dollar / roi / profit field.  UNITS only.  executed ALWAYS False.
  * NEVER mutates the append-only ledger.
  * <=300 LOC; ASCII only; no secrets; no network.
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.clv_ledger_enrich import enrich_rows

_DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"
)
_HONEST_NOTE = (
    "PM paper trail -- executed=False, channel=paper, no real orders. "
    "CLV = better-number-than-close (positive = good). "
    "null CLV = no closing line available (INSUFFICIENT_DATA). "
    "Venue: kalshi|polymarket only. No $ edge claimed."
)
_TIER_RANK: Dict[Optional[str], int] = {"A": 0, "B": 1, "C": 2, None: 3}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_raw(path: Optional[Path]) -> List[Dict[str, Any]]:
    """Load raw JSONL rows from ledger; never raises."""
    target = path or _DEFAULT_LEDGER
    if not target.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(_json.loads(line))
                    except Exception:  # noqa: BLE001
                        pass
    except Exception:  # noqa: BLE001
        pass
    return rows


def _read_trail(path: Optional[Path]) -> List[Dict[str, Any]]:
    """Load collapsed trail rows via frontend.paper_trail (or raw JSONL fallback)."""
    try:
        from frontend.paper_trail import read_trail  # noqa: PLC0415
        return read_trail(path)
    except Exception:  # noqa: BLE001
        return _read_raw(path)


def _tier_sort_key(row: Dict[str, Any]) -> tuple:
    tier = row.get("tier")
    rank = _TIER_RANK.get(str(tier) if tier else None, 3)
    mp = -(float(row["model_prob"]) if row.get("model_prob") is not None else 0.0)
    clv = -(float(row["clv_pct"]) if row.get("clv_pct") is not None else 0.0)
    return (rank, mp, clv)


def _shape(row: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one enriched row for API output. No $ fields; executed always False."""
    clv_pct = row.get("clv_pct")
    clv_val: Optional[float] = float(clv_pct) if clv_pct is not None else None
    clv_status = row.get("clv_status")
    if clv_val is None and row.get("status") == "settled":
        clv_status = clv_status or "no_close"
    return {
        "bet_id": row.get("bet_id") or row.get("game_id"),
        "ts": row.get("ts"),
        "settled_at": row.get("settled_at"),
        "sport": row.get("sport"),
        "matchup": row.get("matchup"),
        "side": row.get("side"),
        "market_type": row.get("market_type"),
        "venue": row.get("venue", "unknown"),
        "market_id": row.get("market_id"),
        "taken_book": row.get("taken_book"),
        "taken_decimal": row.get("taken_decimal"),
        "model_prob": row.get("model_prob"),
        "model_ev": row.get("model_ev"),
        "tier": row.get("tier"),
        "flat_unit": row.get("flat_unit"),
        "quarter_kelly": row.get("quarter_kelly"),
        "stake_units": row.get("stake_units"),
        "status": row.get("status", "open"),
        "outcome": row.get("outcome"),
        "clv_pct": clv_val,
        "beat_close": row.get("beat_close"),
        "clv_is_proxy": bool(row.get("clv_is_proxy", False)),
        "clv_status": clv_status,
        "clv_unavailable": row.get("clv_unavailable", clv_val is None),
        "executed": False,
        "is_pm": bool(row.get("is_pm", False)),
    }


def _filter(
    rows: List[Dict[str, Any]],
    venue: Optional[str],
    result: Optional[str],
    tier: Optional[str],
) -> List[Dict[str, Any]]:
    out = rows
    if venue:
        v = venue.lower()
        out = [r for r in out if str(r.get("venue", "")).lower() == v]
    if result:
        r_l = result.lower()
        if r_l in ("win", "loss", "push", "void"):
            out = [r for r in out if str(r.get("outcome") or "").lower() == r_l]
        elif r_l in ("open", "settled"):
            out = [r for r in out if str(r.get("status", "")).lower() == r_l]
    if tier:
        t = tier.upper()
        out = [r for r in out if str(r.get("tier") or "").upper() == t]
    return out


# Enrichment does per-row close lookups, so a full ledger pass costs seconds
# even warm. Cache the enriched trail keyed on ledger mtime (re-applied
# 2026-07-15 after an external git-restore wiped it).
# ponytail: process-local dict cache; move to disk if multi-proc ever needs it.
_ENRICH_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _enriched_trail(path: Optional[Path]) -> List[Dict[str, Any]]:
    """Enriched trail rows, cached on the ledger file's mtime."""
    target = path if path is not None else _DEFAULT_LEDGER
    try:
        mtime = target.stat().st_mtime
    except OSError:
        mtime = -1.0
    key = str(target)
    hit = _ENRICH_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    rows = enrich_rows(_read_trail(path))
    _ENRICH_CACHE[key] = (mtime, rows)
    return rows


def _pm_enriched(path: Optional[Path]) -> List[Dict[str, Any]]:
    """Return enriched, PM-only trail rows."""
    return [r for r in _enriched_trail(path) if bool(r.get("is_pm", False))]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def browse_pm_trail(
    ledger_path: Optional[Path] = None,
    *,
    venue: Optional[str] = None,
    result: Optional[str] = None,
    tier: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """Paginated, filtered PM paper-trade list (Kalshi/Polymarket only).

    Optional filters: venue ("kalshi"|"polymarket"), result ("win"|"loss"|...|
    "open"|"settled"), tier ("A"|"B"|"C"). Pagination via offset/limit.
    """
    limit = min(max(1, limit), 500)
    offset = max(0, offset)
    try:
        pm_rows = _pm_enriched(ledger_path)
    except Exception:  # noqa: BLE001
        pm_rows = []
    filtered = _filter(pm_rows, venue, result, tier)
    page = [_shape(r) for r in filtered[offset: offset + limit]]
    return {
        "status": "ok",
        "count": len(page),
        "total_pm": len(filtered),
        "offset": offset,
        "limit": limit,
        "trades": page,
        "honest_note": _HONEST_NOTE,
    }


def best_pm_trades(
    ledger_path: Optional[Path] = None,
    *,
    top_n: int = 20,
) -> Dict[str, Any]:
    """Top-N best trades ranked by tier + confidence + CLV.

    "Best trades it would have made" = sort by tier A>B>C, then model_prob
    descending, then clv_pct descending.  CLV shown honestly (null = no close).
    Sportsbook rows excluded.
    """
    top_n = min(max(1, top_n), 200)
    try:
        pm_rows = _pm_enriched(ledger_path)
    except Exception:  # noqa: BLE001
        pm_rows = []
    ranked = sorted(pm_rows, key=_tier_sort_key)
    top = [_shape(r) for r in ranked[:top_n]]
    return {
        "status": "ok",
        "count": len(top),
        "top_n": top_n,
        "trades": top,
        "honest_note": _HONEST_NOTE,
    }


def trade_detail(
    bet_id: str,
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Full execution detail for one PM trade by bet_id (or fallback game_id).

    Searches the raw ledger by stored bet_id first (settled twin preferred),
    then falls back to collapsed trail by synthetic game_id.
    """
    # -- 1. Raw ledger search by bet_id (handles durable ids from record_bet)
    raw_rows = _read_raw(ledger_path)
    raw_match: Optional[Dict[str, Any]] = None
    for r in raw_rows:
        if str(r.get("bet_id") or "") == bet_id:
            if raw_match is None or str(r.get("status", "")) == "settled":
                raw_match = r

    if raw_match is not None:
        enriched = enrich_rows([raw_match])[0]
        try:
            from frontend.paper_trail import _build_trail_row  # noqa: PLC0415
            trail_like = _build_trail_row(raw_match)
            trail_like.update({k: v for k, v in enriched.items()
                               if v is not None or k not in trail_like})
            shaped = _shape(trail_like)
        except Exception:  # noqa: BLE001
            shaped = _shape(enriched)
        return {"status": "ok", "trade": shaped, "honest_note": _HONEST_NOTE}

    # -- 2. Fallback: collapsed trail searched by game_id
    try:
        trail = _enriched_trail(ledger_path)
    except Exception:  # noqa: BLE001
        trail = []
    match = next((r for r in trail if str(r.get("game_id") or "") == bet_id), None)
    if match is None:
        return {"status": "not_found", "trade": None, "honest_note": _HONEST_NOTE}
    return {"status": "ok", "trade": _shape(match), "honest_note": _HONEST_NOTE}


__all__ = ["browse_pm_trail", "best_pm_trades", "trade_detail"]
