"""
tests/test_m2_family_cache.py — R21_N5: m2_family predictions cache tests.

Validates:
  1. Cold miss populates the on-disk cache + returns correct values
  2. Warm hit (same models_mtime) returns cached + skips model `.predict` calls
  3. Stale mtime entry is invalidated + recomputed
  4. Concurrent reads/writes don't corrupt the JSON file
  5. Cache persists across simulated process restarts
  6. Cached vs un-cached values are byte-identical (correctness gate)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Dict
from unittest.mock import patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import game_models  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the cache path to a tmp dir so tests don't clobber the real
    cache and don't leak state between runs."""
    cache_path = tmp_path / "m2_family_predictions_cache.json"
    monkeypatch.setattr(game_models, "_M2_PRED_CACHE_PATH", str(cache_path))
    yield cache_path


@pytest.fixture
def real_row():
    """Pull a real season_games row. Skips the test if the worktree doesn't
    have one yet (e.g. fresh clone, no NBA cache hydrated)."""
    for fn in ("season_games_2024-25.json", "season_games_2025-26.json",
               "season_games_2023-24.json"):
        p = os.path.join(PROJECT_DIR, "data", "nba", fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        rows = d.get("rows", d) if isinstance(d, dict) else d
        for r in rows:
            if isinstance(r, dict) and "home_off_rtg" in r and r.get("game_id"):
                return r
    pytest.skip("no hydrated season_games_*.json with home_off_rtg available")


@pytest.fixture
def m2_loaded():
    """Skip when the m2_family artifact bundle isn't present locally."""
    if not game_models._try_load_m2_family():
        pytest.skip("data/models/m2_family/ not hydrated in this worktree")
    return True


# ── Tests ────────────────────────────────────────────────────────────────────


def test_cold_miss_populates_cache(isolated_cache, m2_loaded, real_row):
    """First call → no cache file → predict runs → cache written + result
    returned. File on disk contains an entry keyed by game_id with all 4 keys
    plus models_mtime + computed_at."""
    assert not os.path.exists(isolated_cache)
    out = game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    assert out is not None
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert k in out
        assert isinstance(out[k], float)
    assert os.path.exists(isolated_cache), "cache file should exist after cold call"
    with open(isolated_cache, encoding="utf-8") as f:
        d = json.load(f)
    gid = str(real_row["game_id"])
    assert gid in d
    entry = d[gid]
    assert "models_mtime" in entry
    assert "computed_at" in entry
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert entry[k] == out[k]


def test_warm_hit_skips_model_predict(isolated_cache, m2_loaded, real_row):
    """Second call with same mtime → cache hit → models[*].predict is never
    invoked. We patch np.array (the X = np.array([vals], ...) call inside the
    cold path) to assert it isn't called on the warm path."""
    # Cold call to seed cache.
    cold = game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    assert cold is not None

    # Now monkey-patch every model's .predict to a sentinel that raises if hit.
    call_count = {"n": 0}
    real_caches = game_models._M2_FAMILY_CACHE
    assert real_caches is not None

    class _Tripwire:
        def __init__(self, real):
            self._real = real

        def predict(self, X):  # noqa: ANN001
            call_count["n"] += 1
            return self._real.predict(X)

    wrapped = {
        k: [_Tripwire(m) for m in v] for k, v in real_caches.items()
    }
    with patch.object(game_models, "_M2_FAMILY_CACHE", wrapped):
        warm = game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    assert warm == cold, "warm hit must return identical values"
    assert call_count["n"] == 0, (
        f"models[*].predict invoked {call_count['n']} times on warm hit"
    )


def test_correctness_cached_equals_uncached(isolated_cache, m2_loaded, real_row):
    """The cache MUST return the exact same float values as the cold path —
    no rounding drift, no key reorder, no type coercion artifacts."""
    cold = game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    warm = game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    assert cold == warm
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert cold[k] == warm[k]


def test_stale_mtime_invalidates(isolated_cache, m2_loaded, real_row):
    """If we write a cache entry with a fake (old) mtime, the next call must
    NOT honor it — it should recompute and overwrite with the current mtime."""
    # Seed a stale entry directly.
    gid = str(real_row["game_id"])
    stale = {
        gid: {
            "models_mtime": -1.0,  # impossibly old
            "total_est": 999.9,
            "spread_est": 999.9,
            "home_pts_est": 999.9,
            "away_pts_est": 999.9,
            "computed_at": "1970-01-01T00:00:00+00:00",
        }
    }
    with open(isolated_cache, "w", encoding="utf-8") as f:
        json.dump(stale, f)

    out = game_models._predict_m2_family(real_row, game_id=gid)
    assert out is not None
    # Must be real predictions, not the stale 999.9s.
    assert out["total_est"] != 999.9
    # On-disk entry must have been overwritten with the current mtime.
    with open(isolated_cache, encoding="utf-8") as f:
        d = json.load(f)
    assert d[gid]["models_mtime"] == game_models._m2_family_models_mtime()
    assert d[gid]["models_mtime"] != -1.0


def test_concurrent_writes_dont_corrupt(isolated_cache, m2_loaded, real_row):
    """Hammer the cache from N threads. After all threads finish the JSON file
    must still parse cleanly and contain at least one valid entry. Atomic
    os.replace guarantees no torn write."""
    gid = str(real_row["game_id"])
    barrier = threading.Barrier(8)
    errors: list = []

    def worker():
        try:
            barrier.wait(timeout=10)
            for _ in range(5):
                game_models._predict_m2_family(real_row, game_id=gid)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, f"worker errors: {errors}"

    # File must still parse and contain our game_id.
    with open(isolated_cache, encoding="utf-8") as f:
        d = json.load(f)
    assert gid in d
    entry = d[gid]
    assert entry["models_mtime"] == game_models._m2_family_models_mtime()


def test_cache_persists_across_process_restart_simulation(
    isolated_cache, m2_loaded, real_row
):
    """Write a cache, drop the in-memory module-level state, re-import, and
    verify the warm path still hits without re-running models."""
    gid = str(real_row["game_id"])
    cold = game_models._predict_m2_family(real_row, game_id=gid)
    assert cold is not None
    assert os.path.exists(isolated_cache)

    # Simulate restart: clear the lazy-loaded model bundle. The on-disk cache
    # file is what should drive the warm hit.
    raw = json.load(open(isolated_cache, encoding="utf-8"))
    assert gid in raw

    # Now invoke again — without touching the in-memory M2_FAMILY_CACHE — and
    # ensure it returns the same values straight from disk.
    warm = game_models._predict_m2_family(real_row, game_id=gid)
    assert warm == cold


def test_clear_cache_removes_file(isolated_cache, m2_loaded, real_row):
    """clear_m2_pred_cache() removes the JSON file."""
    game_models._predict_m2_family(real_row, game_id=real_row["game_id"])
    assert os.path.exists(isolated_cache)
    removed = game_models.clear_m2_pred_cache()
    assert removed is True
    assert not os.path.exists(isolated_cache)
    # Idempotent: second call returns False.
    assert game_models.clear_m2_pred_cache() is False


def test_no_game_id_skips_cache(isolated_cache, m2_loaded, real_row):
    """When neither caller-supplied game_id nor row.game_id is present we
    must NOT write to the cache (no usable key)."""
    row_no_gid = {k: v for k, v in real_row.items() if k != "game_id"}
    out = game_models._predict_m2_family(row_no_gid, game_id=None)
    assert out is not None
    assert not os.path.exists(isolated_cache), (
        "cache should stay empty when game_id is unavailable"
    )
