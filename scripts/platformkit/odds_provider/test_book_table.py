"""Per-file tests for the all-books-per-card line-shopping table.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_book_table.py -q

Acceptance:
  - Every contributing book is listed per (market,side) with price + freshness.
  - Best = highest fresh SPORTSBOOK price; a higher STALE price never wins.
  - Prediction-market (kalshi) books are listed (is_pm) but never selected best.
  - Spread/total extended nodes flow into their own (market,side) cells.
  - book_table_to_jsonable produces JSON-safe rows, best-bettable-first.
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.odds_provider.book_table import (
    book_table_for_event, book_table_to_jsonable, MONEYLINE, SPREAD, TOTAL,
)

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
_FRESH = "2026-06-20T11:59:00+00:00"   # 1 min old
_STALE = "2026-06-20T11:00:00+00:00"   # 60 min old


def _event():
    return {
        "event_id": "g1", "sport": "nba",
        "home": "Boston Celtics", "away": "Los Angeles Lakers",
        "as_of": _FRESH,
        "prices": {
            "espn:DK": {"home": 1.80, "away": 2.05},
            "pinnacle": {
                "home": 1.83, "away": 2.00,
                "spread": {"home": {"line": -5.5, "odds": 1.91},
                           "away": {"line": 5.5, "odds": 1.90}},
                "total": {"over": {"line": 220.5, "odds": 1.95},
                          "under": {"line": 220.5, "odds": 1.87}},
            },
            "kalshi": {"home": 1.99, "away": 1.99, "draw": None},
        },
    }


class TestBooksListed:
    def test_all_ml_home_books_listed(self):
        t = book_table_for_event(_event(), now=_NOW)
        books = {b["book"] for b in t[(MONEYLINE, "home")]["books"]}
        assert books == {"espn:DK", "pinnacle", "kalshi"}

    def test_pm_flagged(self):
        t = book_table_for_event(_event(), now=_NOW)
        pm = [b for b in t[(MONEYLINE, "home")]["books"] if b["book"] == "kalshi"]
        assert pm and pm[0]["is_pm"] is True


class TestBestSelection:
    def test_best_is_highest_fresh_sportsbook(self):
        # kalshi 1.99 is highest but PM; pinnacle 1.83 > espn 1.80 -> pinnacle wins.
        t = book_table_for_event(_event(), now=_NOW)
        best = t[(MONEYLINE, "home")]["best"]
        assert best["book"] == "pinnacle"
        assert best["price"] == 1.83

    def test_pm_never_best(self):
        t = book_table_for_event(_event(), now=_NOW)
        assert t[(MONEYLINE, "home")]["best"]["book"] != "kalshi"

    def test_stale_higher_price_never_wins(self):
        # espn fresh @1.80, pinnacle STALE @1.83 -> best must be espn (fresh lower).
        ev = _event()
        t = book_table_for_event(ev, venue_as_of={
            "espn:DK": _FRESH, "pinnacle": _STALE, "kalshi": _FRESH,
        }, now=_NOW)
        best = t[(MONEYLINE, "home")]["best"]
        assert best["book"] == "espn:DK"
        assert best["price"] == 1.80

    def test_no_fresh_book_best_none(self):
        ev = _event()
        t = book_table_for_event(ev, venue_as_of={
            "espn:DK": _STALE, "pinnacle": _STALE, "kalshi": _STALE,
        }, now=_NOW)
        assert t[(MONEYLINE, "home")]["best"] is None


class TestSpreadTotalCells:
    def test_spread_cell(self):
        t = book_table_for_event(_event(), now=_NOW)
        cell = t[(SPREAD, "home")]
        assert cell["best"]["book"] == "pinnacle"
        assert cell["best"]["line"] == -5.5

    def test_total_cell(self):
        t = book_table_for_event(_event(), now=_NOW)
        assert (TOTAL, "over") in t
        assert t[(TOTAL, "over")]["best"]["line"] == 220.5


class TestJsonable:
    def test_rows_json_safe_and_sorted(self):
        t = book_table_for_event(_event(), now=_NOW)
        rows = book_table_to_jsonable(t)
        keys = [(r["market_type"], r["side"]) for r in rows]
        assert keys == sorted(keys)
        # First book in an ML home row is the best bettable (fresh sportsbook).
        ml_home = next(r for r in rows
                       if r["market_type"] == MONEYLINE and r["side"] == "home")
        assert ml_home["books"][0]["book"] == "pinnacle"

    def test_garbage_event_empty(self):
        assert book_table_for_event({"prices": "nope"}, now=_NOW) == {}
