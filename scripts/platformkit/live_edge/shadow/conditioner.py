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
minutes prior (130559e5, beats baseline OOS, pinball 3.16->3.06).

D1-PREREQS update (2026-07-14): persist_minutes.py (this cycle) now persists
a fitted estimator to data/omni/live_edge/combine/minutes_estimator.pkl. If
present on disk, the registry entry ACTIVATES and predicts minutes via the
persisted model (state must carry the fitted feature_cols, e.g. baseline_min/
foul_rate_prior); if the pkl is absent (or the state doesn't carry the
required features) it stays exactly as before -- conditioned==unconditioned,
no fabricated edge. The OTHER prerequisite (a live player-prop/minutes-market
feed landing on the A1 bus) is still open per feed_probe.py's PROBE.md --
this activation is necessary but arms with zero live ticks until that feed
exists. Do not read an active-but-untriggered entry as an edge claim.

INVARIANTS: stdlib+joblib only (joblib is an existing sklearn dependency
already vendored for minutes_combiner.py); ASCII stdout; <=300 LOC; no $/edge
claims; never writes anything (pure functions -- shadow_ledger.py owns
persistence).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

_ESTIMATOR_CACHE: list = []

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


def _load_c1_estimator():
    """(model, meta) from the persisted C1 artifact, cached once per process
    (module-scope singleton, not functools.lru_cache -- keeps this importable
    without a hashable-args requirement). Fail-open to (None, None) on any
    load error -- a broken pkl must degrade to no-op, never crash a tick."""
    if _ESTIMATOR_CACHE:
        return _ESTIMATOR_CACHE[0]
    try:
        from scripts.platformkit.live_edge.combine import persist_minutes as pm
        result = pm.load_estimator()
    except Exception:  # noqa: BLE001 -- fail-open, no fabricated edge on a load error
        result = (None, None)
    _ESTIMATOR_CACHE.append(result)
    return result


def _c1_minutes_prior_apply(state: Dict[str, Any]) -> float:
    """C1 foul-trouble->minutes prior. Loads the persisted estimator
    (data/omni/live_edge/combine/minutes_estimator.pkl) if present and
    predicts minutes from *state*'s pregame-knowable features (meta's
    feature_cols, e.g. baseline_min/foul_rate_prior); returns the model's
    delta over state["baseline_min"] (the naive market-shaped baseline) so
    the overlay composes the same way every other mechanism does (additive
    delta onto unconditioned). No persisted estimator, or *state* missing a
    required feature -> 0.0 (honest no-op -- identical to the pre-persist
    behavior, never fabricates an adjustment)."""
    model, meta = _load_c1_estimator()
    if model is None or meta is None:
        return 0.0
    cols = meta.get("feature_cols") or []
    baseline = state.get("baseline_min")
    if not cols or baseline is None or any(c not in state for c in cols):
        return 0.0
    try:
        pred = float(model.predict([[state[c] for c in cols]])[0])
    except Exception:  # noqa: BLE001 -- fail-open, never crash a tick on a bad state shape
        return 0.0
    return pred - float(baseline)


def _default_registry() -> List[Dict[str, Any]]:
    """Registry built fresh (active flag reflects real disk state each call,
    self-healing if the estimator is persisted mid-process by another lane)."""
    model, _ = _load_c1_estimator()
    return [
        {
            "name": "c1_minutes_prior",
            "market_family": "ingame.props.minutes",
            "source_claim": "329c45d92e094fba",
            "active": model is not None,
            "apply": _c1_minutes_prior_apply,
        },
    ]


MECHANISM_REGISTRY: List[Dict[str, Any]] = _default_registry()


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
    reg = _default_registry() if registry is None else registry
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
