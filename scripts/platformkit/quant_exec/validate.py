"""scripts.platformkit.quant_exec.validate -- ONE auditable bet-validation object.

TRANSPARENCY ONLY. This builds a single, auditable bet-validation verdict for the
quant Execution API. It makes NO predictive claim and computes NO new math: every
number is produced by a vetted, already-audited helper, reused VERBATIM:

  * tier         -- frontend.exec_decision.assign_tier (P5 EV floors, proxy bump).
  * units        -- frontend.exec_decision.quarter_kelly_units (capped, variance-
                    aware quarter-Kelly) + a flat 1u CLV-tracking stake.
  * devig        -- scripts.platformkit.odds_shop.devig_twoway (vetted Shin solver).
  * EV           -- scripts.platformkit.odds_shop.ev_vs_price (p*odds - 1).
  * CLV          -- scripts.platformkit.quant.clv_core.audit_clv (the ONE sign-
                    audited yardstick over the two verified compute paths).

HONESTY (enforced by shape and by the rails):
  * Most verdicts are no_bet / matches-the-close -- that is a SUCCESS, not a miss.
    A row whose model prob sits on the devigged close clears no tier floor and is
    decision='no_bet'; we surface it as such, never inflated.
  * gate_proven defaults FALSE. It flips True ONLY when handed a VERIFIED eval-gate
    token (a truthy, structurally-valid proof handle). CLV vs_close stays UNPROVEN;
    this module never upgrades anything to vs_close and never self-stamps a flag.
  * edge = model_prob - devigged_close. EV vs the BEST bettable price is an
    EXECUTION number, never a beat-the-close edge. No $ edge is claimed.
  * NO $/roi/pnl/bankroll/stake_dollars field anywhere -- units/probability only.

Build invariants: additive; <=300 LOC; ASCII only; reuse, never reimplement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from frontend.exec_decision import assign_tier, quarter_kelly_units

logger = logging.getLogger(__name__)

_FLAT_UNIT = 1.0

__all__ = ["BetValidation", "build_validation", "is_verified_gate_token"]


def is_verified_gate_token(token: Any) -> bool:
    """True ONLY for a structurally-valid VERIFIED eval-gate proof handle.

    A proof token is accepted iff it is a mapping that explicitly carries
    {"verified": True, "passed": True} (the eval-gate's own pass stamp). Anything
    else -- None, a bare bool, a string, a partial/absent dict -- is REJECTED, so
    gate_proven defaults FALSE and can never be flipped by a truthy-but-unverified
    value. This module NEVER mints a token; it only inspects one handed to it.
    """
    if not isinstance(token, dict):
        return False
    return token.get("verified") is True and token.get("passed") is True


def _fnum(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _devigged_close(close_home: Optional[float], close_away: Optional[float],
                    side: str) -> Optional[float]:
    """Shin-devigged fair prob of *side* from the two-way closing prices.

    Reuses odds_shop.devig_twoway VERBATIM. home->leg 0, away->leg 1. Returns None
    on a one-sided market or any devig miss (we never infer the missing side).
    """
    if close_home is None or close_away is None:
        return None
    try:
        from scripts.platformkit.odds_shop import devig_twoway
        fair_home, fair_away = devig_twoway(close_home, close_away)
    except Exception as exc:  # noqa: BLE001 -- devig must never sink a verdict
        logger.debug("validate: devig_twoway failed: %s", exc)
        return None
    s = side.strip().lower()
    fair = fair_home if s == "home" else fair_away if s == "away" else None
    if fair is None or not (0.0 < fair < 1.0):
        return None
    return float(fair)


def _ev(model_prob: Optional[float], best_decimal: Optional[float]) -> Optional[float]:
    """EV per 1u at the best bettable price via odds_shop.ev_vs_price (verbatim)."""
    if model_prob is None or best_decimal is None:
        return None
    try:
        from scripts.platformkit.odds_shop import ev_vs_price
        return float(ev_vs_price(float(model_prob), float(best_decimal)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("validate: ev_vs_price failed: %s", exc)
        return None


@dataclass(frozen=True)
class BetValidation:
    """One auditable bet-validation verdict. NO $/roi/pnl field -- units only.

    side/market    -- what is being validated.
    model_prob     -- the calibrated model probability for *side*.
    devigged_close -- Shin-devigged fair close prob for *side* (or None).
    edge           -- model_prob - devigged_close (None if either is missing).
    ev             -- EV per 1u at the best bettable price (None if missing).
    tier           -- P5 tier (A/B/C) or None (None => decision is no_bet).
    decision       -- 'bet' iff a tier clears, else 'no_bet'.
    flat_unit/kelly_units/stake_units -- UNIT-space stake (never dollars).
    clv            -- the sign-audited clv_core record (or None when not gradeable).
    gate_proven    -- FALSE unless a VERIFIED eval-gate token was supplied.
    """
    side: str
    market: str
    model_prob: Optional[float]
    devigged_close: Optional[float]
    edge: Optional[float]
    ev: Optional[float]
    tier: Optional[str]
    decision: str
    flat_unit: float
    kelly_units: float
    stake_units: float
    clv: Optional[Dict[str, Any]]
    gate_proven: bool
    clv_is_proxy: bool
    note: str = field(default="")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "market": self.market,
            "model_prob": self.model_prob,
            "devigged_close": self.devigged_close,
            "edge": self.edge,
            "ev": self.ev,
            "tier": self.tier,
            "decision": self.decision,
            "flat_unit": self.flat_unit,
            "kelly_units": self.kelly_units,
            "stake_units": self.stake_units,
            "clv": self.clv,
            "gate_proven": self.gate_proven,
            "clv_is_proxy": self.clv_is_proxy,
            "units": "probability",  # explicit: never dollars
            "edge_claimed": False,
            "real_money_enabled": False,
            "note": self.note,
        }


_MATCHES_CLOSE_NOTE = (
    "no_bet: model prob sits on the devigged close -- a SUCCESS (we match the "
    "efficient close), not a miss. Units only; no $ edge claimed."
)
_BET_NOTE = (
    "Execution candidate vs the best bettable price (line-shopping), NOT a "
    "beat-the-close edge. Units only; CLV is the only honest yardstick."
)


def build_validation(
    *,
    side: str,
    market: str,
    model_prob: Any,
    best_decimal: Any = None,
    close_home: Any = None,
    close_away: Any = None,
    clv_is_proxy: bool = True,
    clv_record: Optional[Dict[str, Any]] = None,
    gate_token: Any = None,
) -> BetValidation:
    """Build ONE auditable bet-validation verdict (units only, NO $ field).

    Reuses assign_tier + quarter_kelly_units + odds_shop devig/EV + (optionally) a
    precomputed clv_core record. Steps:
      1. devig the two-way close -> devigged_close for *side* (Shin, verbatim).
      2. edge = model_prob - devigged_close.
      3. EV per 1u at the best bettable price (odds_shop.ev_vs_price).
      4. tier = assign_tier(ev, clv_is_proxy) -- proxy floors are stricter.
      5. when a tier clears: stake = flat 1u + capped quarter-Kelly units; else
         decision='no_bet' with 0 units (matches-the-close is the common, honest
         outcome).
      6. gate_proven = is_verified_gate_token(gate_token) -- FALSE by default.

    *clv_record* is a clv_core.ClvAudit.as_record() dict if the caller already graded
    CLV (we never recompute it here). Never raises.
    """
    side_s = str(side)
    mp = _fnum(model_prob)
    bd = _fnum(best_decimal)
    ch = _fnum(close_home)
    ca = _fnum(close_away)
    proxy = bool(clv_is_proxy)

    devig = _devigged_close(ch, ca, side_s)
    edge = (mp - devig) if (mp is not None and devig is not None) else None
    ev = _ev(mp, bd)
    tier = assign_tier(ev, proxy)
    gate_proven = is_verified_gate_token(gate_token)

    if tier is None:
        decision = "no_bet"
        flat = 0.0
        kelly = 0.0
        stake = 0.0
        note = _MATCHES_CLOSE_NOTE
    else:
        decision = "bet"
        flat = _FLAT_UNIT
        kelly = quarter_kelly_units(mp, bd)
        stake = round(_FLAT_UNIT + kelly, 6)
        note = _BET_NOTE

    return BetValidation(
        side=side_s,
        market=str(market),
        model_prob=mp,
        devigged_close=devig,
        edge=(round(edge, 6) if edge is not None else None),
        ev=(round(ev, 6) if ev is not None else None),
        tier=tier,
        decision=decision,
        flat_unit=flat,
        kelly_units=kelly,
        stake_units=stake,
        clv=clv_record,
        gate_proven=gate_proven,
        clv_is_proxy=proxy,
        note=note,
    )
