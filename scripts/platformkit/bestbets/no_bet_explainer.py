"""scripts.platformkit.bestbets.no_bet_explainer -- BBQ5-4 honest no-bet surface.

Divergences below the per-sport EV floor are silently dropped by the pipeline,
giving the UI no way to tell the user WHY a candidate was not a bet.  This
module is the pure explainer layer: given a candidate and the floor config it
returns a plain dict with the decision, tier, ev, floor_used, and a human-
readable reason string.

Design rails (binding):
  * PURE -- no IO, no network, no global state mutation.  Same inputs -> same out.
  * NEVER imports bestbets_compute (no circular dep).
  * NEVER fabricates an edge to clear the floor.
  * NEVER invents a dollar/roi/pnl/profit/bankroll/usd key.
  * ev is EV-per-unit (p*odds - 1), not a $ amount.
  * decimal_odds None (offseason/UNAVAILABLE) -> decision:no_bet, reason:UNAVAILABLE.
  * Empty / garbage inputs -> decision:no_bet, never raises.
  * reason string contains enough info for the UI: what floor was used + what ev is.
  * <=300 LOC; ASCII only; stdlib + repo-internal only.

Return schema (all keys always present):
  {
    "decision":   "bet" | "no_bet",
    "tier":       "A" | "B" | "C" | None,
    "ev":         float | None,          # EV-per-unit; None when undetermined
    "floor_used": float | None,          # the C-floor for the sport; None when undetermined
    "reason":     str,                   # human-readable; NEVER mentions $ / profit
  }

Per-file test: tests/platformkit/bestbets/test_no_bet_explainer.py
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:  # package import (normal runtime)
    from scripts.platformkit.bestbets.floor_config import get_floors
    from scripts.platformkit.odds_shop import ev_vs_price
except ImportError:  # pragma: no cover  (hermetic sibling import fallback)
    from floor_config import get_floors  # type: ignore
    from odds_shop import ev_vs_price  # type: ignore


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> Optional[float]:
    """Return float(val) or None on any error (including NaN check)."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _pick_tier(ev: float, floors: Dict[str, float]) -> Optional[str]:
    """Return the highest tier whose floor ev clears, or None below C floor.

    Scans weakest->strongest: C, B, A.  Returns the highest matching label.
    """
    label: Optional[str] = None
    for name in ("C", "B", "A"):
        if ev >= floors[name]:
            label = name
    return label


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain(
    model_prob: Any,
    market_prob: Any,
    decimal_odds: Any,
    sport: str = "nba",
    *,
    clv_is_proxy: bool = False,
) -> Dict[str, Any]:
    """Return an explanation dict for a candidate bet.

    Parameters
    ----------
    model_prob:
        Model probability for the over/yes side (0 < p < 1).
    market_prob:
        Market (devigged) probability for the same side.  Accepted for
        interface symmetry; not used to compute EV (ev_vs_price uses
        model_prob + decimal_odds).
    decimal_odds:
        Best available decimal price.  None -> UNAVAILABLE (offseason).
    sport:
        Canonical sport slug (case-insensitive).  Used to look up the
        per-sport floor via floor_config.get_floors.
    clv_is_proxy:
        When True, every EV floor is raised by EV_PROXY_PENALTY from
        floor_config / policy (same contract as prop_tier.tier_prop).
        Default False so the explainer works for both prop and game lines.

    Returns
    -------
    Dict with keys: decision, tier, ev, floor_used, reason.
    No $, roi, pnl, profit, bankroll, usd, dollar key is ever present.
    """
    try:
        return _explain_inner(model_prob, market_prob, decimal_odds, sport,
                              clv_is_proxy=clv_is_proxy)
    except Exception:  # noqa: BLE001
        return _no_bet(ev=None, floor_used=None,
                       reason="explain: unexpected error; returning no_bet")


def _explain_inner(
    model_prob: Any,
    market_prob: Any,
    decimal_odds: Any,
    sport: str,
    *,
    clv_is_proxy: bool,
) -> Dict[str, Any]:
    """Implementation -- called from explain() which catches all exceptions."""

    # ------------------------------------------------------------------
    # 1. Unavailable odds (offseason / no quote)
    # ------------------------------------------------------------------
    if decimal_odds is None:
        return _no_bet(ev=None, floor_used=None,
                       reason="UNAVAILABLE: decimal_odds is None (offseason/no quote); "
                              "no ev computed; not a bet")

    # ------------------------------------------------------------------
    # 2. Validate inputs -- garbage -> no_bet, never raise
    # ------------------------------------------------------------------
    p_model = _safe_float(model_prob)
    if p_model is None or not (0.0 < p_model < 1.0):
        return _no_bet(ev=None, floor_used=None,
                       reason="no_bet: model_prob invalid or out of (0,1) range")

    odds = _safe_float(decimal_odds)
    if odds is None or odds <= 1.0:
        return _no_bet(ev=None, floor_used=None,
                       reason="no_bet: decimal_odds invalid or <= 1.0 (not a valid price)")

    # market_prob validation is lenient -- it is display-only here.
    # We do not use it to compute EV; just accept or ignore.

    # ------------------------------------------------------------------
    # 3. Compute EV (EV-per-unit, not $)
    # ------------------------------------------------------------------
    ev = ev_vs_price(p_model, odds)   # p*odds - 1

    # ------------------------------------------------------------------
    # 4. Look up per-sport floors
    # ------------------------------------------------------------------
    raw_floors = get_floors(sport)  # {"A": float, "B": float, "C": float}

    # Apply proxy penalty to every floor when CLV will be graded against a
    # proxy close (same contract as prop_tier and pm_trading.policy).
    try:
        from scripts.platformkit.pm_trading.policy import EV_PROXY_PENALTY
    except ImportError:  # pragma: no cover
        EV_PROXY_PENALTY = 0.01  # known constant; local fallback

    bump = EV_PROXY_PENALTY if clv_is_proxy else 0.0
    floors = {t: raw_floors[t] + bump for t in ("A", "B", "C")}
    c_floor = floors["C"]  # lowest floor; used in the reason string

    # ------------------------------------------------------------------
    # 5. Assign tier (or None below C floor)
    # ------------------------------------------------------------------
    t = _pick_tier(ev, floors)

    if t is None:
        # Below the C floor for this sport
        return _no_bet(
            ev=ev,
            floor_used=c_floor,
            reason=(
                "no_bet: ev {ev:.4f} is below {sport} C floor {floor:.4f}"
                "{proxy_note}; divergence exists but does not clear the "
                "calibration threshold".format(
                    ev=ev,
                    sport=sport.upper() if sport else "UNKNOWN",
                    floor=c_floor,
                    proxy_note=" (proxy-adjusted)" if clv_is_proxy else "",
                )
            ),
        )

    # Clears the floor -> bet
    return {
        "decision": "bet",
        "tier": t,
        "ev": round(ev, 6),
        "floor_used": round(c_floor, 6),
        "reason": (
            "bet tier {tier}: ev {ev:.4f} clears {sport} {tier} floor "
            "{floor:.4f}{proxy_note}; calibrated divergence is bettable".format(
                tier=t,
                ev=ev,
                sport=sport.upper() if sport else "UNKNOWN",
                floor=floors[t],
                proxy_note=" (proxy-adjusted)" if clv_is_proxy else "",
            )
        ),
    }


def _no_bet(
    ev: Optional[float],
    floor_used: Optional[float],
    reason: str,
) -> Dict[str, Any]:
    """Construct a canonical no_bet result dict."""
    return {
        "decision": "no_bet",
        "tier": None,
        "ev": round(ev, 6) if ev is not None else None,
        "floor_used": round(floor_used, 6) if floor_used is not None else None,
        "reason": reason,
    }


__all__ = ["explain"]
