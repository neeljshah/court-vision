"""Per-file tests for scoreboard_venue.py

Acceptance criteria from PT-5-scoreboard-venue:
  - 10 kalshi + 5 poly rows -> by_venue['kalshi']['n'] == 10 and
    by_venue['poly']['n'] == 5
  - Venue with n < min_n -> mean_clv_pct is None and appears in
    insufficient_data_venues
  - No $ / pnl key on any output dict
  - unknown/empty taken_book -> bucket key is 'unknown'
  - Empty ledger -> n_settled == 0, by_venue == {}

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/pm_trading/test_scoreboard_venue.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List


def _make_row(venue: str, clv_pct: float, is_proxy: bool = False) -> Dict[str, Any]:
    """Build a minimal settled ledger row for testing."""
    return {
        "status": "settled",
        "taken_book": venue,
        "clv_pct": clv_pct,
        "clv_is_proxy": is_proxy,
    }


def _make_rows(venue: str, n: int, base_clv: float = 1.5) -> List[Dict[str, Any]]:
    """Make n settled rows for the given venue with varying clv_pct."""
    rows = []
    for i in range(n):
        # Alternate positive/negative to give meaningful mean
        sign = 1 if i % 3 != 0 else -1
        rows.append(_make_row(venue, round(sign * (base_clv + i * 0.1), 4)))
    return rows


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from scripts.platformkit.pm_trading.scoreboard_venue import (
    DEFAULT_MIN_N,
    build_venue_scoreboard,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAcceptanceCriteria:
    """PT-5-scoreboard-venue acceptance: 10 kalshi + 5 poly rows."""

    def _build(self, min_n: int = 5) -> Dict[str, Any]:
        rows = _make_rows("kalshi", 10) + _make_rows("poly", 5)
        return build_venue_scoreboard(rows=rows, min_n=min_n)

    def test_n_counts_correct(self):
        result = self._build()
        assert result["by_venue"]["kalshi"]["n"] == 10
        assert result["by_venue"]["poly"]["n"] == 5

    def test_n_settled_total(self):
        result = self._build()
        assert result["n_settled"] == 15

    def test_kalshi_clv_fields_present_and_float(self):
        result = self._build()
        k = result["by_venue"]["kalshi"]
        assert isinstance(k["mean_clv_pct"], float)
        assert isinstance(k["beat_close_rate"], float)

    def test_poly_clv_fields_present_and_float(self):
        result = self._build()
        p = result["by_venue"]["poly"]
        assert isinstance(p["mean_clv_pct"], float)
        assert isinstance(p["beat_close_rate"], float)

    def test_beat_close_rate_is_fraction_not_pct(self):
        """beat_close_rate must be in [0, 1], NOT 0..100."""
        result = self._build()
        for venue_stats in result["by_venue"].values():
            bcr = venue_stats["beat_close_rate"]
            if bcr is not None:
                assert 0.0 <= bcr <= 1.0, (
                    "beat_close_rate must be fraction [0,1], got %r" % bcr
                )


class TestInsufficientData:
    """Venues below min_n -> INSUFFICIENT_DATA (null CLV fields)."""

    def test_venue_below_min_n_returns_null_clv(self):
        rows = _make_rows("kalshi", 10) + _make_rows("poly", 3)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        p = result["by_venue"]["poly"]
        assert p["n"] == 3
        assert p["mean_clv_pct"] is None
        assert p["beat_close_rate"] is None

    def test_venue_below_min_n_in_insufficient_list(self):
        rows = _make_rows("kalshi", 10) + _make_rows("poly", 3)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        assert "poly" in result["insufficient_data_venues"]

    def test_venue_at_min_n_is_sufficient(self):
        rows = _make_rows("kalshi", 5) + _make_rows("poly", 5)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        assert result["by_venue"]["kalshi"]["mean_clv_pct"] is not None
        assert result["by_venue"]["poly"]["mean_clv_pct"] is not None
        assert result["insufficient_data_venues"] == []

    def test_venue_above_min_n_not_in_insufficient_list(self):
        rows = _make_rows("sportsbook", 20)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        assert "sportsbook" not in result["insufficient_data_venues"]


class TestNoDollarFields:
    """Output must never contain $ / pnl / roi keys."""

    _BANNED = {"pnl", "roi", "dollar", "profit", "revenue", "bankroll"}

    def _check_no_banned_keys(self, d: Dict[str, Any]) -> None:
        for key in d:
            for banned in self._BANNED:
                assert banned not in key.lower(), (
                    "Banned $ field found: %r" % key
                )

    def test_top_level_no_dollar_fields(self):
        rows = _make_rows("kalshi", 10) + _make_rows("poly", 5)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        self._check_no_banned_keys(result)

    def test_by_venue_no_dollar_fields(self):
        rows = _make_rows("kalshi", 10) + _make_rows("poly", 5)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        for venue_stats in result["by_venue"].values():
            self._check_no_banned_keys(venue_stats)


class TestEdgeCases:
    """Edge cases: empty ledger, unknown venue, open rows excluded."""

    def test_empty_ledger_returns_zero_n_settled(self):
        result = build_venue_scoreboard(rows=[], min_n=5)
        assert result["n_settled"] == 0
        assert result["by_venue"] == {}
        assert result["insufficient_data_venues"] == []

    def test_open_rows_excluded(self):
        rows = [
            {"status": "open", "taken_book": "kalshi", "clv_pct": 2.0},
            _make_row("kalshi", 1.5),
        ]
        result = build_venue_scoreboard(rows=rows, min_n=1)
        assert result["n_settled"] == 1
        assert result["by_venue"]["kalshi"]["n"] == 1

    def test_row_without_clv_pct_excluded(self):
        rows = [
            {"status": "settled", "taken_book": "kalshi"},   # no clv_pct
            _make_row("kalshi", 1.5),
        ]
        result = build_venue_scoreboard(rows=rows, min_n=1)
        assert result["by_venue"]["kalshi"]["n"] == 1

    def test_unknown_venue_key_for_empty_taken_book(self):
        row = {"status": "settled", "taken_book": "", "clv_pct": 1.0}
        result = build_venue_scoreboard(rows=[row], min_n=1)
        assert "unknown" in result["by_venue"]

    def test_venue_field_takes_precedence_over_taken_book(self):
        row = {
            "status": "settled",
            "venue": "kalshi",
            "taken_book": "other",
            "clv_pct": 1.0,
        }
        result = build_venue_scoreboard(rows=[row], min_n=1)
        assert "kalshi" in result["by_venue"]
        assert "other" not in result["by_venue"]

    def test_n_true_n_proxy_counts(self):
        rows = [
            _make_row("kalshi", 1.0, is_proxy=False),
            _make_row("kalshi", 2.0, is_proxy=True),
            _make_row("kalshi", -0.5, is_proxy=False),
        ]
        result = build_venue_scoreboard(rows=rows, min_n=1)
        k = result["by_venue"]["kalshi"]
        assert k["n_true_close"] == 2
        assert k["n_proxy_close"] == 1

    def test_median_prefers_true_close_over_proxy(self):
        # One fat proxy outlier (+40) must not enter the headline median when
        # true-close rows exist; mean_clv_pct (context) still sees it.
        rows = [
            _make_row("kalshi", 1.0, is_proxy=False),
            _make_row("kalshi", 3.0, is_proxy=False),
            _make_row("kalshi", 40.0, is_proxy=True),
        ]
        result = build_venue_scoreboard(rows=rows, min_n=1)
        k = result["by_venue"]["kalshi"]
        assert k["basis"] == "true_close"
        assert abs(k["median_clv_pct"] - 2.0) < 1e-6      # median of [1.0, 3.0]
        assert k["mean_clv_pct"] > 10.0                     # context mean sees +40

    def test_median_falls_back_to_proxy_only_when_no_true_close(self):
        rows = [
            _make_row("kalshi", 2.0, is_proxy=True),
            _make_row("kalshi", 4.0, is_proxy=True),
        ]
        result = build_venue_scoreboard(rows=rows, min_n=1)
        k = result["by_venue"]["kalshi"]
        assert k["basis"] == "proxy_only"
        assert abs(k["median_clv_pct"] - 3.0) < 1e-6

    def test_insufficient_data_venue_has_null_median_and_basis(self):
        rows = _make_rows("poly", 3)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        p = result["by_venue"]["poly"]
        assert p["median_clv_pct"] is None
        assert p["basis"] is None

    def test_honest_note_present(self):
        result = build_venue_scoreboard(rows=[], min_n=5)
        assert "honest_note" in result
        assert len(result["honest_note"]) > 10

    def test_as_of_present(self):
        result = build_venue_scoreboard(rows=[], min_n=5)
        assert "as_of" in result
        assert result["as_of"].startswith("20")

    def test_default_min_n_is_int(self):
        assert isinstance(DEFAULT_MIN_N, int)
        assert DEFAULT_MIN_N > 0

    def test_multi_venue_sorted_keys(self):
        rows = _make_rows("sportsbook", 10) + _make_rows("kalshi", 10)
        result = build_venue_scoreboard(rows=rows, min_n=5)
        keys = list(result["by_venue"].keys())
        assert keys == sorted(keys), "by_venue keys should be sorted"
