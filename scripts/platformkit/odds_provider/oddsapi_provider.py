"""scripts.platformkit.odds_provider.oddsapi_provider -- The Odds API multi-book shim.

Fetches sportsbook moneyline/spread/total from api.the-odds-api.com/v4.
Requires ODDS_API_KEY env var; UNAVAILABLE immediately when key absent (no stub).

API: GET /v4/sports/{sport_key}/odds?apiKey=<key>&regions=us&markets=h2h,spreads,totals
     &oddsFormat=decimal  -> list[event{bookmakers:[{title, markets:[{key,outcomes}]}]}]
Prices already in decimal (>1.0). Venue labels: "oddsapi:<BookTitle>".
No price fabricated; no edge/ROI claim; calibration only.

sport_key map: nba->basketball_nba, mlb->baseball_mlb, soccer->soccer_epl,
               soccer_intl->soccer_fifa_world_cup, tennis->tennis_atp_us_open
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, unavailable, is_unavailable
from .http_cache import disk_cache_get_meta, http_get_json

logger = logging.getLogger(__name__)

_BASE = "https://api.the-odds-api.com/v4/sports"
_MIN_BOOKS = 3   # acceptance floor: at least this many distinct books expected live

_SPORT_KEY: Dict[str, str] = {
    "nba":         "basketball_nba",
    "mlb":         "baseball_mlb",
    "soccer":      "soccer_epl",
    "soccer_intl": "soccer_fifa_world_cup",
    "tennis":      "tennis_atp_us_open",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _api_key() -> Optional[str]:
    """Read ODDS_API_KEY from ENV only.  Returns None when absent/blank."""
    v = os.environ.get("ODDS_API_KEY", "")
    return v.strip() if v.strip() else None


# --------------------------------------------------------------------------- #
# Pure parsers (no I/O; unit-testable on canned payloads).
# --------------------------------------------------------------------------- #

def _safe_decimal(value: Any) -> Optional[float]:
    """Parse a decimal odds float; None on missing / non-numeric / <=1.0."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 1.0 else None


def _parse_h2h(outcomes: List[Dict[str, Any]],
               home: str, away: str,
               ) -> Dict[str, Optional[float]]:
    """Extract moneyline home/away decimal prices from an h2h outcomes list.

    Outcomes are matched to home/away by exact name.  Missing / unrecognised
    teams -> that side is absent (never fabricated).
    """
    sides: Dict[str, Optional[float]] = {}
    for o in outcomes or []:
        name = str(o.get("name") or "")
        price = _safe_decimal(o.get("price"))
        if price is None:
            continue
        if name == home:
            sides["home"] = price
        elif name == away:
            sides["away"] = price
    return sides


def _parse_spread(outcomes: List[Dict[str, Any]],
                  home: str, away: str,
                  ) -> Optional[Dict[str, Any]]:
    """Build a spread sub-node {home:{line,odds}, away:{line,odds}} if both sides present."""
    h_node: Optional[Dict[str, Any]] = None
    a_node: Optional[Dict[str, Any]] = None
    for o in outcomes or []:
        name = str(o.get("name") or "")
        price = _safe_decimal(o.get("price"))
        try:
            point = float(o.get("point"))
        except (TypeError, ValueError):
            continue
        if price is None:
            continue
        if name == home:
            h_node = {"line": point, "odds": price}
        elif name == away:
            a_node = {"line": point, "odds": price}
    if h_node is None or a_node is None:
        return None
    return {"home": h_node, "away": a_node}


def _parse_total(outcomes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a total sub-node {over:{line,odds}, under:{line,odds}} if both present."""
    o_node: Optional[Dict[str, Any]] = None
    u_node: Optional[Dict[str, Any]] = None
    for o in outcomes or []:
        name = str(o.get("name") or "").lower()
        price = _safe_decimal(o.get("price"))
        try:
            point = float(o.get("point"))
        except (TypeError, ValueError):
            continue
        if price is None:
            continue
        if name == "over":
            o_node = {"line": point, "odds": price}
        elif name == "under":
            u_node = {"line": point, "odds": price}
    if o_node is None or u_node is None:
        return None
    return {"over": o_node, "under": u_node}


def parse_bookmakers(event: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract per-venue price dict from one Odds API event object.

    Returns {venue_label: {"home": dec, "away": dec,
                           "spread": {...}|absent, "total": {...}|absent}}
    where venue_label = "oddsapi:<BookTitle>".  A bookmaker that does not
    quote a side is absent (never guessed).  Malformed bookmakers are skipped
    (never crash).
    """
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    out: Dict[str, Dict[str, Any]] = {}
    for bk in event.get("bookmakers") or []:
        try:
            title = str(bk.get("title") or bk.get("key") or "")
            if not title:
                continue
            venue = f"oddsapi:{title}"
            mkt_map: Dict[str, List[Dict[str, Any]]] = {}
            for mkt in bk.get("markets") or []:
                key = str(mkt.get("key") or "")
                mkt_map[key] = list(mkt.get("outcomes") or [])
            sides: Dict[str, Any] = {}
            # Moneyline (h2h)
            if "h2h" in mkt_map:
                ml = _parse_h2h(mkt_map["h2h"], home, away)
                sides.update(ml)
            # Spread -- additive only; a missing spread never corrupts moneyline
            if "spreads" in mkt_map:
                sp = _parse_spread(mkt_map["spreads"], home, away)
                if sp is not None:
                    sides["spread"] = sp
            # Total -- additive only
            if "totals" in mkt_map:
                tot = _parse_total(mkt_map["totals"])
                if tot is not None:
                    sides["total"] = tot
            if sides:
                out[venue] = sides
        except Exception:  # noqa: BLE001 -- one bad bookmaker must not abort the rest
            continue
    return out


def parse_events(payload: Any, sport: str,
                 as_of: Optional[str] = None) -> List[OddsEvent]:
    """Turn a raw Odds API v4 response list into normalized OddsEvents.

    Pure; unit-testable on canned payloads.  Events with no usable bookmakers
    or no home/away name are skipped.  *as_of* is the TRUE fetched-at (cache-honest).
    """
    as_of = as_of or _now_iso()
    if not isinstance(payload, list):
        return []
    out: List[OddsEvent] = []
    for ev in payload:
        if not isinstance(ev, dict):
            continue
        home = str(ev.get("home_team") or "").strip()
        away = str(ev.get("away_team") or "").strip()
        if not home or not away:
            continue
        eid = str(ev.get("id") or "")
        commence = ev.get("commence_time")
        prices = parse_bookmakers(ev)
        if not prices:
            continue
        out.append(OddsEvent(
            event_id=eid, sport=sport, home=home, away=away,
            commence_time=str(commence) if commence else None,
            prices=prices, source="oddsapi", as_of=as_of))
    return out


# --------------------------------------------------------------------------- #
# Provider class.
# --------------------------------------------------------------------------- #

class OddsApiProvider:
    """The Odds API multi-book team-market provider.

    Returns list[OddsEvent] with 5+ sportsbook venues (DraftKings, FanDuel,
    BetMGM, Caesars, PointsBet, ...) when ODDS_API_KEY is set; returns
    UNAVAILABLE (reason stated, no fabricated price) when the key is absent.

    Provider contract (mirrors espn.py / kalshi.py):
      * fetch() never raises.
      * All prices are decimal (>1.0) and come directly from the API -- no
        fabrication, no stub, no edge claim.
      * Venue labels: "oddsapi:<BookTitle>" (e.g. "oddsapi:DraftKings").
      * Venue type = VENUE_SPORTSBOOK (these are real regulated books).
    """

    name = "oddsapi"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True,
                 regions: str = "us",
                 markets: str = "h2h,spreads,totals") -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._regions = regions
        self._markets = markets

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso) -- TRUE fetch time (stale-never-green)."""
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        """Fetch multi-book odds for *sport*.

        Returns list[OddsEvent] on success, or unavailable() when:
          * ODDS_API_KEY env var is absent/blank
          * sport is not supported
          * API call fails or returns unexpected shape
          * The parsed payload contains zero events (not an error, just empty)

        Never raises; never fabricates a price; never claims an edge.
        """
        sport = sport.lower()
        key = _api_key()
        if not key:
            return unavailable("oddsapi: ODDS_API_KEY env var not set")
        sport_key = _SPORT_KEY.get(sport)
        if not sport_key:
            return unavailable(f"oddsapi: unsupported sport '{sport}'")
        params = urllib.parse.urlencode({
            "apiKey":      key,
            "regions":     self._regions,
            "markets":     self._markets,
            "oddsFormat":  "decimal",
        })
        url = f"{_BASE}/{sport_key}/odds?{params}"
        try:
            body, fetched_at = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("oddsapi fetch failed for %s: %s", sport, exc)
            return unavailable(f"oddsapi call failed ({type(exc).__name__})")
        if not isinstance(body, list):
            return unavailable("oddsapi: unexpected payload shape (not a list)")
        events = parse_events(body, sport, fetched_at)
        return events


__all__ = [
    "OddsApiProvider",
    "parse_events",
    "parse_bookmakers",
    "_parse_h2h",
    "_parse_spread",
    "_parse_total",
]
