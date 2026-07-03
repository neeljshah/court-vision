"""sell.sell_edge_routes -- buyer-facing edge + paper-place sell endpoints.

Mounts into sell.serve_sell:app additively (guarded include_router).

Endpoints
---------
GET /sell/v1/edges/{sport}
    Deep edge view for every game in the sport snapshot.
    Requires feature "live_edges" (pro + enterprise; NOT free).

GET /sell/v1/edges/{sport}/{game_id}
    Single-game deep edge object.
    Requires feature "live_edges".

POST /sell/v1/paper/place
    Place a manual paper trade (PAPER ONLY; executed always False).
    Requires feature "paper_place" (pro + enterprise; NOT free).
    Delegates validation + recording to frontend.exec_routes logic (reuses
    predict_service.store anti-fabrication guard and clv_ledger append).

Auth
----
Pass the key in Authorization: Bearer <key> or ?api_key=<key>.
Unauthorized -> 401. Out-of-plan -> 403.

Honesty
-------
* edge_claimed=false on every response.
* No $ / dollar / roi / profit / pnl / bankroll field anywhere.
* honest_note on every response.
* Delegation to build_edge_view / build_game_edge (pure over store).

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets;
no $-edge field; additive -- does NOT modify existing sell endpoints.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Body, Header, HTTPException, Query
    from fastapi.responses import JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError("sell.sell_edge_routes requires fastapi.") from exc

import sell.authz as _authz
import sell.entitlements as _ent
import sell.usage_meter as _meter

router = APIRouter()

_EDGE_CLAIMED: bool = False
_HONEST_NOTE: str = (
    "Calibrated decision-support only. Markets are efficient; no $ edge is "
    "claimed. edge_claimed=false always. CLV is the honest yardstick."
)

# --------------------------------------------------------------------------- #
# Auth helpers (mirrors serve_sell._authenticate / _require_feature)          #
# --------------------------------------------------------------------------- #

def _extract_key(authorization: Optional[str], api_key: Optional[str]) -> Optional[str]:
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    if api_key:
        return api_key.strip()
    return None


def _authenticate(authorization: Optional[str],
                  api_key: Optional[str]) -> tuple:
    """Return (tenant, plan) or raise 401."""
    key = _extract_key(authorization, api_key)
    if not key:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key",
                    "message": "Provide key via Authorization: Bearer <key> or ?api_key=",
                    "edge_claimed": _EDGE_CLAIMED},
        )
    result = _authz.verify_key(key)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key",
                    "message": "Key is invalid, forged, or expired.",
                    "edge_claimed": _EDGE_CLAIMED},
        )
    return result  # (tenant, plan)


def _require_feature(plan: str, feature: str) -> None:
    if not _ent.allowed(plan, feature):
        min_plan = _ent.feature_min_plan(feature)
        raise HTTPException(
            status_code=403,
            detail={"error": "plan_insufficient",
                    "feature": feature,
                    "your_plan": plan,
                    "required_plan": min_plan or "pro",
                    "edge_claimed": _EDGE_CLAIMED,
                    "honest_note": _HONEST_NOTE},
        )


def _honest_wrap(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove stray $ keys; inject edge_claimed=false + honest_note."""
    out = {k: v for k, v in payload.items()
           if not any(t in k.lower() for t in ("roi", "profit", "$edge", "pnl",
                                                "bankroll", "dollar"))}
    out["edge_claimed"] = _EDGE_CLAIMED
    out["honest_note"] = _HONEST_NOTE
    return out


# --------------------------------------------------------------------------- #
# Edge view endpoints                                                           #
# --------------------------------------------------------------------------- #

@router.get("/sell/v1/edges/{sport}")
async def sell_edges_sport(
    sport: str,
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    """Deep edge view for every game in *sport*. Requires live_edges feature."""
    tenant, plan = _authenticate(authorization, api_key)
    _require_feature(plan, "live_edges")
    _meter.record(tenant, "/sell/v1/edges/%s" % sport)

    try:
        from frontend.edge_api import build_edge_view
        view = build_edge_view(sport)
    except Exception as exc:  # noqa: BLE001 -- edge_api must not raise but be safe
        logger.warning("sell_edge_routes: build_edge_view failed: %s", exc)
        view = {"sport": sport, "status": "unavailable",
                "reason": "edge assembler error", "games": [], "count": 0}

    body = _honest_wrap(view)
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


@router.get("/sell/v1/edges/{sport}/{game_id}")
async def sell_edges_game(
    sport: str,
    game_id: str,
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    """Single-game deep edge object. Requires live_edges feature."""
    tenant, plan = _authenticate(authorization, api_key)
    _require_feature(plan, "live_edges")
    _meter.record(tenant, "/sell/v1/edges/%s/%s" % (sport, game_id))

    try:
        from frontend.edge_api import build_game_edge
        view = build_game_edge(sport, game_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sell_edge_routes: build_game_edge failed: %s", exc)
        view = {"sport": sport, "game_id": game_id, "status": "unavailable",
                "reason": "edge assembler error"}

    body = _honest_wrap(view)
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


# --------------------------------------------------------------------------- #
# Paper placement endpoint                                                      #
# --------------------------------------------------------------------------- #

@router.post("/sell/v1/paper/place")
async def sell_paper_place(
    payload: Dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> JSONResponse:
    """Place a manual paper bet via the sell API (PAPER ONLY; executed=False).

    Delegates ALL validation and recording to frontend.exec_routes._* helpers
    (store anti-fabrication guard, clv_ledger LOCKED append, idempotency).
    Requires paper_place feature (pro + enterprise).
    """
    tenant, plan = _authenticate(authorization, api_key)
    _require_feature(plan, "paper_place")
    _meter.record(tenant, "/sell/v1/paper/place")

    # Delegate to the exec_routes placement logic (reuse, no reimplementation).
    try:
        from frontend.exec_routes import (
            _find_market,
            _find_edge,
            _matchup_for,
            _idem_key,
            _existing_open,
            _quarter_kelly,
            _public_row,
            _HONEST_NOTE as _EXEC_NOTE,
            _CHANNEL,
            _PRICE_EPS,
        )
        from predict_service import store as _store
    except Exception as exc:  # noqa: BLE001
        logger.warning("sell_edge_routes: exec_routes import failed: %s", exc)
        return JSONResponse({"status": "unavailable",
                             "reason": "placement engine unavailable",
                             "edge_claimed": _EDGE_CLAIMED},
                            status_code=503)

    sport = str(payload.get("sport", "")).strip()
    game_id = str(payload.get("game_id", "")).strip()
    market_type = str(payload.get("market_type", "")).strip()
    side = str(payload.get("side", "")).strip()
    book = str(payload.get("book", "")).strip()
    if not (sport and game_id and market_type and side and book):
        return JSONResponse({"status": "rejected",
                             "reason": "missing required field (sport, game_id, "
                                       "market_type, side, book all required)",
                             "edge_claimed": _EDGE_CLAIMED}, status_code=422)
    try:
        taken_decimal = float(payload.get("taken_decimal"))
    except (TypeError, ValueError):
        return JSONResponse({"status": "rejected",
                             "reason": "taken_decimal must be a number",
                             "edge_claimed": _EDGE_CLAIMED}, status_code=422)
    if taken_decimal <= 1.0:
        return JSONResponse({"status": "rejected",
                             "reason": "taken_decimal must be > 1.0",
                             "edge_claimed": _EDGE_CLAIMED}, status_code=422)

    env = _store.read_latest(sport)
    if getattr(env, "status", "unavailable") != "ok":
        return JSONResponse({"status": "rejected",
                             "reason": "sport %r has no live snapshot" % sport,
                             "edge_claimed": _EDGE_CLAIMED}, status_code=400)

    market = _find_market(env, game_id, market_type, side, book, taken_decimal)
    if market is None:
        return JSONResponse({"status": "rejected",
                             "reason": "no live store line matches the placement; "
                                       "fabricated or stale lines are rejected",
                             "edge_claimed": _EDGE_CLAIMED}, status_code=400)

    idem_key = _idem_key(sport, game_id, market_type, side, book)
    existing = _existing_open(idem_key, None)
    if existing is not None:
        body = _honest_wrap({"status": "ok", "idempotent": True,
                             "bet": _public_row(existing)})
        return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})

    edge = _find_edge(env, game_id, market_type, side)
    model_prob = getattr(edge, "model_prob", None) if edge is not None else None
    edge_ev = getattr(edge, "ev", None) if edge is not None else None
    tier = getattr(edge, "tier", None) if edge is not None else None
    matchup = _matchup_for(env, game_id)
    qk = _quarter_kelly(model_prob, taken_decimal)
    stake_units = round(1.0 + qk, 6)

    try:
        from scripts.platformkit.clv_ledger import record_bet
        rec = record_bet(sport=sport, matchup=matchup, side=side,
                         taken_book=book, taken_decimal=taken_decimal,
                         model_prob=model_prob, stake=0.0)
    except ValueError as exc:
        return JSONResponse({"status": "rejected", "reason": str(exc),
                             "edge_claimed": _EDGE_CLAIMED}, status_code=422)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sell_edge_routes: record_bet failed: %s", exc)
        return JSONResponse({"status": "error",
                             "reason": "could not record paper bet",
                             "edge_claimed": _EDGE_CLAIMED}, status_code=500)

    rec.update({"game_id": game_id, "market_type": market_type,
                "channel": _CHANNEL, "idem_key": idem_key,
                "ev": (float(edge_ev) if edge_ev is not None else None),
                "tier": (str(tier) if tier is not None else None),
                "stake_units": stake_units, "executed": False})
    try:
        from scripts.platformkit.clv_ledger_io import append_row
        append_row(rec)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sell_edge_routes: enriched append_row failed: %s", exc)

    body = _honest_wrap({"status": "ok", "idempotent": False,
                         "bet": _public_row(rec)})
    return JSONResponse(content=body, headers={"X-Edge-Claimed": "false"})


__all__ = ["router"]
