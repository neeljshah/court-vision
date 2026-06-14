"""scripts.platformkit.frontend.feed_multi — MultiFeed aggregator + arbitrage slate bridge.

HONEST: markets are efficient and NO model edge is ever claimed here.  The ONLY
value this module surfaces is cross-book line-shopping / arbitrage / devig / CLV,
which exists ONLY when >=2 distinct books quote the same outcome on the same game.
Merging two feeds (e.g. ESPN + Bovada) that each carry ~1 book is THE mechanism
that lights up those opportunities — it does NOT create a model alpha.

Key exports:
  MultiFeed         — combine N OddsFeed objects into one multi-book slate.
  game_to_slate_entry  — GameOdds -> arbitrage.scan_slate dict (exact shape).
  games_to_slate    — list of GameOdds -> list of slate entries.
  scan_games        — convenience wrapper: games -> arbitrage.scan_slate result.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed, Quote

logger = logging.getLogger(__name__)

# Honest banner (re-stated here for any caller reading module-level strings)
_HONEST_BANNER = (
    "MultiFeed value = line-shop / devig / CLV ONLY (NOT model alpha). "
    "Cross-book opportunities arise only when >=2 distinct books price the same outcome."
)

# Market name translation: Quote.market -> slate market name expected by arbitrage.py
# arbitrage.detect_middles iterates ("total","spread") — NOT ("totals","spreads")
_MARKET_SLUG: Dict[str, str] = {
    "h2h": "h2h",
    "spreads": "spread",
    "totals": "total",
}

# For each slate market name: ordered list of canonical outcome labels.
# detect_middles treats outcomes[0] as the low side, outcomes[1] as the high side.
# detect_arbitrage uses all outcomes to confirm all sides are priced.
_MARKET_OUTCOMES: Dict[str, List[str]] = {
    "h2h": ["home", "away"],
    "total": ["over", "under"],   # over = low line side (under = high line side)
    "spread": ["home", "away"],
}


# ---------------------------------------------------------------------------
# MultiFeed
# ---------------------------------------------------------------------------

class MultiFeed(OddsFeed):
    """Aggregate N OddsFeed objects into one multi-book slate.

    Rules:
    * Each sub-feed.fetch() is wrapped in try/except; errors are logged and the
      feed is skipped — remaining feeds are always returned.
    * Games are merged by game_id: quotes are unioned, deduped by
      (book, market, side, line) keeping last-seen.
    * merged GameOdds.source = "+".join(sorted distinct sub-sources).
    * Games present in only one feed pass through unchanged.
    * Return order = first-seen game_id order across feeds.
    """

    name: str = "multi"
    note: str = _HONEST_BANNER

    def __init__(self, feeds: List[OddsFeed]) -> None:
        """
        Args:
            feeds: OddsFeed instances to aggregate (>=1 recommended; >=2 for
                   multi-book value).  May be empty — returns [] gracefully.
        """
        self._feeds: List[OddsFeed] = list(feeds)

    def is_live(self) -> bool:
        """True when ANY sub-feed is live (connected to a real multi-book provider)."""
        return any(f.is_live() for f in self._feeds)

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        """Fetch + merge all sub-feeds for *sport*.

        A failing sub-feed is logged and skipped; others still contribute.
        Returns a stable list (first-seen game_id order).
        """
        # game_id -> accumulated state
        order: List[str] = []                   # first-seen insertion order
        merged_meta: Dict[str, Dict[str, Any]] = {}   # game_id -> {home,away,sport,ct}
        merged_quotes: Dict[str, Dict[tuple, Quote]] = {}  # game_id -> {dedup_key: Quote}
        merged_sources: Dict[str, List[str]] = {}          # game_id -> [source, ...]

        for feed in self._feeds:
            try:
                games = feed.fetch(sport, date=date)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MultiFeed: sub-feed %r raised during fetch (sport=%s): %s — skipping",
                    getattr(feed, "name", repr(feed)), sport, exc,
                )
                continue

            for game in games:
                gid = game.game_id
                if gid not in merged_meta:
                    order.append(gid)
                    merged_meta[gid] = {
                        "home": game.home,
                        "away": game.away,
                        "sport": game.sport,
                        "ct": game.commence_time,
                    }
                    merged_quotes[gid] = {}
                    merged_sources[gid] = []

                # union quotes; dedup by (book, market, side, line); keep last
                for q in game.quotes:
                    key = (q.book, q.market, q.side, q.line)
                    merged_quotes[gid][key] = q

                src = game.source
                if src not in merged_sources[gid]:
                    merged_sources[gid].append(src)

        # Assemble merged GameOdds objects
        result: List[GameOdds] = []
        for gid in order:
            meta = merged_meta[gid]
            quotes = list(merged_quotes[gid].values())
            source = "+".join(sorted(merged_sources[gid]))
            result.append(GameOdds(
                game_id=gid,
                sport=meta["sport"],
                home=meta["home"],
                away=meta["away"],
                commence_time=meta["ct"],
                quotes=quotes,
                source=source,
            ))
        return result


def distinct_books(game: GameOdds) -> int:
    """Count distinct book names across all quotes on *game*."""
    return len({q.book for q in game.quotes})


# ---------------------------------------------------------------------------
# GameOdds -> arbitrage slate bridge
# ---------------------------------------------------------------------------

def game_to_slate_entry(game: GameOdds) -> Dict[str, Any]:
    """Convert a GameOdds to the exact dict shape arbitrage.scan_slate consumes.

    Output shape::

        {
          "event_id": game.game_id,
          "sport":    game.sport,
          "markets": {
            "<mkt>": {
              "outcomes": ["side_a", "side_b"],
              "books":    [{"book","side","decimal_odds","line"}, ...]
            },
            ...
          }
        }

    Market name mapping (Quote.market -> slate key):
      "h2h"     -> "h2h"    (outcomes: ["home","away"])
      "totals"  -> "total"  (outcomes: ["over","under"])
      "spreads" -> "spread" (outcomes: ["home","away"])

    detect_middles() iterates ("total","spread") and treats outcomes[0] as the
    low side and outcomes[1] as the high side.  Ordering is fixed by
    _MARKET_OUTCOMES above.
    """
    # Accumulate books per slate market
    mkt_books: Dict[str, List[Dict[str, Any]]] = {}

    for q in game.quotes:
        slug = _MARKET_SLUG.get(q.market)
        if slug is None:
            continue  # unknown market type — skip gracefully
        if slug not in mkt_books:
            mkt_books[slug] = []
        mkt_books[slug].append({
            "book": q.book,
            "side": q.side,
            "decimal_odds": q.decimal_odds,
            "line": q.line,
        })

    # Build markets dict with canonical outcome ordering
    markets: Dict[str, Any] = {}
    for slug, books in mkt_books.items():
        markets[slug] = {
            "outcomes": _MARKET_OUTCOMES.get(slug, []),
            "books": books,
        }

    return {
        "event_id": game.game_id,
        "sport": game.sport,
        "markets": markets,
    }


def games_to_slate(games: List[GameOdds]) -> List[Dict[str, Any]]:
    """Convert a list of GameOdds to the full slate list for arbitrage.scan_slate."""
    return [game_to_slate_entry(g) for g in games]


def scan_games(games: List[GameOdds], **kwargs: Any) -> Dict[str, Any]:
    """Convenience wrapper: GameOdds list -> arbitrage.scan_slate result.

    Lazily imports arbitrage to avoid circular-import risk.
    kwargs are forwarded to scan_slate (e.g. devig_method, min_middle_width).

    HONEST: any arbitrage surfaced here is cross-book line-shop value only.
    It is NOT model alpha — markets are efficient.
    """
    from scripts.platformkit.frontend import arbitrage  # lazy import
    slate = games_to_slate(games)
    return arbitrage.scan_slate(slate, **kwargs)


__all__ = [
    "MultiFeed",
    "distinct_books",
    "game_to_slate_entry",
    "games_to_slate",
    "scan_games",
]
