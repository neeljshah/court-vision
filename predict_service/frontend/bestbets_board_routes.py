"""predict_service.frontend.bestbets_board_routes -- UNIFIED multi-sport best-bets board.

GET /api/bestbets/board?sport=&tier=&status=live|pregame|done

Serves the DAEMON-written unified board (data/frontend/best_bets.json) which already
contains EVERY market as its own card: moneyline + total + spread game cards AND
player-prop cards (market_type in {"prop","player_prop"}). The daemon path is read
through cached_board_read (freshness SLA + past-tipoff sanitize); a missing/stale
file falls back to on-request compute_best_bets() per sport so the route never dark.

RANKING / CAPS (so ~thousands of model-only props do not flood the board):
  1. PRICED bets first -- game markets (ML/total/spread) + priced props (real line +
     market_prob), by tier (A>B>C) then confidence desc.
  2. Then MODEL-ONLY props (no line), by reliability+confidence, capped at
     MODEL_ONLY_CAP_PER_SPORT/sport. Surplus is NOT silently dropped:
     model_only_truncated={sport:n_more}, model_only_more=total.

HONESTY: units (not $); edge_vs_market = model_prob - market_prob (prob diff, null
for model-only); clv may be INSUFFICIENT_DATA; NO $/pnl/roi/profit field; stale-
never-green (stale cache served status='stale', overall never forced 'ok'; past-
tipoff dropped on read); real-money default-DENY (edge_claimed=False always).

INVARIANTS: <=300 LOC; ASCII; predict_service/frontend/ only; no $-edge; per-file test.
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

# Per-sport cap on MODEL-ONLY props (no market line). Priced/game cards are never
# capped. Surplus is reported honestly via model_only_truncated, not dropped silently.
MODEL_ONLY_CAP_PER_SPORT = 25

_TIER_RANK = {"A": 0, "B": 1, "C": 2}
_PROP_MARKETS = frozenset({"prop", "player_prop"})


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _active_sports() -> List[str]:
    """Active sports from the canonical registry (degrades to a default on error)."""
    try:
        from predict_service import registry  # noqa: PLC0415
        return list(registry.active_sports() or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets_board_routes._active_sports: registry failed (%s)", exc)
    return ["nba", "mlb", "soccer_intl", "tennis"]


# ---------------------------------------------------------------------------
# Card classification + ranking
# ---------------------------------------------------------------------------

def _is_model_only(card: Dict[str, Any]) -> bool:
    """True when a card carries NO real market line/price (model-only prop view)."""
    if card.get("model_only") is True:
        return True
    if str(card.get("market_type", "")) in _PROP_MARKETS:
        # A prop with no market_prob AND no best_odds is a pure model view.
        if card.get("market_prob") is None and card.get("best_odds") is None:
            return True
    return False


def _conf(card: Dict[str, Any]) -> float:
    try:
        return float(card.get("confidence") or card.get("model_prob") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _rank_key(card: Dict[str, Any]):
    """Sort key: tier rank (A first), reliable first, then confidence desc."""
    tier = str(card.get("tier") or "C").upper()
    reliable = 0 if card.get("reliable") else 1
    return (_TIER_RANK.get(tier, 99), reliable, -_conf(card))


def _rank_and_cap(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split priced vs model-only, rank each, cap model-only per sport.

    Returns {cards, model_only_more, model_only_truncated} where cards is the final
    ranked list (priced first, then capped model-only) and the truncation counts are
    honest -- surplus model-only props are reported, never silently dropped.
    """
    priced: List[Dict[str, Any]] = []
    model_only: List[Dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        (model_only if _is_model_only(c) else priced).append(c)

    priced.sort(key=_rank_key)
    model_only.sort(key=_rank_key)

    kept_mo: List[Dict[str, Any]] = []
    per_sport_kept: Dict[str, int] = {}
    truncated: Dict[str, int] = {}
    for c in model_only:
        sp = str(c.get("sport") or "?")
        if per_sport_kept.get(sp, 0) < MODEL_ONLY_CAP_PER_SPORT:
            kept_mo.append(c)
            per_sport_kept[sp] = per_sport_kept.get(sp, 0) + 1
        else:
            truncated[sp] = truncated.get(sp, 0) + 1

    return {
        "cards": priced + kept_mo,
        "model_only_more": sum(truncated.values()),
        "model_only_truncated": truncated,
    }


def _apply_filters(
    cards: List[Dict[str, Any]],
    sport_key: Optional[str],
    tier_f: Optional[str],
    status_f: Optional[str],
) -> List[Dict[str, Any]]:
    """Apply sport/tier/status query filters. Model-only props (tier=MODEL_VIEW) are
    kept under a tier filter only when that filter matches their tier label."""
    out = cards
    if sport_key:
        out = [c for c in out if str(c.get("sport", "")).lower() == sport_key]
    if tier_f:
        out = [c for c in out if str(c.get("tier") or "").upper() == tier_f]
    if status_f:
        out = [c for c in out if str(c.get("status") or "").lower() == status_f]
    return out


def _from_daemon_cache() -> Optional[Dict[str, Any]]:
    """Read the daemon-written unified board through the freshness-gated reader.

    Returns the cached_board_read envelope (status fresh|stale|unavailable) or None
    if the reader module is unavailable. Game-market cards are passed through the
    pre-serve filter (drops Yes/No binaries, dead/degenerate markets, stale tipoffs);
    prop cards bypass that filter because a model-only prop legitimately has a null
    market_prob and must not be dropped by the market_prob<0.02 game-card rule.
    """
    try:
        from scripts.platformkit.bestbets.cached_board_read import read as _read  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets_board: cached_board_read unavailable (%s)", exc)
        return None
    try:
        env = _read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("bestbets_board: cached_board_read.read failed: %s", exc)
        return None
    if not isinstance(env, dict) or env.get("status") == "unavailable":
        return None

    raw_cards = [c for c in (env.get("cards") or []) if isinstance(c, dict)]
    game_cards = [c for c in raw_cards if str(c.get("market_type", "")) not in _PROP_MARKETS]
    prop_cards = [c for c in raw_cards if str(c.get("market_type", "")) in _PROP_MARKETS]
    try:
        from predict_service.frontend.bestbets_board_filter import filter_cards  # noqa: PLC0415
        game_cards = filter_cards(game_cards)
    except Exception as exc:  # noqa: BLE001
        logger.debug("bestbets_board: filter_cards skipped (%s)", exc)
    env["_clean_cards"] = game_cards + prop_cards
    return env


def _from_compute(sports: List[str], status_f: Optional[str]) -> List[Dict[str, Any]]:
    """Fallback: collect cards via on-request compute_best_bets per sport."""
    cards: List[Dict[str, Any]] = []
    for sp in sports:
        try:
            result = compute_best_bets(
                sp, status_filter=status_f, include_props=True,
            )
            cards.extend(result.get("cards") or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("bestbets_board: compute_best_bets(%s) failed: %s", sp, exc)
    return cards


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
    """Unified best-bets board: ML + total + spread + props, ranked, capped.

    PRICED bets (game markets + priced props) rank first; MODEL-ONLY props follow,
    capped per sport with an honest 'N more' count. Serves the daemon-written
    unified board (freshness-gated, stale-never-green); falls back to on-request
    compute when the cache is missing. No $ field; edge_claimed=False always.
    """
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

    sport_key = (sport or "").strip().lower() or None
    sports = [sport_key] if sport_key else _active_sports()

    # -- source: daemon cache (preferred) or on-request compute (fallback) --
    env = _from_daemon_cache()
    source = "unavailable"
    cache_status = "unavailable"
    stale = False
    stale_note = ""
    generated_at = None
    if env is not None:
        source = "daemon_cache"
        cache_status = str(env.get("status") or "unavailable")
        stale = cache_status == "stale"
        stale_note = str(env.get("stale_note") or "")
        generated_at = env.get("generated_at")
        raw_cards = list(env.get("_clean_cards") or [])
    else:
        source = "compute"
        raw_cards = _from_compute(sports, status_f)

    # -- filter, rank, cap --
    filtered = _apply_filters(raw_cards, sport_key, tier_f, status_f)
    ranked = _rank_and_cap(filtered)
    cards = ranked["cards"]

    # stale-never-green: never report 'ok' when the cache was stale.
    if stale:
        overall_status = "stale"
    elif source == "daemon_cache":
        overall_status = "ok"
    else:
        overall_status = "ok"

    body: Dict[str, Any] = {
        "status": overall_status,
        "source": source,
        "cache_status": cache_status,
        "stale": stale,
        "generated_at": generated_at,
        "sports": sports,
        "count": len(cards),
        "cards": cards,
        "model_only_more": ranked["model_only_more"],
        "model_only_truncated": ranked["model_only_truncated"],
        "model_only_cap_per_sport": MODEL_ONLY_CAP_PER_SPORT,
        "filters": {"sport": sport_key, "tier": tier_f, "status": status_f},
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
    }
    if stale_note:
        body["stale_note"] = stale_note
    return JSONResponse(body)


__all__ = ["router", "MODEL_ONLY_CAP_PER_SPORT", "_rank_and_cap", "_is_model_only"]
