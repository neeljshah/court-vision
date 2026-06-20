"""policy.py -- PURE tiered bet policy (no IO, no placement, no network).

Given an edge's EV (and, when sizing, the model probability + the price you can
actually get), this module answers two questions and NOTHING else:

  1. tier(...)        -> which evidence/EV tier is this, if any?  ("A"/"B"/"C"/None)
  2. stake_units(...) -> how many UNITS to stake, under the LOCKED dual-staking
                         decision: BOTH a flat unit (-> the honest CLV record) AND
                         a quarter-Kelly fraction (-> the bankroll curve).

DESIGN RAILS (binding):
  * PURE. No file/network IO, no placement, no global state. Same inputs ->
    same outputs. The integration agent calls this to STAMP tier + stakes onto a
    row; it does not move money. The real-money gate (separate) is decision-only
    and a human flip is always required.
  * EV is EV-per-1-unit-staked = p*odds - 1 (the same definition as
    scripts.platformkit.odds_shop.ev_vs_price). NOT a dollar amount.
  * Kelly is NEVER re-derived here. The quarter-Kelly fraction and its hard cap
    are IMPORTED from risk.py (which imports them from betting_portfolio), so the
    one source of truth cannot drift.
  * UNITS only -- there is NO $/dollar field anywhere in the return. No edge /
    ROI is claimed; CLV is the only honest yardstick (computed downstream).

EV FLOORS (pre-registered constants -- documented, not tuned per slate):
  Tier A: EV >= EV_FLOOR_A   strongest measured edge.
  Tier B: EV >= EV_FLOOR_B   solid edge.
  Tier C: EV >= EV_FLOOR_C   marginal but bettable.
  EV <  EV_FLOOR_C -> None   below floor: NO bet.

CLV-proxy handling: when the close we will settle against is a PROXY (not a true
settled close), the evidence is weaker, so we REQUIRE a higher EV by adding
EV_PROXY_PENALTY to every floor. The flag is surfaced, never hidden.

Build only under scripts/platformkit/; <=300 LOC; ASCII only; no secrets.
"""
from __future__ import annotations

from typing import Dict, Optional

try:  # package import (normal runtime)
    from .risk import KELLY_FRACTION, KELLY_PCT_MAX, kelly_fraction_binary
    from .venues.base import Side
except ImportError:  # pragma: no cover  (flat sibling import for hermetic tests)
    from risk import KELLY_FRACTION, KELLY_PCT_MAX, kelly_fraction_binary  # type: ignore
    from venues.base import Side  # type: ignore

# --------------------------------------------------------------------------
# Pre-registered EV floors (EV = p*odds - 1, per 1 unit staked). These are
# named module constants by design: they are part of the pre-registered policy,
# not a per-slate knob. A is the strongest-EV tier, C the marginal floor.
# --------------------------------------------------------------------------
EV_FLOOR_A: float = 0.08   # >= +8% EV at the taken price
EV_FLOOR_B: float = 0.04   # >= +4% EV
EV_FLOOR_C: float = 0.02   # >= +2% EV (marginal but bettable)

# When the settle-against close is a proxy (clv_is_proxy=True) the CLV evidence
# is weaker, so every floor is raised by this margin before tiering.
EV_PROXY_PENALTY: float = 0.01

# Re-exported so callers can size with the SAME quarter-Kelly the policy assumes.
QUARTER_KELLY_FRACTION: float = KELLY_FRACTION   # 0.25 (imported, never redefined)
KELLY_CAP: float = KELLY_PCT_MAX                 # 0.25 hard clamp (imported)

# Ordered weakest -> strongest so tiering can scan once.
_TIER_FLOORS = (("C", EV_FLOOR_C), ("B", EV_FLOOR_B), ("A", EV_FLOOR_A))


def floors_for(clv_is_proxy: bool = False) -> Dict[str, float]:
    """The effective (proxy-adjusted) EV floor for each tier. Pure helper."""
    bump = EV_PROXY_PENALTY if clv_is_proxy else 0.0
    return {"A": EV_FLOOR_A + bump,
            "B": EV_FLOOR_B + bump,
            "C": EV_FLOOR_C + bump}


def tier(*, ev: float,
         model_prob: Optional[float] = None,
         market_prob: Optional[float] = None,
         clv_is_proxy: bool = False) -> Optional[str]:
    """Assign an evidence/EV tier from the EV floors. Pure function.

    Returns "A" (strongest EV) / "B" / "C" (marginal) when *ev* clears the
    corresponding pre-registered floor, else None (below floor -> no bet).
    Monotonic in *ev*: a higher EV never yields a weaker tier. When
    *clv_is_proxy* is True every floor is raised by EV_PROXY_PENALTY.

    *model_prob* / *market_prob* are accepted for forward-compatible signatures
    (the integration agent passes them through) but the tier is EV-driven; they
    are only used as a sanity gate: a non-finite or out-of-range probability
    cannot produce a bet.
    """
    try:
        e = float(ev)
    except (TypeError, ValueError):
        return None
    if e != e:  # NaN
        return None
    for p in (model_prob, market_prob):
        if p is not None:
            try:
                pf = float(p)
            except (TypeError, ValueError):
                return None
            if pf != pf or not (0.0 <= pf <= 1.0):
                return None
    bump = EV_PROXY_PENALTY if clv_is_proxy else 0.0
    label: Optional[str] = None
    for name, floor in _TIER_FLOORS:           # weakest -> strongest
        if e >= floor + bump:
            label = name
    return label


def _kelly_units(model_prob: float, taken_decimal: float) -> float:
    """Quarter-Kelly fraction-of-bankroll for a decimal-odds bet, via risk.py.

    Expressed in the binary-contract form risk.py uses: implied price
    m = 1/decimal. BUY YES at price m with fair prob p -> the SAME fractional
    Kelly the live risk gate would apply, hard-clamped to KELLY_CAP. 0.0 when
    there is no positive edge. This IS the unit stake for quarter-Kelly: one
    "unit" == one fraction-of-bankroll, so flat-unit and Kelly live on the same
    units axis (no dollars).
    """
    try:
        p = float(model_prob)
        o = float(taken_decimal)
    except (TypeError, ValueError):
        return 0.0
    if not (o > 1.0) or not (0.0 <= p <= 1.0):
        return 0.0
    price = 1.0 / o
    return float(kelly_fraction_binary(p, price, Side.BUY,
                                       corr=0.0,
                                       kelly_fraction=KELLY_FRACTION))


def stake_units(*, ev: float,
                model_prob: Optional[float],
                taken_decimal: Optional[float],
                tier: Optional[str],
                clv_is_proxy: bool = False) -> Dict[str, float]:
    """Both stakes for a row, in UNITS (no $/dollar field) -- locked dual-staking.

    Returns {"flat_unit": <1.0 | 0.0>, "quarter_kelly": <fraction>}:
      * flat_unit    -- 1.0 for ANY tiered bet (tier in A/B/C), else 0.0. This is
                        the honest, variance-controlled CLV record: one unit per
                        bet regardless of size.
      * quarter_kelly -- the quarter-Kelly fraction-of-bankroll (reused from
                        risk.py), for the bankroll curve. 0.0 when there is no
                        tier or no positive Kelly edge at the taken price.

    *tier* is taken as given (the caller tiers once, then sizes) so the two calls
    cannot disagree. When *tier* is None nothing is staked on either axis.
    """
    if tier is None:
        return {"flat_unit": 0.0, "quarter_kelly": 0.0}
    flat = 1.0
    qk = 0.0
    if model_prob is not None and taken_decimal is not None:
        qk = _kelly_units(model_prob, taken_decimal)
    return {"flat_unit": flat, "quarter_kelly": qk}


__all__ = [
    "EV_FLOOR_A",
    "EV_FLOOR_B",
    "EV_FLOOR_C",
    "EV_PROXY_PENALTY",
    "QUARTER_KELLY_FRACTION",
    "KELLY_CAP",
    "floors_for",
    "tier",
    "stake_units",
]
