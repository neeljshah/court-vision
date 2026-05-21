"""
Tests for src/cache/predictive_cache.py
"""

from __future__ import annotations

import os
import sys
import time

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.cache.predictive_cache import PredictiveCache, state_hash, make_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache(tmp_path):
    return PredictiveCache(cache_dir=str(tmp_path / "pc"))


def _pred(n: int) -> dict:
    return {"points": float(n), "assists": float(n % 5)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_state_hash_deterministic():
    """Hash must be key-order independent and sensitive to value changes."""
    assert state_hash({"a": 1, "b": 2}) == state_hash({"b": 2, "a": 1})
    assert state_hash({"a": 1}) != state_hash({"a": 2})


def test_put_get_roundtrip(tmp_path):
    """A prediction stored with put() is retrievable with get()."""
    cache = _cache(tmp_path)
    pred = {"points": 22.5, "rebounds": 7.0}
    state = {"lineup": ["LBJ", "AD"], "model_version": "v3"}

    cache.put("GAME_001", "pts", state, pred)
    result = cache.get("GAME_001", "pts", state)

    assert result == pred


def test_miss_returns_none(tmp_path):
    """get() on a key that was never put returns None and records a miss."""
    cache = _cache(tmp_path)
    result = cache.get("GAME_999", "reb", {"lineup": ["X"]})

    assert result is None
    assert cache.stats()["misses"] == 1


def test_hit_rate_over_80_percent(tmp_path):
    """Consecutive slate run simulation: 20 hits out of 22 lookups ≈ 0.91."""
    cache = _cache(tmp_path)

    # First pass — populate 20 entries
    entries = [
        ("GAME_{:03d}".format(i), "pts", {"model": "v1", "idx": i})
        for i in range(20)
    ]
    for idx, (game_id, market, state) in enumerate(entries):
        cache.put(game_id, market, state, _pred(idx))

    # Second pass — look up all 20 (hits) + 2 brand-new (misses)
    for game_id, market, state in entries:
        cache.get(game_id, market, state)

    cache.get("GAME_NEW_1", "pts", {"model": "v1", "idx": 100})
    cache.get("GAME_NEW_2", "pts", {"model": "v1", "idx": 101})

    s = cache.stats()
    assert s["hit_rate"] > 0.80, f"hit_rate={s['hit_rate']:.3f}"


def test_ttl_expiry(tmp_path):
    """After TTL expires, a cold get() (L1 cleared) returns None."""
    cache = PredictiveCache(cache_dir=str(tmp_path / "pc"), ttl_seconds=0.01)
    state = {"model": "v1"}

    cache.put("GAME_TTL", "ast", state, {"assists": 5.0})

    # Wait for TTL to expire
    time.sleep(0.05)

    # Flush L1 so the cache must consult L2
    cache.clear()

    result = cache.get("GAME_TTL", "ast", state)
    assert result is None


def test_invalidate(tmp_path):
    """invalidate(game_id) removes that game's entries and leaves others intact."""
    cache = _cache(tmp_path)
    state_a = {"model": "v1"}
    state_b = {"model": "v1"}
    pred_a = {"points": 10.0}
    pred_b = {"points": 20.0}

    cache.put("A", "pts", state_a, pred_a)
    cache.put("B", "pts", state_b, pred_b)

    removed = cache.invalidate("A")

    assert removed == 1
    assert cache.get("A", "pts", state_a) is None
    assert cache.get("B", "pts", state_b) == pred_b
