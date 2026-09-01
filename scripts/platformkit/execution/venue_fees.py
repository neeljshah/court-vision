"""scripts.platformkit.execution.venue_fees -- the ONE canonical fee module.

Every venue fee formula used anywhere under scripts/platformkit/ should call
into this file. Each formula below carries its own citation + retrieval date;
anything NOT confirmed against a primary/official source fails CLOSED
(raises NotImplementedError) rather than guessing.

KALSHI (confirmed 2026-09-01 against help.kalshi.com/en/articles/13823805-fees,
page dated April 19, 2026, cross-checked via marketmath.io/platforms/kalshi):
    taker fee = ceil_to_cent($0.07 * C * P * (1 - P))
    maker fee = ceil_to_cent($0.0175 * C * P * (1 - P))  (0.25x taker coef)
  C is the CONTRACT COUNT and it sits INSIDE the ceiling: the schedule rounds
  up ONCE per order batch, not once per contract. Fees are therefore NOT
  linear in size (10 contracts @ $0.50 is $0.18, not 10 x $0.02 = $0.20) --
  ceiling per-contract overstates cost by up to a cent per contract.
  NOTE: a $0.035/contract fee CAP reported only by the secondary aggregator is
  UNVERIFIED against the primary PDF (2x 429 + a forced-download block this
  session) and is NOT applied here. A reported sports-series fee exception
  (help.kalshi.com, same page) is also unresolved and NOT modeled. The 0.25x
  maker ratio is inherited from econ/cost_model.py's 2026-07-02 verification
  and was NOT independently re-confirmed this session.

POLYMARKET (confirmed 2026-09-01 against docs.polymarket.com/trading/fees,
official docs, fetched directly):
    fee = shares * feeRate * P * (1 - P)   -- a PARABOLIC formula, structurally
    like Kalshi's, NOT a flat percentage of notional.
    Sports-category feeRate = 0.05 (July 2026 update; was 0.03 in March 2026).
    Maker fee = $0 always ("Makers are never charged fees. Only takers pay.")
  *notional* here is a SHARE COUNT ($1-payout shares, Kalshi-style contracts),
  matching the doc's own worked example: 100 shares @ P=0.50 -> fee =
  100 * 0.05 * 0.5 * 0.5 = $1.25.
  UNIT WARNING for callers that charge bps-of-dollar-notional: that $1.25 is
  1.25 cents per SHARE, which is 2.5% of the $50 DOLLAR notional (100 * $0.50),
  NOT 1.25%. In general fee / dollar_notional = feeRate * (1 - P), so the
  rate-of-notional RISES as price falls (-> 5% as P -> 0, 2.5% at P = 0.50).
  Divide the per-share fee by P before handing any bps figure to such an engine.
  Maker rebates (15% of sports fees, since July 2026) and relayer gas are NOT
  modeled here (no current-doc confirmation of a stable per-trade figure).

SCOPE: fees here are ENTRY-side only. Kalshi settlement is free, so a
hold-to-settlement EV needs one fee, not two. econ/cost_model.py's
breakeven_edge_prob models a ROUND TRIP (enter-then-exit) instead -- the two
modules answer different questions and their numbers are not interchangeable.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; no $-edge claims
(this is a fee/cost model, never a profit claim). Input contract: unparseable
price/size -> 0.0 fee (never raises); a numerically valid price OUTSIDE [0, 1]
-> ValueError, because that is a cents-vs-dollars unit error and returning a
$0 fee for it would silently INFLATE EV; an unrecognized venue/mode/side ->
NotImplementedError. Sizes are magnitudes: a negative count is charged as its
absolute value, so a fee can never be credited back into EV.
"""
from __future__ import annotations

import math
from typing import Optional

_KALSHI_TAKER_COEF = 0.07
_KALSHI_MAKER_COEF = 0.0175  # 0.25x taker, per schedule's stated ratio

_POLYMARKET_TAKER_FEE_RATE = 0.05  # Sports category, July 2026 update
_POLYMARKET_MAKER_FEE_RATE = 0.0   # makers are never charged

_VENUES = ("kalshi", "polymarket")
_MODES = ("maker", "taker")
_SIDES = ("yes", "no")

_PRICE_EPS = 1e-9  # float-noise tolerance around the [0, 1] bounds


def _ceil_to_cent(dollars: float) -> float:
    """Round UP to the nearest whole cent (both schedules ceil, never round)."""
    return math.ceil(round(dollars * 100.0, 6)) / 100.0


def _prob(price: object) -> Optional[float]:
    """Coerce a price to a probability in [0, 1].

    Returns None for unparseable input (the caller then yields a 0.0 fee).
    Raises ValueError for a numerically valid price outside [0, 1] -- that is
    a unit mismatch (cents passed where a probability was expected), and a
    silent 0.0 fee there would understate cost and inflate EV.
    """
    try:
        p = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(p):
        return None
    if p < -_PRICE_EPS or p > 1.0 + _PRICE_EPS:
        raise ValueError(
            "venue_fees: price %r is outside [0, 1] -- prices are probabilities, "
            "not cents (pass 0.50, not 50)" % (price,))
    return min(max(p, 0.0), 1.0)


def _count(size: object) -> Optional[float]:
    """Coerce a contract/share count to a non-negative magnitude."""
    try:
        n = float(size)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(n):
        return None
    return abs(n)


def _kalshi_fee(contracts: object, price: object, coef: float) -> float:
    """Shared Kalshi batch fee: the cent-ceiling applies ONCE to the whole order."""
    p = _prob(price)
    n = _count(contracts)
    if p is None or n is None:
        return 0.0
    return _ceil_to_cent(coef * n * p * (1.0 - p))


def fee_kalshi_taker(contracts: float, price: float) -> float:
    """Total Kalshi TAKER fee in dollars for *contracts* contracts at *price*."""
    return _kalshi_fee(contracts, price, _KALSHI_TAKER_COEF)


def fee_kalshi_maker(contracts: float, price: float) -> float:
    """Total Kalshi MAKER fee in dollars for *contracts* contracts at *price*."""
    return _kalshi_fee(contracts, price, _KALSHI_MAKER_COEF)


def _norm_mode(mode: object) -> str:
    """Normalize a maker/taker mode string, failing CLOSED on anything else."""
    m = str(mode).strip().lower()
    if m not in _MODES:
        raise NotImplementedError(
            "venue_fees: mode must be one of %r, got %r -- refusing to guess a "
            "fee tier (an unrecognized mode must never silently bill as taker)"
            % (list(_MODES), mode))
    return m


def fee_polymarket(mode: str, notional: float, price: float) -> float:
    """Polymarket Sports-category fee in dollars.

    *mode*: "taker" (5% feeRate) or "maker" ($0, always) -- this is the fee
    TIER, not the yes/no side of the market. *notional* is a count of $1-payout
    shares (same convention as a Kalshi contract count), NOT dollars of
    notional; see the module docstring's UNIT WARNING before converting to bps.
    *price* is the share price/probability in [0, 1].
    """
    rate = (_POLYMARKET_MAKER_FEE_RATE if _norm_mode(mode) == "maker"
            else _POLYMARKET_TAKER_FEE_RATE)
    p = _prob(price)
    shares = _count(notional)
    if p is None or shares is None:
        return 0.0
    return shares * rate * p * (1.0 - p)


def expected_value_after_fees(p_model: float, price: float, side: str,
                                venue: str, mode: str) -> float:
    """EV per $1-notional contract, net of the ENTRY-side venue/mode fee.

    *price* is the price of the SIDE actually held (i.e. already the "no"
    price if side="no" -- same convention as econ.cost_model.breakeven_edge_prob).
    *p_model* is the model's calibrated probability of the YES outcome.
    Gross EV per contract = p_true - price, where p_true is the model's
    probability of the held side paying off; the fee is then SUBTRACTED, so it
    can only ever reduce EV. Assumes hold-to-settlement (Kalshi settlement is
    free); for an enter-then-exit round trip use cost_model.breakeven_edge_prob.
    Raises NotImplementedError for any venue/mode/side combination this module
    has no verified fee formula for -- never silently guesses or defaults.
    """
    v = str(venue).strip().lower()
    s = str(side).strip().lower()
    if v not in _VENUES:
        raise NotImplementedError("venue_fees: no verified fee schedule for venue=%r" % venue)
    m = _norm_mode(mode)
    if s not in _SIDES:
        raise NotImplementedError("venue_fees: side must be 'yes' or 'no', got %r" % side)
    p = _prob(price)
    if p is None:
        raise NotImplementedError("venue_fees: unparseable price %r" % (price,))
    p_true = float(p_model) if s == "yes" else (1.0 - float(p_model))
    gross = p_true - p
    if v == "kalshi":
        fee = fee_kalshi_taker(1.0, p) if m == "taker" else fee_kalshi_maker(1.0, p)
    else:  # polymarket
        fee = fee_polymarket(m, 1.0, p)
    return gross - fee


__all__ = [
    "fee_kalshi_taker",
    "fee_kalshi_maker",
    "fee_polymarket",
    "expected_value_after_fees",
]
