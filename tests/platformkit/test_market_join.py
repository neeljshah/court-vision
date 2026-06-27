"""Per-file unit tests for odds_provider.market_join (NETWORK-FREE).

Run ONLY this file:
    python -m pytest tests/platformkit/test_market_join.py -q

Covers:
  * A matched (edge, quote) pair joins correctly, carrying model_prob + book line
    + devigged_prob in a single JoinedRow.
  * An edge with NO matching quote is omitted (never fabricated into a row).
  * A quote with no matching edge is silently ignored.
  * Multiple books per side -> ALL rows kept (one JoinedRow per (edge, book) pair);
    callers pick best price; nothing is dropped.
  * EdgeRow dicts and EdgeRow-like objects are both accepted.
  * Malformed edges / quotes (missing key fields) are silently skipped.
"""
from dataclasses import dataclass
from typing import Optional

import pytest

from scripts.platformkit.odds_provider.market_join import (
    JoinedRow, join_quotes_to_edges)
from scripts.platformkit.odds_provider.markets import (
    MONEYLINE, SPREAD, TOTAL, MarketQuote)

# --------------------------------------------------------------------------- #
# Minimal EdgeRow-alike (dataclass) -- avoids importing predict_service.contracts
# so this test is pure platformkit and does not depend on predict_service init.
# --------------------------------------------------------------------------- #

@dataclass
class _Edge:
    game_id: str
    market_type: str
    side: str
    model_prob: float
    market_prob: float
    ev: float
    tier: Optional[str] = None
    book: str = ""
    line: Optional[float] = None
    clv_is_proxy: bool = True


# --------------------------------------------------------------------------- #
# Fixtures -- canned quotes
# --------------------------------------------------------------------------- #

_CAPTURED = "2026-06-18T20:00:00+00:00"


def _ml_quote(game_id, side, book, odds, devigged=None):
    return MarketQuote(
        sport="nba", game_id=game_id, home="Boston Celtics",
        away="New York Knicks", market_type=MONEYLINE, side=side,
        line=None, odds=odds, book=book,
        captured_at=_CAPTURED, devigged_prob=devigged,
    )


def _spread_quote(game_id, side, line, book, odds, devigged=None):
    return MarketQuote(
        sport="nba", game_id=game_id, home="Boston Celtics",
        away="New York Knicks", market_type=SPREAD, side=side,
        line=line, odds=odds, book=book,
        captured_at=_CAPTURED, devigged_prob=devigged,
    )


def _total_quote(game_id, side, line, book, odds, devigged=None):
    return MarketQuote(
        sport="nba", game_id=game_id, home="Boston Celtics",
        away="New York Knicks", market_type=TOTAL, side=side,
        line=line, odds=odds, book=book,
        captured_at=_CAPTURED, devigged_prob=devigged,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

class TestMatchedPairJoin:
    """A fully-formed edge + matching quote -> one JoinedRow with all fields."""

    def test_basic_moneyline_join(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
            tier="B", book="espn:DraftKings", clv_is_proxy=False,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.61, devigged=0.622)
        rows = join_quotes_to_edges([edge], [quote])

        assert len(rows) == 1
        r = rows[0]
        assert isinstance(r, JoinedRow)
        assert r.game_id == "401"
        assert r.market_type == MONEYLINE
        assert r.side == "home"
        # edge fields preserved
        assert r.model_prob == pytest.approx(0.58)
        assert r.market_prob == pytest.approx(0.62)
        assert r.ev == pytest.approx(-0.07)
        assert r.tier == "B"
        assert r.edge_book == "espn:DraftKings"
        assert r.edge_line is None
        assert r.edge_clv_is_proxy is False
        # quote fields preserved
        assert r.quote_book == "espn:DraftKings"
        assert r.quote_line is None
        assert r.quote_odds == pytest.approx(1.61)
        assert r.quote_devigged_prob == pytest.approx(0.622)
        assert r.quote_captured_at == _CAPTURED

    def test_spread_join_carries_line(self):
        edge = _Edge(
            game_id="401", market_type=SPREAD, side="home",
            model_prob=0.52, market_prob=0.50, ev=0.04,
            tier="A", book="espn:DraftKings", line=-5.5,
        )
        quote = _spread_quote("401", "home", -5.5, "espn:DraftKings", 1.91, 0.495)
        rows = join_quotes_to_edges([edge], [quote])

        assert len(rows) == 1
        r = rows[0]
        assert r.edge_line == -5.5
        assert r.quote_line == -5.5
        assert r.quote_odds == pytest.approx(1.91)
        assert r.quote_devigged_prob == pytest.approx(0.495)

    def test_total_join_over_under(self):
        edge_over = _Edge(
            game_id="401", market_type=TOTAL, side="over",
            model_prob=0.55, market_prob=0.50, ev=0.10, tier="C",
        )
        q_over = _total_quote("401", "over", 220.5, "espn:DraftKings", 1.95, 0.501)
        q_under = _total_quote("401", "under", 220.5, "espn:DraftKings", 1.87, 0.499)
        rows = join_quotes_to_edges([edge_over], [q_over, q_under])

        # only over edge supplied -> only the over quote should match
        assert len(rows) == 1
        assert rows[0].side == "over"
        assert rows[0].quote_line == 220.5

    def test_to_dict_is_json_safe(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="away",
            model_prob=0.42, market_prob=0.38, ev=0.10, tier=None,
        )
        quote = _ml_quote("401", "away", "kalshi", 2.50)
        rows = join_quotes_to_edges([edge], [quote])
        d = rows[0].to_dict()
        assert d["game_id"] == "401"
        assert d["model_prob"] == pytest.approx(0.42)
        assert d["quote_devigged_prob"] is None  # one-sided quote -> None, not fabricated


class TestNoMatchOmission:
    """Edges without a matching quote are omitted; quotes with no edge ignored."""

    def test_edge_with_no_quote_is_omitted(self):
        edge = _Edge(
            game_id="999", market_type=MONEYLINE, side="home",
            model_prob=0.55, market_prob=0.50, ev=0.10,
        )
        # quote is for a different game
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.50)
        rows = join_quotes_to_edges([edge], [quote])
        assert rows == []

    def test_edge_with_wrong_market_type_is_omitted(self):
        edge = _Edge(
            game_id="401", market_type=SPREAD, side="home",
            model_prob=0.52, market_prob=0.50, ev=0.04,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.50)  # moneyline, not spread
        rows = join_quotes_to_edges([edge], [quote])
        assert rows == []

    def test_edge_with_wrong_side_is_omitted(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="away",
            model_prob=0.42, market_prob=0.38, ev=0.10,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.50)  # home, not away
        rows = join_quotes_to_edges([edge], [quote])
        assert rows == []

    def test_quote_with_no_edge_is_ignored(self):
        # quote for a game that has no edge -> should produce zero rows
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.50)
        rows = join_quotes_to_edges([], [quote])
        assert rows == []

    def test_empty_inputs_returns_empty(self):
        assert join_quotes_to_edges([], []) == []

    def test_partial_match(self):
        # one edge matches, one does not
        e_match = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
        )
        e_miss = _Edge(
            game_id="402", market_type=MONEYLINE, side="home",
            model_prob=0.55, market_prob=0.50, ev=0.10,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.61)
        rows = join_quotes_to_edges([e_match, e_miss], [quote])
        assert len(rows) == 1
        assert rows[0].game_id == "401"


class TestMultipleBooksPerSide:
    """Multiple books pricing the same side -> all rows kept (one per book).

    Design choice: KEEP ALL rows.  Caller can filter/sort by quote_odds to pick
    best price, or use all rows to compute CLV vs each venue's close independently.
    """

    def test_two_books_produce_two_rows(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07, tier="B",
        )
        q_dk = _ml_quote("401", "home", "espn:DraftKings", 1.61, devigged=0.622)
        q_fv = _ml_quote("401", "home", "espn:FanDuel", 1.63, devigged=0.619)
        q_km = _ml_quote("401", "home", "kalshi", 1.58)

        rows = join_quotes_to_edges([edge], [q_dk, q_fv, q_km])

        assert len(rows) == 3
        books = {r.quote_book for r in rows}
        assert books == {"espn:DraftKings", "espn:FanDuel", "kalshi"}
        # every row shares the same model edge fields
        for r in rows:
            assert r.game_id == "401"
            assert r.model_prob == pytest.approx(0.58)
            assert r.tier == "B"

    def test_best_price_identifiable(self):
        """Caller can identify best price by sorting; no row is dropped."""
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="away",
            model_prob=0.42, market_prob=0.38, ev=0.10,
        )
        q1 = _ml_quote("401", "away", "espn:DraftKings", 2.50)
        q2 = _ml_quote("401", "away", "espn:BetMGM", 2.60)  # better price
        rows = join_quotes_to_edges([edge], [q1, q2])
        best = max(rows, key=lambda r: r.quote_odds)
        assert best.quote_book == "espn:BetMGM"
        assert best.quote_odds == pytest.approx(2.60)

    def test_multiple_edges_multiple_books(self):
        """Two edges (different markets) each with two books -> four rows."""
        e_ml = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
        )
        e_spread = _Edge(
            game_id="401", market_type=SPREAD, side="home",
            model_prob=0.52, market_prob=0.50, ev=0.04, line=-5.5,
        )
        q_ml_dk = _ml_quote("401", "home", "espn:DraftKings", 1.61)
        q_ml_fv = _ml_quote("401", "home", "espn:FanDuel", 1.63)
        q_sp_dk = _spread_quote("401", "home", -5.5, "espn:DraftKings", 1.91)
        q_sp_fv = _spread_quote("401", "home", -5.5, "espn:FanDuel", 1.90)
        rows = join_quotes_to_edges(
            [e_ml, e_spread],
            [q_ml_dk, q_ml_fv, q_sp_dk, q_sp_fv],
        )
        assert len(rows) == 4
        ml_rows = [r for r in rows if r.market_type == MONEYLINE]
        sp_rows = [r for r in rows if r.market_type == SPREAD]
        assert len(ml_rows) == 2 and len(sp_rows) == 2


class TestInputFlexibility:
    """Both EdgeRow-like dataclasses and plain dicts are accepted."""

    def test_dict_edge_accepted(self):
        edge_dict = {
            "game_id": "401", "market_type": MONEYLINE, "side": "home",
            "model_prob": 0.58, "market_prob": 0.62, "ev": -0.07,
            "tier": "B", "book": "espn:DraftKings", "line": None,
            "clv_is_proxy": False,
        }
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.61)
        rows = join_quotes_to_edges([edge_dict], [quote])
        assert len(rows) == 1
        r = rows[0]
        assert r.model_prob == pytest.approx(0.58)
        assert r.tier == "B"
        assert r.edge_clv_is_proxy is False

    def test_dict_edge_missing_optional_fields(self):
        # Minimal dict with only join key + required numeric fields
        edge_dict = {
            "game_id": "401", "market_type": MONEYLINE, "side": "away",
            "model_prob": 0.42, "market_prob": 0.38, "ev": 0.10,
        }
        quote = _ml_quote("401", "away", "kalshi", 2.50)
        rows = join_quotes_to_edges([edge_dict], [quote])
        assert len(rows) == 1
        assert rows[0].tier is None
        assert rows[0].edge_book == ""


class TestMalformedInputs:
    """Malformed edges and quotes are silently skipped -- never raise."""

    def test_malformed_edge_missing_game_id(self):
        bad_edge = {"market_type": MONEYLINE, "side": "home",
                    "model_prob": 0.55, "market_prob": 0.50, "ev": 0.10}
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.50)
        rows = join_quotes_to_edges([bad_edge], [quote])
        assert rows == []

    def test_none_in_edge_list_skipped(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.61)
        # None slipped in between valid edges
        rows = join_quotes_to_edges([None, edge, None], [quote])
        assert len(rows) == 1

    def test_returns_list_type(self):
        rows = join_quotes_to_edges([], [])
        assert isinstance(rows, list)


class TestDeviggPropagation:
    """devigged_prob from quote is carried through; None stays None."""

    def test_devigged_prob_propagated(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
        )
        quote = _ml_quote("401", "home", "espn:DraftKings", 1.61, devigged=0.6215)
        rows = join_quotes_to_edges([edge], [quote])
        assert rows[0].quote_devigged_prob == pytest.approx(0.6215)

    def test_none_devigged_stays_none(self):
        edge = _Edge(
            game_id="401", market_type=MONEYLINE, side="home",
            model_prob=0.58, market_prob=0.62, ev=-0.07,
        )
        quote = _ml_quote("401", "home", "kalshi", 1.55, devigged=None)
        rows = join_quotes_to_edges([edge], [quote])
        assert rows[0].quote_devigged_prob is None
