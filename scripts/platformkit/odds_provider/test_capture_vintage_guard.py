"""Per-file tests for capture_vintage_guard.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/odds_provider/test_capture_vintage_guard.py -q

Acceptance criteria (R6-2-captured-at-vintage-guard):
  1. Same price tuple seen at t0, re-served at t1 > t0 with identical odds
     -> returned captured_at == t0 (NOT t1).
  2. Changed odds -> captured_at updates to the new tick's timestamp.
  3. age >= sla -> is_stale_capture True.
  4. No $ field anywhere in VintageResult.
  5. Never raises on bad input.
  6. age_sec is None when captured_at is unparseable.
  7. price_changed=False on unchanged re-serve; True on advance().
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.odds_provider.capture_vintage_guard import (
    DEFAULT_SLA_SEC,
    CaptureVintageGuard,
    VintageResult,
    guard_quote,
)
from scripts.platformkit.odds_provider.markets import MarketQuote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _ago(seconds: float, *, base: datetime = _T0) -> str:
    """ISO-8601 string for a timestamp *seconds* before *base*."""
    return _iso(base - timedelta(seconds=seconds))


_SENTINEL = object()  # sentinel to distinguish "not passed" from explicit None


def _make_quote(
    *,
    game_id: str = "nba|LAL|BOS|2026-06-18",
    market_type: str = "moneyline",
    side: str = "home",
    odds: float = 1.91,
    line: float | None = None,
    book: str = "espn:DraftKings",
    captured_at: object = _SENTINEL,
) -> MarketQuote:
    """Build a minimal MarketQuote for testing.

    When captured_at is not supplied the default _ago(60) is used.
    Pass captured_at=None explicitly to test the None-timestamp path.
    """
    if captured_at is _SENTINEL:
        ts = _ago(60)
    else:
        ts = captured_at  # type: ignore[assignment]
    return MarketQuote(
        sport="nba",
        game_id=game_id,
        home="LAL",
        away="BOS",
        market_type=market_type,
        side=side,
        line=line,
        odds=odds,
        book=book,
        captured_at=ts,  # type: ignore[arg-type]
        devigged_prob=None,
    )


# ---------------------------------------------------------------------------
# Core acceptance: same price -> original captured_at preserved
# ---------------------------------------------------------------------------

class TestSamePriceTuplePreservesOriginalTimestamp:
    """AC-1: re-served identical odds return the ORIGINAL t0, not t1."""

    def test_second_serve_returns_original_captured_at(self):
        """Identical re-serve at t1 > t0 -> result.captured_at == t0."""
        guard = CaptureVintageGuard()
        t0 = _ago(300)  # 5 minutes ago

        q0 = _make_quote(captured_at=t0, odds=1.91)
        r0 = guard.guard(q0, now=_T0)
        assert r0.captured_at == t0

        # Same game/market/book/odds, but serve-layer re-stamped to now-ish.
        t1 = _ago(5)  # re-served 5s ago
        q1 = _make_quote(captured_at=t1, odds=1.91)
        r1 = guard.guard(q1, now=_T0)

        # Must return the ORIGINAL t0, not t1.
        assert r1.captured_at == t0, (
            f"Expected original t0={t0!r} but got {r1.captured_at!r}"
        )

    def test_original_not_t1_on_third_serve(self):
        """Multiple re-serves all return the first observed timestamp."""
        guard = CaptureVintageGuard()
        t0 = _ago(600)

        guard.guard(_make_quote(captured_at=t0, odds=2.10), now=_T0)
        guard.guard(_make_quote(captured_at=_ago(300), odds=2.10), now=_T0)
        r = guard.guard(_make_quote(captured_at=_ago(10), odds=2.10), now=_T0)

        assert r.captured_at == t0

    def test_price_changed_false_on_identical_odds(self):
        """price_changed must be False when odds are unchanged."""
        guard = CaptureVintageGuard()
        guard.guard(_make_quote(captured_at=_ago(300), odds=1.95), now=_T0)
        r = guard.guard(_make_quote(captured_at=_ago(5), odds=1.95), now=_T0)

        assert r.price_changed is False

    def test_different_book_tracked_independently(self):
        """Two books for the same game+market are independent registry entries."""
        guard = CaptureVintageGuard()
        t_dk = _ago(600)
        t_fd = _ago(400)

        guard.guard(_make_quote(book="DraftKings", captured_at=t_dk, odds=1.91), now=_T0)
        guard.guard(_make_quote(book="FanDuel", captured_at=t_fd, odds=1.91), now=_T0)

        # Re-serve for each book.
        r_dk = guard.guard(_make_quote(book="DraftKings", captured_at=_ago(5), odds=1.91), now=_T0)
        r_fd = guard.guard(_make_quote(book="FanDuel", captured_at=_ago(5), odds=1.91), now=_T0)

        assert r_dk.captured_at == t_dk
        assert r_fd.captured_at == t_fd

    def test_different_game_tracked_independently(self):
        """Different game_ids have separate registry slots."""
        guard = CaptureVintageGuard()
        t_g1 = _ago(500)
        t_g2 = _ago(200)

        guard.guard(_make_quote(game_id="game1", captured_at=t_g1, odds=1.91), now=_T0)
        guard.guard(_make_quote(game_id="game2", captured_at=t_g2, odds=1.91), now=_T0)

        r_g1 = guard.guard(_make_quote(game_id="game1", captured_at=_ago(5), odds=1.91), now=_T0)
        r_g2 = guard.guard(_make_quote(game_id="game2", captured_at=_ago(5), odds=1.91), now=_T0)

        assert r_g1.captured_at == t_g1
        assert r_g2.captured_at == t_g2


# ---------------------------------------------------------------------------
# AC-2: changed odds -> captured_at advances to new tick
# ---------------------------------------------------------------------------

class TestChangedOddsAdvancesToNewTimestamp:
    """AC-2: when odds change, the registry should reflect the new tick."""

    def test_changed_odds_via_advance_returns_new_timestamp(self):
        """advance() with new_captured_at -> result.captured_at == new_ts."""
        guard = CaptureVintageGuard()
        t0 = _ago(300)
        t_new = _ago(10)

        q_old = _make_quote(captured_at=t0, odds=1.91)
        guard.guard(q_old, now=_T0)

        # Build a quote representing the new price.
        q_new = _make_quote(captured_at=t_new, odds=1.95)  # odds changed
        r = guard.advance(q_new, new_captured_at=t_new, now=_T0)

        assert r.captured_at == t_new
        assert r.price_changed is True

    def test_after_advance_subsequent_same_odds_return_new_ts(self):
        """After price change, identical re-serves use the advanced timestamp."""
        guard = CaptureVintageGuard()
        t0 = _ago(600)
        t_new = _ago(50)

        q_v1 = _make_quote(captured_at=t0, odds=1.91)
        guard.guard(q_v1, now=_T0)

        # Odds move; call advance() to register new price epoch.
        q_v2 = _make_quote(captured_at=t_new, odds=1.95)
        guard.advance(q_v2, new_captured_at=t_new, now=_T0)

        # Subsequent re-serve at same new odds uses t_new, not t0.
        r = guard.guard(q_v2, now=_T0)
        assert r.captured_at == t_new
        assert r.price_changed is False

    def test_first_observation_is_not_price_changed(self):
        """First time a price key appears price_changed must be False."""
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=_ago(100), odds=1.91), now=_T0)
        assert r.price_changed is False


# ---------------------------------------------------------------------------
# AC-3: age >= sla -> is_stale_capture True
# ---------------------------------------------------------------------------

class TestStaleCaptureFlag:
    """AC-3: is_stale_capture reflects whether the original captured_at is past SLA."""

    def test_fresh_capture_not_stale(self):
        """captured_at within SLA -> is_stale_capture False."""
        guard = CaptureVintageGuard()
        ts = _ago(60)  # 1 minute old -- well within 900s SLA
        r = guard.guard(_make_quote(captured_at=ts), now=_T0, sla_sec=DEFAULT_SLA_SEC)
        assert r.is_stale_capture is False

    def test_stale_capture_flagged(self):
        """captured_at >= sla_sec old -> is_stale_capture True."""
        guard = CaptureVintageGuard()
        ts = _ago(DEFAULT_SLA_SEC + 1)  # 1 second past SLA
        r = guard.guard(_make_quote(captured_at=ts), now=_T0, sla_sec=DEFAULT_SLA_SEC)
        assert r.is_stale_capture is True

    def test_exactly_at_sla_boundary_is_stale(self):
        """age_sec == sla_sec exactly -> is_stale_capture True (>= check)."""
        guard = CaptureVintageGuard()
        ts = _ago(DEFAULT_SLA_SEC)  # exactly at the boundary
        r = guard.guard(_make_quote(captured_at=ts), now=_T0, sla_sec=DEFAULT_SLA_SEC)
        assert r.is_stale_capture is True

    def test_re_serve_inherits_stale_flag_from_original_ts(self):
        """Re-serve with fresh serve-time stamp but stale original -> is_stale=True."""
        guard = CaptureVintageGuard()
        t_original = _ago(1200)  # 20 minutes ago -> stale at 15-min SLA

        # First ingest at t_original.
        guard.guard(_make_quote(captured_at=t_original, odds=1.91), now=_T0)

        # Re-serve with a fresh timestamp but SAME odds.
        r = guard.guard(_make_quote(captured_at=_ago(5), odds=1.91), now=_T0)

        # captured_at is the original stale timestamp; is_stale_capture must be True.
        assert r.captured_at == t_original
        assert r.is_stale_capture is True

    def test_custom_sla_respected(self):
        """Custom sla_sec parameter overrides the default."""
        guard = CaptureVintageGuard()
        ts = _ago(400)  # 400s old

        # Default 900s SLA -> fresh.
        r_fresh = guard.guard(
            _make_quote(captured_at=ts), now=_T0, sla_sec=900.0
        )
        assert r_fresh.is_stale_capture is False

        # Tight 300s SLA -> stale.
        guard2 = CaptureVintageGuard()
        r_stale = guard2.guard(
            _make_quote(captured_at=ts), now=_T0, sla_sec=300.0
        )
        assert r_stale.is_stale_capture is True

    def test_age_sec_matches_sla_check(self):
        """age_sec is consistent with is_stale_capture classification."""
        guard = CaptureVintageGuard()
        ts = _ago(500)

        r = guard.guard(_make_quote(captured_at=ts), now=_T0, sla_sec=DEFAULT_SLA_SEC)

        assert r.age_sec == pytest.approx(500.0, abs=1.0)
        assert r.is_stale_capture is (r.age_sec >= DEFAULT_SLA_SEC)


# ---------------------------------------------------------------------------
# AC-4: no $ field
# ---------------------------------------------------------------------------

class TestNoDollarField:
    """AC-4: no dollar-sign keys or money-related fields in VintageResult."""

    def _check_no_money_fields(self, result: VintageResult) -> None:
        d = dataclasses.asdict(result)
        s = str(d).lower()
        forbidden = ("roi", "pnl", "profit", "bankroll", "stake", "usd", "$")
        for key in forbidden:
            assert key not in s, f"Forbidden key {key!r} found in result: {d}"

    def test_no_dollar_field_fresh_result(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=_ago(60)), now=_T0)
        self._check_no_money_fields(r)

    def test_no_dollar_field_stale_result(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=_ago(2000)), now=_T0)
        self._check_no_money_fields(r)

    def test_no_dollar_field_advance_result(self):
        guard = CaptureVintageGuard()
        q = _make_quote(captured_at=_ago(600), odds=1.91)
        guard.guard(q, now=_T0)
        r = guard.advance(q, new_captured_at=_ago(10), now=_T0)
        self._check_no_money_fields(r)


# ---------------------------------------------------------------------------
# AC-5: never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """AC-5: guard() must never propagate exceptions on bad input."""

    def test_none_captured_at_does_not_raise(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=None), now=_T0)  # type: ignore[arg-type]
        assert isinstance(r, VintageResult)

    def test_empty_captured_at_does_not_raise(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=""), now=_T0)
        assert isinstance(r, VintageResult)

    def test_garbage_captured_at_does_not_raise(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at="not-a-date"), now=_T0)
        assert isinstance(r, VintageResult)

    def test_none_now_defaults_to_utc_now(self):
        """now=None should default to datetime.now(utc) without raising."""
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=_ago(60)), now=None)
        assert isinstance(r, VintageResult)
        assert r.age_sec is not None
        assert r.age_sec > 0

    def test_advance_with_bad_ts_does_not_raise(self):
        guard = CaptureVintageGuard()
        q = _make_quote(captured_at=_ago(300))
        r = guard.advance(q, new_captured_at="garbage", now=_T0)
        assert isinstance(r, VintageResult)


# ---------------------------------------------------------------------------
# AC-6: age_sec is None when captured_at is unparseable
# ---------------------------------------------------------------------------

class TestAgeSecNoneOnBadTimestamp:
    """AC-6: unparseable captured_at yields age_sec=None."""

    def test_garbage_ts_age_sec_is_none(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at="not-a-date"), now=_T0)
        assert r.age_sec is None

    def test_none_ts_age_sec_is_none(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at=None), now=_T0)  # type: ignore[arg-type]
        assert r.age_sec is None

    def test_bad_ts_also_is_stale(self):
        """Unparseable timestamp is conservatively stale."""
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(captured_at="2026-99-99"), now=_T0)
        assert r.is_stale_capture is True


# ---------------------------------------------------------------------------
# AC-7: price_changed semantics
# ---------------------------------------------------------------------------

class TestPriceChangedFlag:
    """AC-7: price_changed=False on identical re-serve; True via advance()."""

    def test_first_observation_price_changed_false(self):
        guard = CaptureVintageGuard()
        r = guard.guard(_make_quote(odds=1.91), now=_T0)
        assert r.price_changed is False

    def test_same_odds_re_serve_price_changed_false(self):
        guard = CaptureVintageGuard()
        guard.guard(_make_quote(odds=1.91, captured_at=_ago(300)), now=_T0)
        r = guard.guard(_make_quote(odds=1.91, captured_at=_ago(10)), now=_T0)
        assert r.price_changed is False

    def test_advance_always_price_changed_true(self):
        guard = CaptureVintageGuard()
        q = _make_quote(odds=1.95, captured_at=_ago(60))
        r = guard.advance(q, new_captured_at=_ago(5), now=_T0)
        assert r.price_changed is True


# ---------------------------------------------------------------------------
# Utility: clear() and registry_size
# ---------------------------------------------------------------------------

class TestGuardUtilities:
    """clear() resets the registry; registry_size tracks entry count."""

    def test_registry_size_grows_with_distinct_keys(self):
        guard = CaptureVintageGuard()
        assert guard.registry_size == 0

        guard.guard(_make_quote(game_id="g1"), now=_T0)
        guard.guard(_make_quote(game_id="g2"), now=_T0)
        assert guard.registry_size == 2

    def test_same_key_does_not_grow_registry(self):
        guard = CaptureVintageGuard()
        guard.guard(_make_quote(odds=1.91, captured_at=_ago(300)), now=_T0)
        guard.guard(_make_quote(odds=1.91, captured_at=_ago(10)), now=_T0)
        assert guard.registry_size == 1

    def test_clear_resets_registry(self):
        guard = CaptureVintageGuard()
        guard.guard(_make_quote(), now=_T0)
        assert guard.registry_size == 1

        guard.clear()
        assert guard.registry_size == 0

    def test_after_clear_first_observe_is_fresh_baseline(self):
        """After clear(), the next observed timestamp is the new baseline."""
        guard = CaptureVintageGuard()
        t0 = _ago(600)
        guard.guard(_make_quote(captured_at=t0, odds=1.91), now=_T0)

        guard.clear()

        t_new = _ago(30)
        r = guard.guard(_make_quote(captured_at=t_new, odds=1.91), now=_T0)
        assert r.captured_at == t_new


# ---------------------------------------------------------------------------
# Module-level guard_quote convenience
# ---------------------------------------------------------------------------

class TestModuleLevelGuardQuote:
    """guard_quote() shortcut should not raise and should return VintageResult."""

    def test_guard_quote_returns_vintage_result(self):
        from scripts.platformkit.odds_provider import capture_vintage_guard as mod
        # Reset the module-level guard between test runs to avoid state pollution.
        mod._GLOBAL_GUARD.clear()

        q = _make_quote(captured_at=_ago(60))
        r = guard_quote(q, now=_T0)
        assert isinstance(r, VintageResult)
        assert r.age_sec == pytest.approx(60.0, abs=1.0)
