"""test_book_norm — book-label normalization + the false-arb regression it fixes.

LIVE FINDING (W106): ESPN surfaces the SAME operator twice — "draftkings" (pregame)
AND "draftkings - live odds" (in-play).  Treating them as two books fabricated a
FALSE cross-book arbitrage (a stale pregame ML vs an in-play line is not
risk-free).  normalize_book collapses operator variants so only genuinely
DIFFERENT operators count as distinct books.  No network here.
"""
from __future__ import annotations

from typing import Any, Dict, List

from scripts.platformkit.frontend.book_norm import normalize_book
from scripts.platformkit.frontend.feed import normalize_book as reexported
from scripts.platformkit.frontend.feed_espn import EspnFreeFeed
from scripts.platformkit.frontend.feed_multi import MultiFeed, distinct_books, scan_games


# --- unit: normalize_book --------------------------------------------------
def test_collapses_live_variants() -> None:
    assert normalize_book("DraftKings - Live Odds") == "draftkings"
    assert normalize_book("draftkings - live") == "draftkings"
    assert normalize_book("FanDuel (Live)") == "fanduel"
    assert normalize_book("BetMGM Live Odds") == "betmgm"
    assert normalize_book("Caesars - Pregame") == "caesars"


def test_clean_names_pass_through() -> None:
    assert normalize_book("DraftKings") == "draftkings"
    assert normalize_book("FanDuel") == "fanduel"
    assert normalize_book("  BetMGM ") == "betmgm"


def test_empty_or_none_is_unknown() -> None:
    assert normalize_book(None) == "unknown"
    assert normalize_book("") == "unknown"
    assert normalize_book("   ") == "unknown"


def test_feed_reexports_same_function() -> None:
    # `from ...feed import normalize_book` must keep working (back-compat).
    assert reexported is normalize_book


# --- synthetic ESPN payload (mirrors the real scoreboard shape) ------------
def _provider(name: str, home_ml: int, away_ml: int) -> Dict[str, Any]:
    return {"provider": {"name": name},
            "homeTeamOdds": {"moneyLine": home_ml},
            "awayTeamOdds": {"moneyLine": away_ml}}


def _event(odds: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"id": "401", "date": "2026-06-14T23:00Z",
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"displayName": "Orioles"}},
                {"homeAway": "away", "team": {"displayName": "Padres"}}],
                "odds": odds}]}


def _feed_with(events: List[Dict[str, Any]]) -> EspnFreeFeed:
    return EspnFreeFeed(http_get=lambda url: {"events": events}, fetch_core=False)


# --- regression: same operator pregame+live collapses to ONE book ----------
def test_same_operator_pregame_and_live_collapse_to_one_book() -> None:
    # DraftKings pregame (home +150) AND DraftKings live (home -180): same operator.
    feed = _feed_with([_event([
        _provider("DraftKings", 150, -180),
        _provider("DraftKings - Live Odds", -180, 150)])])
    g = feed.fetch("mlb_sbro")[0]
    assert {q.book for q in g.quotes} == {"draftkings"}  # NOT two books


def test_no_false_cross_book_arb_from_one_operators_pregame_vs_live() -> None:
    # If the live variant were a distinct book, best home@one + best away@other
    # could look like an arb. After normalization there is ONE operator -> none.
    feed = _feed_with([_event([
        _provider("DraftKings", 150, -180),
        _provider("DraftKings - Live Odds", -180, 150)])])
    games = MultiFeed([feed]).fetch("mlb_sbro")
    assert max((distinct_books(g) for g in games), default=0) == 1
    res = scan_games(games)
    assert res["n_multibook_games"] == 0
    assert res["arbitrage"] == []


def test_two_genuine_operators_still_count_as_two_books() -> None:
    # The fix must NOT suppress real cross-book diversity.
    feed = _feed_with([_event([
        _provider("DraftKings", -110, -110),
        _provider("FanDuel", -110, -110)])])
    g = feed.fetch("mlb_sbro")[0]
    assert {q.book for q in g.quotes} == {"draftkings", "fanduel"}
    assert distinct_books(g) == 2
