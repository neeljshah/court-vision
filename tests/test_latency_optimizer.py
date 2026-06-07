"""tests/test_latency_optimizer.py — Phase A latency-optimizer regression."""
from __future__ import annotations

import time

import pytest

from src.live.latency_optimizer import (
    EventCoalescer,
    LatencyProbe,
    is_game_live,
    lru_ttl_cache,
)


def test_lru_ttl_cache_caches_within_ttl():
    calls = {"n": 0}

    @lru_ttl_cache(maxsize=4, ttl_seconds=5.0)
    def expensive(x):
        calls["n"] += 1
        return x * 2

    assert expensive(3) == 6
    assert expensive(3) == 6
    assert expensive(3) == 6
    assert calls["n"] == 1  # only 1 actual call


def test_lru_ttl_cache_expires_after_ttl():
    calls = {"n": 0}

    @lru_ttl_cache(maxsize=4, ttl_seconds=0.05)
    def f(x):
        calls["n"] += 1
        return x

    f(1)
    time.sleep(0.08)
    f(1)
    assert calls["n"] == 2


def test_lru_ttl_cache_evicts_oldest_at_maxsize():
    @lru_ttl_cache(maxsize=2, ttl_seconds=5.0)
    def f(x):
        return x

    f(1); f(2); f(3)   # 1 should be evicted
    info = f.cache_info()
    assert info["entries"] == 2


def test_coalescer_drops_duplicate_in_window():
    c = EventCoalescer(window_seconds=1.0)
    assert c.should_emit("evt:42") is True
    assert c.should_emit("evt:42") is False
    assert c.should_emit("evt:43") is True   # different key


def test_coalescer_allows_emit_after_window():
    c = EventCoalescer(window_seconds=0.05)
    assert c.should_emit("k") is True
    time.sleep(0.08)
    assert c.should_emit("k") is True


def test_is_game_live_canonical_schema():
    assert is_game_live({"game_status": "LIVE"}) is True
    assert is_game_live({"game_status": "PREGAME"}) is False
    assert is_game_live({"game_status": "FINAL"}) is False


def test_is_game_live_raw_cdn_schema():
    assert is_game_live({"gameStatus": 2}) is True
    assert is_game_live({"gameStatus": 1}) is False
    assert is_game_live({"gameStatus": 3}) is False


def test_is_game_live_handles_none_and_empty():
    assert is_game_live(None) is False
    assert is_game_live({}) is False


def test_latency_probe_basic():
    p = LatencyProbe()
    p.mark("a")
    time.sleep(0.01)
    p.mark("b")
    elapsed = p.elapsed_ms("a", "b")
    assert 5.0 < elapsed < 200.0


def test_latency_probe_missing_marks_raises():
    p = LatencyProbe()
    p.mark("a")
    with pytest.raises(KeyError):
        p.elapsed_ms("a", "b")
