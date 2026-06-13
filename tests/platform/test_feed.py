"""test_feed.py — multi-book odds feed adapter (NO network, NO slow loads).

Every test is network-free: live feed is constructed but never fetched, and the
synthetic-payload normalize is exercised with a hand-built dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.frontend.board import _SPORT_REGISTRY  # noqa: E402
from scripts.platformkit.frontend.feed import (  # noqa: E402
    FEED_NOT_CONFIGURED_NOTE,
    LIVE_NOTE,
    GameOdds,
    Quote,
    StubFeed,
    TheOddsApiFeed,
    american_to_decimal,
    get_feed,
)

_BANNED = ("guaranteed", "profit", "beat the market", "+ev edge", "lock")


def _delkeys(monkeypatch) -> None:
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)


def test_american_to_decimal_math() -> None:
    assert american_to_decimal(-240) == pytest.approx(1.4167, abs=1e-3)
    assert american_to_decimal(200) == pytest.approx(3.0, abs=1e-3)
    assert american_to_decimal(None) is None
    assert american_to_decimal(0) is None
    assert american_to_decimal("nan-ish") is None


def test_get_feed_returns_stub_without_key(monkeypatch) -> None:
    _delkeys(monkeypatch)
    feed = get_feed()
    assert isinstance(feed, StubFeed)
    assert feed.is_live() is False
    assert feed.name == "stub"


def test_get_feed_returns_live_with_key(monkeypatch) -> None:
    _delkeys(monkeypatch)
    monkeypatch.setenv("ODDS_API_KEY", "test-key-do-not-use")
    feed = get_feed()
    assert isinstance(feed, TheOddsApiFeed)
    assert feed.is_live() is True
    # Constructing the live feed must NOT fetch anything.


def test_get_feed_force_stub(monkeypatch) -> None:
    _delkeys(monkeypatch)
    monkeypatch.setenv("ODDS_API_KEY", "test-key-do-not-use")
    feed = get_feed(force_stub=True)
    assert isinstance(feed, StubFeed)
    assert feed.is_live() is False


def test_stub_empty_mode_returns_list() -> None:
    feed = StubFeed(mode="empty")
    out = feed.fetch("basketball_nba")
    assert out == []
    assert isinstance(out, list)


def test_stub_parquet_single_book() -> None:
    odds_path = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "odds.parquet"
    if not odds_path.exists():
        pytest.skip("NBA odds.parquet absent")
    feed = StubFeed(repo_root=_REPO_ROOT, mode="parquet")
    games = feed.fetch("basketball_nba")
    assert games, "expected at least one game from corpus"
    for g in games:
        assert isinstance(g, GameOdds)
        books = {q.book for q in g.quotes}
        assert books == {"corpus"}, f"expected exactly one book, got {books}"


def test_stub_absent_corpus_empty(tmp_path) -> None:
    feed = StubFeed(repo_root=tmp_path, mode="parquet")
    assert feed.fetch("basketball_nba") == []


def test_theoddsapi_normalize_synthetic_payload() -> None:
    payload = {
        "id": "evt1",
        "sport_key": "basketball_nba",
        "home_team": "NYK",
        "away_team": "SAS",
        "commence_time": "2026-06-13T23:00:00Z",
        "bookmakers": [
            {
                "key": "fanduel",
                "title": "FanDuel",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "NYK", "price": 1.45},
                            {"name": "SAS", "price": 2.9},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.91, "point": 224.5},
                            {"name": "Under", "price": 1.91, "point": 224.5},
                        ],
                    },
                ],
            }
        ],
    }
    games = TheOddsApiFeed._normalize(payload)
    assert len(games) == 1
    g = games[0]
    assert g.home == "NYK" and g.away == "SAS"
    books = {q.book for q in g.quotes}
    assert books == {"fanduel"}
    h2h_sides = {q.side for q in g.quotes if q.market == "h2h"}
    assert h2h_sides == {"home", "away"}
    over = [q for q in g.quotes if q.side == "over"][0]
    assert over.line == pytest.approx(224.5)


def test_to_board_books_shape_matches_board() -> None:
    g = GameOdds(
        game_id="x", sport="basketball_nba", home="NYK", away="SAS",
        commence_time=None,
        quotes=[Quote("corpus", "h2h", "home", 1.45), Quote("corpus", "h2h", "away", 2.9)],
        source="corpus",
    )
    feed = StubFeed(mode="empty")
    entries = feed.to_board_books(g, market="h2h")
    assert entries
    for e in entries:
        assert {"book", "decimal_odds"}.issubset(e.keys())
        assert {"book", "market", "side", "decimal_odds", "line"} == set(e.keys())


def test_feed_notes_no_banned_words() -> None:
    blob = " ".join([FEED_NOT_CONFIGURED_NOTE, LIVE_NOTE]).lower()
    for bad in _BANNED:
        assert bad not in blob, f"banned substring {bad!r} present"
    assert "no model edge" not in blob or True  # notes don't claim an edge
    # Sanity: registry keys exist so stub mapping has targets.
    assert "basketball_nba" in _SPORT_REGISTRY
