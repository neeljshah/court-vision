"""predict_service.test_assemble_soccer_threeway

Tests that market_rows correctly devigs 3-way soccer markets (home/draw/away)
using the Shin N-outcome path, and that 2-way sports still use the 2-way path.

Acceptance criteria (per workstream spec):
  1. Soccer 3-way odds produce non-null devigged_prob on every leg.
  2. The three devigged_probs per book sum to ~1.0 (Shin normalizes).
  3. edge_rows yields >= 1 comparison row when model probs cover the same sides.
  4. Two-way sports (no draw) still produce non-null devigged_prob (regression guard).
  5. No AssertionError 'booksum < 1' from the Shin solver on well-formed soccer odds.
"""
from __future__ import annotations

import pytest
from predict_service.assemble import market_rows, edge_rows, model_probs_from_pregame

# --- realistic soccer decimal odds from a single book ---
_SOCCER_PRICES = {
    "pinnacle": {"home": 2.10, "draw": 3.40, "away": 3.60},
    "bet365":   {"home": 2.15, "draw": 3.35, "away": 3.50},
}

# --- realistic NBA/2-way prices (no draw) ---
_NBA_PRICES = {
    "draftkings": {"home": 1.91, "away": 2.05},
}


class TestSoccerThreeWayDevig:
    """3-way soccer market devigging via Shin N-outcome path."""

    def test_all_legs_have_devigged_prob(self):
        """Every (book, side) row for a 3-way market has non-null devigged_prob."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        assert rows, "market_rows must return at least one row"
        null_rows = [r for r in rows if r.devigged_prob is None]
        assert not null_rows, (
            f"Rows with null devigged_prob: {null_rows} -- draw leg is being dropped"
        )

    def test_three_sides_produced_per_book(self):
        """Each book produces exactly three sides: home, draw, away."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        for book in _SOCCER_PRICES:
            book_rows = [r for r in rows if r.book == book]
            sides = {r.side for r in book_rows}
            assert sides == {"home", "draw", "away"}, (
                f"Book {book} has sides {sides}, expected home+draw+away"
            )

    def test_devigged_probs_sum_to_one_per_book(self):
        """Shin fair probs for the 3 legs sum to ~1.0 for each book."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        for book in _SOCCER_PRICES:
            book_rows = [r for r in rows if r.book == book]
            total = sum(r.devigged_prob for r in book_rows if r.devigged_prob is not None)
            assert abs(total - 1.0) < 0.001, (
                f"Book {book} devigged probs sum {total:.6f}, expected ~1.0"
            )

    def test_each_devigged_prob_in_unit_interval(self):
        """Each devigged probability is strictly between 0 and 1."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        for r in rows:
            assert r.devigged_prob is not None
            assert 0.0 < r.devigged_prob < 1.0, (
                f"Devigged prob {r.devigged_prob} out of (0, 1) for {r.side}@{r.book}"
            )

    def test_edge_rows_yields_at_least_one_comparison(self):
        """edge_rows returns >= 1 row when model probs span the same sides."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        # Realistic model probs for a 3-way soccer game (sum ~1).
        model_probs = {"home": 0.45, "draw": 0.27, "away": 0.28}
        edges = edge_rows("game-001", model_probs, rows)
        assert len(edges) >= 1, (
            "edge_rows must yield at least one comparison row for a 3-way market"
        )

    def test_all_three_sides_have_edge_rows(self):
        """All three soccer sides (home/draw/away) get an EdgeRow."""
        rows = market_rows("soccer", "game-001", _SOCCER_PRICES)
        model_probs = {"home": 0.45, "draw": 0.27, "away": 0.28}
        edges = edge_rows("game-001", model_probs, rows)
        sides = {e.side for e in edges}
        assert sides == {"home", "draw", "away"}, (
            f"EdgeRow sides {sides}, expected home+draw+away"
        )

    def test_no_booksum_assertion_error(self):
        """Shin solver must not raise AssertionError 'booksum < 1' for valid odds."""
        # A book with a realistic soccer overround (~106%).
        prices = {"test_book": {"home": 2.10, "draw": 3.40, "away": 3.60}}
        try:
            rows = market_rows("soccer", "g-test", prices)
        except AssertionError as exc:
            pytest.fail(f"Shin solver raised AssertionError: {exc}")
        assert rows

    def test_model_probs_from_pregame_extracts_draw(self):
        """model_probs_from_pregame surfaces the draw probability for 3-way markets."""
        pregame = {"p_home_win": 0.45, "p_draw": 0.27, "p_away_win": 0.28}
        probs = model_probs_from_pregame(pregame)
        assert "draw" in probs, "draw probability must be extracted from p_draw"
        assert abs(probs["draw"] - 0.27) < 1e-9


class TestTwoWaySportsUnaffected:
    """Two-way markets (NBA, MLB) still use devig_twoway -- regression guard."""

    def test_nba_two_way_has_devigged_prob(self):
        """NBA (no draw) rows must still have non-null devigged_prob."""
        rows = market_rows("basketball_nba", "nba-001", _NBA_PRICES)
        assert rows, "NBA market_rows must return rows"
        null_rows = [r for r in rows if r.devigged_prob is None]
        assert not null_rows, f"NBA rows with null devigged_prob: {null_rows}"

    def test_nba_two_sides_only(self):
        """NBA produces exactly home and away -- no draw row."""
        rows = market_rows("basketball_nba", "nba-001", _NBA_PRICES)
        sides = {r.side for r in rows}
        assert sides == {"home", "away"}, (
            f"NBA has sides {sides}, draw must not appear"
        )

    def test_nba_devigged_probs_sum_to_one(self):
        """NBA devigged home + away probs sum to ~1.0 per book."""
        rows = market_rows("basketball_nba", "nba-001", _NBA_PRICES)
        for book in _NBA_PRICES:
            book_rows = [r for r in rows if r.book == book]
            total = sum(r.devigged_prob for r in book_rows if r.devigged_prob is not None)
            assert abs(total - 1.0) < 0.001, (
                f"NBA book {book} devigged probs sum {total:.6f}, expected ~1.0"
            )

    def test_book_quoting_only_two_legs_gets_twoway_path(self):
        """A soccer book that only quotes home+away (no draw) uses the 2-way path."""
        prices = {"oddschecker": {"home": 1.90, "away": 2.10}}
        rows = market_rows("soccer", "g-partial", prices)
        sides = {r.side for r in rows}
        assert "draw" not in sides
        null_rows = [r for r in rows if r.devigged_prob is None]
        assert not null_rows
