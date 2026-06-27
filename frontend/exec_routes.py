"""frontend.exec_routes -- MANUAL paper-trade execution from the dashboard.

PAPER ONLY. POST /api/paper/place places a paper bet; GET /api/paper/open lists
open ones. NEVER a real bet (executed ALWAYS False) and NEVER a fabricated/stale
line: a placement is validated against the line CURRENTLY in
predict_service.store.read_latest(sport) before anything is recorded. The record
goes through scripts.platformkit.clv_ledger.record_bet (LOCKED clv_ledger_io
append) on channel="paper_manual" with a stamped model_prob/ev/tier from the
matching store edge and stake sizing flat_unit=1.0 + quarter_kelly. Idempotency
key sport|game_id|market_type|side|book|YYYY-MM-DD makes a same-day
double-submit return the EXISTING open row (no duplicate). Reject 422/400 when:
the 5-tuple has no matching MarketRow; taken_decimal<=1.0; sport snapshot not ok.
No $ / dollar / roi / profit / $edge field -- the "edge" is EV + CLV only.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII-only; no secrets.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Body, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover -- fastapi is required at runtime
    raise ImportError("frontend.exec_routes requires fastapi.") from exc

from frontend.paper_trail import read_trail
from predict_service import store

router = APIRouter()
_CHANNEL = "paper_manual"
# Freshness SLA: a snapshot older than this is STALE and cannot back a placement.
# A stale line reads green nowhere -- we reject 409 rather than record against it.
_STALE_SLA_SEC = float(os.environ.get("PAPER_PLACE_SLA_SEC", "180"))
_HONEST_NOTE = (
    "Paper-only. executed is always False; this is NEVER a real-money path. "
    "Placement is validated against the live store line AND its freshness -- a "
    "fabricated OR stale line cannot be placed. Edges are EV/CLV (probability-"
    "space); no $ edge is claimed."
)


# Pure helpers live in frontend.exec_support (keeps this file <=300 LOC).
from frontend.exec_support import (  # noqa: E402
    existing_open as _existing_open,
    find_edge as _find_edge,
    find_market as _find_market,
    idem_key as _idem_key,
    matchup_for as _matchup_for,
    public_row as _public_row,
    quarter_kelly as _quarter_kelly,
    snapshot_age_sec as _snapshot_age_sec,
)


# -- endpoints ----------------------------------------------------------------
def _reject(reason: str, code: int) -> JSONResponse:
    return JSONResponse({"status": "rejected", "reason": reason}, status_code=code)


@router.post("/api/paper/place")
def paper_place(
    payload: Dict[str, Any] = Body(...),
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """Place a MANUAL paper bet (paper-only, executed always False).

    Validates the line against the live store, records an open paper bet, and
    returns the created row. Idempotent on a same-day double-submit.
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None

    sport = str(payload.get("sport", "")).strip()
    game_id = str(payload.get("game_id", "")).strip()
    market_type = str(payload.get("market_type", "")).strip()
    side = str(payload.get("side", "")).strip()
    book = str(payload.get("book", "")).strip()
    if not (sport and game_id and market_type and side and book):
        return _reject("missing required field (sport, game_id, market_type, "
                       "side, book all required)", 422)
    try:
        taken_decimal = float(payload.get("taken_decimal"))
    except (TypeError, ValueError):
        return _reject("taken_decimal must be a number", 422)
    if taken_decimal <= 1.0:
        return _reject("taken_decimal must be > 1.0", 422)

    # sport active: the store must hold an OK snapshot for it.
    env = store.read_latest(sport)
    if getattr(env, "status", "unavailable") != "ok":
        return _reject("sport %r has no live snapshot (status=%s)"
                       % (sport, getattr(env, "status", "unavailable")), 400)

    # FRESHNESS GATE (P0-6): status=="ok" only means well-formed, NOT fresh. A
    # snapshot past the SLA (or with an unparseable generated_at) is STALE and
    # CANNOT back a placement -- reject 409 rather than record against a dead line.
    age = _snapshot_age_sec(env)
    if age is None or age > _STALE_SLA_SEC:
        return _reject(
            "snapshot is stale (age=%s s, sla=%.0f s); a stale line cannot be "
            "placed" % ("unknown" if age is None else "%.0f" % age, _STALE_SLA_SEC),
            409)

    # The line MUST match a market currently in the store (no fabricated/stale).
    market = _find_market(env, game_id, market_type, side, book, taken_decimal)
    if market is None:
        return _reject("no live store line matches (game_id, market_type, "
                       "side, book, taken_decimal); cannot place a fabricated "
                       "or stale line", 400)

    idem_key = _idem_key(sport, game_id, market_type, side, book)
    # Durable, game-anchored id (survives the UTC-midnight boundary -- P1-8).
    from scripts.platformkit.clv_ledger import bet_id as _mk_bet_id
    target_bet_id = _mk_bet_id({
        "sport": sport, "event_id": game_id, "market": market_type,
        "side": side.strip().lower(), "taken_book": book,
        "game_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })

    # Idempotency: a re-submit of the same bet returns the existing open row.
    existing = _existing_open(idem_key, ledger_path, target_bet_id)
    if existing is not None:
        return JSONResponse(
            {"status": "ok", "idempotent": True,
             "bet": _public_row(existing), "honest_note": _HONEST_NOTE})

    edge = _find_edge(env, game_id, market_type, side)
    model_prob = getattr(edge, "model_prob", None) if edge is not None else None
    edge_ev = getattr(edge, "ev", None) if edge is not None else None
    tier = getattr(edge, "tier", None) if edge is not None else None
    matchup = _matchup_for(env, game_id)

    # Stake sizing: flat_unit=1.0 + quarter_kelly (units), recorded not as $.
    qk = _quarter_kelly(model_prob, taken_decimal)
    stake_units = round(1.0 + qk, 6)

    side_norm = side.strip().lower()
    if side_norm not in ("home", "away"):
        return _reject("side must be 'home' or 'away', got %r" % (side,), 422)

    # PE-P0-05: write EXACTLY ONE enriched open row. We build the full row here
    # (including the durable bet_id) and append ONCE via the locked primitive --
    # we do NOT call record_bet first (that would leave an orphan base open row
    # with no idem_key/tier/stake_units, a phantom duplicate invisible to dedup).
    now = datetime.now(timezone.utc)
    rec: Dict[str, Any] = {
        "ts": now.isoformat(),
        "sport": sport,
        "matchup": matchup,
        "side": side_norm,
        "taken_book": book,
        "taken_decimal": taken_decimal,
        "model_prob": (float(model_prob) if model_prob is not None else None),
        "stake_units": stake_units,
        "status": "open",
        "game_id": game_id,
        "event_id": game_id,
        "game_date": now.strftime("%Y-%m-%d"),
        "market": market_type,
        "market_type": market_type,
        "channel": _CHANNEL,
        "idem_key": idem_key,
        "ev": (float(edge_ev) if edge_ev is not None else None),
        "tier": (str(tier) if tier is not None else None),
        "bet_id": target_bet_id,
        "executed": False,  # INVARIANT: paper-only, never a real bet
    }
    try:
        from scripts.platformkit.clv_ledger_io import append_row
        append_row(rec, path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_routes: append_row failed: %s", exc)
        return JSONResponse(
            {"status": "error", "reason": "could not record paper bet"},
            status_code=500)

    return JSONResponse(
        {"status": "ok", "idempotent": False,
         "bet": _public_row(rec), "honest_note": _HONEST_NOTE})


@router.get("/api/paper/open")
def paper_open(
    sport: Optional[str] = Query(None, description="Filter by sport (e.g. nba)"),
    ledger: Optional[str] = Query(None, description="Override ledger path (tests only)"),
) -> JSONResponse:
    """Current OPEN manual+auto paper bets (status == 'open').

    Reuses frontend.paper_trail.read_trail (collapsed open->settled) and keeps
    only open rows. Never raises -> missing ledger yields an empty list.
    """
    ledger_path: Optional[Path] = Path(ledger) if ledger else None
    try:
        trail = read_trail(ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("exec_routes /api/paper/open error: %s", exc)
        trail = []
    rows = [r for r in trail if str(r.get("status", "")).lower() == "open"]
    if sport:
        rows = [r for r in rows
                if str(r.get("sport", "")).lower() == sport.lower()]
    return JSONResponse(
        {"status": "ok", "count": len(rows), "open": rows,
         "honest_note": _HONEST_NOTE})


__all__ = ["router"]
