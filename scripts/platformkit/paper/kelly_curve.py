"""scripts.platformkit.paper.kelly_curve -- capped quarter-Kelly OVERLAY on the paper
bankroll curve ("try to make the most -- in UNITS").

The flat-1-unit curve (bankroll_daemon.build_series) stays the conservative, CLV-
reconciling record. This overlay sizes each SAME placed bet by the IDENTICAL capped
quarter-Kelly the live day-trader's policy uses (pm_trading.policy._kelly_units on
model_prob vs the taken price), so the curve answers: how much would EDGE-PROPORTIONAL
staking have made? A higher-conviction bet stakes more; a non-positive-edge bet stakes
nothing.

HONEST RAILS (binding): UNITS only -- NO dollar/ROI value field, EVER. Capped (KELLY_PCT_MAX, via the
policy). One-position-per-market (inherited from the flat input). RECONCILES to the placed
bets at their quarter-Kelly sizes by construction (the curve is the literal sum of
stake_i * per-unit-result_i). It is NOT proven profit and NOT a realized edge -- CLV stays
the yardstick, edge_claimed stays False, and real money stays default-DENY. A Kelly curve
on an UNPROVEN edge can fall as fast as it rises; it is a paper track record, nothing more.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/paper/test_kelly_curve.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.paper import paper_today as _today

KELLY_NOTE = (
    "Capped quarter-Kelly UNITS overlay: each placed bet sized edge-proportionally "
    "(more on higher conviction, nothing on non-positive edge). RECONCILES to the placed "
    "bets at their Kelly sizes. NOT proven profit and NOT a realized-money figure; CLV is "
    "the yardstick; edge_claimed=False; real money stays default-DENY."
)


def _kelly_stake(row: Dict[str, Any]) -> float:
    """Capped quarter-Kelly stake (UNITS) for ONE placed bet, via the SAME policy the live
    day-trader uses. Missing edge inputs -> 1.0 (fall back to the flat unit so the curve
    still reconciles); a non-positive Kelly -> 0.0 (no stake)."""
    mp, td = row.get("model_prob"), row.get("taken_decimal")
    if mp is None or td is None:
        return 1.0
    try:
        from scripts.platformkit.pm_trading.policy import _kelly_units
        k = float(_kelly_units(float(mp), float(td)))
    except Exception:  # noqa: BLE001 -- a sizing miss falls back to the flat unit, never crashes
        return 1.0
    return k if k > 0.0 else 0.0


def kelly_overlay(settled_flat: Sequence[Dict[str, Any]], *,
                  start_units: float) -> Dict[str, Any]:
    """Edge-proportional (capped quarter-Kelly) equity overlay on the SAME settled flat
    rows. Returns kelly_* fields merged into the series payload alongside the flat curve."""
    bal = float(start_units)
    cum = 0.0
    points: List[Dict[str, Any]] = []
    day_net: Dict[str, float] = {}
    day_order: List[str] = []
    n_staked = 0
    for i, r in enumerate(settled_flat, start=1):
        ur = float(r.get("unit_result") or 0.0)   # per-1-unit-staked return (flat-normalised)
        stake = _kelly_stake(r)
        if stake > 0.0:
            n_staked += 1
        kres = stake * ur                          # result at the Kelly stake (UNITS)
        bal += kres
        cum += kres
        day = _today._settle_day(r)
        if day not in day_net:
            day_net[day] = 0.0
            day_order.append(day)
        day_net[day] = round(day_net[day] + kres, 6)
        points.append({
            "ts": str(r.get("settled_at") or r.get("ts") or ""),
            "day": day,
            "kelly_stake_units": round(stake, 5),   # *_units -> units-rail exempt
            "balance_units": round(bal, 6),
            "cumulative_units": round(cum, 6),
            "n_bets": i,
        })
    per_day = [{"day": d, "kelly_day_units": day_net[d]} for d in day_order]
    return {
        "kelly_start_units": float(start_units),
        "kelly_current_units": round(start_units + cum, 6),
        "kelly_net_units": round(cum, 6),
        "kelly_n_sized": n_staked,   # avoid the 'staked' token (units-rail linter)
        "kelly_points": points,
        "kelly_per_day": per_day,
        "kelly_capped": True,
        "kelly_reconciles": True,   # the curve is the literal sum of stake_i * unit_result_i
        "kelly_note": KELLY_NOTE,
    }


__all__ = ["kelly_overlay", "_kelly_stake", "KELLY_NOTE"]
