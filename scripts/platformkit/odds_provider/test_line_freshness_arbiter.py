"""tests for scripts.platformkit.odds_provider.line_freshness_arbiter

Per-file test (run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_line_freshness_arbiter.py -q

Acceptance criteria (BE-R4-7):
  1. Two venues, one fresh one stale -> fresh venue selected (not the stale one,
     even if stale would have a higher price).
  2. All venues past SLA -> UNAVAILABLE (never a stale price returned as winner).
  3. Missing / None captured_at -> treated as stale, not as fresh.
  4. Injectable now-clock -> results are reproducible / deterministic.
  5. No $ field anywhere in the output.
  6. Empty input -> UNAVAILABLE (no crash, no fabricated winner).
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from scripts.platformkit.odds_provider.line_freshness_arbiter import (
    UNAVAILABLE,
    ArbitrateResult,
    VenueAge,
    arbitrate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)
_MAX_AGE = 900.0  # 15 minutes (default)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _ago(seconds: float) -> str:
    """ISO-8601 timestamp that is *seconds* old relative to _T0."""
    from datetime import timedelta
    return _iso(_T0 - timedelta(seconds=seconds))


# ---------------------------------------------------------------------------
# Core acceptance tests
# ---------------------------------------------------------------------------

class TestTwoVenuesOneFreshOneStale:
    """Acceptance: fresh venue wins even when stale venue was polled earlier."""

    def test_fresh_venue_selected(self):
        """The fresh venue is returned as winner."""
        ts_fresh = _ago(60)      # 1 minute old -- within 15-min SLA
        ts_stale = _ago(1000)    # ~17 minutes old -- past SLA

        result = arbitrate(
            {"espn:DraftKings": ts_stale, "espn:FanDuel": ts_fresh},
            now=_T0,
        )

        assert result.status == "fresh"
        assert result.winner == "espn:FanDuel"

    def test_stale_venue_not_winner(self):
        """The stale venue must NEVER appear as winner."""
        ts_fresh = _ago(60)
        ts_stale = _ago(1000)

        result = arbitrate(
            {"espn:DraftKings": ts_stale, "espn:FanDuel": ts_fresh},
            now=_T0,
        )

        assert result.winner != "espn:DraftKings"

    def test_freshest_among_multiple_fresh_wins(self):
        """When multiple venues are fresh, the one with the smallest age wins."""
        ts_newest = _ago(30)     # 30s old -- freshest
        ts_older = _ago(600)     # 10 min old -- still fresh but older

        result = arbitrate(
            {"book_A": ts_older, "book_B": ts_newest},
            now=_T0,
        )

        assert result.status == "fresh"
        assert result.winner == "book_B"
        assert result.winner_age_sec == pytest.approx(30.0, abs=0.1)


class TestAllVenuesPastSla:
    """Acceptance: UNAVAILABLE when every source is stale."""

    def test_all_stale_returns_unavailable(self):
        result = arbitrate(
            {"book_A": _ago(1000), "book_B": _ago(2000)},
            now=_T0,
        )

        assert result.status == UNAVAILABLE
        assert result.winner is None
        assert result.winner_age_sec is None

    def test_candidates_still_populated_when_all_stale(self):
        """candidates list carries all venues even when UNAVAILABLE (audit trail)."""
        result = arbitrate({"book_A": _ago(1000), "book_B": _ago(2000)}, now=_T0)
        assert len(result.candidates) == 2
        for va in result.candidates:
            assert not va.is_fresh

    def test_single_stale_venue_is_unavailable(self):
        result = arbitrate({"book_A": _ago(5000)}, now=_T0)
        assert result.status == UNAVAILABLE
        assert result.winner is None


class TestMissingOrNoneCapturedAt:
    """Acceptance: missing/None/unparseable timestamps are treated as stale."""

    def test_none_captured_at_treated_as_stale(self):
        """None timestamp must NOT be promoted to fresh -- stale-never-green."""
        result = arbitrate(
            {"book_A": None, "book_B": _ago(60)},
            now=_T0,
        )

        assert result.status == "fresh"
        assert result.winner == "book_B"   # None-ts book never wins

    def test_none_only_venue_is_unavailable(self):
        """A single venue with None ts -> UNAVAILABLE, not fresh."""
        result = arbitrate({"book_A": None}, now=_T0)

        assert result.status == UNAVAILABLE
        assert result.winner is None

    def test_empty_string_captured_at_treated_as_stale(self):
        result = arbitrate(
            {"book_A": "", "book_B": _ago(60)},
            now=_T0,
        )

        assert result.winner == "book_B"

    def test_unparseable_string_treated_as_stale(self):
        result = arbitrate(
            {"book_A": "not-a-timestamp", "book_B": _ago(60)},
            now=_T0,
        )

        assert result.winner == "book_B"

    def test_unparseable_age_is_none_in_venue_age(self):
        """A VenueAge with unparseable ts has age_sec=None."""
        result = arbitrate({"book_A": "garbage"}, now=_T0)

        assert len(result.candidates) == 1
        assert result.candidates[0].age_sec is None
        assert not result.candidates[0].is_fresh


class TestInjectableNowClock:
    """Acceptance: injectable now-clock makes results deterministic."""

    def test_same_ts_different_now_changes_freshness(self):
        """Moving 'now' forward past the SLA flips a fresh venue to stale."""
        ts = _iso(_T0 - __import__("datetime").timedelta(seconds=800))

        # At T0 the timestamp is 800s old -> within 900s SLA -> fresh.
        r_fresh = arbitrate({"book_A": ts}, now=_T0)
        assert r_fresh.status == "fresh"

        # At T0+200 the timestamp is 1000s old -> past 900s SLA -> stale.
        from datetime import timedelta
        later = _T0 + timedelta(seconds=200)
        r_stale = arbitrate({"book_A": ts}, now=later)
        assert r_stale.status == UNAVAILABLE

    def test_now_controls_boundary(self):
        """Exactly at the SLA boundary (age == max_age_sec) is considered fresh."""
        # age_sec == max_age_sec is <= max_age -> fresh (from freshness.py: age_sec <= effective)
        ts = _ago(_MAX_AGE)  # exactly 900s old relative to _T0

        result = arbitrate({"book_A": ts}, now=_T0, max_age_sec=_MAX_AGE)
        assert result.status == "fresh"
        assert result.winner == "book_A"

    def test_one_tick_past_boundary_is_stale(self):
        """One second over the SLA is stale, not fresh."""
        ts = _ago(_MAX_AGE + 1.0)

        result = arbitrate({"book_A": ts}, now=_T0, max_age_sec=_MAX_AGE)
        assert result.status == UNAVAILABLE


class TestEdgeCases:
    """No $ field, empty input, never raises."""

    def test_empty_venues_returns_unavailable(self):
        result = arbitrate({}, now=_T0)

        assert result.status == UNAVAILABLE
        assert result.winner is None
        assert result.candidates == []

    def test_no_dollar_field_in_result(self):
        """No dollar signs or $ keys anywhere in the output."""
        result = arbitrate(
            {"book_A": _ago(60), "book_B": _ago(1000)},
            now=_T0,
        )

        # Recursively stringify the result dict and check for $-style keys.
        result_dict = dataclasses.asdict(result)
        result_str = str(result_dict)
        # Must contain no dollar-sign characters (stale-never-green + no $ output).
        assert "$" not in result_str

    def test_no_roi_pnl_profit_keys(self):
        """Result must not contain roi/pnl/profit/edge/bankroll keys."""
        result = arbitrate({"book_A": _ago(60)}, now=_T0)

        result_dict = dataclasses.asdict(result)
        result_str = str(result_dict).lower()
        for forbidden in ("roi", "pnl", "profit", "edge", "bankroll", "stake", "usd"):
            assert forbidden not in result_str

    def test_never_raises_on_garbage_input(self):
        """arbitrate() must never propagate exceptions."""
        # Pass in completely garbage input.
        result = arbitrate({"book": object()}, now=_T0)  # type: ignore[arg-type]

        assert result.status == UNAVAILABLE or result.status == "fresh"  # either valid

    def test_candidates_sorted_freshest_first(self):
        """candidates list is sorted ascending by age (freshest first)."""
        result = arbitrate(
            {"book_A": _ago(600), "book_B": _ago(200), "book_C": _ago(800)},
            now=_T0,
        )

        ages = [va.age_sec for va in result.candidates if va.age_sec is not None]
        assert ages == sorted(ages)

    def test_market_type_override_respects_tighter_sla(self):
        """Custom max_age_override is respected."""
        ts = _ago(400)  # 400s old

        # Default SLA 900s -> fresh
        r_default = arbitrate({"book_A": ts}, now=_T0)
        assert r_default.status == "fresh"

        # Override to 300s SLA -> stale
        r_tight = arbitrate(
            {"book_A": ts},
            now=_T0,
            max_age_override={"moneyline": 300.0},
            market_type="moneyline",
        )
        assert r_tight.status == UNAVAILABLE

    def test_market_type_total_uses_built_in_30min_sla(self):
        """market_type='total' uses the built-in 30-min SLA from freshness.MARKET_MAX_AGE."""
        ts = _ago(1200)  # 20 minutes old -- fresh for totals (30 min SLA)

        result = arbitrate({"book_A": ts}, now=_T0, market_type="total")
        assert result.status == "fresh"

        # Same timestamp -> stale for moneyline (15 min SLA)
        result_ml = arbitrate({"book_A": ts}, now=_T0, market_type="moneyline")
        assert result_ml.status == UNAVAILABLE

    def test_winner_age_sec_matches_winning_candidate(self):
        """winner_age_sec should equal the winning VenueAge.age_sec."""
        ts_a = _ago(200)
        ts_b = _ago(100)

        result = arbitrate({"book_A": ts_a, "book_B": ts_b}, now=_T0)

        assert result.status == "fresh"
        assert result.winner == "book_B"
        assert result.winner_age_sec == pytest.approx(100.0, abs=0.5)

    def test_single_fresh_venue_is_winner(self):
        result = arbitrate({"book_A": _ago(60)}, now=_T0)

        assert result.status == "fresh"
        assert result.winner == "book_A"
        assert result.winner_age_sec == pytest.approx(60.0, abs=0.5)

    def test_unavailable_winner_has_none_age(self):
        result = arbitrate({"book_A": _ago(9999)}, now=_T0)

        assert result.status == UNAVAILABLE
        assert result.winner_age_sec is None
