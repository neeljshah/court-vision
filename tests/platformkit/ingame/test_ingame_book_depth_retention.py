"""Per-file test for ingame_book_depth_retention (date-aware sticky eviction).

OFFLINE + deterministic, pure functions only -- no network, no clock injection
needed beyond a fixed now_dt.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_retention.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.ingame.ingame_book_depth_retention import evict_over_cap

_NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)

# "today" (2026-07-05) and "tomorrow" (07-06) are NOT future per the 1-day grace;
# 07-07/07-08 (2-3 days out) ARE future.
_TODAY = "KXMLBGAME-26JUL05AAABBB-AAA"
_TOMORROW = "KXMLBGAME-26JUL06CCCDDD-CCC"
_FUTURE_1 = "KXMLBGAME-26JUL07EEEFFF-EEE"  # 2 days out
_FUTURE_2 = "KXMLBGAME-26JUL08GGGHHH-GGG"  # 3 days out
_NO_DATE = "KXMLBGAME-TEST-AAA"  # unparseable -- no '-DDMONYY' fragment


def test_evict_over_cap_noop_under_cap():
    active = [_TODAY, _FUTURE_1]
    evict_over_cap(active, 5, _NOW)
    assert active == [_TODAY, _FUTURE_1]


def test_evict_over_cap_prefers_future_dated_first():
    """Root-cause regression: a live-today ticker must survive when a
    further-out ticker is the one crowding the cap, even though the future
    ticker was NOT necessarily appended more recently."""
    active = [_TODAY, _FUTURE_1, _FUTURE_2, _TOMORROW]
    evict_over_cap(active, 2, _NOW)
    assert set(active) == {_TODAY, _TOMORROW}


def test_evict_over_cap_drops_oldest_future_first_among_futures():
    active = [_FUTURE_1, _FUTURE_2, _TODAY]
    evict_over_cap(active, 2, _NOW)
    # FUTURE_1 was appended first among the future bucket -> dropped first.
    assert set(active) == {_FUTURE_2, _TODAY}


def test_evict_over_cap_falls_back_to_protected_bucket_when_still_over():
    """Last resort: if the cap is exceeded even with zero future tickers, the
    protected (today/past) bucket is trimmed oldest-first -- never grows
    unbounded."""
    active = [_TODAY, _TOMORROW, _NO_DATE]
    evict_over_cap(active, 1, _NOW)
    assert active == [_NO_DATE]


def test_evict_over_cap_unparseable_ticker_never_evicted_before_a_future_one():
    """An unparseable ticker (no date fragment) reads as 'not future' -- the
    safer bucket -- so it is protected ahead of a real future-dated ticker."""
    active = [_NO_DATE, _FUTURE_1]
    evict_over_cap(active, 1, _NOW)
    assert active == [_NO_DATE]
