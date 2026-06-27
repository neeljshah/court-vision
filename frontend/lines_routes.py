"""frontend.lines_routes -- the all-books LINE BOARD + per-game LINE HISTORY.

BE-P1-01 + BE-P0-05. Two read-only projections over data the canonical store and
the append-only line-history already hold; no new modelling.

  GET /api/lines/{sport}
      Projects EVERY MarketRow in the latest SnapshotEnvelope (book / side / line
      / odds / captured_at / is_close) plus the home/away/tipoff game context, so
      the UI can draw a TRUE all-books board -- not the 3 ranked decision
      candidates bestbets surfaces. A missing snapshot -> status='unavailable'.

  GET /api/lines/{sport}/{game_id}/history[?market_type=&side=]
      The captured TICK SERIES for a game's market(s) from the append-only line
      history (line_store), each tick {captured_at, book, market_type, side, line,
      odds}, plus an is_close flag derived from the vetted line_store.get_close
      (clv_is_proxy when the close is only a last-seen proxy). This enables a
      movement sparkline + CLV-vs-true-close. No history -> empty series, never
      fabricated.

HONESTY: no $ / dollar / roi / profit / pnl / stake / bankroll key anywhere;
is_close/clv_is_proxy are surfaced honestly (a proxy close is flagged, never
hidden); a stale/absent line reads status='unavailable', never green. Markets are
efficient; edge_claimed is always False.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError("frontend.lines_routes requires fastapi.") from exc

from predict_service import store
from predict_service.contracts import HONEST_NOTE

logger = logging.getLogger(__name__)

router = APIRouter()

_STORE_DIR_ENV = "PREDICT_SERVICE_STORE_DIR"


def _store_out_dir() -> Optional[str]:
    val = os.environ.get(_STORE_DIR_ENV)
    return val or None


def _game_context(env) -> Dict[str, Dict[str, Any]]:
    """game_id -> {home, away, tipoff} so the board can label each quote."""
    ctx: Dict[str, Dict[str, Any]] = {}
    for p in env.predictions:
        ctx[p.game_id] = {"home": p.home, "away": p.away, "tipoff": p.tipoff}
    return ctx


@router.get("/api/lines/{sport}")
def lines_for_sport(sport: str,
                    game_id: Optional[str] = Query(None)) -> JSONResponse:
    """All captured MarketRows for *sport* (optionally one game) -- a true board."""
    env = store.read_latest(sport, out_dir=_store_out_dir())
    if env.status != "ok":
        return JSONResponse({
            "status": "unavailable", "sport": sport,
            "reason": env.note or "no snapshot",
            "generated_at": env.generated_at or None,
            "lines": [], "count": 0,
            "honest_note": HONEST_NOTE, "edge_claimed": False,
        })
    ctx = _game_context(env)
    lines: List[Dict[str, Any]] = []
    for m in env.markets:
        if game_id is not None and getattr(m, "game_id", None) != game_id:
            continue
        row = m.to_dict()
        row.update(ctx.get(m.game_id, {}))
        lines.append(row)
    return JSONResponse({
        "status": "ok", "sport": sport,
        "generated_at": env.generated_at,
        "lines": lines, "count": len(lines),
        "honest_note": HONEST_NOTE, "edge_claimed": False,
    })


def _history_rows(sport: str, game_id: str) -> List[Dict[str, Any]]:
    """Every captured tick for this game from the append-only line history."""
    try:
        from scripts.platformkit.odds_provider import line_store  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 -- history is best-effort
        logger.warning("lines_routes: line_store import failed: %s", exc)
        return []
    try:
        rows = line_store._load_rows(game_id, None)  # noqa: SLF001 -- documented reader
    except Exception as exc:  # noqa: BLE001 -- a read miss is an empty series
        logger.warning("lines_routes: history load failed for %s: %s", game_id, exc)
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "captured_at": r.get("captured_at"),
            "book": r.get("book", ""),
            "market_type": r.get("market_type"),
            "side": r.get("side"),
            "line": r.get("line"),
            "odds": r.get("odds"),
        })
    out.sort(key=lambda x: str(x.get("captured_at") or ""))
    return out


def _close_flags(sport: str, game_id: str) -> Dict[str, Any]:
    """The (market,side) at-lock close markers from the vetted line_store.get_close.

    is_true_close=True means clv_is_proxy=False (a real close); False means the
    surfaced close is a last-seen PROXY (clv_is_proxy=True). None on no history.
    """
    try:
        from scripts.platformkit.odds_provider import line_store  # noqa: PLC0415
        res = line_store.get_close(game_id)
    except Exception as exc:  # noqa: BLE001 -- close is advisory
        logger.debug("lines_routes: get_close failed for %s: %s", game_id, exc)
        return {"is_true_close": False, "clv_is_proxy": True, "have_close": False}
    if res is None:
        return {"is_true_close": False, "clv_is_proxy": True, "have_close": False}
    _quotes, is_true = res
    return {"is_true_close": bool(is_true), "clv_is_proxy": (not bool(is_true)),
            "have_close": True}


@router.get("/api/lines/{sport}/{game_id}/history")
def line_history(sport: str, game_id: str,
                 market_type: Optional[str] = Query(None),
                 side: Optional[str] = Query(None)) -> JSONResponse:
    """Captured tick series for a game's market(s) + an honest is_close flag."""
    ticks = _history_rows(sport, game_id)
    if market_type is not None:
        ticks = [t for t in ticks if t.get("market_type") == market_type]
    if side is not None:
        ticks = [t for t in ticks if t.get("side") == side]
    close = _close_flags(sport, game_id)
    status = "ok" if ticks else "unavailable"
    return JSONResponse({
        "status": status, "sport": sport, "game_id": game_id,
        "ticks": ticks, "count": len(ticks),
        "is_close": close["have_close"],
        "is_true_close": close["is_true_close"],
        "clv_is_proxy": close["clv_is_proxy"],
        "honest_note": (
            HONEST_NOTE + " A proxy close (clv_is_proxy=True) is the last-seen "
            "pre-tip line, not a true settled close -- flagged, never hidden."),
        "edge_claimed": False,
    })


__all__ = ["router"]
