"""scripts.platformkit.frontend.feed_bovada — FREE live odds from Bovada's public coupon API.

HONEST (binding): markets are efficient — NO model edge is claimed.  The ONLY value
this feed adds is line-shopping / devig / CLV: Bovada quotes Moneyline, Point Spread,
and Total prices independently of ESPN/DraftKings, so pairing these two free sources
(feed_espn + feed_bovada) gives >=2 books per game and lights up cross-book arbitrage
detection and CLV tracking.  Never claim a model prediction edge based on this data.

Bovada coupon endpoint (no API key, no auth):
  https://www.bovada.lv/services/sports/event/coupon/events/A/description/<path>
  ?marketFilterId=def&lang=en

Response shape (top-level list of "groups"):
  [ { "events": [
      { "id": str, "startTime": int (epoch ms),
        "competitors": [{"name": str, "home": bool}, ...],
        "displayGroups": [
          { "markets": [
            { "description": "Moneyline"|"Point Spread"|"Total",
              "outcomes": [
                { "description": "home team"|"away team"|"Over"|"Under",
                  "price": {"american": str, "decimal": str, "handicap": str|null}
                }, ...
              ] }
          ] }
        ] }
  ] } ]

INJECTABLE http_get: tests pass a synthetic callable; production uses urllib.
NO network at import time or in tests.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.frontend.feed import (
    GameOdds,
    OddsFeed,
    Quote,
    american_to_decimal,
    _mk_game_id,
)
from scripts.platformkit.frontend.board import _safe_float

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 12
_BASE_URL = (
    "https://www.bovada.lv/services/sports/event/coupon/events/A/description"
    "/{path}?marketFilterId=def&lang=en"
)

BOVADA_NOTE = (
    "Free Bovada public coupon feed (no API key).  Quotes REAL prices for "
    "Moneyline, Point Spread, and Total markets.  The only value is "
    "line-shopping / devig / CLV — NOT model alpha.  Markets are efficient."
)

# Platform sport_id -> Bovada URL path(s).  tennis_atp has no reliable Bovada
# coupon -> returns [] gracefully.
_SPORT_PATHS: Dict[str, List[str]] = {
    "basketball_nba": ["basketball/nba"],
    "mlb_sbro": ["baseball/mlb"],
    "soccer_fd": [
        "soccer/epl",
        "soccer/la-liga",
        "soccer/champions-league",
    ],
    "tennis_atp": [],  # no reliable Bovada coupon -> [] gracefully
}

# Bovada "description" strings -> canonical market keys
_MARKET_MAP: Dict[str, str] = {
    "moneyline": "h2h",
    "point spread": "spreads",
    "total": "totals",
}

# Bovada outcome "description" strings (lower) -> canonical side names
_SIDE_MAP: Dict[str, str] = {
    "over": "over",
    "under": "under",
}


def _http_json(url: str) -> Dict[str, Any]:
    """Default production getter (urllib + browser UA).  Never used in tests.

    Returns {} on any error rather than raising.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec GET only
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guard
        logger.warning("Bovada GET failed %s: %s", url, exc)
        return {}


def _epoch_ms_to_iso(epoch_ms: Any) -> Optional[str]:
    """Convert an epoch-milliseconds integer to an ISO-8601 UTC string."""
    try:
        ts = int(epoch_ms) / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


class BovadaFreeFeed(OddsFeed):
    """Live free odds feed from Bovada's public coupon JSON (no API key required).

    Provides real Moneyline / Point Spread / Total prices under book label "bovada".
    Combining with EspnFreeFeed yields >=2 books per game — a prerequisite for
    cross-book line-shopping and CLV tracking.

    HONEST: the sole value is data diversity for line-shop/devig/CLV, NOT a model edge.
    """

    name = "bovada_free"
    note = BOVADA_NOTE

    def __init__(
        self,
        http_get: Optional[Callable[[str], Any]] = None,
    ) -> None:
        """Initialise the feed.

        Args:
            http_get: Injectable HTTP callable (url -> dict or list).  Tests pass a
                      synthetic stub here; production leaves it None (uses urllib).
        """
        self._http_get: Callable[[str], Any] = (
            http_get if http_get is not None else _http_json
        )

    def is_live(self) -> bool:
        """True — this feed speaks to Bovada's real-time coupon endpoint."""
        return True

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        """Return normalized GameOdds for a platform sport id, optionally for one date.

        Args:
            sport:  Platform sport id e.g. "basketball_nba".
            date:   Optional YYYY-MM-DD filter; events outside this date are dropped.

        Returns:
            List[GameOdds] — empty list on any network/parse failure (never raises).
        """
        routes = _SPORT_PATHS.get(sport, [])
        games: List[GameOdds] = []
        for path in routes:
            url = _BASE_URL.format(path=path)
            try:
                payload = self._http_get(url)
            except Exception as exc:  # pragma: no cover - per-route guard
                logger.warning("Bovada fetch failed %s: %s", path, exc)
                continue
            try:
                parsed = self._normalize(payload, sport)
            except Exception as exc:  # pragma: no cover - parse guard
                logger.warning("Bovada normalize failed %s: %s", path, exc)
                continue
            for g in parsed:
                if date is not None and not (g.commence_time or "").startswith(date):
                    continue
                games.append(g)
        return games

    @staticmethod
    def _normalize(payload: Any, sport: str) -> List[GameOdds]:
        """PURE: Bovada coupon payload -> List[GameOdds].

        Accepts the top-level list-of-groups that Bovada returns.  Exercised by tests
        with a synthetic dict — NO network.  Per-event errors are logged + skipped.

        Args:
            payload:  Raw Bovada coupon response (list of group dicts or empty/garbage).
            sport:    Platform sport id to embed in GameOdds.

        Returns:
            List[GameOdds] — may be empty; never raises.
        """
        if not isinstance(payload, list):
            return []
        games: List[GameOdds] = []
        for group in payload:
            if not isinstance(group, dict):
                continue
            for ev in group.get("events", []) or []:
                try:
                    g = BovadaFreeFeed._parse_event(ev, sport)
                except Exception as exc:  # per-event guard
                    logger.warning("Bovada event parse failed: %s", exc)
                    continue
                if g is not None:
                    games.append(g)
        return games

    @staticmethod
    def _parse_event(ev: Dict[str, Any], sport: str) -> Optional[GameOdds]:
        """Parse a single Bovada event dict into a GameOdds object."""
        if not isinstance(ev, dict):
            return None
        home, away = BovadaFreeFeed._teams(ev)
        if home is None or away is None:
            return None
        start_time = ev.get("startTime")
        commence = _epoch_ms_to_iso(start_time) if start_time is not None else None
        date_str = commence[:10] if commence else None
        quotes: List[Quote] = []
        for dg in ev.get("displayGroups", []) or []:
            for mkt in (dg or {}).get("markets", []) or []:
                for q in BovadaFreeFeed._market_quotes(mkt, home, away):
                    quotes.append(q)
        if not quotes:
            return None
        return GameOdds(
            _mk_game_id(sport, date_str, away, home),
            sport, home, away, commence, quotes, "bovada_free",
        )

    @staticmethod
    def _teams(ev: Dict[str, Any]):
        """Extract (home_name, away_name) from competitors list."""
        home = away = None
        for comp in ev.get("competitors", []) or []:
            if not isinstance(comp, dict):
                continue
            name = comp.get("name")
            if name is None:
                continue
            if comp.get("home") is True:
                home = str(name)
            else:
                away = str(name)
        return home, away

    @staticmethod
    def _market_quotes(mkt: Dict[str, Any], home: str, away: str) -> List[Quote]:
        """One Bovada market dict -> zero or more Quote objects."""
        if not isinstance(mkt, dict):
            return []
        desc = str(mkt.get("description") or "").strip().lower()
        market_key = _MARKET_MAP.get(desc)
        if market_key is None:
            return []
        quotes: List[Quote] = []
        for oc in mkt.get("outcomes", []) or []:
            if not isinstance(oc, dict):
                continue
            price_d = oc.get("price") or {}
            dec = _safe_float(price_d.get("decimal"))
            if dec is None:
                dec = american_to_decimal(price_d.get("american"))
            if dec is None:
                continue
            line = _safe_float(price_d.get("handicap"))
            oc_desc = str(oc.get("description") or "").strip().lower()
            side = BovadaFreeFeed._resolve_side(oc_desc, home, away, market_key)
            quotes.append(Quote("bovada", market_key, side, dec, line=line))
        return quotes

    @staticmethod
    def _resolve_side(
        oc_desc: str, home: str, away: str, market_key: str
    ) -> str:
        """Map an outcome description string to a canonical side label."""
        # Direct over/under match
        if oc_desc in _SIDE_MAP:
            return _SIDE_MAP[oc_desc]
        # Team name match (h2h / spreads)
        if oc_desc == home.lower():
            return "home"
        if oc_desc == away.lower():
            return "away"
        # Bovada uses "home team" / "away team" in some markets
        if "home" in oc_desc:
            return "home"
        if "away" in oc_desc:
            return "away"
        return oc_desc  # fallback: preserve raw string


__all__ = ["BovadaFreeFeed", "BOVADA_NOTE", "_SPORT_PATHS"]
