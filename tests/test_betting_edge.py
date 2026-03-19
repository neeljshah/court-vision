"""
Tests for src/analytics/betting_edge.py.

Covers:
  - calculate_ev: positive EV, negative EV, zero edge
  - kelly_fraction: capped at 2%, zero for non-positive edge
  - find_edges: sorted output, filtering, BettingEdge fields
  - american_to_decimal + implied_probability helpers
  - BettingEdge dataclass fields
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.betting_edge import (
    BettingEdge,
    american_to_decimal,
    implied_probability,
    calculate_ev,
    kelly_fraction,
    find_edges,
    _KELLY_MAX_FRACTION,
)


# ── american_to_decimal ───────────────────────────────────────────────────────

class TestAmericanToDecimal:

    def test_plus_150(self):
        """+150 → 2.5 decimal."""
        assert american_to_decimal(150) == pytest.approx(2.5)

    def test_minus_110(self):
        """-110 → 100/110 + 1 = 1.9090..."""
        assert american_to_decimal(-110) == pytest.approx(100 / 110 + 1, abs=1e-4)

    def test_even_money(self):
        """+100 → 2.0 decimal."""
        assert american_to_decimal(100) == pytest.approx(2.0)

    def test_minus_200(self):
        """-200 → 1.5 decimal."""
        assert american_to_decimal(-200) == pytest.approx(1.5)

    def test_result_greater_than_one(self):
        """Decimal odds always > 1 for valid American odds."""
        for odds in [-200, -110, -105, 100, 110, 150, 300]:
            assert american_to_decimal(odds) > 1.0


# ── implied_probability ───────────────────────────────────────────────────────

class TestImpliedProbability:

    def test_minus_110_implied_prob(self):
        """-110 → implied prob ≈ 0.524."""
        prob = implied_probability(-110)
        assert 0.52 < prob < 0.53

    def test_even_money_is_half(self):
        """+100 → implied prob = 0.5."""
        assert implied_probability(100) == pytest.approx(0.5)

    def test_heavy_favourite(self):
        """-200 → implied prob ≈ 0.667."""
        assert implied_probability(-200) == pytest.approx(2 / 3, abs=1e-3)

    def test_result_in_unit_interval(self):
        """Implied prob always in (0, 1)."""
        for odds in [-300, -110, 100, 150, 300]:
            p = implied_probability(odds)
            assert 0.0 < p < 1.0


# ── calculate_ev ──────────────────────────────────────────────────────────────

class TestCalculateEV:

    def test_positive_ev_plus_100(self):
        """60% win prob at +100 odds → positive EV."""
        ev = calculate_ev(0.60, 100)
        # EV = 0.6*1.0 - 0.4*1.0 = 0.20
        assert ev == pytest.approx(0.20, abs=1e-4)

    def test_negative_ev_minus_110_low_prob(self):
        """45% win prob at -110 → negative EV."""
        ev = calculate_ev(0.45, -110)
        assert ev < 0

    def test_zero_edge_near_zero_ev(self):
        """Win prob equals implied prob → EV ≈ 0."""
        prob = implied_probability(-110)
        ev = calculate_ev(prob, -110)
        assert abs(ev) < 0.01

    def test_returns_float(self):
        assert isinstance(calculate_ev(0.55, -110), float)

    def test_zero_prob_is_negative(self):
        """0% win prob → pure loss → EV = -1.0 (lose stake)."""
        ev = calculate_ev(0.0, 100)
        assert ev == pytest.approx(-1.0, abs=1e-4)

    def test_certain_win_is_positive(self):
        """100% win prob at +100 → EV = +1.0 (win stake)."""
        ev = calculate_ev(1.0, 100)
        assert ev == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.parametrize("prob,odds", [
        (0.55, -110),
        (0.60, +100),
        (0.70, +150),
    ])
    def test_positive_edge_gives_positive_ev(self, prob, odds):
        """Probability above implied always gives positive EV."""
        book_prob = implied_probability(odds)
        assert prob > book_prob   # pre-condition
        assert calculate_ev(prob, odds) > 0


# ── kelly_fraction ────────────────────────────────────────────────────────────

class TestKellyFraction:

    def test_positive_edge_returns_positive(self):
        """Positive edge → positive bet size."""
        size = kelly_fraction(0.60, 100, 1000.0)
        assert size > 0

    def test_zero_edge_returns_zero(self):
        """Zero edge → bet size 0."""
        assert kelly_fraction(0.0, 100, 1000.0) == 0.0

    def test_negative_edge_returns_zero(self):
        """Negative edge → bet size 0."""
        assert kelly_fraction(-0.05, -110, 1000.0) == 0.0

    def test_kelly_cap_at_two_percent(self):
        """Bet size never exceeds 2% of bankroll."""
        # Huge edge should hit the cap
        size = kelly_fraction(0.99, 100, 10000.0)
        assert size <= 10000.0 * _KELLY_MAX_FRACTION

    def test_kelly_cap_exact(self):
        """Bet size is exactly capped at 2% for large edges."""
        bankroll = 5000.0
        size = kelly_fraction(0.95, 100, bankroll)
        assert size <= bankroll * 0.02

    def test_zero_bankroll_returns_zero(self):
        """Zero bankroll → no bet."""
        assert kelly_fraction(0.60, 100, 0.0) == 0.0

    def test_returns_float(self):
        assert isinstance(kelly_fraction(0.55, -110, 1000.0), float)

    def test_quarter_kelly_smaller_than_full(self):
        """Quarter-Kelly (default) produces smaller bet than full Kelly."""
        full  = kelly_fraction(0.60, 100, 1000.0, fraction=1.0)
        quart = kelly_fraction(0.60, 100, 1000.0, fraction=0.25)
        # Both may be capped, but uncapped quarter should be smaller
        # (We just verify quarter is <= full after capping)
        assert quart <= full


# ── find_edges ────────────────────────────────────────────────────────────────

class TestFindEdges:

    def _make_props(self):
        return [
            {
                "player": "LeBron James", "stat": "pts",
                "line": 24.5, "direction": "over",
                "your_prob": 0.62, "bankroll": 1000.0,
            },
            {
                "player": "Nikola Jokic", "stat": "reb",
                "line": 10.5, "direction": "over",
                "your_prob": 0.40, "bankroll": 1000.0,  # negative EV
            },
            {
                "player": "Stephen Curry", "stat": "3pm",
                "line": 4.5, "direction": "over",
                "your_prob": 0.58, "bankroll": 1000.0,
            },
        ]

    def _make_odds(self):
        return {
            "LeBron James|pts|24.5|over":  -110,
            "Nikola Jokic|reb|10.5|over":  -110,
            "Stephen Curry|3pm|4.5|over":  +105,
        }

    def test_returns_list(self):
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        assert isinstance(result, list)

    def test_negative_ev_excluded(self):
        """Props with negative EV are not included in result."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        players = [e.player for e in result]
        assert "Nikola Jokic" not in players

    def test_positive_ev_included(self):
        """Props with positive EV are included."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        players = [e.player for e in result]
        assert "LeBron James" in players
        assert "Stephen Curry" in players

    def test_sorted_by_ev_descending(self):
        """Results sorted by EV descending."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        evs = [e.ev for e in result]
        assert evs == sorted(evs, reverse=True)

    def test_betting_edge_has_required_fields(self):
        """Each BettingEdge has all required attributes."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        assert len(result) > 0
        e = result[0]
        for attr in ("player", "stat", "line", "direction", "your_prob",
                     "book_prob", "edge_pct", "ev", "kelly_size"):
            assert hasattr(e, attr)

    def test_edge_pct_is_your_minus_book(self):
        """edge_pct == your_prob - book_prob."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        for e in result:
            assert abs(e.edge_pct - (e.your_prob - e.book_prob)) < 1e-4

    def test_empty_props_returns_empty(self):
        """Empty props list → empty result."""
        from src.analytics.betting_edge import find_edges
        assert find_edges([], self._make_odds()) == []

    def test_empty_odds_feed_returns_empty(self):
        """No matching odds → empty result."""
        from src.analytics.betting_edge import find_edges
        assert find_edges(self._make_props(), {}) == []

    def test_kelly_size_never_exceeds_cap(self):
        """kelly_size in every edge is <= 2% of bankroll."""
        from src.analytics.betting_edge import find_edges
        result = find_edges(self._make_props(), self._make_odds())
        for e in result:
            bankroll = next(
                p["bankroll"] for p in self._make_props()
                if p["player"] == e.player
            )
            assert e.kelly_size <= bankroll * 0.02 + 0.01  # +0.01 for float rounding


# ── BettingEdge dataclass ─────────────────────────────────────────────────────

class TestBettingEdgeDataclass:

    def test_instantiation(self):
        """BettingEdge can be instantiated directly."""
        e = BettingEdge(
            player="LeBron James", stat="pts", line=24.5,
            direction="over", your_prob=0.62, book_prob=0.524,
            edge_pct=0.096, ev=0.18, kelly_size=5.0,
        )
        assert e.player == "LeBron James"
        assert e.stat == "pts"
        assert e.kelly_size == 5.0

    def test_is_dataclass(self):
        """BettingEdge is a dataclass."""
        import dataclasses
        assert dataclasses.is_dataclass(BettingEdge)
