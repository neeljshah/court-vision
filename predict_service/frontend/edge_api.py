"""predict_service.frontend.edge_api -- predict-service-local edge view builder.

Thin wrapper over frontend.edge_api.build_edge_view that adds:

  1. A sport-local build_edge_view() callable importable from predict_service.frontend
     (satisfying bestbets_compute._get_edge_view and v1_completion_gate_mounts
     which do ``from frontend.edge_api import build_edge_view``).

  2. build_mlb_edge_cards(sport, env) -- the MLB-specific ranked edge card builder.
     Given a SnapshotEnvelope with differentiated per-game probabilities, it emits
     ranked BestBetCard-shaped dicts carrying model_prob, market_prob, divergence,
     tier, and confidence.  When the envelope is empty OR the model_prob values
     collapse to a flat prior (degenerate), it returns 0 cards with an honest status.

HONESTY (binding):
  - No $ / pnl / roi / profit / bankroll / usd / dollar field ANYWHERE.
  - divergence = model_prob - market_prob  (probability space, NOT $).
  - tier is an evidence label (A / B / C) derived from EV floors; None = no bet.
  - edge_claimed = False always; this is calibrated decision-support.
  - Degenerate or empty slate -> honest status='degenerate' or status='none'.

RAILS: <= 300 LOC; ASCII only; no IO except the store read delegated to upstream;
no global mutable state; per-file test only (never full-suite pytest).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HONEST_NOTE = (
    "Calibrated decision-support only. Markets are efficient; no $ edge claimed. "
    "divergence = model_prob - market_prob (probability space, NOT $). "
    "tier is an evidence label (A/B/C); no tier = no bet. "
    "units = flat_unit from policy (1.0 per bet, UNITS not $). "
    "clv may be INSUFFICIENT_DATA (no liquid in-play prices in offseason)."
)

# Minimum number of distinct model_prob values for a slate to be non-degenerate.
# An MLB slate that collapses to <= 2 distinct values is a flat-prior fallback.
_MIN_DISTINCT_PROBS: int = 3

# EV floors mirroring exec_decision.TIER_FLOORS (calibrated threshold reuse).
_TIER_FLOORS: Dict[str, float] = {"A": 0.08, "B": 0.04, "C": 0.02}

# Forbidden output fields (honesty rail: never emit these).
_FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "profit", "bankroll", "usd", "dollar", "stake_$", "revenue",
})


# ---------------------------------------------------------------------------
# Delegation to the upstream assembler
# ---------------------------------------------------------------------------

def build_edge_view(sport: str, *, store_out_dir: Any = None) -> Dict[str, Any]:
    """Delegate to frontend.edge_api.build_edge_view. NEVER raises.

    Re-exported here so callers within predict_service can import from this
    module without depending on the frontend/ package path directly.  The
    returned shape is identical to the upstream function; no fields are added
    or removed (this is a pure pass-through).
    """
    try:
        from frontend.edge_api import build_edge_view as _upstream  # noqa: PLC0415
        return _upstream(sport, store_out_dir=store_out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_edge_view(%s) upstream failed: %s", sport, exc)
        return {
            "sport": str(sport),
            "generated_at": "",
            "status": "unavailable",
            "reason": "upstream build_edge_view error: %s" % type(exc).__name__,
            "count": 0,
            "games": [],
            "honest_note": _HONEST_NOTE,
            "edge_claimed": False,
        }


# ---------------------------------------------------------------------------
# MLB-specific ranked edge card builder
# ---------------------------------------------------------------------------

def _distinct_model_probs(games: List[Dict[str, Any]]) -> int:
    """Count distinct model_prob values across all comparison rows in *games*."""
    seen: set = set()
    for g in games:
        for row in g.get("comparison") or []:
            if not isinstance(row, dict):
                continue
            mp = row.get("model_prob")
            if mp is None:
                continue
            try:
                seen.add(round(float(mp), 6))
            except (TypeError, ValueError):
                pass
    return len(seen)


def _tier_from_ev(ev: Optional[float]) -> Optional[str]:
    """Assign the highest evidence tier that *ev* clears, or None (no bet)."""
    if ev is None:
        return None
    try:
        ev_f = float(ev)
    except (TypeError, ValueError):
        return None
    for tier in ("A", "B", "C"):
        if ev_f >= _TIER_FLOORS[tier]:
            return tier
    return None


def _card_from_row(
    row: Dict[str, Any],
    game: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Build one ranked edge card from a comparison row + its parent game.

    Returns None when the row has no viable model_prob / market_prob pair OR
    when the derived tier is None (below the C floor -> no bet).  Never raises.
    No $ field is produced; all quantities are probability-space or unit-counts.
    """
    try:
        mp = row.get("model_prob")
        mkt = row.get("market_prob")
        if mp is None or mkt is None:
            return None
        model_prob = float(mp)
        market_prob = float(mkt)
    except (TypeError, ValueError):
        return None

    ev = row.get("ev")
    tier = _tier_from_ev(ev)
    if tier is None:
        return None

    divergence = round(model_prob - market_prob, 6)
    home = str(game.get("home") or "")
    away = str(game.get("away") or "")
    matchup = ("%s vs %s" % (home, away)) if (home and away) else str(game.get("game_id", ""))

    return {
        "game_id": str(game.get("game_id", "")),
        "matchup": matchup,
        "sport": "mlb",
        "market_type": str(row.get("market_type", "")),
        "side": str(row.get("side", "")),
        "model_prob": round(model_prob, 6),
        "market_prob": round(market_prob, 6),
        "divergence": divergence,
        "best_book": str(row.get("best_book") or ""),
        "best_odds": row.get("best_odds"),
        "ev": (round(float(ev), 6) if ev is not None else None),
        "tier": tier,
        "confidence": round(model_prob, 6),
        "clv_is_proxy": bool(row.get("clv_is_proxy", True)),
        "clv": {"clv_status": "INSUFFICIENT_DATA", "clv_is_proxy": True},
        "status": "pregame",
        "edge_claimed": False,
        "honest_note": _HONEST_NOTE,
        "tipoff_utc": game.get("tipoff"),
    }


_TIER_RANK = {"A": 0, "B": 1, "C": 2}


def build_mlb_edge_cards(
    view: Dict[str, Any],
) -> Dict[str, Any]:
    """Map a build_edge_view result for MLB into ranked edge cards.

    Acceptance contract:
      - Differentiated multi-game envelope (>= _MIN_DISTINCT_PROBS distinct
        model_prob values) -> >0 ranked cards, each with model_prob,
        market_prob, divergence, tier; no $ field.
      - Flat prior (<=2 distinct probs across >= 3 games) -> 0 cards,
        status='degenerate', honest message.
      - Empty / unavailable envelope -> 0 cards, status='none'.

    Parameters
    ----------
    view:
        Return value of build_edge_view('mlb').

    Returns
    -------
    dict with keys: status, cards, count, honest_note, edge_claimed,
    and optional: degenerate_reason, generated_at.
    """
    if not isinstance(view, dict) or view.get("status") != "ok":
        return {
            "status": "none",
            "cards": [],
            "count": 0,
            "honest_note": _HONEST_NOTE,
            "edge_claimed": False,
            "degenerate_reason": "snapshot unavailable or not ok",
        }

    games: List[Dict[str, Any]] = list(view.get("games") or [])

    # Empty slate -- honest 'none right now' state.
    if not games:
        return {
            "status": "none",
            "cards": [],
            "count": 0,
            "generated_at": view.get("generated_at", ""),
            "honest_note": _HONEST_NOTE,
            "edge_claimed": False,
            "degenerate_reason": "no games in snapshot",
        }

    # Degeneracy gate: flat-prior MLB slates must not surface as ranked bets.
    n_games = len(games)
    distinct = _distinct_model_probs(games)
    if n_games >= _MIN_DISTINCT_PROBS and distinct <= 2:
        return {
            "status": "degenerate",
            "cards": [],
            "count": 0,
            "generated_at": view.get("generated_at", ""),
            "honest_note": _HONEST_NOTE,
            "edge_claimed": False,
            "degenerate_reason": (
                "MLB model_prob collapsed to %d distinct value(s) across %d games; "
                "flat-prior fallback -- not a calibrated edge" % (distinct, n_games)
            ),
        }

    # Build cards from comparison rows.
    cards: List[Dict[str, Any]] = []
    for game in games:
        if not isinstance(game, dict) or game.get("status") != "ok":
            continue
        for row in game.get("comparison") or []:
            if not isinstance(row, dict):
                continue
            card = _card_from_row(row, game)
            if card is None:
                continue
            # Safety: strip any forbidden key that crept in.
            for fk in _FORBIDDEN_KEYS:
                card.pop(fk, None)
            cards.append(card)

    # Rank: tier (A first) then confidence (model_prob) descending.
    cards.sort(
        key=lambda c: (
            _TIER_RANK.get(str(c.get("tier") or "C"), 99),
            -float(c.get("confidence") or 0.0),
        )
    )

    return {
        "status": "ok",
        "cards": cards,
        "count": len(cards),
        "generated_at": view.get("generated_at", ""),
        "honest_note": _HONEST_NOTE,
        "edge_claimed": False,
    }


__all__ = [
    "build_edge_view",
    "build_mlb_edge_cards",
]
