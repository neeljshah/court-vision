"""scripts.platformkit.odds_provider.pinnacle -- keyless Pinnacle sharp-line provider.

Pinnacle is the sharpest sportsbook (lowest vig, market-efficient closing line).
Its guest API at guest.api.arcadia.pinnacle.com/0.1 is publicly accessible with
no auth -- the same endpoint the legacy pinnacle_scraper.py uses.

Flow:
  1. GET /leagues/{league_id}/matchups -> parent game matchups with team names.
  2. GET /leagues/{league_id}/markets/straight -> moneyline/spread/total markets.
  3. Join on matchupId; keep only period=0 (full-game) markets; convert American
     price field -> decimal odds; emit one OddsEvent per game tagged venue='pinnacle'
     carrying moneyline AND (when quoted) spread AND total nodes.

Markets parsed (all period=0 / full-game only):
  * moneyline -> prices['pinnacle']['home'/'away'] (decimal).
  * spread    -> prices['pinnacle']['spread'] = {'home': {'line','odds'},
                 'away': {'line','odds'}}. Each price leg carries its own `points`
                 handicap (home negative when favoured); `designation` maps the leg.
  * total     -> prices['pinnacle']['total']  = {'over': {'line','odds'},
                 'under': {'line','odds'}}. `points` is the O/U line. Pinnacle
                 totals omit `designation`, so legs are paired by index (over=0,
                 under=1) per the legacy scraper convention.
A spread/total node is emitted ONLY when both legs have a usable line AND price;
a partial market is dropped (never fabricated). This mirrors the extended per-venue
shape that markets.quotes_from_aggregate consumes (same as the ESPN provider).

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

from .base import OddsEvent, unavailable, VENUE_SPORTSBOOK
from .http_cache import disk_cache_get_meta, http_get_json
from .pinnacle_parse import moneyline_sides, spread_node, total_node

# Backward-compatible private aliases (tests / callers may import these names).
_spread_node = spread_node
_total_node = total_node

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


# ---------------------------------------------------------------------------
# Pure parsers -- no I/O; unit-testable on canned payloads. The per-market leg
# parsers (moneyline_sides / spread_node / total_node) live in pinnacle_parse.
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
    - Only period=0 (full-game) moneyline/spread/total markets are included.
    - Moneyline -> sides['home'/'away']; spread -> sides['spread']; total ->
      sides['total'] (extended node shape consumed by markets.quotes_from_aggregate).
      A spread/total node is added ONLY when both legs have a line AND a price.
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

    # Build matchupId -> market maps (period=0 / full-game only; first seen wins)
    # for each of moneyline, spread, total.
    ml_by_matchup: Dict[int, Dict[str, Any]] = {}
    spread_by_matchup: Dict[int, Dict[str, Any]] = {}
    total_by_matchup: Dict[int, Dict[str, Any]] = {}
    _index = {"moneyline": ml_by_matchup, "spread": spread_by_matchup,
              "total": total_by_matchup}
    for mk in markets or []:
        target = _index.get(mk.get("type"))
        if target is None:
            continue
        if mk.get("period") != 0:
            continue
        mid = mk.get("matchupId")
        if mid is None or mid in target:
            continue
        target[mid] = mk

    out: List[OddsEvent] = []
    for game_id, mu in parent_by_id.items():
        home, away = _team_names(mu.get("participants") or [])
        if not home or not away:
            continue
        start_time = mu.get("startTime")

        # Build the prices dict for the 'pinnacle' venue: moneyline + spread + total.
        prices: Dict[str, Dict[str, Any]] = {}
        sides: Dict[str, Any] = {}
        mk = ml_by_matchup.get(game_id)
        if mk:
            sides.update(moneyline_sides(mk.get("prices") or []))
        spread_mk = spread_by_matchup.get(game_id)
        if spread_mk:
            spread = spread_node(spread_mk.get("prices") or [])
            if spread is not None:
                sides["spread"] = spread
        total_mk = total_by_matchup.get(game_id)
        if total_mk:
            total = total_node(total_mk.get("prices") or [])
            if total is not None:
                sides["total"] = total
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
    "_spread_node",
    "_total_node",
    "_LEAGUE_ID",
    "VENUE_SPORTSBOOK",
]
