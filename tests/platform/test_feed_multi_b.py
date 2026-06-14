"""tests.platform.test_feed_multi_b — offline tests for game_to_slate_entry,
games_to_slate, and the end-to-end arbitrage unlock proof.

HONEST: any arbitrage surface here is cross-book line-shop value only (NOT model
alpha).  Markets are efficient; these tests use *synthetic* numbers that are
deliberately unrealistic to prove the pipeline wires up end-to-end.
No network calls; no parquet reads; no codebase side-effects.

Split: this file covers game_to_slate_entry, games_to_slate, and the E2E proof.
       See test_feed_multi.py for MultiFeed.is_live and MultiFeed.fetch tests.
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed, Quote
from scripts.platformkit.frontend.feed_multi import (
    MultiFeed,
    distinct_books,
    game_to_slate_entry,
    games_to_slate,
    scan_games,
)


# ---------------------------------------------------------------------------
# Helpers — fake feeds (fully offline; duplicated from test_feed_multi.py
# so each file is standalone)
# ---------------------------------------------------------------------------

def _make_game(
    game_id: str = "nba:2026-06-14:away@home",
    sport: str = "nba",
    home: str = "home",
    away: str = "away",
    quotes: Optional[List[Quote]] = None,
    source: str = "feed_a",
) -> GameOdds:
    return GameOdds(
        game_id=game_id,
        sport=sport,
        home=home,
        away=away,
        commence_time="2026-06-14T00:00:00Z",
        quotes=quotes or [],
        source=source,
    )


class StaticFeed(OddsFeed):
    """Returns a pre-built list of GameOdds; never touches the network."""

    name = "static"

    def __init__(self, games: List[GameOdds], source_name: str = "static") -> None:
        self._games = games
        self.name = source_name

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        return list(self._games)


# ---------------------------------------------------------------------------
# game_to_slate_entry shape
# ---------------------------------------------------------------------------

def test_game_to_slate_entry_h2h_shape():
    """game_to_slate_entry produces exact arbitrage.scan_slate shape for h2h."""
    quotes = [
        Quote("book_a", "h2h", "home", 1.90),
        Quote("book_b", "h2h", "away", 2.10),
    ]
    game = _make_game(quotes=quotes)
    entry = game_to_slate_entry(game)

    assert entry["event_id"] == game.game_id
    assert entry["sport"] == game.sport
    assert "h2h" in entry["markets"]

    h2h = entry["markets"]["h2h"]
    assert h2h["outcomes"] == ["home", "away"]
    sides_in_books = {b["side"] for b in h2h["books"]}
    assert sides_in_books == {"home", "away"}


def test_game_to_slate_entry_totals_maps_to_total():
    """Quote.market='totals' -> slate key 'total' (what detect_middles iterates)."""
    quotes = [
        Quote("book_a", "totals", "over", 1.91, line=224.5),
        Quote("book_b", "totals", "under", 1.91, line=225.5),
    ]
    game = _make_game(quotes=quotes)
    entry = game_to_slate_entry(game)

    assert "total" in entry["markets"]
    total = entry["markets"]["total"]
    assert total["outcomes"] == ["over", "under"]


def test_game_to_slate_entry_spreads_maps_to_spread():
    """Quote.market='spreads' -> slate key 'spread'."""
    quotes = [
        Quote("book_a", "spreads", "home", 1.91, line=-5.5),
        Quote("book_b", "spreads", "away", 1.91, line=5.5),
    ]
    game = _make_game(quotes=quotes)
    entry = game_to_slate_entry(game)

    assert "spread" in entry["markets"]


def test_game_to_slate_entry_book_entry_fields():
    """Each book entry must carry book, side, decimal_odds, line."""
    q = Quote("fanduel", "h2h", "home", 1.85)
    game = _make_game(quotes=[q])
    entry = game_to_slate_entry(game)
    book_entry = entry["markets"]["h2h"]["books"][0]
    assert set(book_entry.keys()) >= {"book", "side", "decimal_odds", "line"}
    assert book_entry["book"] == "fanduel"
    assert book_entry["decimal_odds"] == 1.85


# ---------------------------------------------------------------------------
# games_to_slate
# ---------------------------------------------------------------------------

def test_games_to_slate_list_mapping():
    q_a = Quote("a", "h2h", "home", 1.90)
    q_b = Quote("b", "h2h", "away", 2.05)
    games = [
        _make_game("g1", quotes=[q_a]),
        _make_game("g2", quotes=[q_b]),
    ]
    slate = games_to_slate(games)
    assert len(slate) == 2
    assert slate[0]["event_id"] == "g1"
    assert slate[1]["event_id"] == "g2"


# ---------------------------------------------------------------------------
# END-TO-END UNLOCK PROOF
# ---------------------------------------------------------------------------

def test_end_to_end_multifeed_lights_up_arbitrage():
    """
    HONEST: this test uses *synthetic* numbers designed to show the pipeline
    wires correctly.  The decimal odds below (home=2.10, away=2.10) give an
    inverse-sum of ~0.952 < 1, which is a synthetic arbitrage.  Real markets
    are efficient; this combination does not exist in practice.

    Value class: cross-book line-shopping / arbitrage ONLY (NOT model alpha).

    Pipeline under test:
      feed_a (book_espn) + feed_b (book_bovada)
        -> MultiFeed.fetch
        -> games_to_slate
        -> arbitrage.scan_slate
        -> result["n_multibook_games"] >= 1
        -> result["arbitrage"] is non-empty  (synthetic arb detected)
    """
    gid = "nba:2026-06-14:proof@game"

    # Two books on the same game, each quoting a different side better
    # Synthetic: inverse-sum = 1/2.10 + 1/2.10 ≈ 0.952 < 1 => arb found
    q_home = Quote("espn_synthetic", "h2h", "home", 2.10)
    q_away = Quote("bovada_synthetic", "h2h", "away", 2.10)

    feed_a = StaticFeed(
        [GameOdds(gid, "nba", "home_team", "away_team", None, [q_home], "espn")],
        "espn",
    )
    feed_b = StaticFeed(
        [GameOdds(gid, "nba", "home_team", "away_team", None, [q_away], "bovada")],
        "bovada",
    )

    mf = MultiFeed([feed_a, feed_b])
    merged_games = mf.fetch("nba")

    # Verify merge produced 2 distinct books
    assert len(merged_games) == 1
    assert distinct_books(merged_games[0]) == 2

    # Convert to slate and scan
    result = scan_games(merged_games)

    # The multi-book unlock: at least 1 game with >=2 books
    assert result["n_multibook_games"] >= 1, (
        f"Expected n_multibook_games>=1, got {result['n_multibook_games']}"
    )

    # The synthetic arb must be detected (each book prices the other side worse)
    assert len(result["arbitrage"]) >= 1, (
        f"Expected synthetic arb to be found. scan result: {result}"
    )

    # Validate arb shape (honest label present)
    arb = result["arbitrage"][0]
    assert arb["event_id"] == gid
    assert arb["inverse_sum"] < 1.0
    assert "NOT model alpha" in arb["label"]
