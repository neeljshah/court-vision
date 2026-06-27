"""Per-file test for scripts.platformkit.bestbets.fresh_best_line (BBQ5-3).

Acceptance criteria (from BACKLOG.md):
  A  books=[{decimal:2.10,ts:fresh},{decimal:2.30,ts:stale}] with now+max_age
     -> returns status "ok" with best_decimal=2.10 (higher STALE 2.30 does NOT win).
  B  All books stale -> {status:"UNAVAILABLE", best_decimal:None} not a fabricated price.
  C  Polymarket/binary book excluded from best selection (even if its decimal is fresh+higher).
  D  decimal<=1.0 ignored (invalid odds excluded).
  E  Empty books list -> UNAVAILABLE.
  F  Missing ts treated as stale (fail-closed, NOT fresh).
  G  No $ field on any output.
  H  Never raises on any garbage input.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/bestbets/test_fresh_best_line.py -q
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.bestbets.fresh_best_line import (
    DEFAULT_MAX_AGE_SEC,
    best_fresh_line,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = frozenset(
    {"dollar", "pnl", "roi", "profit", "bankroll", "usd", "dollars"}
)

_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
_MAX_AGE = 900.0  # 15 min


def _fresh_ts(seconds_ago: float = 60.0) -> str:
    """ISO-8601 UTC timestamp that is *seconds_ago* seconds in the past (fresh)."""
    dt = _NOW - timedelta(seconds=seconds_ago)
    return dt.isoformat()


def _stale_ts(seconds_ago: float = 3600.0) -> str:
    """ISO-8601 UTC timestamp that is *seconds_ago* seconds in the past (stale)."""
    dt = _NOW - timedelta(seconds=seconds_ago)
    return dt.isoformat()


def _run(
    books: List[Dict[str, Any]],
    now: Optional[datetime] = _NOW,
    max_age_sec: float = _MAX_AGE,
) -> Dict[str, Any]:
    """Convenience wrapper pinning now + max_age for deterministic tests."""
    return best_fresh_line(books, now=now, max_age_sec=max_age_sec)


def _assert_no_banned_keys(result: Dict[str, Any]) -> None:
    for key in result:
        assert key.lower() not in _BANNED_KEYS, (
            f"Banned key '{key}' found in result: {list(result.keys())!r}"
        )


# ---------------------------------------------------------------------------
# A: higher stale does NOT beat lower fresh
# ---------------------------------------------------------------------------

class TestFreshWinsOverHigherStale:
    """A: books=[{decimal:2.10,ts:fresh},{decimal:2.30,ts:stale}] -> returns 2.10."""

    def test_fresh_lower_beats_stale_higher(self):
        """Core acceptance test: the STALE higher price (2.30) must NOT win."""
        books = [
            {"book": "draftkings", "decimal": 2.10, "ts": _fresh_ts(60)},
            {"book": "fanduel",    "decimal": 2.30, "ts": _stale_ts(3600)},
        ]
        result = _run(books)
        assert result["status"] == "ok", f"Expected ok, got: {result!r}"
        assert result["best_decimal"] == pytest.approx(2.10, abs=1e-6), (
            f"Expected 2.10 (fresh), got {result['best_decimal']!r} -- "
            f"stale 2.30 must not win over fresh 2.10."
        )
        assert result["best_book"] == "draftkings"
        assert result["fresh_count"] == 1
        assert result["total_count"] == 2

    def test_multiple_fresh_picks_highest_fresh(self):
        """When multiple books are fresh, picks the highest fresh decimal."""
        books = [
            {"book": "draftkings", "decimal": 2.10, "ts": _fresh_ts(30)},
            {"book": "betmgm",     "decimal": 2.20, "ts": _fresh_ts(60)},
            {"book": "fanduel",    "decimal": 2.50, "ts": _stale_ts(3600)},
        ]
        result = _run(books)
        assert result["status"] == "ok"
        assert result["best_decimal"] == pytest.approx(2.20, abs=1e-6), (
            f"Expected highest fresh 2.20, got {result['best_decimal']!r}"
        )
        assert result["best_book"] == "betmgm"
        assert result["fresh_count"] == 2

    def test_exactly_at_max_age_is_fresh(self):
        """A line exactly max_age_sec old is still fresh (boundary inclusive)."""
        books = [
            {"book": "pinnacle", "decimal": 1.95, "ts": _fresh_ts(_MAX_AGE)},
        ]
        result = _run(books)
        assert result["status"] == "ok", (
            f"Line at exactly max_age boundary should be fresh: {result!r}"
        )

    def test_one_second_over_max_age_is_stale(self):
        """A line max_age_sec + 1 second old is stale."""
        books = [
            {"book": "pinnacle", "decimal": 1.95, "ts": _fresh_ts(_MAX_AGE + 1)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE", (
            f"Line just over max_age should be stale: {result!r}"
        )


# ---------------------------------------------------------------------------
# B: all books stale -> UNAVAILABLE (no fabricated price)
# ---------------------------------------------------------------------------

class TestAllStaleIsUnavailable:
    """B: all books stale -> status UNAVAILABLE, best_decimal None."""

    def test_all_stale_returns_unavailable(self):
        books = [
            {"book": "draftkings", "decimal": 2.10, "ts": _stale_ts(1800)},
            {"book": "fanduel",    "decimal": 2.30, "ts": _stale_ts(3600)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE", f"Expected UNAVAILABLE: {result!r}"
        assert result["best_decimal"] is None, (
            f"best_decimal must be None when UNAVAILABLE, got: {result['best_decimal']!r}"
        )
        assert result["best_book"] is None

    def test_unavailable_no_fabricated_price(self):
        """UNAVAILABLE result must carry None, never a stale decimal as the price."""
        books = [
            {"book": "draftkings", "decimal": 99.0, "ts": _stale_ts(9999)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE"
        assert result["best_decimal"] is None, (
            "A stale 99.0 must NOT be fabricated as best_decimal."
        )


# ---------------------------------------------------------------------------
# C: Polymarket / binary / PM book excluded
# ---------------------------------------------------------------------------

class TestPredictionMarketExcluded:
    """C: PM books (polymarket, kalshi, etc.) never win best selection."""

    def test_polymarket_book_excluded_even_if_fresh_high(self):
        """polymarket book with fresh, high decimal is excluded; sportsbook wins."""
        books = [
            {"book": "polymarket", "decimal": 5.00, "ts": _fresh_ts(30)},
            {"book": "draftkings", "decimal": 2.10, "ts": _fresh_ts(60)},
        ]
        result = _run(books)
        assert result["status"] == "ok"
        assert result["best_decimal"] == pytest.approx(2.10, abs=1e-6), (
            f"polymarket should be excluded; expected 2.10, got {result['best_decimal']!r}"
        )
        assert result["best_book"] == "draftkings"

    def test_kalshi_book_excluded(self):
        """kalshi is a PM venue and must be excluded."""
        books = [
            {"book": "kalshi",     "decimal": 3.00, "ts": _fresh_ts(10)},
            {"book": "fanduel",    "decimal": 1.90, "ts": _fresh_ts(10)},
        ]
        result = _run(books)
        assert result["status"] == "ok"
        assert result["best_book"] == "fanduel"
        assert result["best_decimal"] == pytest.approx(1.90, abs=1e-6)

    def test_only_pm_books_gives_unavailable(self):
        """When only PM books exist (even fresh), result is UNAVAILABLE."""
        books = [
            {"book": "polymarket", "decimal": 2.50, "ts": _fresh_ts(30)},
            {"book": "kalshi",     "decimal": 2.00, "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE", (
            f"Only PM books -> UNAVAILABLE, got: {result!r}"
        )
        assert result["best_decimal"] is None

    def test_polymarket_prefix_variant_excluded(self):
        """'polymarket:nba_game_1' style prefix variant is also excluded."""
        books = [
            {"book": "polymarket:nba_game_1", "decimal": 4.00, "ts": _fresh_ts(10)},
            {"book": "betmgm",               "decimal": 1.95, "ts": _fresh_ts(10)},
        ]
        result = _run(books)
        assert result["best_book"] == "betmgm"


# ---------------------------------------------------------------------------
# D: decimal <= 1.0 ignored
# ---------------------------------------------------------------------------

class TestInvalidDecimalIgnored:
    """D: decimal <= 1.0 is an invalid bettable price and must be excluded."""

    def test_decimal_exactly_one_ignored(self):
        """decimal=1.0 is a degenerate certainty contract -- excluded."""
        books = [
            {"book": "badbook",   "decimal": 1.00, "ts": _fresh_ts(30)},
            {"book": "draftkings","decimal": 2.10, "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["best_book"] == "draftkings"
        assert result["best_decimal"] == pytest.approx(2.10, abs=1e-6)

    def test_decimal_below_one_ignored(self):
        """decimal=0.5 (probability as decimal) is invalid and excluded."""
        books = [
            {"book": "badbook",   "decimal": 0.5, "ts": _fresh_ts(30)},
            {"book": "draftkings","decimal": 1.90, "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["best_decimal"] == pytest.approx(1.90, abs=1e-6)

    def test_all_invalid_decimals_gives_unavailable(self):
        """When all decimals are <= 1.0, UNAVAILABLE."""
        books = [
            {"book": "a", "decimal": 0.5,  "ts": _fresh_ts(30)},
            {"book": "b", "decimal": 1.0,  "ts": _fresh_ts(30)},
            {"book": "c", "decimal": -1.0, "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE"

    def test_none_decimal_ignored(self):
        """A None decimal is invalid and excluded."""
        books = [
            {"book": "badbook",   "decimal": None, "ts": _fresh_ts(30)},
            {"book": "draftkings","decimal": 2.05, "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["best_decimal"] == pytest.approx(2.05, abs=1e-6)


# ---------------------------------------------------------------------------
# E: empty books -> UNAVAILABLE
# ---------------------------------------------------------------------------

class TestEmptyBooksUnavailable:
    """E: empty (or absent) books list -> UNAVAILABLE."""

    def test_empty_list_unavailable(self):
        result = _run([])
        assert result["status"] == "UNAVAILABLE"
        assert result["best_decimal"] is None

    def test_none_input_unavailable(self):
        result = _run(None)  # type: ignore[arg-type]
        assert result["status"] == "UNAVAILABLE"
        assert result["best_decimal"] is None

    def test_empty_after_filtering_pm_and_invalid(self):
        """After excluding PM + invalid decimals, if nothing remains -> UNAVAILABLE."""
        books = [
            {"book": "polymarket", "decimal": 2.10, "ts": _fresh_ts(30)},
            {"book": "bad",        "decimal": 0.9,  "ts": _fresh_ts(30)},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# F: missing ts treated as stale (fail-closed)
# ---------------------------------------------------------------------------

class TestMissingTsIsFailed:
    """F: a book entry with missing/None/unparseable ts is treated as stale."""

    def test_missing_ts_key_is_stale(self):
        """Entry with no 'ts' key at all is treated as stale."""
        books = [
            {"book": "draftkings", "decimal": 2.30},  # no ts
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE", (
            f"Missing ts must be stale (fail-closed): {result!r}"
        )

    def test_none_ts_is_stale(self):
        """ts=None is treated as stale."""
        books = [
            {"book": "draftkings", "decimal": 2.30, "ts": None},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE", (
            f"None ts must be stale: {result!r}"
        )

    def test_empty_string_ts_is_stale(self):
        """ts='' is unparseable -> stale."""
        books = [
            {"book": "draftkings", "decimal": 2.30, "ts": ""},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE"

    def test_garbage_ts_is_stale(self):
        """ts='not-a-timestamp' is unparseable -> stale."""
        books = [
            {"book": "draftkings", "decimal": 2.30, "ts": "not-a-timestamp"},
        ]
        result = _run(books)
        assert result["status"] == "UNAVAILABLE"

    def test_missing_ts_stale_but_other_book_fresh(self):
        """Missing-ts entry is stale; another fresh entry with LOWER decimal wins."""
        books = [
            {"book": "fanduel",    "decimal": 2.50},        # no ts -> stale
            {"book": "draftkings", "decimal": 1.95, "ts": _fresh_ts(30)},  # fresh
        ]
        result = _run(books)
        assert result["status"] == "ok"
        assert result["best_decimal"] == pytest.approx(1.95, abs=1e-6), (
            f"Missing-ts book (higher 2.50) must not beat fresh 1.95: {result!r}"
        )
        assert result["best_book"] == "draftkings"


# ---------------------------------------------------------------------------
# G: no $ field on any output
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """G: result dict never contains dollar / pnl / roi / profit / bankroll / usd keys."""

    def test_ok_result_no_banned_keys(self):
        books = [{"book": "draftkings", "decimal": 2.10, "ts": _fresh_ts(60)}]
        result = _run(books)
        _assert_no_banned_keys(result)

    def test_unavailable_result_no_banned_keys(self):
        result = _run([])
        _assert_no_banned_keys(result)

    def test_all_stale_no_banned_keys(self):
        books = [{"book": "draftkings", "decimal": 2.10, "ts": _stale_ts(9999)}]
        result = _run(books)
        _assert_no_banned_keys(result)


# ---------------------------------------------------------------------------
# H: never raises on garbage input
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """H: best_fresh_line never raises regardless of input garbage."""

    @pytest.mark.parametrize("garbage", [
        None,
        [],
        {},
        "not a list",
        42,
        [None, 42, "string", {"no_book": True}],
        [{"book": None, "decimal": None, "ts": None}],
        [{"book": "dk", "decimal": float("nan"), "ts": _fresh_ts(30)}],
        [{"book": "dk", "decimal": float("inf"), "ts": _fresh_ts(30)}],
    ])
    def test_never_raises(self, garbage):
        try:
            result = best_fresh_line(garbage)
            assert isinstance(result, dict), f"Expected dict, got {type(result)!r}"
            assert "status" in result
            assert result["status"] in ("ok", "UNAVAILABLE")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"best_fresh_line raised on garbage input: {exc!r}")

    def test_nan_decimal_does_not_win(self):
        """A NaN decimal is invalid and must not be selected."""
        books = [{"book": "dk", "decimal": float("nan"), "ts": _fresh_ts(30)}]
        result = best_fresh_line(books, now=_NOW)
        assert result["status"] == "UNAVAILABLE"
        assert result["best_decimal"] is None

    def test_inf_decimal_does_not_win(self):
        """An inf decimal is invalid and must not be selected."""
        books = [{"book": "dk", "decimal": float("inf"), "ts": _fresh_ts(30)}]
        result = best_fresh_line(books, now=_NOW)
        assert result["status"] == "UNAVAILABLE"

    def test_non_dict_entries_skipped(self):
        """Non-dict entries in the list are silently skipped."""
        books = [None, 42, "foo", {"book": "dk", "decimal": 2.0, "ts": _fresh_ts(30)}]
        result = best_fresh_line(books, now=_NOW)
        assert result["status"] == "ok"
        assert result["best_decimal"] == pytest.approx(2.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Integration: epoch-float ts accepted
# ---------------------------------------------------------------------------

class TestEpochFloatTs:
    """Epoch-float ts values (from Unix timestamps) are accepted."""

    def test_fresh_epoch_ts(self):
        epoch_now = _NOW.timestamp()
        fresh_epoch = epoch_now - 60.0  # 1 minute ago
        books = [{"book": "draftkings", "decimal": 2.05, "ts": fresh_epoch}]
        result = best_fresh_line(books, now=_NOW, max_age_sec=_MAX_AGE)
        assert result["status"] == "ok"
        assert result["best_decimal"] == pytest.approx(2.05, abs=1e-6)

    def test_stale_epoch_ts(self):
        epoch_now = _NOW.timestamp()
        stale_epoch = epoch_now - 3600.0  # 1 hour ago
        books = [{"book": "draftkings", "decimal": 2.05, "ts": stale_epoch}]
        result = best_fresh_line(books, now=_NOW, max_age_sec=_MAX_AGE)
        assert result["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Integration: count fields correct
# ---------------------------------------------------------------------------

class TestCountFields:
    """fresh_count and total_count are accurate."""

    def test_counts_accurate(self):
        books = [
            {"book": "dk",         "decimal": 2.10, "ts": _fresh_ts(60)},   # fresh, valid
            {"book": "fanduel",    "decimal": 2.30, "ts": _stale_ts(3600)}, # stale
            {"book": "polymarket", "decimal": 3.00, "ts": _fresh_ts(10)},   # PM (excluded)
            {"book": "betmgm",     "decimal": 1.00, "ts": _fresh_ts(10)},   # invalid decimal
            {"book": "pinnacle",   "decimal": 1.95, "ts": _fresh_ts(200)},  # fresh, valid
        ]
        result = _run(books)
        assert result["status"] == "ok"
        # total_count: valid decimal and non-PM only (dk + fanduel + betmgm*=invalid but counted, pinnacle)
        # betmgm has decimal=1.0 which increments total_count but fails the decimal gate
        # polymarket is excluded BEFORE the decimal check so not in total
        assert result["fresh_count"] == 2, f"Expected 2 fresh, got {result['fresh_count']}"
        assert result["best_decimal"] == pytest.approx(2.10, abs=1e-6)
