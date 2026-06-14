"""scripts.platformkit.frontend.feed_espn — FREE live odds feed from ESPN.

HONEST (binding): markets are efficient — NO model edge is ever claimed.
Two ESPN shapes consumed: site scoreboard (site.api.espn.com/.../{path}/scoreboard)
+ per-event core (sports.core.api.espn.com/v2/.../events/{eid}/.../odds).
Iterates EVERY provider/book per event; multi-book line-shop/CLV lights up
automatically when >=2 books quote the same outcome.
Two provider shapes handled: DraftKings (American moneyLine) and Bet365
(homeTeamOdds.odds.value decimal ratio). Soccer 1X2 draw included.
NO network at import time/in tests: http_get is INJECTABLE.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.frontend.feed import (
    GameOdds,
    OddsFeed,
    Quote,
    american_to_decimal,
    normalize_book,
    _mk_game_id,
)
from scripts.platformkit.frontend.board import _safe_float

logger = logging.getLogger(__name__)

_SITE_BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
_CORE_BASE = (
    "https://sports.core.api.espn.com/v2/sports/{sportcore}/leagues/{league}"
    "/events/{eid}/competitions/{eid}/odds"
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 12

# ESPN supplies spread/total LINES but NOT their prices. We assume the -110
# market-standard price (decimal 1.9091) for those two sides so the line shows
# on the board.  HONEST: this is an ASSUMED price, not a quoted one — only the
# h2h (moneyLine) prices are real.  A real spread/total price needs a feed that
# quotes it (a paid book API), at which point line-shop on those markets is valid.
_ASSUMED_PRICE_DECIMAL = 1.9091

# platform sport_id -> [(site_path, sportcore, league), ...]
_SPORT_PATHS: Dict[str, List[Tuple[str, str, str]]] = {
    "basketball_nba": [("basketball/nba", "basketball", "nba")],
    "mlb_sbro": [("baseball/mlb", "baseball", "mlb")],
    "soccer_fd": [
        ("soccer/eng.1", "soccer", "eng.1"),
        ("soccer/esp.1", "soccer", "esp.1"),
        ("soccer/ita.1", "soccer", "ita.1"),
        ("soccer/ger.1", "soccer", "ger.1"),
        ("soccer/fra.1", "soccer", "fra.1"),
    ],
    "tennis_atp": [],  # ESPN tennis has no reliable betting odds -> [] gracefully
}

ESPN_NOTE = (
    "Free ESPN public odds (~1 book/game, currently DraftKings). "
    "h2h prices are real (moneyLine); spread/total prices are the ASSUMED -110 "
    "standard (ESPN gives lines only). Powers live board + CLV + freshness; "
    "cross-book arbitrage needs >=2 books quoting real prices."
)


def _http_json(url: str) -> Dict[str, Any]:
    """Default network getter (urllib + browser UA + timeout).  PRODUCTION only.

    Never used in tests — http_get is injected there.  Returns {} on any error.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network guard
        logger.warning("ESPN GET failed %s: %s", url, exc)
        return {}


class EspnFreeFeed(OddsFeed):
    """Live free multi-source feed normalizing ESPN scoreboard + core odds."""

    name = "espn_free"
    note = ESPN_NOTE

    def __init__(
        self,
        http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
        fetch_core: bool = True,
    ) -> None:
        self._http_get = http_get if http_get is not None else _http_json
        self.fetch_core = fetch_core
        self.skipped_no_odds = 0  # count of events with no parseable odds

    def is_live(self) -> bool:
        return True

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        """Return normalized GameOdds for a sport (optionally one YYYY-MM-DD)."""
        self.skipped_no_odds = 0
        routes = _SPORT_PATHS.get(sport, [])
        games: List[GameOdds] = []
        for site_path, sportcore, league in routes:
            try:
                payload = self._http_get(_SITE_BASE.format(path=site_path))
            except Exception as exc:  # never crash on a bad route
                logger.warning("scoreboard fetch failed %s: %s", site_path, exc)
                continue
            for ev in (payload or {}).get("events", []) or []:
                try:
                    g = self._parse_event(ev, sport, sportcore, league)
                except Exception as exc:  # per-event guard
                    logger.warning("event parse failed: %s", exc)
                    continue
                if g is None:
                    continue
                if date is not None and not (g.commence_time or "").startswith(date):
                    continue
                games.append(g)
        return games

    def _parse_event(
        self, ev: Dict[str, Any], sport: str, sportcore: str, league: str
    ) -> Optional[GameOdds]:
        """One ESPN scoreboard event (+core odds) -> GameOdds, or None if no odds."""
        comps = ev.get("competitions") or []
        if not comps:
            return None
        comp = comps[0]
        home, away = self._teams(comp)
        if home is None or away is None:
            return None
        commence = ev.get("date")
        eid = ev.get("id")
        odds_items: List[Dict[str, Any]] = list(comp.get("odds") or [])
        if self.fetch_core and eid is not None:
            odds_items.extend(self._core_odds(eid, sportcore, league))
        quotes: List[Quote] = []
        seen: set = set()
        for item in odds_items:
            for q in self._provider_quotes(item):
                key = (q.book, q.market, q.side)
                if key in seen:
                    continue
                seen.add(key)
                quotes.append(q)
        if not quotes:
            self.skipped_no_odds += 1
            return None
        date = str(commence)[:10] if commence else None
        ct = str(commence) if commence else None
        return GameOdds(
            _mk_game_id(sport, date, away, home), sport, home, away, ct, quotes, self.name
        )

    def _core_odds(self, eid: Any, sportcore: str, league: str) -> List[Dict[str, Any]]:
        """Fetch the per-event core odds items (more books when available)."""
        url = _CORE_BASE.format(sportcore=sportcore, league=league, eid=eid)
        try:
            payload = self._http_get(url)
        except Exception as exc:  # core endpoint is best-effort
            logger.warning("core odds fetch failed %s: %s", eid, exc)
            return []
        return list((payload or {}).get("items", []) or [])

    @staticmethod
    def _teams(comp: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        home = away = None
        for c in comp.get("competitors") or []:
            team = c.get("team") or {}
            name = team.get("displayName") or team.get("abbreviation")
            if name is None:
                continue
            if c.get("homeAway") == "home":
                home = str(name)
            elif c.get("homeAway") == "away":
                away = str(name)
        return home, away

    @staticmethod
    def _team_decimal(side_dict: Dict[str, Any]) -> Optional[float]:
        """Decimal h2h price from homeTeamOdds/awayTeamOdds (two ESPN shapes).

        Shape A (DraftKings): side_dict["moneyLine"] -> American -> decimal.
        Shape B (Bet365): side_dict["odds"]["value"] -> decimal ratio (>1).
        """
        dec = american_to_decimal(side_dict.get("moneyLine"))
        if dec is not None:
            return dec
        raw = _safe_float((side_dict.get("odds") or {}).get("value"))
        return raw if (raw is not None and raw > 1.0) else None

    @staticmethod
    def _draw_decimal(item: Dict[str, Any]) -> Optional[float]:
        """Decimal draw price for soccer 1X2.  DK: American; Bet365: decimal ratio."""
        draw = item.get("drawOdds") or {}
        if not isinstance(draw, dict):
            return None
        dec = american_to_decimal(draw.get("moneyLine"))
        if dec is not None:
            return dec
        raw = _safe_float(draw.get("value"))
        return raw if (raw is not None and raw > 1.0) else None

    @staticmethod
    def _provider_quotes(item: Dict[str, Any]) -> List[Quote]:
        """One provider dict -> Quotes (h2h / draw / spreads / totals).

        Handles DraftKings shape (American moneyLine, overOdds/underOdds, drawOdds)
        and Bet365 shape (homeTeamOdds.odds.value decimal, drawOdds.value).
        HONEST: spread/overUnder are LINES not prices (_ASSUMED_PRICE_DECIMAL).
        overOdds/underOdds ARE real prices when quoted by the provider.
        """
        if not isinstance(item, dict):
            return []
        provider = item.get("provider") or {}
        book = normalize_book(provider.get("name"))
        quotes: List[Quote] = []

        hto = item.get("homeTeamOdds") or {}
        ato = item.get("awayTeamOdds") or {}

        home_dec = EspnFreeFeed._team_decimal(hto)
        away_dec = EspnFreeFeed._team_decimal(ato)
        draw_dec = EspnFreeFeed._draw_decimal(item)

        if home_dec is not None:
            quotes.append(Quote(book, "h2h", "home", home_dec))
        if away_dec is not None:
            quotes.append(Quote(book, "h2h", "away", away_dec))
        # 1X2 draw market (soccer): only emit when a genuine draw price exists
        if draw_dec is not None:
            quotes.append(Quote(book, "h2h", "draw", draw_dec))

        spread = _safe_float(item.get("spread"))
        if spread is not None:  # ASSUMED -110 price (ESPN gives line, not price)
            quotes.append(Quote(book, "spreads", "home", _ASSUMED_PRICE_DECIMAL, line=spread))
            quotes.append(Quote(book, "spreads", "away", _ASSUMED_PRICE_DECIMAL, line=-spread))

        total = _safe_float(item.get("overUnder"))
        if total is not None:
            # Use real overOdds/underOdds when the provider quotes them (American);
            # else fall back to the ASSUMED -110.  HONEST: fallback is NOT a quoted price.
            over_price = american_to_decimal(item.get("overOdds"))
            under_price = american_to_decimal(item.get("underOdds"))
            quotes.append(Quote(book, "totals", "over",
                                over_price if over_price is not None else _ASSUMED_PRICE_DECIMAL,
                                line=total))
            quotes.append(Quote(book, "totals", "under",
                                under_price if under_price is not None else _ASSUMED_PRICE_DECIMAL,
                                line=total))
        return quotes


def get_free_multi_feed(repo_root: Optional[Path] = None) -> OddsFeed:
    """Compose all FREE no-key books into one MultiFeed (ESPN + Bovada).

    With >=2 free books quoting the same game, cross-book arbitrage /
    line-shopping / CLV light up AUTOMATICALLY (markets efficient — NO model
    edge; the only value is line-shop/devig/CLV).  Lazy imports keep import-time
    light and avoid any import cycle.  A book that returns nothing (e.g. Bovada
    while network egress is blocked) degrades the merge gracefully to whatever
    books DID return — no rewrite needed when a 2nd source comes online.
    """
    from scripts.platformkit.frontend.feed_multi import MultiFeed
    from scripts.platformkit.frontend.feed_bovada import BovadaFreeFeed
    return MultiFeed([EspnFreeFeed(), BovadaFreeFeed()])


def get_feed_auto(repo_root: Optional[Path] = None, *, force_stub: bool = False) -> OddsFeed:
    """Default feed selector: paid key -> TheOddsApiFeed; else FREE multi-book.

    Order: force_stub -> on-disk StubFeed ; ODDS_API_KEY/THE_ODDS_API_KEY ->
    TheOddsApiFeed (multi-book) ; else get_free_multi_feed() (ESPN + Bovada,
    free live).  The app lights up FREE by default — no paid key required, and
    cross-book arb/line-shop/CLV activate the moment >=2 books return live data.
    """
    if force_stub:
        from scripts.platformkit.frontend.feed import StubFeed
        return StubFeed(repo_root, mode="parquet")
    key = os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")
    if key:
        from scripts.platformkit.frontend.feed import TheOddsApiFeed
        return TheOddsApiFeed(api_key=key)
    return get_free_multi_feed(repo_root)


__all__ = ["EspnFreeFeed", "get_feed_auto", "get_free_multi_feed", "ESPN_NOTE", "_SPORT_PATHS"]
