"""scripts.platformkit.execution.ingame_exec_gate -- in-game placement gate helper.

Composes the expected-CLV gate (execution.expected_clv_gate) and an optional
adverse-price-drift check into ONE suppress-only decision for
inplay_daytrader.on_tick's ENTER path. SUPPRESS-ONLY: it can only turn a
would-be "bet" into "no_bet", never manufacture a bet or loosen the edge/
liquidity/freshness gates already passed upstream. PAPER / UNITS only.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from scripts.platformkit.execution import expected_clv_gate as _gate
from scripts.platformkit.execution.thresholds import (
    INGAME_EXPECTED_CLV_MIN_PCT, INGAME_MAX_DRIFT_PCT,
)


def _drift_pct(signal_decimal: Optional[float], fresh_decimal: Optional[float]) -> Optional[float]:
    """Percent change in obtainable decimal from signal time to a fresher observation.

    Negative = the price got worse (adverse) since the signal was computed. None if
    no fresher observation was supplied (the common case: one tick, one price) --
    never fabricates a drift figure from a single observation.
    """
    if signal_decimal is None or fresh_decimal is None:
        return None
    try:
        sd, fd = float(signal_decimal), float(fresh_decimal)
    except (TypeError, ValueError):
        return None
    if sd <= 0.0:
        return None
    return (fd - sd) / sd * 100.0


def evaluate_placement(ev: Dict[str, Any], tick: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate the expected-CLV + drift gates for the chosen-side ENTER *ev* dict.

    *ev* is inplay_edge_signal.evaluate's return dict. Mirrors clv.best_price's own
    expected_clv_pct convention (fair vs the price actually taken): here the FAIR
    estimate is the calibrated model probability (bet_model_prob) -- the model IS
    the fair-value estimate, the devigged market price is merely what it is
    compared against upstream -- and the TAKEN price is the obtainable decimal for
    the chosen side. This is mathematically ev*100 restated as a percent, gated
    against a pre-registered floor independent of the proxy-adjusted tier floor
    already applied upstream (never loosens it; only an additional, lower-set net).
    *tick* may optionally carry "fresh_obtainable_decimal": a fresher price
    observed for the same side at/near placement time; when absent (today's
    default -- no fresher-price source is wired), drift_pct is None and drift
    never suppresses.

    Returns {"suppress": bool, "reason": Optional[str], "exec_gate": dict} where
    exec_gate is expected_clv_gate.gate()'s dict plus a "drift_pct" field.
    """
    taken_decimal = ev.get("obtainable_decimal")
    fair_prob = ev.get("bet_model_prob")
    g = _gate.gate(taken_decimal=taken_decimal, fair_prob=fair_prob,
                   threshold_pct=INGAME_EXPECTED_CLV_MIN_PCT)
    drift = _drift_pct(taken_decimal, tick.get("fresh_obtainable_decimal"))
    g["drift_pct"] = drift
    if drift is not None and drift <= -INGAME_MAX_DRIFT_PCT:
        return {"suppress": True, "reason": "drift", "exec_gate": g}
    if not g.get("passed", False):
        return {"suppress": True, "reason": "expected_clv_below_floor", "exec_gate": g}
    return {"suppress": False, "reason": None, "exec_gate": g}


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    ev_ok = {"obtainable_decimal": 1.818, "bet_model_prob": 0.80}  # big model edge
    r_ok = evaluate_placement(ev_ok, {})
    assert r_ok["suppress"] is False and r_ok["exec_gate"]["drift_pct"] is None

    ev_low = {"obtainable_decimal": 1.818, "bet_model_prob": 0.55}  # tiny model edge
    r_low = evaluate_placement(ev_low, {})
    assert r_low["suppress"] is True and r_low["reason"] == "expected_clv_below_floor"

    r_drift = evaluate_placement(ev_ok, {"fresh_obtainable_decimal": 1.60})
    assert r_drift["suppress"] is True and r_drift["reason"] == "drift"
    print("ingame_exec_gate self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["evaluate_placement"]
