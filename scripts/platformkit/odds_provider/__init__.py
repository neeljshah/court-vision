"""scripts.platformkit.odds_provider -- CourtVision's OWN odds aggregation service.

Pulls live odds from LEGITIMATELY-accessible public sources (Kalshi public
market-data API, Polymarket gamma API, ESPN free summary endpoint), normalises
them into one shape, and feeds the existing scripts.platformkit.odds_shop pure
functions (best_line / devig_twoway / detect_arb / summarise_twoway), which expect
`{venue: {side: decimal_odds}}`.

This is OUR odds API over PREDICTION-MARKET + ESPN sources. It is NOT a
DraftKings/FanDuel/sportsbook scraper -- direct scraping of those books violates
their ToS and is explicitly out of scope. ESPN merely republishes one book's line
on its free public endpoint; we read that, we do not scrape the book.

HONESTY: every provider reads any needed token from ENV only, and degrades to
status="unavailable" with NO fabricated price when a source is down. No exception
bubbles out of a provider.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC/file; no secrets.
"""
from __future__ import annotations

from .base import (
    OddsEvent, Provider, UNAVAILABLE, VENUE_PREDICTION_MARKET, VENUE_SPORTSBOOK,
    american_to_decimal, is_prediction_market, prob_to_decimal, venue_type,
    venue_types)

__all__ = [
    "OddsEvent",
    "Provider",
    "UNAVAILABLE",
    "american_to_decimal",
    "prob_to_decimal",
    "VENUE_SPORTSBOOK",
    "VENUE_PREDICTION_MARKET",
    "venue_type",
    "is_prediction_market",
    "venue_types",
]
