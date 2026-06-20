"""Per-file unit tests for scripts.platformkit.odds_provider.line_matrix.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_line_matrix.py -q

NETWORK-FREE: all tests inject canned aggregate() payloads; no real HTTP calls.

Acceptance matrix (LS-05):
- ESPN + Kalshi game -> >=2 distinct books per market-type row
- Per-cell freshness matches as_of age (fresh vs stale boundary)
- Single-book game -> 1 BookCell, status="single_book" (honest)
- Offseason / empty slate -> status="unavailable", rows=[]
- No $ field anywhere in output
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

import pytest

from scripts.platformkit.odds_provider.line_matrix import (
    build_line_matrix,
    LineMatrix, MarketRow, BookCell,
    STATUS_OK, STATUS_SINGLE, STATUS_UNAVAILABLE,
)
from scripts.platformkit.odds_provider.markets import MONEYLINE, SPREAD, TOTAL

# ---------------------------------------------------------------------- #
# Helpers -- canned aggregate() payloads
# ---------------------------------------------------------------------- #

_FIXED_TS = "2026-06-17T23:00:00+00:00"   # "fresh" reference base
_STALE_TS = "2026-06-17T20:00:00+00:00"   # >15 min before _NOW


def _now_dt() -> datetime:
    """A fixed 'now' so freshness is deterministic in all tests."""
    return datetime(2026, 6, 17, 23, 5, 0, tzinfo=timezone.utc)


def _agg_two_books(*, include_spread: bool = False,
                   include_total: bool = False) -> Dict[str, Any]:
    """Canned aggregate payload: ESPN sportsbook + Kalshi PM, same NBA game."""
    prices: Dict[str, Any] = {
        "espn:DraftKings": {"home": 1.91, "away": 1.95},
        "kalshi": {"home": 1.0 / 0.60, "away": 1.0 / 0.45},
    }
    if include_spread:
        prices["espn:DraftKings"]["spread"] = {
            "home": {"line": -3.5, "odds": 1.91},
            "away": {"line":  3.5, "odds": 1.91},
        }
    if include_total:
        prices["espn:DraftKings"]["total"] = {
            "over":  {"line": 220.5, "odds": 1.91},
            "under": {"line": 220.5, "odds": 1.91},
        }
    return {
        "sport": "nba",
        "status": "ok",
        "as_of": _FIXED_TS,
        "sources": {"espn": "ok", "kalshi": "ok"},
        "events": [{
            "event_id": "nba-2026-06-17-bos-lal",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "Los Angeles Lakers",
            "commence_time": "2026-06-17T23:00Z",
            "prices": prices,
            "source": "aggregate",
            "as_of": _FIXED_TS,
        }],
    }


def _agg_single_book() -> Dict[str, Any]:
    """Aggregate with only one book (ESPN, no Kalshi/PM)."""
    return {
        "sport": "nba",
        "status": "ok",
        "as_of": _FIXED_TS,
        "sources": {"espn": "ok"},
        "events": [{
            "event_id": "nba-2026-06-17-bos-lal",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "Los Angeles Lakers",
            "commence_time": "2026-06-17T23:00Z",
            "prices": {"espn:DraftKings": {"home": 1.91, "away": 1.95}},
            "source": "aggregate",
            "as_of": _FIXED_TS,
        }],
    }


def _agg_stale_cell() -> Dict[str, Any]:
    """Aggregate with one fresh and one stale as_of per-event."""
    return {
        "sport": "nba",
        "status": "ok",
        "as_of": _STALE_TS,
        "sources": {"espn": "ok", "kalshi": "ok"},
        "events": [{
            "event_id": "nba-2026-06-17-bos-lal",
            "sport": "nba",
            "home": "Boston Celtics",
            "away": "Los Angeles Lakers",
            "commence_time": "2026-06-17T23:00Z",
            "prices": {
                "espn:DraftKings": {"home": 1.91, "away": 1.95},
                "kalshi": {"home": 1.67, "away": 2.22},
            },
            "source": "aggregate",
            "as_of": _STALE_TS,
        }],
    }


def _agg_unavailable() -> Dict[str, Any]:
    """Aggregate where all providers failed -> status unavailable."""
    return {
        "sport": "nba",
        "status": "unavailable",
        "as_of": _FIXED_TS,
        "sources": {"espn": "error (OSError)", "kalshi": "error (OSError)"},
        "events": [],
    }


def _agg_empty_events() -> Dict[str, Any]:
    """Aggregate ok but no events (offseason)."""
    return {
        "sport": "nba",
        "status": "ok",
        "as_of": _FIXED_TS,
        "sources": {"espn": "ok"},
        "events": [],
    }


# ---------------------------------------------------------------------- #
# Tests: two-book (ESPN sportsbook + Kalshi PM) moneyline game
# ---------------------------------------------------------------------- #

def test_two_books_moneyline_ok():
    """LS-05 primary: ESPN+Kalshi -> >=2 distinct books on moneyline row."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())

    assert m.status == STATUS_OK
    assert m.sport == "nba"
    assert m.home == "Boston Celtics"
    assert m.away == "Los Angeles Lakers"

    ml_rows = [r for r in m.rows if r.market_type == MONEYLINE]
    assert len(ml_rows) == 1, "must have a moneyline row"
    row = ml_rows[0]
    assert row.book_count >= 2, "must have >=2 books"
    assert row.status == STATUS_OK

    books = {c.book for c in row.books}
    assert "espn:DraftKings" in books, "ESPN sportsbook must appear"
    assert "kalshi" in books, "Kalshi PM must appear"


def test_two_books_venue_types():
    """Venue types correctly tagged: ESPN=sportsbook, Kalshi=prediction_market."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())
    ml_row = next(r for r in m.rows if r.market_type == MONEYLINE)
    by_book = {c.book: c for c in ml_row.books}
    assert by_book["espn:DraftKings"].venue_type == "sportsbook"
    assert by_book["kalshi"].venue_type == "prediction_market"


def test_two_books_prices_populated():
    """Both home_odds and away_odds are non-None for each book on moneyline."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())
    ml_row = next(r for r in m.rows if r.market_type == MONEYLINE)
    for cell in ml_row.books:
        assert cell.home_odds is not None and cell.home_odds > 1.0
        assert cell.away_odds is not None and cell.away_odds > 1.0
        assert cell.line is None  # no handicap on moneyline


def test_spread_row_present_when_quoted():
    """Spread row appears when ESPN quotes spread; Kalshi (no spread) absent."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(include_spread=True), now=_now_dt())
    sp_rows = [r for r in m.rows if r.market_type == SPREAD]
    assert len(sp_rows) == 1
    row = sp_rows[0]
    # Only ESPN quotes spread in the canned payload
    assert row.book_count == 1
    assert row.status == STATUS_SINGLE
    cell = row.books[0]
    assert cell.book == "espn:DraftKings"
    assert cell.line == -3.5 or cell.line == 3.5  # whichever side won


def test_total_row_present_when_quoted():
    """Total row appears when ESPN quotes total."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(include_total=True), now=_now_dt())
    tot_rows = [r for r in m.rows if r.market_type == TOTAL]
    assert len(tot_rows) == 1
    row = tot_rows[0]
    assert row.book_count == 1
    cell = row.books[0]
    assert cell.over_odds is not None
    assert cell.under_odds is not None
    assert math.isclose(cell.line, 220.5)


# ---------------------------------------------------------------------- #
# Tests: freshness per-cell matches as_of age
# ---------------------------------------------------------------------- #

def test_fresh_cells_when_recent_timestamp():
    """Cells captured <15 min ago -> freshness='fresh'."""
    # _now_dt() is 5 min after _FIXED_TS -> cells should be fresh
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())
    ml_row = next(r for r in m.rows if r.market_type == MONEYLINE)
    for cell in ml_row.books:
        assert cell.freshness == "fresh", (
            f"book={cell.book} age={cell.age_sec}s should be fresh")
        assert cell.age_sec is not None and cell.age_sec < 900.0


def test_stale_cells_when_old_timestamp():
    """Cells captured >15 min ago -> freshness='stale'."""
    # _STALE_TS is 3h before _now_dt() -> stale
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_stale_cell(), now=_now_dt())
    ml_row = next(r for r in m.rows if r.market_type == MONEYLINE)
    for cell in ml_row.books:
        assert cell.freshness == "stale", (
            f"book={cell.book} age={cell.age_sec}s should be stale")
        assert cell.age_sec is not None and cell.age_sec > 900.0


def test_as_of_is_oldest_timestamp():
    """matrix.as_of equals the OLDEST cell captured_at (stale-never-green)."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_stale_cell(), now=_now_dt())
    # only _STALE_TS is in the payload
    assert m.as_of == _STALE_TS


# ---------------------------------------------------------------------- #
# Tests: single-book honest handling
# ---------------------------------------------------------------------- #

def test_single_book_honest_label():
    """Single-book game -> book_count=1, status='single_book' (not ok or unavailable)."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_single_book(), now=_now_dt())
    # matrix itself is not STATUS_UNAVAILABLE since we do have a book
    assert m.status in (STATUS_OK, STATUS_SINGLE)
    ml_row = next((r for r in m.rows if r.market_type == MONEYLINE), None)
    assert ml_row is not None
    assert ml_row.book_count == 1
    assert ml_row.status == STATUS_SINGLE


# ---------------------------------------------------------------------- #
# Tests: offseason / empty -> UNAVAILABLE
# ---------------------------------------------------------------------- #

def test_offseason_empty_events_unavailable():
    """No events in slate -> LineMatrix status=unavailable, rows=[]."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_empty_events(), now=_now_dt())
    assert m.status == STATUS_UNAVAILABLE
    assert m.rows == []


def test_all_providers_down_unavailable():
    """All providers failed -> status=unavailable."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_unavailable(), now=_now_dt())
    assert m.status == STATUS_UNAVAILABLE
    assert m.rows == []


def test_game_not_in_slate_unavailable():
    """Requested game absent from slate -> unavailable (no fabricated data)."""
    m = build_line_matrix(
        "nba", "Phoenix Suns", "Miami Heat",
        agg=_agg_two_books(), now=_now_dt())
    assert m.status == STATUS_UNAVAILABLE
    assert m.rows == []


# ---------------------------------------------------------------------- #
# Tests: no $ field
# ---------------------------------------------------------------------- #

def test_no_dollar_field_in_output():
    """No field named with '$', 'roi', 'profit', 'payout', 'dollar' anywhere."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())
    d = m.to_dict()
    import json
    serialized = json.dumps(d).lower()
    for banned in ("$", "roi", "profit", "payout"):
        assert banned not in serialized, (
            f"banned field/value '{banned}' found in output")


# ---------------------------------------------------------------------- #
# Tests: team name matching tolerance
# ---------------------------------------------------------------------- #

def test_nickname_match_finds_game():
    """Partial team name 'Celtics' still finds the game ('Boston Celtics')."""
    m = build_line_matrix(
        "nba", "Celtics", "Lakers",
        agg=_agg_two_books(), now=_now_dt())
    # should find the game -- teams_match handles subset nickname
    assert m.status in (STATUS_OK, STATUS_SINGLE)
    assert len(m.rows) > 0


# ---------------------------------------------------------------------- #
# Tests: to_dict round-trips cleanly
# ---------------------------------------------------------------------- #

def test_to_dict_serializable():
    """LineMatrix.to_dict() is JSON-serializable (no custom objects)."""
    import json
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(include_spread=True, include_total=True),
        now=_now_dt())
    d = m.to_dict()
    s = json.dumps(d)  # must not raise
    roundtrip = json.loads(s)
    assert roundtrip["status"] == STATUS_OK
    # Confirm rows present
    market_types = {r["market_type"] for r in roundtrip["rows"]}
    assert MONEYLINE in market_types


# ---------------------------------------------------------------------- #
# Tests: devigged_prob filled when both sides present
# ---------------------------------------------------------------------- #

def test_devigged_prob_filled_when_both_sides():
    """devigged_home / devigged_away are populated for a full two-way quote."""
    m = build_line_matrix(
        "nba", "Boston Celtics", "Los Angeles Lakers",
        agg=_agg_two_books(), now=_now_dt())
    ml_row = next(r for r in m.rows if r.market_type == MONEYLINE)
    # ESPN DraftKings has both home + away odds -> devig must be filled
    espn_cell = next(
        (c for c in ml_row.books if c.book == "espn:DraftKings"), None)
    assert espn_cell is not None
    assert espn_cell.devigged_home is not None
    assert espn_cell.devigged_away is not None
    # fair probs sum to ~1.0 (within floating-point tolerance)
    assert math.isclose(
        espn_cell.devigged_home + espn_cell.devigged_away, 1.0, abs_tol=0.01)
