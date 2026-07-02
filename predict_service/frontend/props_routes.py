"""predict_service.frontend.props_routes -- player-prop prediction endpoints.

W2 (api-props): exposes calibrated P(over/under) prop predictions per bettable
prop line per book.

  GET /api/predict/props/{sport}
      Returns all PlayerPropRow entries for the current snapshot's games.
      NBA in offseason -> UNAVAILABLE (prop lines empty, no fabrication).

  GET /api/predict/props/{sport}/{game_id}
      Single-game PlayerPropRow list. 404 if game not in snapshot.

PlayerPropRow:
  {player, stat, line, book, p_over, p_under, proj_mean, proj_sigma,
   edge_vs_market, tier, confidence, clv_is_proxy, date, sport, honest_note}

Source of prop lines:
  The snapshot's MarketRows (markets[] on each PredictionRecord) are scanned for
  market_type=="player_prop".  If none exist (offseason, no feed), the response
  degrades to UNAVAILABLE with an honest message.

HONESTY: p_over in [0,1] is a probability. edge_vs_market is a probability
difference. No $ / pnl / roi field. clv_is_proxy=True always (no true closing
lines for props in NBA offseason). Real-money stays default-DENY.

INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O; read-only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Path as FPath, Query
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise ImportError("props_routes requires fastapi.") from exc

from predict_service import store
from predict_service.prop_surface import build_props_response, unavailable_response
from predict_service.prop_surface_scraped import build_scraped_props_response
from predict_service.contracts import HONEST_NOTE

logger = logging.getLogger(__name__)

router = APIRouter()

_PROP_MARKET_TYPE = "player_prop"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _today_utc() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _prop_lines_from_markets(markets: List[Any]) -> List[Dict[str, Any]]:
    """Extract player-prop market rows from a list of MarketRow-like objects.

    Accepts both dataclass instances (with .market_type) and dicts.
    Returns list of dicts with player, stat, line, book, market_prob.
    """
    rows: List[Dict[str, Any]] = []
    for m in markets:
        mt = getattr(m, "market_type", None) or (m.get("market_type") if isinstance(m, dict) else None)
        if mt != _PROP_MARKET_TYPE:
            continue
        # MarketRow.side encodes "{player}:{stat}" for prop markets.
        side = getattr(m, "side", None) or (m.get("side") if isinstance(m, dict) else None) or ""
        if ":" in str(side):
            parts = str(side).split(":", 1)
            player, stat = parts[0].strip(), parts[1].strip()
        else:
            # Fallback: side is stat, player must be in a separate field.
            player = getattr(m, "player", None) or (m.get("player") if isinstance(m, dict) else None) or ""
            stat = str(side).lower()
        line = getattr(m, "line", None)
        if line is None and isinstance(m, dict):
            line = m.get("line")
        book = getattr(m, "book", "") or (m.get("book", "") if isinstance(m, dict) else "")
        devig = getattr(m, "devigged_prob", None)
        if devig is None and isinstance(m, dict):
            devig = m.get("devigged_prob")
        if player and stat and line is not None:
            rows.append({"player": player, "stat": stat,
                         "line": float(line), "book": book,
                         "market_prob": devig})
    return rows


def _snap_date(envelope) -> str:
    """Best-effort date string from snapshot generated_at."""
    ts = getattr(envelope, "generated_at", None)
    if ts:
        try:
            return str(ts)[:10]
        except Exception:  # noqa: BLE001
            pass
    return _today_utc()


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@router.get("/api/predict/props/{sport}")
def get_props_for_sport(
    sport: str = FPath(..., description="Sport code (nba, mlb, soccer, tennis, ...)"),
    date: Optional[str] = Query(
        default=None,
        description="Date override YYYY-MM-DD (defaults to snapshot date)"
    ),
) -> JSONResponse:
    """All player-prop predictions for sport.

    Joins the current snapshot's prop market rows to the domain pricer.
    Degrades to UNAVAILABLE when no prop lines exist (NBA offseason, etc.).
    No $ field; clv_is_proxy=True; real-money default-DENY.
    """
    try:
        env = store.read_latest(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_routes: read_latest(%s) failed: %s", sport, exc)
        env = None

    if env is None or getattr(env, "status", "unavailable") == "unavailable":
        return JSONResponse(
            unavailable_response(sport, f"no snapshot for sport '{sport}'"),
            status_code=503)

    prop_date = date or _snap_date(env)
    all_lines: List[Dict[str, Any]] = []
    for pred in getattr(env, "predictions", []) or []:
        markets = getattr(pred, "markets", []) or []
        all_lines.extend(_prop_lines_from_markets(markets))

    if not all_lines:
        # No domain-model prop market rows in THIS sport's own game snapshot (the
        # NBA-pricer path never gets fed for mlb/soccer_intl) -- fall back to the
        # real scraped-book prop board before reporting UNAVAILABLE.
        scraped = build_scraped_props_response(sport)
        if scraped is not None:
            scraped["generated_at"] = getattr(env, "generated_at", None)
            return JSONResponse(scraped)

    body = build_props_response(sport, prop_date, all_lines)
    body["generated_at"] = getattr(env, "generated_at", None)
    body["edge_claimed"] = False
    return JSONResponse(body)


@router.get("/api/predict/props/{sport}/{game_id}")
def get_props_for_game(
    sport: str = FPath(..., description="Sport code"),
    game_id: str = FPath(..., description="Game identifier"),
    date: Optional[str] = Query(
        default=None,
        description="Date override YYYY-MM-DD"
    ),
) -> JSONResponse:
    """Player-prop predictions for a single game.

    Returns 404 when the game is absent from the current snapshot.
    Degrades to UNAVAILABLE when no prop lines exist for this game.
    """
    try:
        env = store.read_latest(sport)
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_routes: read_latest(%s) failed: %s", sport, exc)
        env = None

    if env is None or getattr(env, "status", "unavailable") == "unavailable":
        return JSONResponse(
            unavailable_response(sport, f"no snapshot for sport '{sport}'"),
            status_code=503)

    pred = None
    for p in getattr(env, "predictions", []) or []:
        if getattr(p, "game_id", None) == game_id:
            pred = p
            break

    if pred is None:
        return JSONResponse(
            {"status": "not_found", "sport": sport, "game_id": game_id,
             "reason": "game_id not in current snapshot", "rows": [],
             "edge_claimed": False, "honest_note": HONEST_NOTE},
            status_code=404)

    prop_date = date or _snap_date(env)
    lines = _prop_lines_from_markets(getattr(pred, "markets", []) or [])
    body = build_props_response(sport, prop_date, lines, game_id=game_id)
    body["generated_at"] = getattr(env, "generated_at", None)
    body["home"] = getattr(pred, "home", None)
    body["away"] = getattr(pred, "away", None)
    body["edge_claimed"] = False
    return JSONResponse(body)


__all__ = ["router"]
