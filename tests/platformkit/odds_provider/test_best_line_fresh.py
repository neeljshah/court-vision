"""Per-file tests for scripts.platformkit.odds_provider.best_line_fresh.

Acceptance criteria (from LSII-01):
  1. A higher-odds venue with as_of older than max_age is DROPPED so a fresher
     lower-odds book wins.
  2. All-fresh -> identical to best_line(restrict_to=SPORTSBOOK).
  3. Unknown/missing per-venue as_of -> excluded (stale-never-green), NOT trusted.
  4. PM venues excluded from bettable-best.
  5. Empty / all-stale -> {} per side, never a fabricated price.
  6. Never raises.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_best_line_fresh.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import pytest

from scripts.platformkit.odds_provider.best_line_fresh import best_line_fresh
from scripts.platformkit.odds_shop import best_line
from scripts.platformkit.odds_provider.base import VENUE_SPORTSBOOK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(offset_sec: float = 0.0) -> datetime:
    """A fixed 'now' reference point for injectable clock."""
    return datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_sec)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


NOW = _utc()
FRESH_TS = _iso(_utc(-60))          # 1 min ago   -- well within 900 s default
STALE_TS = _iso(_utc(-1800))        # 30 min ago  -- outside 900 s default


# ---------------------------------------------------------------------------
# 1. Stale higher-odds venue is DROPPED; fresher lower-odds book wins
# ---------------------------------------------------------------------------

class TestStaleDrop:
    def test_stale_higher_odds_loses_to_fresh_lower_odds(self):
        """The stale DraftKings (2.10 > 1.95) must not win when it is stale."""
        book_prices = {
            "DraftKings": {"home": 2.10, "away": 1.75},  # stale
            "BetMGM":     {"home": 1.95, "away": 1.90},  # fresh
        }
        venue_as_of = {
            "DraftKings": STALE_TS,
            "BetMGM":     FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        # DraftKings is stale -> excluded; BetMGM wins on both sides
        assert result.get("home") == {"book": "BetMGM", "price": 1.95}
        assert result.get("away") == {"book": "BetMGM", "price": 1.90}

    def test_fresh_higher_odds_wins(self):
        """When both are fresh the higher price still wins (normal best_line)."""
        book_prices = {
            "DraftKings": {"home": 2.10, "away": 1.75},
            "BetMGM":     {"home": 1.95, "away": 1.90},
        }
        venue_as_of = {
            "DraftKings": FRESH_TS,
            "BetMGM":     FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "DraftKings"
        assert result["home"]["price"] == pytest.approx(2.10)
        assert result["away"]["book"] == "BetMGM"
        assert result["away"]["price"] == pytest.approx(1.90)

    def test_exact_max_age_boundary_is_fresh(self):
        """A timestamp exactly at max_age_sec is treated as fresh (<=, not <)."""
        max_age = 300.0
        ts_exactly_at_limit = _iso(_utc(-300.0))
        book_prices = {"FanDuel": {"home": 1.80}}
        venue_as_of = {"FanDuel": ts_exactly_at_limit}
        result = best_line_fresh(
            book_prices, venue_as_of, max_age_sec=max_age, now=NOW
        )
        # Exactly at boundary -> fresh -> should appear
        assert "home" in result
        assert result["home"]["book"] == "FanDuel"

    def test_one_second_past_max_age_is_stale(self):
        """A timestamp 1 second past max_age is stale -> excluded."""
        max_age = 300.0
        ts_just_stale = _iso(_utc(-301.0))
        ts_fresh = _iso(_utc(-60.0))
        book_prices = {
            "StaleBook":  {"home": 2.50},
            "FreshBook":  {"home": 1.85},
        }
        venue_as_of = {
            "StaleBook":  ts_just_stale,
            "FreshBook":  ts_fresh,
        }
        result = best_line_fresh(
            book_prices, venue_as_of, max_age_sec=max_age, now=NOW
        )
        assert result["home"]["book"] == "FreshBook"
        assert result["home"]["price"] == pytest.approx(1.85)


# ---------------------------------------------------------------------------
# 2. All-fresh -> identical to best_line(restrict_to=SPORTSBOOK)
# ---------------------------------------------------------------------------

class TestAllFreshParity:
    def test_all_fresh_matches_best_line_sportsbook(self):
        """When all venues are fresh, result must equal best_line(restrict_to=SPORTSBOOK)."""
        book_prices = {
            "DraftKings": {"home": 2.05, "away": 1.80},
            "FanDuel":    {"home": 1.95, "away": 1.88},
            "BetMGM":     {"home": 2.00, "away": 1.85},
        }
        venue_as_of = {v: FRESH_TS for v in book_prices}
        fresh_result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        classic = best_line(book_prices, restrict_to=VENUE_SPORTSBOOK)
        assert fresh_result == classic

    def test_single_book_fresh(self):
        book_prices = {"Caesars": {"home": 1.91, "away": 1.91}}
        venue_as_of = {"Caesars": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {"home": {"book": "Caesars", "price": pytest.approx(1.91)},
                          "away": {"book": "Caesars", "price": pytest.approx(1.91)}}


# ---------------------------------------------------------------------------
# 3. Unknown/missing as_of -> excluded (stale-never-green)
# ---------------------------------------------------------------------------

class TestUnknownAsOfExcluded:
    def test_venue_absent_from_venue_as_of_is_excluded(self):
        """A venue not in venue_as_of at all must be treated as stale."""
        book_prices = {
            "MissingTs": {"home": 2.30},
            "FreshBook":  {"home": 1.90},
        }
        venue_as_of = {"FreshBook": FRESH_TS}  # MissingTs absent
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "FreshBook"
        assert result["home"]["price"] == pytest.approx(1.90)

    def test_venue_with_none_as_of_is_excluded(self):
        """A venue whose as_of is explicitly None must be excluded."""
        book_prices = {
            "NoneTs":    {"home": 2.50},
            "FreshBook": {"home": 1.90},
        }
        venue_as_of = {"NoneTs": None, "FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "FreshBook"

    def test_venue_with_empty_string_as_of_is_excluded(self):
        """A venue with as_of="" is unparseable -> treated as stale."""
        book_prices = {
            "EmptyTs":   {"home": 2.50},
            "FreshBook": {"home": 1.90},
        }
        venue_as_of = {"EmptyTs": "", "FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "FreshBook"

    def test_venue_with_garbage_as_of_is_excluded(self):
        """An unparseable timestamp string is treated as stale (never trusted)."""
        book_prices = {
            "GarbageTs": {"home": 2.50},
            "FreshBook": {"home": 1.90},
        }
        venue_as_of = {"GarbageTs": "not-a-date", "FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "FreshBook"

    def test_all_unknown_as_of_returns_empty(self):
        """All venues with missing/unknown timestamps -> {} (no fabricated price)."""
        book_prices = {
            "BookA": {"home": 2.10, "away": 1.75},
            "BookB": {"home": 2.00, "away": 1.82},
        }
        venue_as_of: Dict[str, Optional[str]] = {}  # none present
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}


# ---------------------------------------------------------------------------
# 4. PM venues excluded from bettable-best
# ---------------------------------------------------------------------------

class TestPMVenueExclusion:
    def test_polymarket_excluded_even_if_fresh(self):
        """Polymarket is a PM venue and must never win the bettable best."""
        book_prices = {
            "polymarket": {"home": 3.00, "away": 1.50},  # best odds but PM
            "DraftKings": {"home": 1.95, "away": 1.90},  # sportsbook
        }
        venue_as_of = {
            "polymarket": FRESH_TS,
            "DraftKings": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "DraftKings"
        assert result["away"]["book"] == "DraftKings"

    def test_kalshi_excluded_even_if_fresh(self):
        """Kalshi is a PM venue and must never win the bettable best."""
        book_prices = {
            "kalshi":    {"home": 4.00},
            "FanDuel":   {"home": 1.91},
        }
        venue_as_of = {
            "kalshi":  FRESH_TS,
            "FanDuel": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "FanDuel"

    def test_pm_colon_prefix_excluded(self):
        """kalshi: prefixed venues are PM and must be excluded."""
        book_prices = {
            "kalshi:nba-game": {"home": 5.00},
            "BetMGM":          {"home": 2.00},
        }
        venue_as_of = {
            "kalshi:nba-game": FRESH_TS,
            "BetMGM":          FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "BetMGM"

    def test_all_pm_returns_empty(self):
        """When only PM venues are present -> {} (not a fabricated price)."""
        book_prices = {
            "polymarket": {"home": 2.50, "away": 1.60},
            "kalshi":     {"home": 2.80, "away": 1.55},
        }
        venue_as_of = {
            "polymarket": FRESH_TS,
            "kalshi":     FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}


# ---------------------------------------------------------------------------
# 5. Empty / all-stale -> {} per side, never a fabricated price
# ---------------------------------------------------------------------------

class TestEmptyAndAllStale:
    def test_empty_book_prices(self):
        result = best_line_fresh({}, {}, now=NOW)
        assert result == {}

    def test_all_stale_venues(self):
        book_prices = {
            "BookA": {"home": 2.10, "away": 1.80},
            "BookB": {"home": 2.05, "away": 1.82},
        }
        venue_as_of = {
            "BookA": STALE_TS,
            "BookB": STALE_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}

    def test_empty_prices_per_venue(self):
        """Venues with empty side dicts produce no output."""
        book_prices = {"FreshBook": {}}
        venue_as_of = {"FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}

    def test_only_invalid_prices_le_one(self):
        """Prices <= 1.0 are rejected as invalid decimal odds."""
        book_prices = {"FreshBook": {"home": 0.8, "away": 1.0}}
        venue_as_of = {"FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}

    def test_non_numeric_prices_skipped(self):
        """Non-numeric prices are skipped without raising."""
        book_prices = {"FreshBook": {"home": "n/a", "away": None}}
        venue_as_of = {"FreshBook": FRESH_TS}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {}


# ---------------------------------------------------------------------------
# 6. Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_none_book_prices(self):
        """Pathologically bad input must not raise."""
        result = best_line_fresh(None, {}, now=NOW)  # type: ignore[arg-type]
        assert result == {}

    def test_none_venue_as_of(self):
        book_prices = {"FreshBook": {"home": 1.90}}
        result = best_line_fresh(book_prices, None, now=NOW)  # type: ignore[arg-type]
        assert result == {}

    def test_garbage_book_prices_values(self):
        """Venues with non-dict prices are skipped, never raise."""
        book_prices = {
            "WeirdBook": "not-a-dict",   # type: ignore[dict-item]
            "FreshBook": {"home": 1.91},
        }
        venue_as_of = {
            "WeirdBook": FRESH_TS,
            "FreshBook": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result == {"home": {"book": "FreshBook", "price": pytest.approx(1.91)}}

    def test_z_suffix_timestamp_parsed_correctly(self):
        """ISO timestamps with Z suffix (not +00:00) must be accepted."""
        ts_z = "2026-06-20T11:59:00Z"   # 1 minute before NOW
        book_prices = {"FanDuel": {"home": 1.91}}
        venue_as_of = {"FanDuel": ts_z}
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert "home" in result
        assert result["home"]["book"] == "FanDuel"


# ---------------------------------------------------------------------------
# 7. Multi-side + best-per-side correctness
# ---------------------------------------------------------------------------

class TestMultiSide:
    def test_best_per_side_independently(self):
        """Different books can be best on different sides."""
        book_prices = {
            "BookA": {"home": 2.10, "away": 1.75},
            "BookB": {"home": 1.95, "away": 1.92},
        }
        venue_as_of = {
            "BookA": FRESH_TS,
            "BookB": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert result["home"]["book"] == "BookA"
        assert result["home"]["price"] == pytest.approx(2.10)
        assert result["away"]["book"] == "BookB"
        assert result["away"]["price"] == pytest.approx(1.92)

    def test_partial_coverage_no_fabrication(self):
        """A venue quoting only one side does not fabricate the other."""
        book_prices = {
            "HomeOnlyBook": {"home": 2.10},
            "AwayOnlyBook": {"away": 1.95},
        }
        venue_as_of = {
            "HomeOnlyBook": FRESH_TS,
            "AwayOnlyBook": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert "home" in result and result["home"]["book"] == "HomeOnlyBook"
        assert "away" in result and result["away"]["book"] == "AwayOnlyBook"

    def test_stale_book_provides_only_side_means_side_absent(self):
        """If the only book for a side is stale, that side is absent from result."""
        book_prices = {
            "StaleHomeOnly": {"home": 2.50},          # stale, only home quoter
            "FreshAwayOnly": {"away": 1.90},           # fresh, only away quoter
        }
        venue_as_of = {
            "StaleHomeOnly": STALE_TS,
            "FreshAwayOnly": FRESH_TS,
        }
        result = best_line_fresh(book_prices, venue_as_of, now=NOW)
        assert "home" not in result   # no fresh book quotes home -> absent
        assert result.get("away") == {"book": "FreshAwayOnly", "price": pytest.approx(1.90)}


# ---------------------------------------------------------------------------
# 8. Custom max_age_sec respected
# ---------------------------------------------------------------------------

class TestCustomMaxAge:
    def test_custom_max_age_tighter_than_default(self):
        """A 60-second max_age excludes a venue that would be fresh at 900s."""
        ts_120s_ago = _iso(_utc(-120))
        book_prices = {
            "SlightlyStale": {"home": 2.00},
            "VeryFresh":     {"home": 1.85},
        }
        venue_as_of = {
            "SlightlyStale": ts_120s_ago,
            "VeryFresh":     FRESH_TS,
        }
        result = best_line_fresh(
            book_prices, venue_as_of, max_age_sec=60.0, now=NOW
        )
        # 120s > 60s limit -> SlightlyStale excluded
        assert result["home"]["book"] == "VeryFresh"

    def test_custom_max_age_looser_accepts_older_ts(self):
        """A 3600-second max_age accepts a venue that is 30 minutes old."""
        book_prices = {
            "OlderBook": {"home": 2.00},
        }
        venue_as_of = {"OlderBook": STALE_TS}  # 30 min ago, within 3600 s
        result = best_line_fresh(
            book_prices, venue_as_of, max_age_sec=3600.0, now=NOW
        )
        assert "home" in result
        assert result["home"]["book"] == "OlderBook"
