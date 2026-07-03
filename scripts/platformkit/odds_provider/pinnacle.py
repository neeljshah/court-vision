"""scripts.platformkit.odds_provider.pinnacle -- keyless Pinnacle sharp-line provider.

Pinnacle is the sharpest sportsbook (lowest vig, market-efficient closing line).
Its guest API at guest.api.arcadia.pinnacle.com/0.1 is publicly accessible with
no auth -- the same endpoint the legacy pinnacle_scraper.py uses.

Flow (per resolved league id -- see below):
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

Honesty: venue='pinnacle' (VENUE_SPORTSBOOK); empty/unreachable API -> [] (no
exception, no fabricated price); unexpected shape -> UNAVAILABLE sentinel; no
$ or P&L field; no edge claim.

Sport -> Pinnacle league id(s): nba/mlb/soccer are static (year-round leagues);
tennis/soccer_intl rotate as tournaments change and are resolved LIVE (TTL disk
cache + stale-cache fallback + self-healing 401 invalidation) by
pinnacle_league_resolver.resolve_league_ids -- see that module for why a
hardcoded rotating tournament id cannot stay fresh.
"""
from __future__ import annotations

import logging
import urllib.error
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from . import pinnacle_league_resolver
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
    "soccer_intl": 2686,
    "tennis":      12,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _team_names(participants: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Extract (home, away) via alignment='home'/'away'; ('', '') if either is
    missing so the caller can skip the event (never guessed)."""
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

    Pure; safe to unit-test on canned payloads. Rules: only parent matchups
    (no type='special', no parentId) produce games; only period=0 (full-game)
    moneyline/spread/total markets are included; moneyline -> sides['home'/
    'away'], spread -> sides['spread'], total -> sides['total'] (extended node
    shape consumed by markets.quotes_from_aggregate), added ONLY when both legs
    have a line AND a price; a game with no usable moneyline is still emitted
    (empty prices dict) when team names are present; games with an empty
    home/away name are skipped; designation ('home'/'away') maps each leg, or
    first=home/second=away when absent; all prices are American->decimal
    (>1.0), invalid/missing omitted (never fabricated); venue is always
    'pinnacle'; as_of is the TRUE fetched-at (cache-honest, stale-never-green).
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

    Two API calls per resolved league id (matchups + straight markets), both
    covered by the shared TTL disk cache. A per-league failure is isolated (see
    fetch); venue label 'pinnacle' (VENUE_SPORTSBOOK); prices are decimal (>1.0),
    converted from Pinnacle American moneyline integers.
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

    def _fetch_league(
        self, sport: str, league_id: int,
    ) -> Union[List[OddsEvent], Dict[str, str]]:
        """Fetch+parse ONE league id (one matchups call + one markets call)."""
        matchups_url = f"{_BASE}/leagues/{league_id}/matchups"
        markets_url = f"{_BASE}/leagues/{league_id}/markets/straight"

        matchups_body, as_of = self._get(matchups_url)
        if not isinstance(matchups_body, list):
            return unavailable("pinnacle: unexpected matchups shape (not a list)")

        markets_body, markets_as_of = self._get(markets_url)
        if not isinstance(markets_body, list):
            return unavailable("pinnacle: unexpected markets shape (not a list)")

        # as_of = OLDEST of the two fetch timestamps (stale-never-green floor).
        true_as_of = _oldest_as_of(as_of, markets_as_of)
        return parse_games(matchups_body, markets_body, sport, true_as_of)

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        """Resolve+fetch all live league id(s) for *sport* (static ids for
        nba/mlb/soccer; live-resolved + cached for rotating tournament sports --
        see pinnacle_league_resolver), concatenating events across leagues. A
        401 on one league (delisted/rotated) invalidates its cache entry and is
        skipped in favor of the others; any other per-league error is likewise
        skipped. Returns list[OddsEvent] (may be empty), or unavailable() when no
        id resolves or every league failed. Never raises; never fabricates data.
        """
        sport = sport.lower()
        league_ids = pinnacle_league_resolver.resolve_league_ids(
            sport, http_get=self._http_get)
        if not league_ids:
            return unavailable(f"pinnacle: no live league ids for '{sport}'")

        events: List[OddsEvent] = []
        last_reason: Optional[str] = None
        any_ok = False
        for league_id in league_ids:
            try:
                result = self._fetch_league(sport, league_id)
            except Exception as exc:  # noqa: BLE001 -- isolate one league, keep going
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 401:
                    logger.warning(
                        "pinnacle league %s 401 for %s (delisted) -- invalidating",
                        league_id, sport)
                    pinnacle_league_resolver.invalidate(sport)
                else:
                    logger.warning("pinnacle league %s failed for %s: %s",
                                    league_id, sport, exc)
                last_reason = f"pinnacle call failed ({type(exc).__name__})"
                continue
            if isinstance(result, dict):  # unavailable sentinel from this league
                last_reason = result.get("reason", "pinnacle: unavailable")
                continue
            any_ok = True
            events.extend(result)

        if not any_ok and not events:
            return unavailable(last_reason or f"pinnacle: no data for '{sport}'")
        return events


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
