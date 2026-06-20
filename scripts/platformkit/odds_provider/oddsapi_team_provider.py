"""scripts.platformkit.odds_provider.oddsapi_team_provider -- OddsAPI team-market shim.

LSII-05: 5+ real distinct books when ODDS_API_KEY is set, else UNAVAILABLE.

This module is the canonical entry-point for the OddsAPI multi-book team-market
provider as wired into default_providers / aggregate. It re-exports the full
implementation from oddsapi_provider (single source of truth) plus a thin
convenience constructor and the american_to_decimal helper from base so callers
can import everything team-market related from ONE place.

API shape contract (same as espn.py / kalshi.py):
  * fetch(sport) -> list[OddsEvent] | unavailable-dict; never raises.
  * All prices decimal (> 1.0), taken DIRECTLY from the API -- no fabrication.
  * Venue labels "oddsapi:<BookTitle>" (real regulated US sportsbooks).
  * ODDS_API_KEY absent/blank -> unavailable(reason); never a synthetic price.
  * Malformed/empty payload -> unavailable or empty list; never raises.

merge_events compatibility: OddsEvent.prices shape is IDENTICAL to ESPN/Kalshi so
aggregate.merge_events / to_odds_lookup work without any mapping layer.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Union

from .base import (
    OddsEvent,
    american_to_decimal,
    is_unavailable,
    unavailable,
)
from .oddsapi_provider import (
    OddsApiProvider,
    _parse_h2h,
    _parse_spread,
    _parse_total,
    parse_bookmakers,
    parse_events,
)


def make_team_provider(
    http_get: Optional[Callable[[str], Any]] = None,
    *,
    use_cache: bool = True,
    regions: str = "us",
    markets: str = "h2h,spreads,totals",
) -> OddsApiProvider:
    """Build an OddsApiProvider with sensible team-market defaults.

    Returns an OddsApiProvider ready to call fetch(sport).  All prices are
    decimal (>1.0) real sportsbook prices; UNAVAILABLE when key absent.
    No edge/ROI claim; calibration only.
    """
    kw: dict = {"use_cache": use_cache, "regions": regions, "markets": markets}
    if http_get is not None:
        kw["http_get"] = http_get
    return OddsApiProvider(**kw)


__all__ = [
    # Main provider class
    "OddsApiProvider",
    # Convenience constructor
    "make_team_provider",
    # Pure parsers (unit-testable on canned payloads)
    "parse_events",
    "parse_bookmakers",
    "_parse_h2h",
    "_parse_spread",
    "_parse_total",
    # Re-exported schema / helpers (one-stop import for callers)
    "OddsEvent",
    "american_to_decimal",
    "is_unavailable",
    "unavailable",
]
