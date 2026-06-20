"""scripts.platformkit.odds_provider.best_line_fresh -- freshness-aware best-line.

Wraps odds_shop.best_line with a per-venue freshness gate so a STALE cached
venue can NEVER win the best price over a fresher lower-odds book.

Public API
----------
best_line_fresh(
    book_prices         : {venue: {side: decimal_odds}},
    venue_as_of         : {venue: str|None},      # per-venue ISO-8601 timestamps
    *,
    max_age_sec         : float = DEFAULT_MAX_AGE_SEC,
    now                 : Optional[datetime] = None,
    market_type         : Optional[str] = None,
) -> Dict[str, Dict[str, Any]]   # {side: {"book": str, "price": float}}

Stale-never-green rules (binding):
  1. A venue whose as_of is OLDER than max_age_sec is excluded.
  2. A venue whose as_of is unknown or unparseable is excluded (not trusted).
  3. Prediction-market venues (Kalshi/Polymarket) are ALWAYS excluded from the
     bettable-best result (they are not bettable sportsbook lines).
  4. All-stale or empty input -> {} per side; NEVER a fabricated price.
  5. Never raises.

build_on: odds_shop.best_line (read-only), freshness.freshness_status (pure),
          base.venue_type/VENUE_SPORTSBOOK, OddsEvent per-venue as_of.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from scripts.platformkit.odds_provider.freshness import (
    DEFAULT_MAX_AGE_SEC,
    freshness_status,
)
from scripts.platformkit.odds_provider.base import (
    VENUE_SPORTSBOOK,
    venue_type,
)

# Re-export the default for callers that import from here.
DEFAULT_MAX_AGE_SEC = DEFAULT_MAX_AGE_SEC  # noqa: PLW0127


def _is_venue_fresh(
    venue: str,
    venue_as_of: Dict[str, Optional[str]],
    *,
    now: Optional[datetime],
    max_age_sec: float,
    market_type: Optional[str],
) -> bool:
    """True iff *venue* has a known, parseable, fresh as_of timestamp.

    Rules:
    - Missing from venue_as_of -> False (stale-never-green: absent = not trusted).
    - Present but None / empty -> False (same rule).
    - Present but older than max_age_sec -> False (stale).
    - Present AND within max_age_sec -> True (fresh).
    """
    ts = venue_as_of.get(venue)  # None when key absent OR value is None
    if not ts:
        return False
    status = freshness_status(
        ts,
        now=now,
        max_age_sec=max_age_sec,
        market_type=market_type,
    )
    return status["status"] == "fresh"


def best_line_fresh(
    book_prices: Dict[str, Dict[str, float]],
    venue_as_of: Dict[str, Optional[str]],
    *,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    now: Optional[datetime] = None,
    market_type: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Best (highest) decimal odds per side, FRESH sportsbook venues only.

    Parameters
    ----------
    book_prices : {venue: {side: decimal_odds}}
        Multi-book price dict -- the same shape odds_shop.best_line consumes.
        Prices <= 1.0 are rejected (must be decimal odds > 1.0).
    venue_as_of : {venue: ISO-8601 str | None}
        Per-venue capture timestamps.  A venue whose key is absent from this
        dict, or whose value is None/empty/unparseable, is treated as STALE and
        is excluded from selection -- stale-never-green means unknown timestamps
        are never trusted.
    max_age_sec : float
        Maximum acceptable age in seconds (default 900 = 15 min from freshness).
        Per-market defaults from freshness.MARKET_MAX_AGE apply when market_type
        is set and max_age_sec is still at the DEFAULT.
    now : Optional[datetime]
        Injectable UTC clock (default: datetime.now(utc)).  Pass a fixed value
        in tests so staleness calculations are deterministic.
    market_type : Optional[str]
        "moneyline" | "spread" | "total" | "prop" -- passed into freshness so
        per-market age overrides from freshness.MARKET_MAX_AGE apply.

    Returns
    -------
    {side: {"book": str, "price": float}}
        Best fresh sportsbook price per side.  A side absent from every FRESH
        bettable book is omitted.  An all-stale or empty input returns {} --
        never a fabricated price, never raises.
    """
    best: Dict[str, Dict[str, Any]] = {}
    try:
        for venue, prices in book_prices.items():
            # Rule 3: prediction-market venues never win the bettable best.
            if venue_type(venue) != VENUE_SPORTSBOOK:
                continue
            # Rules 1-2: missing/unknown/stale as_of -> skip.
            if not _is_venue_fresh(
                venue,
                venue_as_of,
                now=now,
                max_age_sec=max_age_sec,
                market_type=market_type,
            ):
                continue
            if not isinstance(prices, dict):
                continue
            for side, price in prices.items():
                try:
                    p = float(price)
                except (TypeError, ValueError):
                    continue
                if p <= 1.0:  # must be valid decimal odds
                    continue
                cur = best.get(side)
                if cur is None or p > cur["price"]:
                    best[side] = {"book": venue, "price": p}
    except Exception:  # noqa: BLE001 -- never raises; degrade to {}
        return {}
    return best


__all__ = [
    "best_line_fresh",
    "DEFAULT_MAX_AGE_SEC",
]
