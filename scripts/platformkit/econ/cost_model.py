"""scripts.platformkit.econ.cost_model -- per-venue TAKER cost model (6.1).

Answers ONE question honestly: how big does the model-vs-market probability
divergence need to be, at a given price, for a TAKER order to be +EV after
real transaction costs? This is measurement infrastructure only -- it changes
no behavior and places no orders.

FEE SCHEDULES LIVE IN execution/venue_fees.py (the ONE canonical, cited fee
module, re-verified 2026-09-01) -- the Kalshi/Polymarket functions below are
thin wrappers over it so the two files' schedules can never drift again.

PROVENANCE (web-verified 2026-07-02, cross-checked 2+ independent sources each;
RE-VERIFY against the official Kalshi fee schedule PDF + Polymarket docs before
Phase 8.2 ever runs for real money -- fee schedules change):

  KALSHI: taker fee per contract, in dollars, at contract price P in [0.01,0.99]:
      fee = ceil_to_cent(0.07 * P * (1 - P))
  Maker fee is 0.25x the taker formula:
      fee = ceil_to_cent(0.0175 * P * (1 - P))
  Max fee lands at P=0.50: 1.75c/contract taker (bills 2c after the cent
  ceiling), 0.44c/contract maker (bills 1c after the cent ceiling). This is
  the STANDARD schedule; some Kalshi market categories are reported to carry
  different fee schedules for special events. We have NO confirmed evidence
  this applies to the sports series this system trades (KXMLBGAME/KXWCGAME),
  so we default to the standard 0.07 formula. NOW.md's own working figure of
  "~3-5c round-trip late-game" is roughly 2x a per-side taker fee near the 50c
  region plus half-spread, which is consistent with this formula (2 * 1.75c =
  3.5c) -- treated here as a cross-check, not a separate source of truth.

  POLYMARKET: the March-2026 flat 0.75%-of-notional Sports rate is SUPERSEDED
  (July 2026 update, confirmed 2026-09-01 against docs.polymarket.com/trading/
  fees -- see venue_fees.py): taker fee = shares * 0.05 * P * (1 - P), a
  PARABOLIC formula like Kalshi's, where shares are $1-payout shares. Maker
  orders are free. On-chain/relayer gas is ~$0.003-0.005/trade and paid by the
  relayer, not the trader per-fill -- modeled here as a named, overridable
  constant defaulting near 0, never silently hardcoded away.

  DFS PICK'EM (Underdog / PrizePicks) payout multipliers (both platforms
  independently converged on close numbers for their "must hit every leg"
  product -- PrizePicks calls it Power Play, Underdog calls it Standard):
    2-pick=3x, 3-pick=6x, 4-pick=10x, 5-pick=20x, 6-pick=37.5x.
  Breakeven joint probability for an N-pick slip at multiplier M:
      need P(all correct) > 1/M  (that's the payout structure's own vig)
  For EQUAL-probability legs, the per-leg breakeven is the N-th root:
      per_leg_breakeven ~= (1/M) ** (1/N)
  e.g. 2-pick @ 3x: joint breakeven = 1/3 = 0.333; per-leg ~= sqrt(1/3) = 0.577.
  DFS is lower priority than Kalshi/Polymarket for this build pass (props
  channel currently has 0% CLV coverage, not a near-term GREEN candidate) --
  only 2-pick and 3-pick Power Play/Standard are implemented; PrizePicks Flex
  Play (partial-win-tolerant) tables are NOT implemented here (starter-quality,
  honestly caveated). Structured as a dict so more pick-counts/variants can be
  added later without a rewrite.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII only; no $-edge claims
(everything here is a PROBABILITY threshold, never a dollar figure); never
raises on malformed input -- returns None/NaN-safe defaults instead.
"""
from __future__ import annotations

from typing import Optional

from scripts.platformkit.execution import venue_fees as _vf


def _mode(side: object) -> str:
    """Legacy side -> venue_fees mode. Anything not "maker" falls through to
    "taker" -- the CONSERVATIVE (higher-fee) tier -- because this module's
    contract is never-raises; venue_fees itself fails closed on junk modes."""
    return "maker" if str(side).strip().lower() == "maker" else "taker"


# ---------------------------------------------------------------------------
# Kalshi -- thin wrapper over execution.venue_fees (the canonical schedule)
# ---------------------------------------------------------------------------

def kalshi_fee_per_contract(price: float, side: str = "taker") -> float:
    """Kalshi fee in DOLLARS for one $1-notional contract at *price* (0.01-0.99).

    Delegates to execution.venue_fees (the ONE canonical schedule); this
    wrapper only preserves cost_model's legacy input contract. side: "taker"
    or "maker". Never raises: out-of-range/invalid price clamps into
    [0.01, 0.99] first (venue_fees would raise ValueError instead).
    """
    try:
        p = min(max(float(price), 0.01), 0.99)
    except (TypeError, ValueError):
        return 0.0
    if _mode(side) == "maker":
        return _vf.fee_kalshi_maker(1.0, p)
    return _vf.fee_kalshi_taker(1.0, p)


# ---------------------------------------------------------------------------
# Polymarket -- thin wrapper over execution.venue_fees (the canonical schedule)
# ---------------------------------------------------------------------------

# Relayer gas is paid by the relayer, not the trader, per-fill -- modeled as an
# overridable constant near 0 rather than silently assumed away.
POLYMARKET_GAS_PER_TRADE = 0.004  # dollars; midpoint of the observed $0.003-0.005 band


def polymarket_fee(notional: float, side: str = "taker",
                    include_gas: bool = False, *, price: float) -> float:
    """Polymarket Sports-category fee in DOLLARS via venue_fees.fee_polymarket.

    SIGNATURE CHANGE 2026-09-01: the superseded flat 0.75%-of-dollar-notional
    formula is gone. The cited schedule is parabolic in price, so *price*
    (share probability in [0, 1]) is REQUIRED, and *notional* is now a count
    of $1-payout shares (venue_fees' convention), NOT dollars of notional.
    Maker orders are free. A numerically valid price outside [0, 1] raises
    ValueError (a cents-vs-dollars unit error -- a silent $0 fee would inflate
    EV); unparseable notional/price still returns 0.0. Gas is excluded by
    default (paid by the relayer); include_gas=True adds the named constant.
    """
    fee = _vf.fee_polymarket(_mode(side), notional, price)
    if include_gas:
        fee += POLYMARKET_GAS_PER_TRADE
    return fee


# ---------------------------------------------------------------------------
# breakeven_edge_prob -- venue-agnostic entry point
# ---------------------------------------------------------------------------

def breakeven_edge_prob(venue: str, price: float, size: float = 1.0,
                         side: str = "taker") -> Optional[float]:
    """The model-vs-market probability divergence needed to be +EV after costs.

    *price* is the probability/decimal price of the side taken, in (0, 1) for
    Kalshi-style dollar-contract venues. Returns the ADDITIONAL probability
    edge (in probability units, e.g. 0.02 = 2 percentage points) the model
    must have over the quoted price to clear round-trip costs (entry + exit,
    i.e. 2x the per-side fee -- this system's practice is enter-then-exit, not
    hold-to-settlement, per NOW.md's round-trip framing).

    size is contracts (Kalshi, fee is PER-CONTRACT so breakeven PROBABILITY is
    size-INVARIANT -- confirmed below in the monotonicity test) or $1-payout
    shares (Polymarket, fee is LINEAR in shares so likewise size-invariant in
    probability terms).

    Returns None for an unrecognized venue (never raises, never guesses).
    """
    v = str(venue).strip().lower()
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if not (0.0 < p < 1.0):
        return None
    if v == "kalshi":
        fee_in = kalshi_fee_per_contract(p, side=side)
        fee_out = kalshi_fee_per_contract(1.0 - p, side=side)  # exit = opposite side's price
        round_trip = fee_in + fee_out
        # size is contracts; each contract pays $1 notional at settlement, so
        # the breakeven PROBABILITY (cost / $1 notional) does not depend on size.
        return round(round_trip, 6)
    if v == "polymarket":
        # Per $1-payout share; the parabolic schedule makes the fee depend on
        # price now: entry at p, exit at the opposite side's price 1-p (same
        # convention as the Kalshi branch; P*(1-P) is symmetric so both legs
        # cost the same).
        fee_in = polymarket_fee(1.0, side=side, include_gas=False, price=p)
        fee_out = polymarket_fee(1.0, side=side, include_gas=False, price=1.0 - p)
        return round(fee_in + fee_out, 6)
    return None


# ---------------------------------------------------------------------------
# DFS pick'em breakeven table
# ---------------------------------------------------------------------------

# multiplier tables: {platform: {play_type: {n_picks: multiplier}}}
# Only 2-pick/3-pick standard/power-play are load-bearing today (see docstring);
# the rest of the standard table is included since it costs nothing to encode,
# but is NOT claimed as verified to the same standard.
DFS_MULTIPLIER_TABLE = {
    "prizepicks": {
        "power_play": {2: 3.0, 3: 6.0, 4: 10.0, 5: 20.0, 6: 37.5},
        # Flex Play: partial-win-tolerant, NOT fully implemented -- starter-quality
        # entries only for the pick-counts explicitly given in the spec.
        "flex_play": {
            3: {3: 3.0, 2: 1.0},               # {hits: multiplier}
            4: {4: 6.0, 3: 1.5},
            5: {5: 10.0, 4: 2.0, 3: 0.4},
            6: {6: 25.0, 5: 2.0, 4: 0.4},
        },
    },
    "underdog": {
        "standard": {2: 3.0, 3: 6.0, 4: 10.0, 5: 20.0, 6: 37.5},
    },
}


def dfs_breakeven_prob(platform: str, n_picks: int,
                        play_type: str = "power_play") -> Optional[float]:
    """Per-leg breakeven probability for an N-pick DFS pick'em slip.

    Assumes EQUAL-probability legs (the honest simplification stated in the
    module docstring): joint breakeven = 1/multiplier; per-leg breakeven is the
    N-th root of that, i.e. per_leg = (1/multiplier) ** (1/n_picks).

    Only "must hit every leg" (power_play/standard) tables support this closed
    form; Flex Play's partial-win payouts need a full binomial EV solve, which
    is NOT implemented here (out of scope / lower priority per the spec) --
    returns None for flex_play rather than a wrong number.
    """
    plat = str(platform).strip().lower()
    pt = str(play_type).strip().lower()
    table = DFS_MULTIPLIER_TABLE.get(plat, {}).get(pt)
    if table is None:
        return None
    if pt == "flex_play":
        return None  # partial-win payout needs a binomial EV solve, not built here
    mult = table.get(int(n_picks))
    if mult is None or mult <= 0:
        return None
    joint_breakeven = 1.0 / mult
    per_leg = joint_breakeven ** (1.0 / int(n_picks))
    return round(per_leg, 6)


def dfs_joint_breakeven_prob(platform: str, n_picks: int,
                              play_type: str = "power_play") -> Optional[float]:
    """The raw joint (all-legs-correct) breakeven probability = 1/multiplier."""
    plat = str(platform).strip().lower()
    pt = str(play_type).strip().lower()
    table = DFS_MULTIPLIER_TABLE.get(plat, {}).get(pt)
    if table is None or pt == "flex_play":
        return None
    mult = table.get(int(n_picks))
    if mult is None or mult <= 0:
        return None
    return round(1.0 / mult, 6)


__all__ = [
    "kalshi_fee_per_contract",
    "polymarket_fee",
    "POLYMARKET_GAS_PER_TRADE",
    "breakeven_edge_prob",
    "DFS_MULTIPLIER_TABLE",
    "dfs_breakeven_prob",
    "dfs_joint_breakeven_prob",
]
