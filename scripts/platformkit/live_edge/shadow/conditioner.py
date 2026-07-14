"""scripts.platformkit.live_edge.shadow.conditioner -- LIVE-EDGE D1 shadow
conditioner.

Takes ONE bus-tick payload (the odds:* shape captured by bus.py: sport,
game_id/home/away, market_type, devigged_prob, book, ...) and produces an
unconditioned surface (== the market's own devigged_prob -- "trust the
market", the same honest baseline every calibration test in this repo uses)
and a conditioned surface (the unconditioned one, overlaid by any ACTIVE
registered validated mechanism whose market_family matches this tick).

VALIDATED-MECHANISM REGISTRY -- nearly empty by design (2026-07-14): the
situational-conditioning track is a proven NULL (B4-HARDEN bb790fc2: 0/20k
corrected DEFENSIBLE). The one surviving mechanism is C1's foul-trouble ->
minutes prior (130559e5, beats baseline OOS, pinball 3.16->3.06). It is
registered here but marked INACTIVE: C1 never persisted a fitted estimator
(data/omni/live_edge/combine/ holds only report JSON, no model artifact) and
its market family (ingame.props.minutes) has no live ticks on the bus yet
(bus only carries odds:*/injury:* -- no minutes-prop feed). Registering it
inactive rather than omitting it means arming later (fitted model + minutes
ticks both exist) is a one-line flip, not a rebuild. Do not read an inactive
entry as an edge claim -- zero mechanisms overlay any tick today.

INVARIANTS: stdlib only; ASCII stdout; <=300 LOC; no $/edge claims; never
writes anything (pure functions -- shadow_ledger.py owns persistence).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# market_type (as captured by bus odds:* rows) -> a stable market-family label
# the mechanism registry keys off of.
TICK_MARKET_FAMILY = {
    "moneyline": "pregame.moneyline",
    "spread": "pregame.spread",
    "total": "pregame.total",
}

# families whose predictions are probabilities and must clip to [0, 1] after
# a mechanism overlay (minutes-shaped families are NOT probabilities).
_PROB_FAMILIES = {"pregame.moneyline"}


def _c1_minutes_prior_inactive(state: Dict[str, Any]) -> float:
    """C1 foul-trouble->minutes prior. Registered, INACTIVE -- see module
    docstring. Always returns 0.0 until a fitted estimator is persisted."""
    return 0.0


MECHANISM_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "c1_minutes_prior",
        "market_family": "ingame.props.minutes",
        "source_claim": "329c45d92e094fba",
        "active": False,
        "apply": _c1_minutes_prior_inactive,
    },
]


def tick_market_family(payload: Dict[str, Any]) -> str:
    """market_type from a bus odds:* payload -> stable market-family label."""
    mt = payload.get("market_type")
    return TICK_MARKET_FAMILY.get(mt, f"other.{mt}")


def condition_tick(
    payload: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    *,
    registry: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """One bus-tick payload -> {market_family, unconditioned_pred,
    conditioned_pred, mechanism_applied}. `state` is any extra pregame-
    knowable context a mechanism's apply() needs (e.g. baseline_min,
    foul_rate_prior for C1); unused when no ACTIVE mechanism matches.

    SHADOW ONLY -- the caller logs both surfaces via shadow_ledger.py; this
    function never persists anything and never feeds a bet path."""
    state = state or {}
    reg = MECHANISM_REGISTRY if registry is None else registry
    family = tick_market_family(payload)
    unconditioned = float(payload["devigged_prob"])
    conditioned = unconditioned
    applied: Optional[str] = None
    for mech in reg:
        if not mech.get("active", False) or mech["market_family"] != family:
            continue
        adj_fn: Callable[[Dict[str, Any]], float] = mech["apply"]
        conditioned = conditioned + float(adj_fn(state))
        applied = mech["name"]
        break  # ponytail: only ever 1 mechanism per family today; revisit if >1 ever active together
    if family in _PROB_FAMILIES:
        conditioned = min(max(conditioned, 0.0), 1.0)
    return {
        "market_family": family,
        "unconditioned_pred": unconditioned,
        "conditioned_pred": conditioned,
        "mechanism_applied": applied,
    }


__all__ = ["MECHANISM_REGISTRY", "condition_tick", "tick_market_family"]
