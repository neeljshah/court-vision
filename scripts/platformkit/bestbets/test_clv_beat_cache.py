"""Per-file tests for scripts.platformkit.bestbets.clv_beat_cache (BB-Q10).

Acceptance criteria:
  A. 3 settled true-close rows -> cache built keyed by (sport, market).
  B. get_beat_rate returns dict with {n, pct_beat_close, mean_clv_pct, status}.
  C. Proxy / null clv_pct rows EXCLUDED from beat-rate (not counted).
  D. Missing-file (empty row list) -> INSUFFICIENT_DATA safe.
  E. No $/roi/pnl key anywhere in any output.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/bestbets/test_clv_beat_cache.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.bestbets.clv_beat_cache import (
    MIN_N,
    build_beat_cache,
    get_beat_rate,
    load_beat_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEYS = {"dollar", "roi", "pnl", "profit", "revenue", "bankroll", "stake_dollars"}


def _make_settled_row(
    sport: str,
    market: str,
    clv_pct: float,
    *,
    is_proxy: bool = False,
) -> dict:
    """Minimal settled true-close ledger row."""
    return {
        "status": "settled",
        "sport": sport,
        "market": market,
        "clv_pct": clv_pct,
        "clv_is_proxy": is_proxy,
        "beat_close": clv_pct > 0.0,
    }


def _assert_no_banned_keys(obj: object) -> None:
    """Recursively assert no banned (dollar/roi/pnl) keys exist.

    Cache keys may be tuples (sport, market); only string keys are checked
    against the banned set.  Tuple keys are descended into their values only.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                assert k.lower() not in _BANNED_KEYS, f"Banned key found: {k!r}"
            _assert_no_banned_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _assert_no_banned_keys(item)


# ---------------------------------------------------------------------------
# A. Cache built from 3 settled true-close rows
# ---------------------------------------------------------------------------

class TestCacheBuiltFromThreeRows:
    """AA -- build_beat_cache with exactly 3 rows for one (sport, market)."""

    def setup_method(self):
        # 3 rows: 2 beat the close, 1 did not
        self.rows = [
            _make_settled_row("nba", "moneyline", 1.5),
            _make_settled_row("nba", "moneyline", 2.0),
            _make_settled_row("nba", "moneyline", -0.5),
        ]
        self.cache = build_beat_cache(self.rows)

    def test_cache_contains_sport_market_key(self):
        assert ("nba", "moneyline") in self.cache, "Expected key ('nba','moneyline') in cache"

    def test_n_equals_three(self):
        result = get_beat_rate(self.cache, "nba", "moneyline")
        assert result["n"] == 3

    def test_pct_beat_close_is_two_thirds(self):
        result = get_beat_rate(self.cache, "nba", "moneyline")
        # 2 out of 3 beat the close -> 66.6667%
        assert result["pct_beat_close"] is not None
        assert abs(result["pct_beat_close"] - (200.0 / 3.0)) < 0.01

    def test_mean_clv_pct_correct(self):
        result = get_beat_rate(self.cache, "nba", "moneyline")
        expected = (1.5 + 2.0 + (-0.5)) / 3.0
        assert result["mean_clv_pct"] is not None
        assert abs(result["mean_clv_pct"] - expected) < 1e-5

    def test_status_is_graded(self):
        result = get_beat_rate(self.cache, "nba", "moneyline")
        assert result["status"] == "graded"

    def test_no_banned_keys(self):
        _assert_no_banned_keys(self.cache)


# ---------------------------------------------------------------------------
# B. get_beat_rate returns expected dict shape
# ---------------------------------------------------------------------------

class TestGetBeatRateShape:
    """BB -- return dict has required keys; works on both hit and miss."""

    _REQUIRED_KEYS = {"n", "pct_beat_close", "mean_clv_pct", "status"}

    def test_hit_has_all_required_keys(self):
        rows = [_make_settled_row("mlb", "moneyline", c) for c in [1.0, 2.0, -1.0]]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "mlb", "moneyline")
        assert self._REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {self._REQUIRED_KEYS - result.keys()}"
        )

    def test_miss_has_all_required_keys(self):
        cache = build_beat_cache([])
        result = get_beat_rate(cache, "nba", "moneyline")
        assert self._REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {self._REQUIRED_KEYS - result.keys()}"
        )

    def test_hit_types_are_correct(self):
        rows = [_make_settled_row("soccer", "totals", c) for c in [0.5, 1.5, 2.5]]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "soccer", "totals")
        assert isinstance(result["n"], int)
        assert isinstance(result["pct_beat_close"], float)
        assert isinstance(result["mean_clv_pct"], float)
        assert isinstance(result["status"], str)

    def test_no_banned_keys_on_hit(self):
        rows = [_make_settled_row("tennis", "moneyline", c) for c in [1.0, 0.5, -0.5]]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "tennis", "moneyline")
        _assert_no_banned_keys(result)

    def test_no_banned_keys_on_miss(self):
        result = get_beat_rate({}, "nba", "totals")
        _assert_no_banned_keys(result)


# ---------------------------------------------------------------------------
# C. Proxy rows EXCLUDED from beat-rate
# ---------------------------------------------------------------------------

class TestProxyExclusion:
    """CC -- proxy rows do not count toward the beat-rate."""

    def test_proxy_rows_do_not_count(self):
        # 2 true-close rows + 5 proxy rows; only the 2 true-close rows should count
        rows = [
            _make_settled_row("nba", "spread", 3.0, is_proxy=False),
            _make_settled_row("nba", "spread", -1.0, is_proxy=False),
            # These are proxy and should be excluded
            _make_settled_row("nba", "spread", 5.0, is_proxy=True),
            _make_settled_row("nba", "spread", 6.0, is_proxy=True),
            _make_settled_row("nba", "spread", 7.0, is_proxy=True),
            _make_settled_row("nba", "spread", 8.0, is_proxy=True),
            _make_settled_row("nba", "spread", 9.0, is_proxy=True),
        ]
        cache = build_beat_cache(rows)
        # n should be 2 (below MIN_N=3) from the true-close rows only
        result = get_beat_rate(cache, "nba", "spread")
        assert result["n"] == 2, f"Expected n=2 (proxy excluded), got {result['n']}"

    def test_proxy_only_gives_insufficient_data(self):
        # Only proxy rows -- no true-close graded rows at all
        rows = [
            _make_settled_row("nba", "totals", c, is_proxy=True)
            for c in [1.0, 2.0, 3.0, 4.0, 5.0]
        ]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "nba", "totals")
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n"] == 0

    def test_null_clv_pct_excluded(self):
        # Rows with clv_pct=None should not count
        rows = [
            {"status": "settled", "sport": "mlb", "market": "moneyline", "clv_pct": None},
            {"status": "settled", "sport": "mlb", "market": "moneyline"},
            _make_settled_row("mlb", "moneyline", 2.0),
        ]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "mlb", "moneyline")
        # Only 1 valid row (n < MIN_N=3)
        assert result["n"] == 1

    def test_open_rows_excluded(self):
        # Open rows (status != "settled") must not count
        rows = [
            {"status": "open", "sport": "nba", "market": "moneyline", "clv_pct": 5.0},
            _make_settled_row("nba", "moneyline", 1.0),
            _make_settled_row("nba", "moneyline", 2.0),
            _make_settled_row("nba", "moneyline", -0.5),
        ]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "nba", "moneyline")
        assert result["n"] == 3


# ---------------------------------------------------------------------------
# D. Missing file -> INSUFFICIENT_DATA safe
# ---------------------------------------------------------------------------

class TestMissingFileSafe:
    """DD -- empty row list (no file on disk) returns INSUFFICIENT_DATA."""

    def test_empty_rows_returns_empty_cache(self):
        cache = build_beat_cache([])
        assert cache == {}

    def test_get_beat_rate_on_empty_cache_is_insufficient(self):
        result = get_beat_rate({}, "nba", "moneyline")
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n"] == 0
        assert result["pct_beat_close"] is None
        assert result["mean_clv_pct"] is None

    def test_load_beat_cache_nonexistent_path_returns_empty(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.jsonl"
        cache = load_beat_cache(path=nonexistent)
        assert cache == {}

    def test_get_beat_rate_after_nonexistent_path_is_safe(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist.jsonl"
        cache = load_beat_cache(path=nonexistent)
        result = get_beat_rate(cache, "nba", "moneyline")
        assert result["status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# E. No $/roi/pnl key anywhere
# ---------------------------------------------------------------------------

class TestNoBannedKeys:
    """EE -- no dollar/roi/pnl key anywhere in cache or result."""

    def test_no_banned_keys_in_cache(self):
        rows = [_make_settled_row("nba", "moneyline", c) for c in [1.0, 2.0, 3.0]]
        cache = build_beat_cache(rows)
        _assert_no_banned_keys(cache)

    def test_no_banned_keys_in_multi_sport_multi_market_cache(self):
        rows = (
            [_make_settled_row("nba", "moneyline", c) for c in [1.0, 2.0, 3.0]]
            + [_make_settled_row("mlb", "moneyline", c) for c in [-1.0, 0.5, 2.5]]
            + [_make_settled_row("soccer", "totals", c) for c in [0.1, 0.2, 0.3]]
        )
        cache = build_beat_cache(rows)
        _assert_no_banned_keys(cache)

    def test_no_banned_keys_in_miss_result(self):
        result = get_beat_rate({}, "nba", "spread")
        _assert_no_banned_keys(result)


# ---------------------------------------------------------------------------
# F. Multi-sport multi-market partitioning
# ---------------------------------------------------------------------------

class TestMultiSportMultiMarket:
    """FF -- different (sport, market) keys are stored independently."""

    def setup_method(self):
        rows = (
            [_make_settled_row("nba", "moneyline", c) for c in [1.0, 2.0, 3.0]]
            + [_make_settled_row("mlb", "moneyline", c) for c in [-1.0, -2.0, -3.0]]
            + [_make_settled_row("nba", "spread", c) for c in [0.5, 0.6, 0.7]]
        )
        self.cache = build_beat_cache(rows)

    def test_nba_moneyline_key_present(self):
        assert ("nba", "moneyline") in self.cache

    def test_mlb_moneyline_key_present(self):
        assert ("mlb", "moneyline") in self.cache

    def test_nba_spread_key_present(self):
        assert ("nba", "spread") in self.cache

    def test_nba_moneyline_all_beat(self):
        result = get_beat_rate(self.cache, "nba", "moneyline")
        assert result["pct_beat_close"] == 100.0

    def test_mlb_moneyline_none_beat(self):
        result = get_beat_rate(self.cache, "mlb", "moneyline")
        assert result["pct_beat_close"] == 0.0

    def test_unknown_key_is_insufficient(self):
        result = get_beat_rate(self.cache, "tennis", "moneyline")
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n"] == 0

    def test_case_insensitive_lookup(self):
        result_upper = get_beat_rate(self.cache, "NBA", "MONEYLINE")
        result_lower = get_beat_rate(self.cache, "nba", "moneyline")
        assert result_upper["n"] == result_lower["n"]


# ---------------------------------------------------------------------------
# G. Below-MIN_N bucket is INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

class TestBelowMinNIsInsufficient:
    """GG -- fewer than MIN_N true-close rows -> INSUFFICIENT_DATA."""

    def test_two_rows_insufficient(self):
        rows = [
            _make_settled_row("nba", "moneyline", 1.0),
            _make_settled_row("nba", "moneyline", 2.0),
        ]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "nba", "moneyline")
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["n"] == 2

    def test_exactly_min_n_rows_is_graded(self):
        rows = [_make_settled_row("nba", "spread", float(i)) for i in range(MIN_N)]
        cache = build_beat_cache(rows)
        result = get_beat_rate(cache, "nba", "spread")
        assert result["status"] == "graded"
        assert result["n"] == MIN_N


# ---------------------------------------------------------------------------
# H. load_beat_cache with real file (integration, tmp_path)
# ---------------------------------------------------------------------------

class TestLoadBeatCacheFromFile:
    """HH -- load_beat_cache wires clv_ledger.load_ledger for the real path."""

    def test_load_from_temp_jsonl(self, tmp_path):
        import json
        ledger_path = tmp_path / "clv_ledger.jsonl"
        rows = [_make_settled_row("soccer", "moneyline", c) for c in [0.5, 1.0, 2.0]]
        with ledger_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

        cache = load_beat_cache(path=ledger_path)
        result = get_beat_rate(cache, "soccer", "moneyline")
        assert result["n"] == 3
        assert result["status"] == "graded"
        _assert_no_banned_keys(result)
