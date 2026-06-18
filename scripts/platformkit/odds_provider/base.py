"""scripts.platformkit.odds_provider.base -- normalized schema + price helpers.

The single normalized record is `OddsEvent`. Every provider parses its native
payload into a list of these (or returns the UNAVAILABLE sentinel). The prices
field is shaped EXACTLY for odds_shop: {venue: {"home": dec, "away": dec,
"draw": dec|None}} where dec is DECIMAL odds (> 1.0). A side a venue does not
quote is simply absent / None -- never fabricated.

Price conversions (pure, fully unit-tested):
  * american_to_decimal : ESPN-style American moneyline -> decimal odds.
  * prob_to_decimal      : implied probability (0..1, e.g. a Kalshi/Polymarket
                           ask price in dollars) -> decimal odds = 1/prob.

No network in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

# Sentinel returned by a provider when its source is down / disabled. A dict so it
# is JSON-serialisable and never confused with a (possibly empty) list of events.
UNAVAILABLE = {"status": "unavailable"}

# --------------------------------------------------------------------------- #
# venue_type -- an HONESTY tag distinguishing a republished SPORTSBOOK price (a
# line you can actually back at a regulated/offshore book) from a PREDICTION
# MARKET YES/NO contract (Kalshi / Polymarket). A thin PM YES ask converts to a
# decimal-looking number but is NOT a bettable sportsbook line: PM depth is tiny,
# the "price" is a last/ask on a binary contract, and surfacing it as the best
# bettable line or as an arb leg is dishonest. We tag every venue so odds_shop /
# the front end can RESTRICT the bettable-best & arb scan to sportsbooks, while
# still exposing PM prices separately for a divergence (PM-vs-book) signal.
VENUE_SPORTSBOOK = "sportsbook"
VENUE_PREDICTION_MARKET = "prediction_market"

# Prediction-market venue identities. ESPN republishes named sportsbooks under the
# "espn:<book>" prefix (those are sportsbooks); Kalshi / Polymarket are PMs. Match
# is by exact name or "<id>:" prefix, case-insensitive. Anything unknown defaults
# to SPORTSBOOK so legacy callers / book labels (e.g. "DK", "FD") are unchanged.
_PM_VENUE_IDS = frozenset({"kalshi", "polymarket", "predictit", "manifold"})


def venue_type(venue: str) -> str:
    """Classify a venue name as VENUE_SPORTSBOOK or VENUE_PREDICTION_MARKET.

    Pure + total (never raises). A prediction-market venue is matched by exact
    name or by a "<id>:" provenance prefix (case-insensitive) against the known
    PM id set; everything else -- including bare sportsbook labels and the
    "espn:<book>" republished-book prefix -- is treated as a sportsbook. The
    default-to-sportsbook fallback keeps every pre-existing caller's result
    identical (no silent reclassification of legacy book labels).
    """
    try:
        v = str(venue).strip().lower()
    except Exception:  # noqa: BLE001 -- classification must never sink a row
        return VENUE_SPORTSBOOK
    if not v:
        return VENUE_SPORTSBOOK
    head = v.split(":", 1)[0]
    if v in _PM_VENUE_IDS or head in _PM_VENUE_IDS:
        return VENUE_PREDICTION_MARKET
    return VENUE_SPORTSBOOK


def is_prediction_market(venue: str) -> bool:
    """True iff *venue* is a prediction market (Kalshi / Polymarket / ...)."""
    return venue_type(venue) == VENUE_PREDICTION_MARKET


def venue_types(venues: Any) -> Dict[str, str]:
    """Map each venue name in *venues* (iterable of names) -> its venue_type tag.

    Convenience for odds_shop: pass the keys of a book_prices dict to get the
    tag map best_line/detect-arb consume. Non-iterable input -> empty map.
    """
    try:
        return {str(v): venue_type(v) for v in venues}
    except TypeError:
        return {}


def unavailable(reason: str) -> Dict[str, str]:
    """Build an honest unavailable sentinel carrying *reason* (no fabricated data)."""
    return {"status": "unavailable", "reason": reason}


def is_unavailable(obj: Any) -> bool:
    """True iff *obj* is an unavailable sentinel (dict with status=unavailable)."""
    return isinstance(obj, dict) and obj.get("status") == "unavailable"


def american_to_decimal(american: Union[int, float]) -> Optional[float]:
    """Convert American moneyline odds to decimal odds (> 1.0).

    +150 -> 2.50 ; -175 -> 1.5714... ; 0 / None / non-numeric -> None.
    """
    try:
        a = float(american)
    except (TypeError, ValueError):
        return None
    if a == 0.0:
        return None
    if a > 0:
        return 1.0 + a / 100.0
    return 1.0 + 100.0 / abs(a)


def prob_to_decimal(prob: Union[int, float]) -> Optional[float]:
    """Convert an implied probability (0..1) to decimal odds = 1/prob.

    Prediction-market ask prices are quoted in dollars in [0, 1] which IS the
    implied probability for that side. Out-of-range / non-positive / >= 1 -> None
    (a price of 1.0 implies certainty -> 1.0 decimal, not a bettable line).
    """
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return None
    if p <= 0.0 or p >= 1.0:
        return None
    return 1.0 / p


@dataclass
class OddsEvent:
    """One normalized event with multi-venue, decimal-odds prices.

    prices: {venue: {"home": dec, "away": dec, "draw": dec|None}} -- exactly the
    shape odds_shop.summarise_twoway / best_line consume (a venue is a "book").
    A side a venue does not price is absent or None; never a guessed number.
    """

    event_id: str
    sport: str
    home: str
    away: str
    commence_time: Optional[str]
    prices: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    source: str = ""
    as_of: Optional[str] = None

    def venues(self) -> List[str]:
        """Venue names present in this event's prices."""
        return list(self.prices.keys())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "home": self.home,
            "away": self.away,
            "commence_time": self.commence_time,
            "prices": self.prices,
            "source": self.source,
            "as_of": self.as_of,
        }


@runtime_checkable
class Provider(Protocol):
    """A normalized odds source.

    fetch(sport) returns either a list[OddsEvent] on success or the UNAVAILABLE
    sentinel dict (see unavailable()) when the source is down / disabled. It must
    NEVER raise and NEVER fabricate a price.
    """

    name: str

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        ...


__all__ = [
    "OddsEvent",
    "Provider",
    "UNAVAILABLE",
    "unavailable",
    "is_unavailable",
    "american_to_decimal",
    "prob_to_decimal",
    "VENUE_SPORTSBOOK",
    "VENUE_PREDICTION_MARKET",
    "venue_type",
    "is_prediction_market",
    "venue_types",
]
