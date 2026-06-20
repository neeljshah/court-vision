"""scripts.platformkit.quant.risk_units -- a UNIT-space portfolio RISK view.

DESCRIPTIVE risk control, NOT a profit/safety guarantee. This module projects a
set of OPEN paper bets into a small, units-only risk picture a desk can read:

  * total_exposure_units   -- the naive sum of staked units across open legs.
  * joint_exposure_units   -- a correlation-ADJUSTED effective exposure that is
                              <= the naive sum: same-game legs are treated as
                              correlated (they do not diversify), cross-game legs
                              as ~independent (they do). The haircut is why
                              joint_exposure_units < total_exposure_units whenever
                              two legs share a game_id.
  * portfolio_variance     -- variance of the units-weighted outcome, built from
                              each leg's Bernoulli model variance p*(1-p) and the
                              same same-game-correlated / cross-game-independent
                              covariance structure. UNITS-squared, never dollars.
  * risk_of_ruin           -- a model-CONDITIONAL probability in [0,1] framed as a
                              STAT, never a safety promise: P(cumulative unit
                              outcome <= -ruin_units) under a normal approximation
                              to the portfolio's units-weighted edge + variance.
                              It is a descriptive number about THIS book under THE
                              MODEL'S OWN probabilities, not a guarantee of capital.

INVARIANTS (honesty rails):
  * UNITS / probability only. NO $/dollar/roi/pnl/profit/bankroll field ANYWHERE
    -- not as a key, not as a value-label. risk_of_ruin / variance are unit-space
    risk numbers, never expected money.
  * Reuses frontend.exec_decision sizing (quarter_kelly_units) when a leg carries
    no explicit stake -- never forks the sizing math.
  * Reuses scripts.platformkit.quant.clv_core only as the units-only door (no new
    CLV math here).
  * Pure, network-free, read-only. NEVER raises -- a malformed leg is skipped.
  * Calibration, not edge: this is a risk VIEW, it claims no edge and sizes no
    real-money action (executed stays False upstream).

Build invariants: additive; <=300 LOC; ASCII only; reuse, never reimplement.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Reuse the vetted units-only sizing -- never fork it.
from frontend.exec_decision import quarter_kelly_units

NOTE = (
    "calibration, not edge; units only (no money field anywhere); risk_of_ruin and "
    "variance are DESCRIPTIVE unit-space stats under the model's own probabilities, "
    "never a safety guarantee"
)

# Same-game legs are treated as fully correlated (they do not diversify). A future
# refinement could read a coherent-sim joint prob; the conservative ceiling here is
# rho=1 within a game, rho=0 across games -- which keeps joint <= naive sum.
_SAME_GAME_RHO = 1.0


def _fnum(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class _Leg:
    """One normalized open leg in units-space. NO $ field."""
    game_id: str
    units: float          # staked units (>= 0)
    p: Optional[float]     # model probability of the backed side (for variance/RoR)
    edge: Optional[float]  # per-unit edge (model_prob - market_prob), if known


def _stake_units(leg: Dict[str, Any]) -> float:
    """Units staked on a leg: explicit stake_units/flat_unit+kelly, else sized.

    Reuses exec_decision.quarter_kelly_units when no explicit stake is present so
    the risk view never invents a sizing rule of its own. Never negative.
    """
    for key in ("stake_units", "units"):
        u = _fnum(leg.get(key))
        if u is not None:
            return max(0.0, u)
    flat = _fnum(leg.get("flat_unit"))
    kelly = _fnum(leg.get("kelly_units"))
    if flat is not None or kelly is not None:
        return max(0.0, (flat or 0.0) + (kelly or 0.0))
    # last resort: size from model_prob + best_odds via the vetted sizing helper.
    p = _fnum(leg.get("model_prob"))
    odds = _fnum(leg.get("best_odds")) or _fnum(leg.get("taken_decimal"))
    sized = quarter_kelly_units(p, odds)
    flat_default = 1.0 if sized > 0.0 else 0.0
    return max(0.0, flat_default + sized)


def _normalize(open_bets: Sequence[Dict[str, Any]]) -> List[_Leg]:
    legs: List[_Leg] = []
    for b in open_bets or []:
        if not isinstance(b, dict):
            continue
        try:
            gid = str(b.get("game_id", b.get("event_id", b.get("id", "")))) or "_"
            units = _stake_units(b)
            if units <= 0.0:
                continue
            p = _fnum(b.get("model_prob"))
            if p is not None and not (0.0 < p < 1.0):
                p = None
            edge = _fnum(b.get("edge"))
            legs.append(_Leg(game_id=gid, units=units, p=p, edge=edge))
        except Exception:  # noqa: BLE001 -- a malformed leg is skipped, never raised
            continue
    return legs


def total_exposure_units(open_bets: Sequence[Dict[str, Any]]) -> float:
    """Naive sum of staked UNITS across open legs (no correlation haircut)."""
    return round(sum(l.units for l in _normalize(open_bets)), 6)


def joint_exposure_units(open_bets: Sequence[Dict[str, Any]]) -> float:
    """Correlation-adjusted effective exposure in UNITS -- always <= naive sum.

    Same-game legs (shared game_id) are correlated (rho=1) so they aggregate by
    sum-then-quadrature with the rest; cross-game legs are independent so they add
    in quadrature. The effective exposure is the L2-combination of per-game block
    sums, which is <= the arithmetic sum (equality only with a single game). This
    is why joint_exposure_units < total_exposure_units whenever >=2 games appear.
    """
    legs = _normalize(open_bets)
    if not legs:
        return 0.0
    by_game: Dict[str, float] = {}
    for l in legs:
        by_game[l.game_id] = by_game.get(l.game_id, 0.0) + l.units
    # within a game: correlated -> the block exposure is the plain sum of its legs.
    # across games: independent -> combine block sums in quadrature (diversifies).
    joint = math.sqrt(sum(s * s for s in by_game.values()))
    naive = sum(by_game.values())
    return round(min(joint, naive), 6)


def portfolio_variance(open_bets: Sequence[Dict[str, Any]]) -> float:
    """Variance (UNITS^2) of the units-weighted outcome under the model's own p.

    Each leg contributes (units^2)*p*(1-p). Same-game legs add a positive
    covariance term (rho=_SAME_GAME_RHO); cross-game covariance is ~0. Legs with
    no usable p contribute 0 variance (never fabricated). Returns 0.0 on an empty
    or p-less book.
    """
    legs = [l for l in _normalize(open_bets) if l.p is not None]
    if not legs:
        return 0.0
    # per-leg Bernoulli variance contribution in unit-weighted space.
    var = 0.0
    for l in legs:
        sd = l.units * math.sqrt(l.p * (1.0 - l.p))  # type: ignore[arg-type]
        var += sd * sd
    # same-game covariance: 2*rho*sd_i*sd_j for each correlated pair in a game.
    by_game: Dict[str, List[_Leg]] = {}
    for l in legs:
        by_game.setdefault(l.game_id, []).append(l)
    for group in by_game.values():
        if len(group) < 2:
            continue
        sds = [g.units * math.sqrt(g.p * (1.0 - g.p)) for g in group]  # type: ignore
        for i in range(len(sds)):
            for j in range(i + 1, len(sds)):
                var += 2.0 * _SAME_GAME_RHO * sds[i] * sds[j]
    return round(var, 8)


def risk_of_ruin(open_bets: Sequence[Dict[str, Any]],
                 ruin_units: float = 10.0) -> float:
    """Model-conditional risk-of-ruin in [0,1] -- a DESCRIPTIVE stat, never a promise.

    Normal-approx P(units-weighted outcome <= -ruin_units) under the model's own
    edge + portfolio variance. mu = sum(units * edge_per_unit) (the expected unit
    drift the MODEL believes); sigma = sqrt(portfolio_variance). With sigma==0 (no
    usable p) it returns 1.0 if mu <= -ruin_units else 0.0. ruin_units must be
    positive. This is a probability statement about THIS book under THE MODEL, not
    a guarantee of capital safety.
    """
    try:
        ruin = abs(float(ruin_units))
    except (TypeError, ValueError):
        return 0.0
    legs = _normalize(open_bets)
    if not legs or ruin <= 0.0:
        return 0.0
    mu = sum(l.units * (l.edge if l.edge is not None else 0.0) for l in legs)
    var = portfolio_variance(open_bets)
    sigma = math.sqrt(var) if var > 0.0 else 0.0
    threshold = -ruin
    if sigma <= 0.0:
        return 1.0 if mu <= threshold else 0.0
    z = (threshold - mu) / sigma
    # standard-normal CDF via erf (stdlib only).
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return round(min(1.0, max(0.0, cdf)), 6)


def portfolio_risk(open_bets: Sequence[Dict[str, Any]],
                   ruin_units: float = 10.0) -> Dict[str, Any]:
    """The full units-only portfolio risk view. NEVER raises. NO $ key.

    Returns {n_legs, n_games, total_exposure_units, joint_exposure_units,
    diversification_units, portfolio_variance_units2, portfolio_sd_units,
    risk_of_ruin, ruin_units, note, units}. joint_exposure_units is <= total by
    construction; diversification_units is the (non-negative) haircut.
    """
    legs = _normalize(open_bets)
    total = total_exposure_units(open_bets)
    joint = joint_exposure_units(open_bets)
    var = portfolio_variance(open_bets)
    return {
        "n_legs": len(legs),
        "n_games": len({l.game_id for l in legs}),
        "total_exposure_units": total,
        "joint_exposure_units": joint,
        "diversification_units": round(max(0.0, total - joint), 6),
        "portfolio_variance_units2": var,
        "portfolio_sd_units": round(math.sqrt(var) if var > 0.0 else 0.0, 6),
        "risk_of_ruin": risk_of_ruin(open_bets, ruin_units=ruin_units),
        "ruin_units": abs(float(ruin_units)) if ruin_units is not None else 0.0,
        "note": NOTE,
        "units": "units",
    }


__all__ = [
    "total_exposure_units",
    "joint_exposure_units",
    "portfolio_variance",
    "risk_of_ruin",
    "portfolio_risk",
]
