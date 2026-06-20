"""scripts.platformkit.odds_provider.pinnacle -- keyless Pinnacle sharp-line provider.

Pinnacle is the sharpest sportsbook (lowest vig, market-efficient closing line).
Its guest API at guest.api.arcadia.pinnacle.com/0.1 is publicly accessible with
no auth -- the same endpoint the legacy pinnacle_scraper.py uses.

Flow:
  1. GET /leagues/{league_id}/matchups -> parent game matchups with team names.
  2. GET /leagues/{league_id}/markets/straight -> moneyline/spread/total markets.
  3. Join on matchupId; keep only period=0 moneyline markets; convert American
     price field -> decimal odds; emit one OddsEvent per game tagged venue='pinnacle'.

Price convention: Pinnacle's `price` field is American odds (e.g. -110, +150).
We convert to decimal (>1.0) via american_to_decimal before emitting.

Honesty:
  * venue = 'pinnacle', venue_type = VENUE_SPORTSBOOK.
  * Empty/unreachable API -> [] (no exception, no fabricated price).
  * Network absent / unexpected shape -> UNAVAILABLE sentinel.
  * No $ or P&L field. No edge claim.

Sport -> Pinnacle league ID mapping (the IDs that have game markets on the API):
  nba: 487,  mlb: 246,  soccer: 1980 (EPL),  soccer_intl: 2764 (FIFA WC),
  tennis: 12 (ATP)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, american_to_decimal, unavailable, VENUE_SPORTSBOOK
from .http_cache import disk_cache_get_meta, http_get_json

logger = logging.getLogger(__name__)

_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"

# Pinnacle league IDs for each supported sport key.
_LEAGUE_ID: Dict[str, int] = {
    "nba":         487,
    "mlb":         246,
    "soccer":      1980,
    "soccer_intl": 2764,
    "tennis":      12,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _team_names(participants: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Extract (home, away) from a Pinnacle matchup participants list.

    Pinnacle uses alignment='home'/'away' on each participant. When both are
    found the canonical pair is returned; otherwise ('', '') is returned so the
    caller can skip the event (never guessed).
    """
    home = away = ""
    for p in participants or []:
        align = (p.get("alignment") or "").lower()
        name = (p.get("name") or "").strip()
        if align == "home":
            home = name
        elif align == "away":
            away = name
    return home, away


def _safe_american(value: Any) -> Optional[float]:
    """Parse an American moneyline int from a Pinnacle price record -> decimal.

    Pinnacle's prices[].price field is an integer American odds value (e.g. -110,
    +150). None on any conversion failure.
    """
    return american_to_decimal(value)


# ---------------------------------------------------------------------------
# Pure parsers -- no I/O; unit-testable on canned payloads.
# ---------------------------------------------------------------------------

def parse_games(
    matchups: List[Dict[str, Any]],
    markets: List[Dict[str, Any]],
    sport: str,
    as_of: Optional[str] = None,
) -> List[OddsEvent]:
    """Turn Pinnacle matchups + straight markets into normalized OddsEvents.

    Pure; safe to unit-test on canned payloads.

    Rules applied:
    - Only parent matchups (those without type='special' and without parentId)
      produce game entries; special/prop matchups are skipped.
    - Only period=0 (full-game) moneyline markets are included in prices.
    - A game with no usable moneyline is still emitted (empty prices dict) when
      team names are present -- the event is real, just no price to show yet.
    - Games with empty home OR empty away name are skipped.
    - Prices[].designation ('home'/'away') maps each leg to the correct side.
      When designation is absent the first price is treated as home, second away.
    - All prices are converted from American to decimal (>1.0); invalid / missing
      prices are omitted (never fabricated).
    - venue label is always 'pinnacle' (VENUE_SPORTSBOOK).
    - as_of is the TRUE fetched-at (cache-honest, stale-never-green).
    """
    as_of = as_of or _now_iso()

    # Index parent matchups by id.
    parent_by_id: Dict[int, Dict[str, Any]] = {}
    for mu in matchups or []:
        # A parent game has no parentId and its type is not 'special'.
        if mu.get("parentId") is not None or mu.get("type") == "special":
            continue
        mid = mu.get("id")
        if mid is not None:
            parent_by_id[mid] = mu

    # Build a matchupId -> moneyline market map (period=0 only; keep first seen).
    ml_by_matchup: Dict[int, Dict[str, Any]] = {}
    for mk in markets or []:
        if mk.get("type") != "moneyline":
            continue
        if mk.get("period") != 0:
            continue
        mid = mk.get("matchupId")
        if mid is None:
            continue
        if mid not in ml_by_matchup:
            ml_by_matchup[mid] = mk

    out: List[OddsEvent] = []
    for game_id, mu in parent_by_id.items():
        home, away = _team_names(mu.get("participants") or [])
        if not home or not away:
            continue
        start_time = mu.get("startTime")

        # Build the prices dict for the 'pinnacle' venue.
        prices: Dict[str, Dict[str, Optional[float]]] = {}
        mk = ml_by_matchup.get(game_id)
        if mk:
            prs = mk.get("prices") or []
            h_dec: Optional[float] = None
            a_dec: Optional[float] = None
            for pr in prs:
                desig = (pr.get("designation") or "").lower()
                dec = _safe_american(pr.get("price"))
                if desig == "home":
                    h_dec = dec
                elif desig == "away":
                    a_dec = dec
            # Fallback: when designation is absent, use index order (home, away).
            if h_dec is None and a_dec is None and len(prs) >= 2:
                h_dec = _safe_american(prs[0].get("price"))
                a_dec = _safe_american(prs[1].get("price"))
            # Emit only sides that are genuinely present (never fabricate).
            sides: Dict[str, Optional[float]] = {}
            if h_dec is not None:
                sides["home"] = h_dec
            if a_dec is not None:
                sides["away"] = a_dec
            if sides:
                prices["pinnacle"] = sides

        out.append(OddsEvent(
            event_id=str(game_id),
            sport=sport,
            home=home,
            away=away,
            commence_time=str(start_time) if start_time else None,
            prices=prices,
            source="pinnacle",
            as_of=as_of,
        ))
    return out


# ---------------------------------------------------------------------------
# Provider class.
# ---------------------------------------------------------------------------

class PinnacleProvider:
    """Keyless Pinnacle sharp-line provider. fetch(sport) -> list[OddsEvent] | UNAVAILABLE.

    Two API calls per fetch (matchups + straight markets), both covered by the
    shared TTL disk cache. A fetch failure on EITHER call degrades to UNAVAILABLE
    rather than emitting partial / fabricated data.

    Venue label: 'pinnacle' (VENUE_SPORTSBOOK).
    Prices: decimal (>1.0), converted from Pinnacle American moneyline integers.
    """

    name = "pinnacle"

    def __init__(
        self,
        http_get: Callable[[str], Any] = http_get_json,
        *,
        use_cache: bool = True,
    ) -> None:
        self._http_get = http_get
        self._use_cache = use_cache

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso). fetched_at is the TRUE network fetch time
        of the body (original fetch time on a cache hit, never now()) so a
        cached/dead feed cannot re-stamp itself fresh (stale-never-green).
        """
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        """Fetch and normalize Pinnacle moneyline odds for *sport*.

        Returns list[OddsEvent] on success (may be empty when no games are live),
        or an unavailable() sentinel when:
          - sport is not in the supported league map
          - either API call fails or returns an unexpected shape
        Never raises; never fabricates a price; never claims an edge.
        """
        sport = sport.lower()
        league_id = _LEAGUE_ID.get(sport)
        if league_id is None:
            return unavailable(f"pinnacle: unsupported sport '{sport}'")

        matchups_url = f"{_BASE}/leagues/{league_id}/matchups"
        markets_url = f"{_BASE}/leagues/{league_id}/markets/straight"

        try:
            matchups_body, as_of = self._get(matchups_url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("pinnacle matchups failed for %s: %s", sport, exc)
            return unavailable(f"pinnacle matchups call failed ({type(exc).__name__})")

        if not isinstance(matchups_body, list):
            return unavailable("pinnacle: unexpected matchups shape (not a list)")

        try:
            markets_body, markets_as_of = self._get(markets_url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("pinnacle markets failed for %s: %s", sport, exc)
            return unavailable(f"pinnacle markets call failed ({type(exc).__name__})")

        if not isinstance(markets_body, list):
            return unavailable("pinnacle: unexpected markets shape (not a list)")

        # as_of = OLDEST of the two fetch timestamps (stale-never-green floor).
        true_as_of = _oldest_as_of(as_of, markets_as_of)
        return parse_games(matchups_body, markets_body, sport, true_as_of)


def _oldest_as_of(a: str, b: str) -> str:
    """Return the older (earlier) of two ISO-8601 timestamps.

    Uses lexicographic comparison which is correct for UTC ISO strings of the
    same format. Falls back to *a* on any parse failure.
    """
    try:
        ta = datetime.fromisoformat(a.replace("Z", "+00:00"))
        tb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return a if ta <= tb else b
    except Exception:  # noqa: BLE001
        return a


__all__ = [
    "PinnacleProvider",
    "parse_games",
    "_LEAGUE_ID",
    "VENUE_SPORTSBOOK",
]
