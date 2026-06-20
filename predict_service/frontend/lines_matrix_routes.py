"""predict_service.frontend.lines_matrix_routes -- multi-book line shopping API.

W1 (api-lines): per-book odds matrix + best-line for line-shopping UI.
VINTAGE WIRE (BE7-2): normalize_markets() preserves original captured_at when
prices are unchanged; is_close=True stamped on every row for post/Final games.
HONESTY: no $ field; PM tagged is_pm=True; stale-never-green; edge_claimed=False.
INVARIANTS: <=300 LOC; predict_service/frontend/; ASCII only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError(
        "predict_service.frontend.lines_matrix_routes requires fastapi."
    ) from exc

from scripts.platformkit.odds_provider.base import (
    VENUE_PREDICTION_MARKET,
    VENUE_SPORTSBOOK,
    venue_type,
)
from scripts.platformkit.odds_provider.aggregate import aggregate
from scripts.platformkit.odds_shop import best_line
from predict_service.contracts import HONEST_NOTE, _TYPICAL_GAME_DURATION_SECONDS
from predict_service.captured_at_vintage import normalize_markets

logger = logging.getLogger(__name__)

router = APIRouter()

# (sport, game_id) -> flat market-row list from last serve; drives vintage wire.
_history_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}


def _is_pm(book: str) -> bool:
    return venue_type(book) == VENUE_PREDICTION_MARKET


def _derive_game_state(commence_time: Optional[str]) -> str:
    """'pre'|'live'|'post' from commence_time. Never raises (returns 'pre')."""
    try:
        if not commence_time:
            return "pre"
        ct = datetime.fromisoformat(str(commence_time).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = (now - ct).total_seconds()
        if elapsed < 0:
            return "pre"
        if elapsed > _TYPICAL_GAME_DURATION_SECONDS:
            return "post"
        return "live"
    except Exception:  # noqa: BLE001
        return "pre"


def _book_rows(
    prices: Dict[str, Dict[str, Any]],
    market_type: str,
    captured_at_default: Optional[str],
) -> List[Dict[str, Any]]:
    """Flat list of rows with market_type+side embedded (needed by vintage_key)."""
    rows: List[Dict[str, Any]] = []

    def _add(side: str, book: str, odds: float, line: Optional[float]) -> None:
        rows.append({
            "book": book,
            "market_type": market_type,
            "side": side,
            "odds": round(float(odds), 6),
            "line": line,
            "captured_at": captured_at_default,
            "is_pm": _is_pm(book),
            "is_close": False,
        })

    if market_type == "moneyline":
        for venue, sides in prices.items():
            if not isinstance(sides, dict):
                continue
            for side in ("home", "away", "draw"):
                v = sides.get(side)
                try:
                    dec = float(v)
                except (TypeError, ValueError):
                    continue
                if dec > 1.0:
                    _add(side, venue, dec, None)

    elif market_type in ("spread", "total"):
        side_a, side_b = (
            ("home", "away") if market_type == "spread"
            else ("over", "under")
        )
        for venue, sides in prices.items():
            if not isinstance(sides, dict):
                continue
            node = sides.get(market_type)
            if not isinstance(node, dict):
                continue
            for side in (side_a, side_b):
                leg = node.get(side)
                if not isinstance(leg, dict):
                    continue
                try:
                    odds = float(leg.get("odds") or 0)
                    lin = float(leg.get("line") or 0)
                except (TypeError, ValueError):
                    continue
                if odds > 1.0:
                    _add(side, venue, odds, lin)

    return rows


def _rows_to_sides(
    rows: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Re-group flat rows into {side: [row, ...]} for the response shape."""
    sides_out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        side = str(r.get("side") or "")
        if not side:
            continue
        if side not in sides_out:
            sides_out[side] = []
        sides_out[side].append({
            "book": r.get("book"),
            "odds": r.get("odds"),
            "line": r.get("line"),
            "captured_at": r.get("captured_at"),
            "is_pm": r.get("is_pm", False),
            "is_close": r.get("is_close", False),
        })
    return sides_out


def _best_sportsbook(
    all_rows: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Best (highest decimal) sportsbook-only price per side."""
    book_prices: Dict[str, Dict[str, float]] = {}
    for side, rows in all_rows.items():
        for r in rows:
            bk = r.get("book") or ""
            if not bk:
                continue
            if bk not in book_prices:
                book_prices[bk] = {}
            try:
                book_prices[bk][side] = float(r["odds"])
            except (TypeError, ValueError, KeyError):
                continue
    best = best_line(book_prices, restrict_to=VENUE_SPORTSBOOK)
    return {side: {"book": d["book"], "odds": round(d["price"], 6)}
            for side, d in best.items()}


@router.get("/api/lines/{sport}/{game_id}")
def lines_matrix(sport: str, game_id: str) -> JSONResponse:
    """Per-market book matrix for one game with vintage-preserving captured_at."""
    try:
        payload = aggregate(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("lines_matrix: aggregate(%s) error: %s", sport, exc)
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport, "game_id": game_id,
             "reason": "aggregate error", "honest_note": HONEST_NOTE,
             "edge_claimed": False},
            status_code=503)

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport, "game_id": game_id,
             "reason": "no live slate", "sources": payload.get("sources", {}),
             "honest_note": HONEST_NOTE, "edge_claimed": False},
            status_code=503)

    events = payload.get("events") or []
    target = next(
        (e for e in events
         if isinstance(e, dict) and str(e.get("event_id", "")) == game_id),
        None)

    if target is None:
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport, "game_id": game_id,
             "reason": "game_id not in current slate",
             "honest_note": HONEST_NOTE, "edge_claimed": False},
            status_code=404)

    prices = target.get("prices") or {}
    captured_at = str(payload.get("as_of") or "")
    game_state = _derive_game_state(target.get("commence_time"))

    flat_rows: List[Dict[str, Any]] = []
    for mtype in ("moneyline", "spread", "total"):
        flat_rows.extend(_book_rows(prices, mtype, captured_at or None))

    cache_key = (sport.lower(), game_id)
    normed = normalize_markets(flat_rows, _history_cache.get(cache_key, []), game_state)
    _history_cache[cache_key] = list(normed)

    markets_out: Dict[str, Any] = {}
    best_out: Dict[str, Any] = {}
    for mtype in ("moneyline", "spread", "total"):
        mtype_rows = [r for r in normed
                      if isinstance(r, dict) and r.get("market_type") == mtype]
        if not mtype_rows:
            continue
        sides_map = _rows_to_sides(mtype_rows)
        if not sides_map:
            continue
        markets_out[mtype] = sides_map
        best_out[mtype] = _best_sportsbook(sides_map)

    return JSONResponse({
        "status": "ok",
        "sport": sport.lower(),
        "game_id": game_id,
        "home": target.get("home"),
        "away": target.get("away"),
        "game_state": game_state,
        "captured_at": captured_at,
        "markets": markets_out,
        "best": best_out,
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    })


@router.get("/api/props/{sport}")
def props_board(sport: str) -> JSONResponse:
    """Cross-source prop best-line board. NBA degrades to UNAVAILABLE in offseason."""
    sport_key = (sport or "").lower().strip()
    try:
        from scripts.platformkit.prop_edge_config import get_config  # noqa: PLC0415
        cfg = get_config(sport_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_board: prop_edge_config.get_config(%s): %s",
                       sport_key, exc)
        cfg = None

    if cfg is None:
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport_key, "props": [], "count": 0,
             "reason": f"no prop board configured for '{sport_key}'",
             "honest_note": HONEST_NOTE, "edge_claimed": False}, status_code=404)

    try:
        providers = cfg.default_providers()
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_board: default_providers(%s): %s", sport_key, exc)
        providers = []
    if not providers:
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport_key,
             "reason": "no prop providers available", "props": [], "count": 0,
             "honest_note": HONEST_NOTE, "edge_claimed": False}, status_code=503)

    try:
        from scripts.platformkit.odds_provider.prop_aggregate import (  # noqa: PLC0415
            best_line_props, prop_best_line_summary,
        )
        rows = best_line_props(providers, sport_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_board: best_line_props(%s): %s", sport_key, exc)
        rows = []

    if not rows:
        extra = cfg.extra or {}
        nba_off = extra.get("offseason_empty") and sport_key == "nba"
        reason = ("NBA prop lines unavailable -- offseason or providers empty."
                  if nba_off else "prop providers returned no lines")
        return JSONResponse(
            {"status": "UNAVAILABLE", "sport": sport_key, "props": [], "count": 0,
             "reason": reason, "honest_note": HONEST_NOTE, "edge_claimed": False},
            status_code=503)

    summaries = [prop_best_line_summary(r) for r in rows]

    return JSONResponse({
        "status": "ok",
        "sport": sport_key,
        "count": len(summaries),
        "props": summaries,
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    })


__all__ = ["router"]
