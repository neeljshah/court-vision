"""scripts.platformkit.odds_provider.kalshi_tick_depth -- tick-level bid/ask/spread.

Split out of inplay_kalshi.py (already at its 300 LOC cap) so the per-tick
placement-time depth fields (best_bid/best_ask/spread_bp) that ingame_exec_gate.
build_exec_depth consumes have their own tiny, testable home. Reads ONLY the
live *_dollars fields already present on a Kalshi /markets list-endpoint row --
no extra HTTP call, no orderbook fetch (that is a DIFFERENT, deeper endpoint;
see ingame_book_depth_kalshi.py for the full order-book reader used elsewhere).
Never fabricates: an unquoted or crossed book reads None, same live-fields-only
discipline as kalshi_liquidity.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; pure
(no I/O). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_tick_depth.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .kalshi_liquidity import _fp as _dollars


def best_bid_ask(market: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """YES (best_bid, best_ask) in dollars off the live *_dollars fields (REUSE
    kalshi_liquidity._fp's coercion -- the same live-fields-only contract the
    liquidity gate already applies). None/None if unquoted -- never fabricated,
    never falls back to the deprecated bare-int fields."""
    return _dollars(market, "yes_bid_dollars"), _dollars(market, "yes_ask_dollars")


def spread_bp(best_bid: Optional[float], best_ask: Optional[float]) -> Optional[float]:
    """(best_ask - best_bid) in basis points of a $1 contract. None if either
    side is unquoted or the book is crossed (negative spread) -- same contract
    as ingame_book_depth_kalshi.spread_bp, computed independently here (this
    module stays a leaf of odds_provider/; no import across the ingame/ lane
    boundary)."""
    if best_bid is None or best_ask is None:
        return None
    s = best_ask - best_bid
    return s * 10000.0 if s >= 0.0 else None


__all__ = ["best_bid_ask", "spread_bp"]
