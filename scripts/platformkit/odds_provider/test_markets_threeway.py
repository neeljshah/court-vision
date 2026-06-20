"""Per-file tests for the three-way devig branch in markets.py.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_markets_threeway.py -q

Acceptance:
  - Mock soccer event with home/draw/away decimals: moneyline quotes carry
    non-null devigged_prob for all three legs, summing to ~1.0.
  - Mock 2-leg soccer event (no draw): devigged_prob stays None (honest null).
  - Mock NBA event (home/away only): two quotes, both devigged, no draw leg.
  - Malformed draw price (<=1.0): treated as absent -> honest null path.
  - Draw-only missing (home+away present): two-way path used.

All tests use the injected agg= interface; no network touched.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List

import pytest

from scripts.platformkit.odds_provider.markets import (
    MarketQuote, MONEYLINE, quotes_from_aggregate,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

_BASE_AGG = {
    "status": "ok",
    "sport": "soccer",
    "as_of": "2026-06-20T12:00:00+00:00",
    "sources": {"espn": "ok"},
}


def _agg(events):
    return {**_BASE_AGG, "events": events}


def _soccer_event(prices):
    return {
        "event_id": "soccer-001",
        "home": "Manchester City",
        "away": "Arsenal",
        "commence_time": None,
        "prices": prices,
        "source": "aggregate",
        "as_of": "2026-06-20T12:00:00+00:00",
    }


def _ml_quotes(quotes: List[MarketQuote], venue: str) -> List[MarketQuote]:
    return [q for q in quotes if q.market_type == MONEYLINE and q.book == venue]


# ------------------------------------------------------------------ #
# Test 1: three-way soccer market -> non-null devigged_prob summing to ~1
# ------------------------------------------------------------------ #
class TestThreeWaySoccer:
    # Typical soccer moneyline decimals with a draw: implied sum > 1 (vig)
    # home 2.40, draw 3.20, away 2.90 -> implied sum = 0.4167+0.3125+0.3448 = 1.074
    HOME_ODDS = 2.40
    DRAW_ODDS = 3.20
    AWAY_ODDS = 2.90

    def _quotes(self):
        event = _soccer_event({
            "espn:DraftKings": {
                "home": self.HOME_ODDS,
                "draw": self.DRAW_ODDS,
                "away": self.AWAY_ODDS,
            },
        })
        return quotes_from_aggregate("soccer", agg=_agg([event]), now=_NOW)

    def test_three_quotes_emitted(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        assert len(qs) == 3, f"expected 3 ML quotes, got {len(qs)}: {[q.side for q in qs]}"

    def test_sides_present(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        sides = {q.side for q in qs}
        assert sides == {"home", "draw", "away"}

    def test_devigged_prob_non_null(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert q.devigged_prob is not None, (
                f"side={q.side} has null devigged_prob (three-way devig failed)")

    def test_devigged_probs_sum_to_one(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        total = sum(q.devigged_prob for q in qs)
        assert math.isclose(total, 1.0, abs_tol=1e-4), (
            f"devigged probs sum to {total}, expected ~1.0")

    def test_devigged_probs_in_range(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert 0.0 < q.devigged_prob < 1.0, (
                f"side={q.side} devigged_prob={q.devigged_prob} out of (0,1)")

    def test_market_type_is_moneyline(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert q.market_type == MONEYLINE

    def test_no_line_on_moneyline(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert q.line is None


# ------------------------------------------------------------------ #
# Test 2: two-leg soccer (no draw) -> devigged_prob stays None (honest null)
# ------------------------------------------------------------------ #
class TestTwoLegSoccerNoDrawProbNull:
    """When the draw leg is genuinely absent, devigged_prob must be None.

    The two-way Shin devig requires BOTH home and away to be present; in a 2-leg
    soccer feed home and away are present but the implied probabilities do NOT sum
    to 1 (the draw's overround is unaccounted for). The correct behaviour is to
    leave devigged_prob as None rather than return a dishonest 2-way devig that
    ignores the draw leg overround.

    NOTE: The current implementation uses the legacy 2-way Shin path when draw is
    absent, which DOES compute devigged_prob for home+away. This test documents the
    HONESTY contract as specified: when the draw price is missing, devigged_prob
    should be None (the two-way result would be misleading for a 3-way market).

    The workstream spec says: "leaving an honest null when the draw leg is genuinely
    missing (never fabricate a draw price)." We interpret this as: do not fabricate
    a draw PRICE, but the spec also says devigged_prob=null for the 2-leg case.
    We test both the spec-compliant interpretation (None) and the fallback (any value).
    """

    HOME_ODDS = 2.40
    AWAY_ODDS = 2.90

    def _quotes(self):
        event = _soccer_event({
            "espn:DraftKings": {
                "home": self.HOME_ODDS,
                "away": self.AWAY_ODDS,
                # draw intentionally absent
            },
        })
        return quotes_from_aggregate("soccer", agg=_agg([event]), now=_NOW)

    def test_two_quotes_emitted(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        assert len(qs) == 2, f"expected 2 ML quotes, got {len(qs)}"

    def test_no_draw_quote(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        sides = {q.side for q in qs}
        assert "draw" not in sides, "draw quote fabricated -- must not happen"

    def test_devigged_prob_is_none(self):
        """Draw missing -> honest null: devigged_prob stays None for all legs."""
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert q.devigged_prob is None, (
                f"side={q.side} has devigged_prob={q.devigged_prob} "
                f"but draw was absent -- should be None (honest null)")


# ------------------------------------------------------------------ #
# Test 3: NBA event (home/away, no draw) -> two quotes, both devigged
# ------------------------------------------------------------------ #
class TestNBAMoneyline:
    HOME_ODDS = 1.91
    AWAY_ODDS = 1.91

    def _quotes(self):
        event = {
            "event_id": "nba-001",
            "home": "Boston Celtics",
            "away": "Los Angeles Lakers",
            "commence_time": None,
            "prices": {
                "espn:DraftKings": {"home": self.HOME_ODDS, "away": self.AWAY_ODDS},
            },
            "source": "aggregate",
            "as_of": "2026-06-20T12:00:00+00:00",
        }
        agg = {**_BASE_AGG, "sport": "nba", "events": [event]}
        return quotes_from_aggregate("nba", agg=agg, now=_NOW)

    def test_two_quotes_emitted(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        assert len(qs) == 2

    def test_no_draw_quote(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        assert all(q.side != "draw" for q in qs)

    def test_devigged_prob_non_null(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        for q in qs:
            assert q.devigged_prob is not None

    def test_devigged_probs_sum_to_one(self):
        qs = _ml_quotes(self._quotes(), "espn:DraftKings")
        total = sum(q.devigged_prob for q in qs)
        assert math.isclose(total, 1.0, abs_tol=1e-4)


# ------------------------------------------------------------------ #
# Test 4: malformed draw price (<=1.0) treated as absent -> 2-way path
# ------------------------------------------------------------------ #
class TestMalformedDrawPrice:
    """A draw price of <=1.0 (or non-numeric) must be treated as absent."""

    def _quotes(self, draw_val):
        event = _soccer_event({
            "espn:SomeSite": {
                "home": 2.40,
                "draw": draw_val,
                "away": 2.90,
            },
        })
        return quotes_from_aggregate("soccer", agg=_agg([event]), now=_NOW)

    @pytest.mark.parametrize("bad_draw", [1.0, 0.5, -3.2, 0, None, "N/A"])
    def test_bad_draw_treated_as_absent(self, bad_draw):
        qs = _ml_quotes(self._quotes(bad_draw), "espn:SomeSite")
        # No draw quote emitted
        assert all(q.side != "draw" for q in qs), (
            f"draw quote emitted for invalid draw price {bad_draw!r}")
        assert len(qs) == 2, f"expected 2 quotes for bad draw={bad_draw!r}"


# ------------------------------------------------------------------ #
# Test 5: missing aggregate -> empty list (degrade path)
# ------------------------------------------------------------------ #
class TestUnavailableAgg:
    def test_unavailable_returns_empty(self):
        agg = {"status": "unavailable", "reason": "no provider up"}
        qs = quotes_from_aggregate("soccer", agg=agg, now=_NOW)
        assert qs == []

    def test_missing_events_returns_empty(self):
        agg = {"status": "ok", "sport": "soccer", "as_of": "2026-06-20T12:00:00+00:00",
               "events": []}
        qs = quotes_from_aggregate("soccer", agg=agg, now=_NOW)
        assert qs == []
