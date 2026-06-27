"""Per-file unit tests for odds_provider.freshness (PURE -- no network, no I/O).

Run ONLY this file (a bare pytest freezes the box):
    python -m pytest tests/platformkit/test_freshness.py -q

Covers:
  - just-fresh (age == max_age exactly -> fresh boundary, inclusive)
  - just-stale (age > max_age by 1 second)
  - unknown (None, empty string, garbage timestamp)
  - is_fresh mirrors freshness_status
  - Z-suffix ISO strings parse correctly
  - per-market override map takes precedence
  - built-in MARKET_MAX_AGE table used when no caller override
  - naive now (no tzinfo) treated as UTC without error
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.odds_provider.freshness import (
    DEFAULT_MAX_AGE_SEC,
    MARKET_MAX_AGE,
    freshness_status,
    is_fresh,
)

# A fixed "now" anchor for all injectable tests.
_NOW = datetime(2026, 6, 18, 20, 0, 0, tzinfo=timezone.utc)

def _ts(offset_sec: float) -> str:
    """ISO-8601 UTC string at _NOW + offset_sec (negative = in the past)."""
    dt = _NOW + timedelta(seconds=offset_sec)
    return dt.isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# freshness_status: boundary cases -- just-fresh / just-stale
# ---------------------------------------------------------------------------

def test_just_fresh_at_boundary():
    # Exactly at max_age -> fresh (inclusive boundary).
    ts = _ts(-DEFAULT_MAX_AGE_SEC)
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "fresh"
    assert abs(result["age_sec"] - DEFAULT_MAX_AGE_SEC) < 0.5


def test_one_second_over_boundary_is_stale():
    ts = _ts(-(DEFAULT_MAX_AGE_SEC + 1.0))
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "stale"
    assert result["age_sec"] > DEFAULT_MAX_AGE_SEC


def test_very_fresh_line():
    ts = _ts(-10.0)  # 10 seconds old
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "fresh"
    assert abs(result["age_sec"] - 10.0) < 0.5


def test_very_stale_line():
    ts = _ts(-7200.0)  # 2 hours old
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "stale"
    assert result["age_sec"] > 7000.0


# ---------------------------------------------------------------------------
# unknown: None / empty / garbage -> status="unknown", age_sec=None, no raise
# ---------------------------------------------------------------------------

def test_none_timestamp_is_unknown():
    result = freshness_status(None, now=_NOW)
    assert result["status"] == "unknown"
    assert result["age_sec"] is None


def test_empty_string_is_unknown():
    result = freshness_status("", now=_NOW)
    assert result["status"] == "unknown"
    assert result["age_sec"] is None


def test_garbage_timestamp_is_unknown():
    result = freshness_status("not-a-date", now=_NOW)
    assert result["status"] == "unknown"
    assert result["age_sec"] is None


def test_numeric_zero_is_unknown():
    result = freshness_status(0, now=_NOW)
    assert result["status"] == "unknown"


# ---------------------------------------------------------------------------
# is_fresh mirrors freshness_status (unknown -> False, conservative)
# ---------------------------------------------------------------------------

def test_is_fresh_returns_true_when_fresh():
    ts = _ts(-60.0)
    assert is_fresh(ts, now=_NOW) is True


def test_is_fresh_returns_false_when_stale():
    ts = _ts(-(DEFAULT_MAX_AGE_SEC + 60.0))
    assert is_fresh(ts, now=_NOW) is False


def test_is_fresh_returns_false_for_unknown():
    # Unknown timestamp is NOT trusted as fresh (conservative).
    assert is_fresh(None, now=_NOW) is False
    assert is_fresh("", now=_NOW) is False
    assert is_fresh("garbage", now=_NOW) is False


# ---------------------------------------------------------------------------
# Z-suffix ISO strings (aggregate as_of / MarketQuote.captured_at shapes)
# ---------------------------------------------------------------------------

def test_z_suffix_parses_as_utc():
    ts = "2026-06-18T19:59:00Z"  # 60 seconds before _NOW
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "fresh"
    assert abs(result["age_sec"] - 60.0) < 0.5


def test_plus00_suffix_parses():
    ts = "2026-06-18T19:59:00+00:00"
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "fresh"


# ---------------------------------------------------------------------------
# Per-market override map: caller override > built-in MARKET_MAX_AGE > default
# ---------------------------------------------------------------------------

def test_custom_max_age_sec_overrides_default():
    # 50 seconds old; default 900 -> fresh, custom 30 -> stale.
    ts = _ts(-50.0)
    assert freshness_status(ts, now=_NOW)["status"] == "fresh"
    assert freshness_status(ts, now=_NOW, max_age_sec=30.0)["status"] == "stale"


def test_builtin_market_max_age_used_when_market_type_given():
    # "total" has a built-in max_age of 1800s.
    # A line 1200s old: fresh as "total" (1800 limit), stale as "moneyline" (900).
    ts = _ts(-1200.0)
    assert freshness_status(ts, now=_NOW, market_type="total")["status"] == "fresh"
    assert freshness_status(ts, now=_NOW, market_type="moneyline")["status"] == "stale"


def test_caller_override_map_beats_builtin():
    # Caller says "total" max age = 600s; built-in says 1800s.
    ts = _ts(-700.0)  # 700s old
    override = {"total": 600.0}
    # With override: stale (700 > 600)
    assert freshness_status(
        ts, now=_NOW, market_type="total", max_age_override=override
    )["status"] == "stale"
    # Without override (built-in 1800s): fresh
    assert freshness_status(
        ts, now=_NOW, market_type="total"
    )["status"] == "fresh"


def test_is_fresh_respects_market_type_and_override():
    ts = _ts(-1200.0)
    assert is_fresh(ts, now=_NOW, market_type="total") is True
    assert is_fresh(ts, now=_NOW, market_type="moneyline") is False
    assert is_fresh(ts, now=_NOW, market_type="total",
                    max_age_override={"total": 600.0}) is False


# ---------------------------------------------------------------------------
# Naive now (no tzinfo) is treated as UTC without raising
# ---------------------------------------------------------------------------

def test_naive_now_treated_as_utc():
    naive_now = datetime(2026, 6, 18, 20, 0, 0)  # no tzinfo
    ts = _ts(-60.0)  # 60s before _NOW (aware UTC)
    # Should not raise; naive is treated as UTC, result matches aware version.
    result_naive = freshness_status(ts, now=naive_now)
    result_aware = freshness_status(ts, now=_NOW)
    assert result_naive["status"] == result_aware["status"]
    assert abs((result_naive["age_sec"] or 0) - (result_aware["age_sec"] or 0)) < 1.0


# ---------------------------------------------------------------------------
# MARKET_MAX_AGE constant sanity
# ---------------------------------------------------------------------------

def test_market_max_age_keys_exist():
    for key in ("moneyline", "spread", "total", "prop"):
        assert key in MARKET_MAX_AGE
        assert MARKET_MAX_AGE[key] > 0


def test_default_max_age_sec_is_positive():
    assert DEFAULT_MAX_AGE_SEC > 0


# ---------------------------------------------------------------------------
# Future-skew guard (the FUTURE half of stale-never-green): a timestamp wildly
# ahead of our clock is a corrupt/clock-skewed feed and must NOT read fresh
# forever; a mild benign skew within tolerance stays fresh.
# ---------------------------------------------------------------------------

def test_far_future_timestamp_is_unknown_not_fresh():
    # A feed stamping 2 days in the future: negative age would otherwise satisfy
    # age <= max_age and read fresh forever. Must classify as untrusted "unknown".
    ts = _ts(2 * 24 * 3600.0)
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "unknown"
    assert not is_fresh(ts, now=_NOW)


def test_mild_future_skew_within_tolerance_is_fresh():
    # +30s ahead is a benign source/box clock offset -> still fresh.
    ts = _ts(30.0)
    result = freshness_status(ts, now=_NOW)
    assert result["status"] == "fresh"


def test_future_skew_boundary_inclusive_then_unknown():
    from scripts.platformkit.odds_provider.freshness import (
        FUTURE_SKEW_TOLERANCE_SEC,
    )
    # Exactly at the tolerance -> still fresh (inclusive); just past -> unknown.
    at = _ts(FUTURE_SKEW_TOLERANCE_SEC)
    over = _ts(FUTURE_SKEW_TOLERANCE_SEC + 1.0)
    assert freshness_status(at, now=_NOW)["status"] == "fresh"
    assert freshness_status(over, now=_NOW)["status"] == "unknown"
