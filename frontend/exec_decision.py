"""frontend.exec_decision -- the EXECUTION decision layer (tiers, floors, stake).

Pure, network-free helpers that turn one model-vs-market comparison row into an
honest BET / NO-BET decision under the P5 execution contract:

  * Edge is model_prob vs the SHIN-devigged price (devig reuses the vetted
    scripts.platformkit.odds_shop.devig_twoway -- never reimplemented here).
  * EV = model_prob * decimal_odds - 1  (odds_shop.ev_vs_price, verbatim).
  * TIER FLOORS on EV: A >= 0.08, B >= 0.04, C >= 0.02.  When the close we settle
    against is a PROXY (not a true settled close) every floor is raised +0.01, so
    a proxy line must clear a stricter bar before it is a bet.
  * Below the C floor -> NO BET (decision='no_bet', tier=None).
  * Stake is sized in UNITS ONLY -- a flat unit (1.0, for CLV tracking) plus a
    capped quarter-Kelly unit (for bankroll).  There is NO dollar / $ field by
    construction: stake is a unit count, never money.

HONESTY: this is decision support, not a profit claim.  +EV vs a soft/PM book is
a line-shopping execution opportunity, not a beat-the-close edge.  CLV
(better-number-than-close) is the only money-adjacent yardstick and is surfaced
(clv_is_proxy flagged) -- it is computed downstream by the vetted clv_ledger,
never as a $ amount here.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no secrets;
no $ key anywhere; reuse odds_shop devig/EV; never claim a money edge.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# P5 tier EV floors (probability-space EV per 1 unit staked).
TIER_FLOORS: Dict[str, float] = {"A": 0.08, "B": 0.04, "C": 0.02}
# A proxy close (not a true settled close) must clear a stricter bar.
PROXY_FLOOR_BUMP = 0.01
# Quarter-Kelly multiplier and a hard cap (units) so one fat row can't dominate.
_KELLY_FRACTION = 0.25
_KELLY_UNIT_CAP = 4.0
_FLAT_UNIT = 1.0

_DECISION_NOTE = (
    "Units only -- there is no dollar field. flat_unit is the 1u CLV-tracking "
    "stake; kelly_units is capped quarter-Kelly for bankroll. A bet below the "
    "C floor is NO BET. CLV (better-number-than-close) is the only honest "
    "yardstick; no $ edge is claimed."
)


def effective_floors(clv_is_proxy: bool) -> Dict[str, float]:
    """Tier floors for this row, raised by PROXY_FLOOR_BUMP when the close is a proxy."""
    bump = PROXY_FLOOR_BUMP if clv_is_proxy else 0.0
    return {tier: floor + bump for tier, floor in TIER_FLOORS.items()}


def assign_tier(ev: Optional[float], clv_is_proxy: bool = False) -> Optional[str]:
    """Highest tier whose (proxy-adjusted) EV floor *ev* clears, else None (no bet).

    A >= 0.08, B >= 0.04, C >= 0.02 (+0.01 each when clv_is_proxy). EV None / below
    the C floor -> None (the row is NOT a bet).
    """
    if ev is None:
        return None
    try:
        ev_f = float(ev)
    except (TypeError, ValueError):
        return None
    floors = effective_floors(bool(clv_is_proxy))
    for tier in ("A", "B", "C"):  # strongest first
        if ev_f >= floors[tier]:
            return tier
    return None


def quarter_kelly_units(model_prob: Optional[float],
                        decimal_odds: Optional[float]) -> float:
    """Capped quarter-Kelly stake in UNITS (never dollars).

    f* = (p*b - (1-p)) / b with b = odds - 1; stake = 0.25 * f*, floored at 0 (a
    non-positive-EV line is never staked) and capped at _KELLY_UNIT_CAP units.
    """
    if model_prob is None or decimal_odds is None:
        return 0.0
    try:
        p = float(model_prob)
        b = float(decimal_odds) - 1.0
    except (TypeError, ValueError):
        return 0.0
    if b <= 0.0 or not (0.0 < p < 1.0):
        return 0.0
    f_star = (p * b - (1.0 - p)) / b
    if f_star <= 0.0 or math.isnan(f_star):
        return 0.0
    return round(min(_KELLY_FRACTION * f_star, _KELLY_UNIT_CAP), 6)


def _ev_from(model_prob: Optional[float], decimal_odds: Optional[float],
             fallback_ev: Optional[float]) -> Optional[float]:
    """EV via odds_shop.ev_vs_price when we have a price+prob, else the upstream EV.

    Reuses the vetted helper verbatim; on any import/compute miss falls back to the
    EV already carried on the comparison row (never fabricates a new number)."""
    if model_prob is not None and decimal_odds is not None:
        try:
            from scripts.platformkit.odds_shop import ev_vs_price
            return float(ev_vs_price(float(model_prob), float(decimal_odds)))
        except Exception as exc:  # noqa: BLE001 -- fall back to upstream EV
            logger.debug("exec_decision: ev_vs_price failed: %s", exc)
    if fallback_ev is not None:
        try:
            return float(fallback_ev)
        except (TypeError, ValueError):
            return None
    return None


def _fnum(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def decide_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one edge_api comparison row into an execution decision.

    *row* is a build_edge_view comparison entry: it carries model_prob,
    market_prob (Shin-devigged), best_odds, best_book, ev, tier, line,
    clv_is_proxy. We (re)compute EV from the best bettable price, assign a tier
    against the proxy-adjusted floors, and -- only when a tier clears -- size a
    flat unit + capped quarter-Kelly unit. Below the C floor: decision='no_bet'.

    Returns a NEW dict (units only, NO $ field). Never raises.
    """
    model_prob = _fnum(row.get("model_prob"))
    market_prob = _fnum(row.get("market_prob"))
    best_odds = _fnum(row.get("best_odds"))
    clv_is_proxy = bool(row.get("clv_is_proxy", False))

    ev = _ev_from(model_prob, best_odds, _fnum(row.get("ev")))
    tier = assign_tier(ev, clv_is_proxy)
    edge = ((model_prob - market_prob)
            if (model_prob is not None and market_prob is not None) else None)

    out: Dict[str, Any] = {
        "market_type": row.get("market_type"),
        "side": row.get("side"),
        "model_prob": model_prob,
        "market_prob": market_prob,  # SHIN-devigged fair prob (best book)
        "best_book": row.get("best_book", ""),
        "best_odds": best_odds,
        "line": row.get("line"),
        "edge": (round(edge, 6) if edge is not None else None),
        "ev": (round(ev, 6) if ev is not None else None),
        "tier": tier,
        "clv_is_proxy": clv_is_proxy,
        "floors": effective_floors(clv_is_proxy),
    }
    if model_prob is None and (row.get("line") is not None
                               or best_odds is not None):
        # LINE-ONLY / MODEL-ONLY: a real fresh book line exists but the model never
        # priced this market (e.g. total / run-line we do not project). Surface the
        # line honestly -- NEVER fabricate a model_prob, tier, EV, or units. This is
        # the same honesty pattern props use for an unpriced projection.
        out["decision"] = "model_only"
        out["flat_unit"] = 0.0
        out["kelly_units"] = 0.0
        out["stake_units"] = 0.0
        out["reason"] = "fresh line, model does not price this market (line-only)"
    elif tier is None:
        out["decision"] = "no_bet"
        out["flat_unit"] = 0.0
        out["kelly_units"] = 0.0
        out["stake_units"] = 0.0
        out["reason"] = "EV below the C floor (no bet)"
    else:
        kelly = quarter_kelly_units(model_prob, best_odds)
        out["decision"] = "bet"
        out["flat_unit"] = _FLAT_UNIT
        out["kelly_units"] = kelly
        out["stake_units"] = round(_FLAT_UNIT + kelly, 6)
    return out


def decide_game(game: Dict[str, Any]) -> Dict[str, Any]:
    """Apply decide_row to every comparison row of one edge_api game object.

    Returns {game_id, home, away, tipoff, candidates[], best_bets[], info_bets[],
    status}. best_bets keeps only decision=='bet' rows, ranked by EV desc;
    info_bets keeps decision=='model_only' rows (a fresh line the model does not
    price -- e.g. total / run-line -- surfaced honestly with NO tier/units/EV).
    Never raises; a non-ok / empty game yields empty lists.
    """
    if not isinstance(game, dict) or game.get("status") != "ok":
        return {
            "game_id": (game or {}).get("game_id"),
            "status": (game or {}).get("status", "unavailable"),
            "candidates": [], "best_bets": [], "info_bets": [],
        }
    candidates = [decide_row(r) for r in (game.get("comparison") or [])]
    best = [c for c in candidates if c.get("decision") == "bet"]
    best.sort(key=lambda c: (c.get("ev") if c.get("ev") is not None else -1.0),
              reverse=True)
    info = [c for c in candidates if c.get("decision") == "model_only"]
    info.sort(key=lambda c: (str(c.get("market_type") or ""),
                             str(c.get("side") or "")))
    return {
        "game_id": game.get("game_id"),
        "home": game.get("home"),
        "away": game.get("away"),
        "tipoff": game.get("tipoff"),
        "status": "ok",
        "candidates": candidates,
        "best_bets": best,
        "info_bets": info,
    }


def decision_note() -> str:
    """The honest units-only / no-bet / CLV note carried on every decision view."""
    return _DECISION_NOTE


__all__ = [
    "TIER_FLOORS",
    "PROXY_FLOOR_BUMP",
    "effective_floors",
    "assign_tier",
    "quarter_kelly_units",
    "decide_row",
    "decide_game",
    "decision_note",
]
