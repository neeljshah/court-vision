"""scripts.platformkit.frontend.feed — multi-book odds FEED ADAPTER interface.

HONEST: markets are efficient — NO model edge is ever claimed. The only value a
feed surfaces is line-shopping / devig / CLV, which exists ONLY when >=2 distinct
books quote the same outcome. The on-disk corpus carries a single historical book
(degrades gracefully, no line-shopping). THE UNLOCK IS DATA: wiring a live
multi-book feed (The Odds API) lights up arb / CLV.

Contract: Quote = one (book, market, side, decimal_odds, line) price; GameOdds =
one game's Quotes from one+ books; OddsFeed = fetch(sport)->List[GameOdds] +
is_live(). src is touched in EXACTLY one place — TheOddsApiFeed.fetch lazily
imports src.data.odds_api_client and delegates. No network at import time/in tests.
"""
from __future__ import annotations

import abc
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.frontend.board import _SPORT_REGISTRY, _safe_float
from scripts.platformkit.frontend.book_norm import normalize_book

logger = logging.getLogger(__name__)

FEED_NOT_CONFIGURED_NOTE = (
    "Live multi-book feed not configured. Set ODDS_API_KEY to go live. "
    "On-disk corpus = one historical book only (no line-shopping)."
)
LIVE_NOTE = "Live feed: The Odds API (multi-book)."


def american_to_decimal(odds: Any) -> Optional[float]:
    """American odds -> decimal odds.  None / 0 / non-numeric -> None."""
    if odds is None:
        return None
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0.0:
        return None
    if o > 0:
        return 1.0 + o / 100.0
    return 1.0 + 100.0 / abs(o)


@dataclass(frozen=True)
class Quote:
    """One normalized price from a single book.  decimal_odds is ALWAYS decimal."""

    book: str  # normalized lowercase
    market: str  # "h2h" | "spreads" | "totals" | ...
    side: str  # "home"/"away"/"over"/"under" or a name
    decimal_odds: float
    line: Optional[float] = None
    last_update: Optional[str] = None


@dataclass(frozen=True)
class GameOdds:
    """One game with quotes from one or more books."""

    game_id: str  # f"{sport}:{date}:{away}@{home}"
    sport: str
    home: str
    away: str
    commence_time: Optional[str]
    quotes: List[Quote] = field(default_factory=list)
    source: str = "unknown"


def _mk_game_id(sport: str, date: Any, away: Any, home: Any) -> str:
    return f"{sport}:{date}:{away}@{home}"


class OddsFeed(abc.ABC):
    """Abstract multi-book odds feed.  Concrete feeds normalize to GameOdds."""

    name: str = "feed"
    note: str = ""

    @abc.abstractmethod
    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        """Return normalized GameOdds for a sport (optionally one date)."""

    @abc.abstractmethod
    def is_live(self) -> bool:
        """True when this feed talks to a real multi-book provider."""

    def to_board_books(self, game: GameOdds, market: str = "h2h") -> List[Dict[str, Any]]:
        """Quotes for one market as board._compute_line_shop_ev expects.

        Returns [{"book","market","side","decimal_odds","line"}, ...] filtered
        to `market`.  Exactly the shape board.py / arbitrage.py read.
        """
        out: List[Dict[str, Any]] = []
        for q in game.quotes:
            if q.market != market:
                continue
            out.append({
                "book": q.book,
                "market": q.market,
                "side": q.side,
                "decimal_odds": q.decimal_odds,
                "line": q.line,
            })
        return out


class StubFeed(OddsFeed):
    """On-disk feed: one synthetic "corpus" book from data/domains/<sport>/odds.parquet.

    mode="parquet" reads the corpus; mode="empty" returns []. Never network,
    never raises on a bad read (logs + returns []).
    """

    name = "stub"
    note = FEED_NOT_CONFIGURED_NOTE

    def __init__(self, repo_root: Optional[Path] = None, mode: str = "parquet") -> None:
        if mode not in ("parquet", "empty"):
            raise ValueError(f"mode must be 'parquet' or 'empty', got {mode!r}")
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
        self.mode = mode

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        if self.mode == "empty":
            return []
        reg = _SPORT_REGISTRY.get(sport)
        if reg is None:
            return []
        odds_path = self.repo_root / reg["corpus_dir"] / "odds.parquet"
        if not odds_path.exists():
            return []
        try:
            import pandas as pd  # local: keep pandas off the import-time hot path
            df = pd.read_parquet(odds_path)
            games = [self._row_to_game(sport, rec) for rec in df.to_dict("records")]
        except Exception as exc:  # pragma: no cover - defensive read guard
            logger.error("StubFeed: read/map failed for %s (%s): %s", sport, odds_path, exc)
            return []
        return [g for g in games if g is not None and (date is None or str(g.commence_time) == date)]

    @staticmethod
    def _row_to_game(sport: str, rec: Dict[str, Any]) -> Optional[GameOdds]:
        """Map ONE corpus row -> ONE GameOdds with a single synthetic 'corpus' book."""
        date = rec.get("date")
        home = rec.get("home_team") or rec.get("home")
        away = rec.get("away_team") or rec.get("away")
        if home is None or away is None:
            return None
        home, away = str(home), str(away)
        quotes: List[Quote] = []
        home_ml = american_to_decimal(rec.get("home_ml"))
        away_ml = american_to_decimal(rec.get("away_ml"))
        if home_ml is not None:
            quotes.append(Quote("corpus", "h2h", "home", home_ml))
        if away_ml is not None:
            quotes.append(Quote("corpus", "h2h", "away", away_ml))
        total = _safe_float(rec.get("total"))
        if total is not None:
            quotes.append(Quote("corpus", "totals", "over", 1.9091, line=total))
            quotes.append(Quote("corpus", "totals", "under", 1.9091, line=total))
        spread = _safe_float(rec.get("spread"))
        if spread is not None:
            quotes.append(Quote("corpus", "spreads", "home", 1.9091, line=spread))
            quotes.append(Quote("corpus", "spreads", "away", 1.9091, line=-spread))
        if not quotes:
            return None
        ct = str(date) if date is not None else None
        return GameOdds(_mk_game_id(sport, date, away, home), sport, home, away, ct, quotes, "corpus")


class TheOddsApiFeed(OddsFeed):
    """Live multi-book feed delegating to src.data.odds_api_client.

    EXACTLY what the user must provide for this to go live:
      * Endpoint: GET v4/sports/{sport}/events/{id}/odds (per-event), plus
        v4/sports/{sport}/events to index events.
      * Params: regions (e.g. "us"), markets ("h2h,spreads,totals"),
        oddsFormat=decimal.
      * Cost: events index = 1 unit, per-event odds = 1 unit, historical = 10
        units; budget gate MAX_UNITS = 20000 (enforced by odds_api_client).
      * Env var: ODDS_API_KEY (or THE_ODDS_API_KEY).  NEVER hardcode the key.
    Guarantee: NO network call is made at import time or in tests.  The
    src.data.odds_api_client import is LAZY (inside fetch only); _normalize is a
    pure function tests exercise with a synthetic dict.
    """

    name = "theoddsapi"
    note = LIVE_NOTE

    def __init__(self, api_key: str, *, region: str = "us",
                 markets: tuple = ("h2h", "spreads", "totals")) -> None:
        self._api_key = api_key  # held only to confirm a key was supplied; never logged
        self.region = region
        self.markets = tuple(markets)

    def is_live(self) -> bool:
        return True

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        """Delegate to odds_api_client; wrap every error -> log + [] (no crash/hang)."""
        try:
            from src.data import odds_api_client  # lazy: no network/import at module top
            games: List[GameOdds] = []
            for ev in odds_api_client.list_events(date=date) or []:
                ev_id = ev.get("id") if isinstance(ev, dict) else None
                if ev_id is None:
                    continue
                for mkt in self.markets:
                    try:
                        payload = odds_api_client.fetch_event_odds(ev_id, mkt, region=self.region)
                    except Exception as exc:  # pragma: no cover - per-market guard
                        logger.warning("event %s market %s failed: %s", ev_id, mkt, exc)
                        continue
                    games.extend(self._normalize(payload, sport=sport))
            return games
        except Exception as exc:  # pragma: no cover - never crash/hang
            logger.error("TheOddsApiFeed.fetch failed: %s", exc)
            return []

    @staticmethod
    def _normalize(payload: Any, *, sport: Optional[str] = None) -> List[GameOdds]:
        """PURE: a single Odds-API event dict -> List[GameOdds] (one element).

        Walks bookmakers[] -> markets[] -> outcomes[]. Exercised by tests with a
        synthetic dict — NO network.  Accepts a single event dict or a list.
        """
        if isinstance(payload, list):
            out: List[GameOdds] = []
            for item in payload:
                out.extend(TheOddsApiFeed._normalize(item, sport=sport))
            return out
        if not isinstance(payload, dict):
            return []
        sp = str(sport or payload.get("sport_key") or "unknown")
        home = str(payload.get("home_team") or "home")
        away = str(payload.get("away_team") or "away")
        commence = payload.get("commence_time")
        quotes: List[Quote] = []
        for bk in payload.get("bookmakers", []) or []:
            book = normalize_book(bk.get("key") or bk.get("title"))
            for mkt in bk.get("markets", []) or []:
                mkey = str(mkt.get("key") or "h2h")
                for oc in mkt.get("outcomes", []) or []:
                    dec = _safe_float(oc.get("price"))
                    if dec is None:
                        continue
                    side = TheOddsApiFeed._side(oc.get("name"), home, away)
                    quotes.append(Quote(book, mkey, side, dec, line=_safe_float(oc.get("point"))))
        date = str(commence)[:10] if commence else None
        return [GameOdds(_mk_game_id(sp, date, away, home), sp, home, away,
                         str(commence) if commence else None, quotes, "theoddsapi")]

    @staticmethod
    def _side(name: Any, home: str, away: str) -> str:
        s = str(name) if name is not None else ""
        if s == home:
            return "home"
        if s == away:
            return "away"
        low = s.lower()
        if low in ("over", "under", "home", "away"):
            return low
        return s


def get_feed(repo_root: Optional[Path] = None, *, force_stub: bool = False) -> OddsFeed:
    """Return the live feed when a key is configured, else the on-disk StubFeed.

    Never raises when the key is absent.  Key from ODDS_API_KEY or
    THE_ODDS_API_KEY.  force_stub forces StubFeed even with a key.
    """
    key = os.environ.get("ODDS_API_KEY") or os.environ.get("THE_ODDS_API_KEY")
    if key and not force_stub:
        return TheOddsApiFeed(api_key=key)
    return StubFeed(repo_root, mode="parquet")


__all__ = [
    "american_to_decimal",
    "normalize_book",
    "Quote",
    "GameOdds",
    "OddsFeed",
    "StubFeed",
    "TheOddsApiFeed",
    "get_feed",
    "FEED_NOT_CONFIGURED_NOTE",
    "LIVE_NOTE",
]
