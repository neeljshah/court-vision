"""predict_service.frontend.bestbets_board_routes -- multi-sport best-bets board.

W3 (api-bestbets): ranked calibrated divergence cards (props + game markets)
across sports, tier/status sortable.

  GET /api/bestbets/board?sport=&tier=&status=live|pregame|done
      Returns BestBetCard list (decision==bet only), sorted by tier then
      confidence desc. Multi-sport when sport= is omitted.
      Filters: tier=A|B|C, status=live|pregame|done.

Card shape (no $ field):
  {game_id, matchup, sport, market_type, prop_player, prop_stat, side,
   model_prob, market_prob, best_book, best_odds, all_books, edge_vs_market,
   units, tier, confidence, clv, clv_is_proxy, status, honest_note}

HONESTY:
  - units = flat_unit from policy (1.0 per bet, UNITS not $).
  - edge_vs_market = model_prob - market_prob (probability diff, NOT $).
  - clv may be INSUFFICIENT_DATA (no liquid in-play prices in NBA offseason).
  - No $ / pnl / roi / profit field anywhere.
  - stale-never-green: if no snapshot, cards=[] with status='ok', no green.
  - real-money stays default-DENY (edge_claimed=False always).

INVARIANTS: <=300 LOC; ASCII only; build under predict_service/frontend/; no src/;
no $-edge; per-file test only.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover -- fastapi required at runtime
    raise ImportError(
        "predict_service.frontend.bestbets_board_routes requires fastapi."
    ) from exc

from predict_service.bestbets_compute import VALID_TIERS, VALID_STATUSES, compute_best_bets
from predict_service.contracts import HONEST_NOTE

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _active_sports() -> List[str]:
    """Active sports from the canonical registry (degrades to [] on error)."""
    try:
        from predict_service import registry  # noqa: PLC0415
        return list(registry.active_sports() or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets_board_routes._active_sports: registry failed (%s)", exc)
    return ["nba", "mlb", "soccer_intl", "tennis"]


# ---------------------------------------------------------------------------
# /api/bestbets/board
# ---------------------------------------------------------------------------

@router.get("/api/bestbets/board")
def bestbets_board(
    sport: Optional[str] = Query(
        default=None,
        description="Sport code (nba, mlb, soccer_intl, tennis). "
                    "Omit for multi-sport rollup.",
    ),
    tier: Optional[str] = Query(
        default=None,
        description="Tier filter: A (strongest) | B | C (marginal).",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Status filter: live | pregame | done.",
    ),
) -> JSONResponse:
    """Multi-sport best-bets board: ranked calibrated divergence cards.

    Returns decision==bet rows only, sorted by tier (A first) then confidence
    (model_prob) descending. Props are included when available; NBA offseason
    degrades gracefully to game-market-only. clv may be INSUFFICIENT_DATA
    (NBA offseason, no liquid in-play prices) -- surfaced honestly, never hidden.

    All edges are probability/EV; no $ field; edge_claimed=False always.
    """
    # -- validate query params --
    tier_f = (tier or "").strip().upper() or None
    if tier_f and tier_f not in VALID_TIERS:
        return JSONResponse(
            {"status": "error",
             "reason": f"invalid tier '{tier_f}'; must be one of A, B, C",
             "cards": [], "count": 0,
             "honest_note": HONEST_NOTE, "edge_claimed": False},
            status_code=400)

    status_f = (status or "").strip().lower() or None
    if status_f and status_f not in VALID_STATUSES:
        return JSONResponse(
            {"status": "error",
             "reason": f"invalid status '{status_f}'; must be live|pregame|done",
             "cards": [], "count": 0,
             "honest_note": HONEST_NOTE, "edge_claimed": False},
            status_code=400)

    # -- resolve sports list --
    sport_key = (sport or "").strip().lower() or None
    if sport_key:
        sports = [sport_key]
    else:
        sports = _active_sports()

    # -- collect cards across sports --
    all_cards: List[Dict[str, Any]] = []
    errors: List[str] = []

    for sp in sports:
        try:
            result = compute_best_bets(
                sp,
                tier_filter=tier_f,
                status_filter=status_f,
                include_props=True,
            )
            all_cards.extend(result.get("cards") or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("bestbets_board: compute_best_bets(%s) failed: %s", sp, exc)
            errors.append(f"{sp}:{type(exc).__name__}")

    # -- sort multi-sport output: tier rank then confidence desc --
    _TIER_RANK = {"A": 0, "B": 1, "C": 2}
    all_cards.sort(
        key=lambda c: (_TIER_RANK.get(str(c.get("tier", "C")), 99),
                       -float(c.get("confidence") or 0.0))
    )

    body: Dict[str, Any] = {
        "status": "ok",
        "sports": sports,
        "count": len(all_cards),
        "cards": all_cards,
        "filters": {
            "sport": sport_key,
            "tier": tier_f,
            "status": status_f,
        },
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    if errors:
        body["errors"] = errors

    return JSONResponse(body)


__all__ = ["router"]
