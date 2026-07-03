"""scripts.platformkit.odds_provider.kalshi_liquidity -- the in-play liquidity gate.

Split out of inplay_kalshi.py (which is near the 300 LOC cap) so the LIVE-fields
liquidity classification has its own small, testable home.

THE LIQUIDITY GATE (the honest fix for "listed but untraded"): a market counts as
tradeable in-play ONLY if, on the LIVE *_dollars / *_fp fields (NOT the deprecated
integer fields which read None):
  * it is open + not settled (the caller already filters status=open), AND
  * its YES spread (yes_ask_dollars - yes_bid_dollars) is <= max_spread, AND
  * its traded volume (volume_fp) is above min_volume, AND
  * both side sizes (yes_bid_size_fp, yes_ask_size_fp) are above min_size.
An untraded pregame contract (all *_fp None / zero, wide/no spread) therefore fails
the gate -- it can never masquerade as a live in-play price.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; pure (no
I/O). Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_liquidity.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Defaults are deliberately conservative: the research probe showed liquid in-season
# game markets sit at a 1-2c spread with 5-6 figure volume / sizes, while untraded
# pregame contracts read None on every *_fp field and have no real spread.
MAX_SPREAD = 0.02   # <= 2c YES bid/ask spread
MIN_VOLUME = 50.0   # traded contracts (volume_fp) floor
MIN_SIZE = 1.0      # both bid_size_fp and ask_size_fp must be above this floor


def _fp(market: Dict[str, Any], key: str) -> Optional[float]:
    """A fractional-point (*_fp) or *_dollars field coerced to float, else None.

    Reads ONLY the LIVE fields. The deprecated bare-integer fields (yes_bid,
    yes_ask, volume, open_interest) read None on the live API, so a market priced
    only by those returns None here and is gated out -- never zero-filled.
    """
    v = market.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _spread(market: Dict[str, Any]) -> Optional[float]:
    """YES bid/ask spread in dollars (ask - bid) from the live *_dollars fields.

    None if either side is unquoted (cannot prove a tight market) or the spread is
    nonsensical (negative). A None spread fails the gate (we never assume tight).
    """
    bid = _fp(market, "yes_bid_dollars")
    ask = _fp(market, "yes_ask_dollars")
    if bid is None or ask is None:
        return None
    s = ask - bid
    return s if s >= 0.0 else None


def is_liquid(market: Dict[str, Any],
              *, max_spread: float = MAX_SPREAD,
              min_volume: float = MIN_VOLUME,
              min_size: float = MIN_SIZE) -> bool:
    """True iff *market* clears the in-play liquidity gate on its LIVE fields.

    Requires a tight quoted spread AND real traded volume AND real depth on BOTH
    sides -- so an untraded pregame contract (None/zero *_fp) is excluded. Pure +
    total; never raises (a malformed market -> False, i.e. VOID, never faked live).
    """
    try:
        spread = _spread(market)
        if spread is None or spread > max_spread:
            return False
        vol = _fp(market, "volume_fp")
        if vol is None or vol <= min_volume:
            return False
        bid_sz = _fp(market, "yes_bid_size_fp")
        ask_sz = _fp(market, "yes_ask_size_fp")
        if bid_sz is None or ask_sz is None:
            return False
        return bid_sz > min_size and ask_sz > min_size
    except Exception as exc:  # noqa: BLE001 -- classification must never sink a row
        logger.debug("is_liquid check failed: %s", exc)
        return False


__all__ = ["is_liquid", "MAX_SPREAD", "MIN_VOLUME", "MIN_SIZE"]
