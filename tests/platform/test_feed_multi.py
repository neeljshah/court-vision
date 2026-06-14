"""tests.platform.test_feed_multi — offline tests for MultiFeed + slate bridge.

HONEST: any arbitrage surface here is cross-book line-shop value only (NOT model
alpha).  Markets are efficient; these tests use *synthetic* numbers that are
deliberately unrealistic to prove the pipeline wires up end-to-end.
No network calls; no parquet reads; no codebase side-effects.

Split: this file covers MultiFeed.is_live, MultiFeed.fetch (merge, skip, dedup).
       See test_feed_multi_b.py for game_to_slate_entry, games_to_slate, and the
       end-to-end arbitrage proof test.
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
# Helpers — fake feeds (fully offline)
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


class LiveFeed(StaticFeed):
    """Static feed that reports is_live() == True."""

    def is_live(self) -> bool:
        return True


class BrokenFeed(OddsFeed):
    """Always raises during fetch — used to test skip-on-error."""

    name = "broken"

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        raise RuntimeError("synthetic feed failure")


# ---------------------------------------------------------------------------
# MultiFeed.is_live
# ---------------------------------------------------------------------------

def test_is_live_any_live():
    """is_live() is True when at least one sub-feed is live."""
    dead = StaticFeed([], "dead")
    live = LiveFeed([], "live")
    mf = MultiFeed([dead, live])
    assert mf.is_live() is True


def test_is_live_all_dead():
    mf = MultiFeed([StaticFeed([], "a"), StaticFeed([], "b")])
    assert mf.is_live() is False


def test_is_live_empty_feeds():
    mf = MultiFeed([])
    assert mf.is_live() is False


# ---------------------------------------------------------------------------
# MultiFeed.fetch — basic merge
# ---------------------------------------------------------------------------

def test_merge_two_feeds_same_game_distinct_books():
    """Two feeds quoting the SAME game_id with DIFFERENT books -> 2 distinct books."""
    gid = "nba:2026-06-14:celtics@nets"
    q_a = Quote("espn", "h2h", "home", 1.90)
    q_b = Quote("bovada", "h2h", "home", 1.87)

    feed_a = StaticFeed([_make_game(gid, quotes=[q_a], source="feed_a")], "feed_a")
    feed_b = StaticFeed([_make_game(gid, quotes=[q_b], source="feed_b")], "feed_b")

    mf = MultiFeed([feed_a, feed_b])
    merged = mf.fetch("nba")

    assert len(merged) == 1
    game = merged[0]
    assert distinct_books(game) == 2
    assert {q.book for q in game.quotes} == {"espn", "bovada"}


def test_game_in_only_one_feed_passes_through():
    """A game present in only feed_a must appear in output unchanged."""
    gid_shared = "nba:2026-06-14:shared@game"
    gid_solo = "nba:2026-06-14:solo@game"

    q_shared_a = Quote("espn", "h2h", "home", 1.85)
    q_shared_b = Quote("bovada", "h2h", "home", 1.83)
    q_solo = Quote("corpus", "h2h", "away", 2.10)

    feed_a = StaticFeed(
        [_make_game(gid_shared, quotes=[q_shared_a], source="fa"),
         _make_game(gid_solo, quotes=[q_solo], source="fa")],
        "fa",
    )
    feed_b = StaticFeed(
        [_make_game(gid_shared, quotes=[q_shared_b], source="fb")],
        "fb",
    )

    mf = MultiFeed([feed_a, feed_b])
    result = mf.fetch("nba")

    assert len(result) == 2
    game_ids = [g.game_id for g in result]
    assert gid_shared in game_ids
    assert gid_solo in game_ids

    solo_game = next(g for g in result if g.game_id == gid_solo)
    assert distinct_books(solo_game) == 1


def test_source_is_sorted_joined_sub_sources():
    """merged.source == '+'.join(sorted distinct sub-sources)."""
    gid = "nba:2026-06-14:x@y"
    feed_a = StaticFeed([_make_game(gid, source="zebra")], "a")
    feed_b = StaticFeed([_make_game(gid, source="alpha")], "b")

    # Assign the game's actual source field to match what feed returns
    game_a = GameOdds(gid, "nba", "y", "x", None, [], "zebra")
    game_b = GameOdds(gid, "nba", "y", "x", None, [], "alpha")
    feed_a = StaticFeed([game_a], "a")
    feed_b = StaticFeed([game_b], "b")

    mf = MultiFeed([feed_a, feed_b])
    [merged] = mf.fetch("nba")
    assert merged.source == "alpha+zebra"  # sorted


# ---------------------------------------------------------------------------
# MultiFeed.fetch — failing sub-feed is skipped
# ---------------------------------------------------------------------------

def test_broken_feed_skipped_others_still_merge():
    """A feed that raises during fetch is skipped; remaining feeds still merge."""
    gid = "nba:2026-06-14:good@game"
    q = Quote("draftkings", "h2h", "home", 1.91)
    good_feed = StaticFeed([_make_game(gid, quotes=[q], source="good")], "good")
    broken = BrokenFeed()

    mf = MultiFeed([broken, good_feed])
    result = mf.fetch("nba")

    assert len(result) == 1
    assert result[0].game_id == gid


def test_all_feeds_broken_returns_empty():
    mf = MultiFeed([BrokenFeed(), BrokenFeed()])
    assert mf.fetch("nba") == []


# ---------------------------------------------------------------------------
# MultiFeed.fetch — deduplication
# ---------------------------------------------------------------------------

def test_dedup_same_book_market_side_line():
    """Same (book, market, side, line) from two feeds collapses to one quote."""
    gid = "nba:2026-06-14:dup@test"
    q = Quote("shared_book", "h2h", "home", 1.90)  # identical in both feeds

    feed_a = StaticFeed([_make_game(gid, quotes=[q], source="a")], "a")
    feed_b = StaticFeed([_make_game(gid, quotes=[q], source="b")], "b")

    mf = MultiFeed([feed_a, feed_b])
    [merged] = mf.fetch("nba")

    # After dedup: only 1 quote for this (book, market, side, line) combo
    matching = [q2 for q2 in merged.quotes
                if q2.book == "shared_book" and q2.market == "h2h" and q2.side == "home"]
    assert len(matching) == 1


def test_dedup_different_line_not_collapsed():
    """Same (book, market, side) but different line values -> kept as two quotes."""
    gid = "nba:2026-06-14:lines@test"
    q1 = Quote("espn", "totals", "over", 1.91, line=224.5)
    q2 = Quote("espn", "totals", "over", 1.91, line=225.5)

    feed_a = StaticFeed([_make_game(gid, quotes=[q1], source="a")], "a")
    feed_b = StaticFeed([_make_game(gid, quotes=[q2], source="b")], "b")

    mf = MultiFeed([feed_a, feed_b])
    [merged] = mf.fetch("nba")
    over_quotes = [q for q in merged.quotes if q.side == "over"]
    assert len(over_quotes) == 2
