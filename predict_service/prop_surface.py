"""predict_service.prop_surface -- build PlayerPropRow list from price_prop.

W2 (api-props): joins prop lines (from W1 / the current snapshot's MarketRows) to
the domain price_prop pricer and produces one PlayerPropRow per (player, stat,
line, book) tuple.

KEY FUNCTION:
  build_prop_rows(sport, date, prop_lines) -> list[dict]
    prop_lines: list of dicts with keys player, stat, line, book,
                market_prob (optional devigged book prob for over).
    Returns PlayerPropRow list.  Never raises; degrades per-row.

  unavailable_response(sport, reason) -> dict
    Standard UNAVAILABLE body (empty rows, no $ field).

PlayerPropRow shape (no $ field):
  {
    "player":          str,
    "stat":            str  (pts|reb|ast|fg3m|stl|blk|tov|pra|...),
    "line":            float,
    "book":            str,
    "p_over":          float|null  (in [0,1]),
    "p_under":         float|null  (in [0,1]),
    "proj_mean":       float|null,
    "proj_sigma":      float|null,
    "edge_vs_market":  float|null  (p_over - market_prob; no $ interpretation),
    "tier":            null  (reserved; not set at this layer),
    "confidence":      str|null    ("recency_gaussian" when priced),
    "clv_is_proxy":    true        (always; no true in-play close for props),
    "date":            str,
    "sport":           str,
    "honest_note":     str
  }

HONESTY: p_over is a probability in [0,1]. edge_vs_market is a probability
difference, NOT a $ edge. clv_is_proxy is always True (no true prop closing lines
for NBA in offseason). No $ / pnl / roi field anywhere.

UNAVAILABLE degradation: NBA prop lines are empty in the offseason (PrizePicks /
Underdog return nothing); when prop_lines is empty, returns UNAVAILABLE status
with empty rows (never fabricates rows). Other sports degrade the same way.

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; read-only; no network I/O.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HONEST_NOTE = (
    "Calibrated P(over/under) vs line: recency-weighted Gaussian projection. "
    "Leak-free (uses only games strictly before date). "
    "Calibration baseline, no $ edge is claimed. "
    "clv_is_proxy=True: no true prop closing lines available in NBA offseason."
)

_NBA_OFFSEASON_NOTE = (
    "NBA player-prop lines unavailable (offseason: PrizePicks/Underdog return empty). "
    "Prop cards show P(over) from the leak-free domain pricer but "
    "'best line across books' is thin until a real prop feed exists."
)


def unavailable_response(sport: str, reason: str = "") -> Dict[str, Any]:
    """UNAVAILABLE envelope -- no rows, no $ field."""
    return {
        "status": "UNAVAILABLE",
        "sport": sport,
        "reason": reason or "no prop lines available",
        "rows": [],
        "count": 0,
        "edge_claimed": False,
        "clv_is_proxy": True,
        "honest_note": _HONEST_NOTE,
    }


def _price_one_row(sport: str, date: Any, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Price a single prop-line row.  Returns None on unrecoverable error."""
    player = row.get("player", "")
    stat = str(row.get("stat", "")).lower()
    line = row.get("line")
    book = str(row.get("book", ""))
    market_prob = row.get("market_prob")  # devigged book P(over) from W1

    if not player or not stat or line is None:
        logger.debug("prop_surface: skipping incomplete row %s", row)
        return None

    try:
        from domains.basketball_nba.prop_card_service import price_one  # noqa: PLC0415
    except ImportError as exc:
        logger.warning("prop_surface: import prop_card_service failed (%s)", exc)
        return None

    priced = price_one(player, stat, float(line), date, market_prob=market_prob)
    if not priced:
        return None

    p_over = priced.get("p_over")
    p_under = priced.get("p_under")
    confidence = "recency_gaussian" if p_over is not None else None

    return {
        "player": str(player),
        "stat": stat,
        "line": float(line),
        "book": book,
        "p_over": p_over,
        "p_under": p_under,
        "proj_mean": priced.get("proj_mean"),
        "proj_sigma": priced.get("proj_sigma"),
        "edge_vs_market": priced.get("edge_vs_market"),
        "tier": None,
        "confidence": confidence,
        "clv_is_proxy": True,
        "date": str(priced.get("date", date)),
        "sport": sport,
        "honest_note": _HONEST_NOTE,
    }


def build_prop_rows(
    sport: str,
    date: Any,
    prop_lines: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build PlayerPropRow list from prop line dicts.

    prop_lines: list of {player, stat, line, book, market_prob (opt)}
    Returns only rows that successfully priced (p_over may still be None for
    insufficient_history players -- those rows are included but p_over=None).
    """
    if not prop_lines:
        return []
    rows: List[Dict[str, Any]] = []
    for raw_row in prop_lines:
        priced = _price_one_row(sport, date, raw_row)
        if priced is not None:
            rows.append(priced)
    return rows


def build_props_response(
    sport: str,
    date: Any,
    prop_lines: List[Dict[str, Any]],
    game_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the full /api/predict/props response body.

    When prop_lines is empty -> UNAVAILABLE (NBA offseason or no feed).
    When rows exist but all have p_over=None -> status='ok' with honest note.
    Never fabricates rows.  No $ field.
    """
    if not prop_lines:
        note = _NBA_OFFSEASON_NOTE if sport == "nba" else "no prop lines available"
        result = unavailable_response(sport, note)
        if game_id:
            result["game_id"] = game_id
        return result

    rows = build_prop_rows(sport, date, prop_lines)
    result: Dict[str, Any] = {
        "status": "ok",
        "sport": sport,
        "date": str(date),
        "rows": rows,
        "count": len(rows),
        "edge_claimed": False,
        "clv_is_proxy": True,
        "honest_note": _HONEST_NOTE,
    }
    if game_id:
        result["game_id"] = game_id
    return result


def build_prop_cards_surface(
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Surface live player-prop CARDS for the unified board (W-PROP-SURFACE). FAST.

    Reads the DECOUPLED prop-card cache (prop_cards_cache.json) that the m13 props
    daemon computes ONCE per 300 s cycle -- the BOUNDED/RANKED set: ALL priced
    props + top-N reliable model-only per sport. This is a pure JSON read with a
    freshness/SLA gate, so the surface never triggers the SLOW full prop-board
    build inline (which hung >240 s).

    MODEL-ONLY props carry model_only=True with NO edge/CLV; PRICED props carry
    edge_vs_market (a prob diff, NOT $). A missing/stale cache degrades honestly to
    [] (props omitted, never a hang, never stale-served-as-live). Never raises.
    """
    try:
        from scripts.platformkit.bestbets import prop_cards_cache  # noqa: PLC0415
        env = prop_cards_cache.read(now_epoch=now)
        cards = env.get("cards") if isinstance(env, dict) else None
        if isinstance(cards, list):
            return [c for c in cards if isinstance(c, dict)]
        return []
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_surface: build_prop_cards_surface unavailable (%s)", exc)
        return []


__all__ = [
    "unavailable_response",
    "build_prop_rows",
    "build_props_response",
    "build_prop_cards_surface",
]
