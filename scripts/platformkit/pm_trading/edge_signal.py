"""edge_signal.py -- map a tradable contract to an edge in basis points.

(Module is named edge_signal, not signal/signals, to avoid colliding with
Python's stdlib `signal` and the repo-root `signals/` namespace package.)

Two honest reference probabilities feed every strategy:
  fair_prob  : our calibrated model probability for the YES outcome, sourced
               from predict_matchup/build_result (or any externally-supplied
               calibrated prob in [0, 1]).
  devig_prob : the vig-removed sportsbook consensus for the same event, used
               as an independent anchor (cross-market arb, sanity).

For a YES contract trading at venue price m (dollars in [0, 1]):
  edge = fair_prob - m          # $ EV per contract if you BUY one YES
Buying YES is +EV when fair_prob > m; the +EV NO side (SELL YES) when
fair_prob < m. edge_bps = edge * 10000.

HONEST RAIL: edge_bps here is a RAW signal, not a claimed edge. No edge is
real until it survives the eval_gate on FORWARD paper P&L + CLV. A large
edge_bps usually means a thin/stale book or a model error -- it is a
hypothesis to forward-test, never a printer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

try:
    from .venues.base import Side
except ImportError:  # pragma: no cover  (flat sibling import for hermetic tests)
    from venues.base import Side  # type: ignore


# --------------------------------------------------------------------------
# odds / probability conversion
# --------------------------------------------------------------------------
def implied_from_decimal(decimal_odds: float) -> float:
    """Raw (vig-inclusive) implied probability from decimal odds."""
    if decimal_odds <= 1.0:
        raise ValueError("decimal odds must be > 1.0")
    return 1.0 / decimal_odds


def implied_from_american(american: int) -> float:
    """Raw (vig-inclusive) implied probability from American odds."""
    a = float(american)
    if a == 0:
        raise ValueError("american odds cannot be 0")
    if a > 0:
        return 100.0 / (a + 100.0)
    return (-a) / ((-a) + 100.0)


# --------------------------------------------------------------------------
# de-vigging (remove the bookmaker overround)
# --------------------------------------------------------------------------
def devig(raw_probs: Sequence[float], method: str = "multiplicative") -> List[float]:
    """Return true probabilities (sum == 1) from raw vig-inclusive ones.

    method:
      "multiplicative" -- proportional normalization q_i / sum(q). Simple,
                          always correct, the workhorse default.
      "shin"           -- Shin (1993) insider-trade model; shades the book
                          toward the favourite-longshot correction. Solved
                          numerically (bisection on the insider fraction z).
    """
    raw = [float(q) for q in raw_probs]
    if len(raw) < 2 or any(q <= 0.0 for q in raw):
        raise ValueError("need >=2 positive raw probabilities")
    s = sum(raw)
    if method == "multiplicative":
        return [q / s for q in raw]
    if method == "shin":
        return _shin(raw)
    raise ValueError("unknown devig method: %s" % method)


def _shin(raw: Sequence[float], iters: int = 80) -> List[float]:
    s = sum(raw)

    def p_of(z: float) -> List[float]:
        out = []
        for q in raw:
            num = math.sqrt(z * z + 4.0 * (1.0 - z) * q * q / s) - z
            out.append(num / (2.0 * (1.0 - z)))
        return out

    # sum(p_of(z)) is sqrt(s) (>1) at z=0 and decreases in z -> bisect to 1.0.
    lo, hi = 0.0, 0.5
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if sum(p_of(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
    p = p_of((lo + hi) / 2.0)
    t = sum(p)
    return [x / t for x in p]  # final exact renormalization


def devig_two_way_american(home_odds: int, away_odds: int,
                           method: str = "multiplicative") -> float:
    """Convenience: devigged P(home/YES) from a two-way American moneyline."""
    qh = implied_from_american(home_odds)
    qa = implied_from_american(away_odds)
    return devig([qh, qa], method=method)[0]


# --------------------------------------------------------------------------
# the signal
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Signal:
    market_id: str
    fair_prob: float            # calibrated model P(YES)
    market_price: float         # venue YES price in [0, 1]
    edge: float                 # fair_prob - market_price ($ EV / contract)
    edge_bps: float             # edge * 10000
    side: Side                  # BUY (long YES) if edge>0 else SELL
    devig_prob: Optional[float] = None     # sportsbook consensus P(YES)
    consensus_edge_bps: Optional[float] = None  # (devig - price) * 10000
    thinness: str = "unknown"

    def agrees_with_consensus(self) -> bool:
        """True when model and devigged book lean the SAME side vs price.

        Disagreement is a yellow flag: the model is fighting the consensus,
        so the edge is more likely a model error than a real mispricing.
        """
        if self.devig_prob is None:
            return True
        return (self.fair_prob - self.market_price) * \
               (self.devig_prob - self.market_price) >= 0.0


def build_signal(market_id: str, fair_prob: float, market_price: float,
                 devig_prob: Optional[float] = None,
                 thinness: str = "unknown") -> Signal:
    """Construct a Signal from a calibrated prob and the live venue price."""
    if not (0.0 <= fair_prob <= 1.0):
        raise ValueError("fair_prob must be in [0, 1]")
    if not (0.0 <= market_price <= 1.0):
        raise ValueError("market_price must be in [0, 1]")
    edge = fair_prob - market_price
    cons = None if devig_prob is None else round((devig_prob - market_price) * 1e4, 4)
    return Signal(
        market_id=market_id,
        fair_prob=round(fair_prob, 6),
        market_price=round(market_price, 6),
        edge=round(edge, 6),
        edge_bps=round(edge * 1e4, 4),
        side=Side.BUY if edge > 0 else Side.SELL,
        devig_prob=None if devig_prob is None else round(devig_prob, 6),
        consensus_edge_bps=cons,
        thinness=thinness,
    )
