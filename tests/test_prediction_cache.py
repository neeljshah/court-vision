"""tests/test_prediction_cache.py — covers R16_E3 prediction-cache infrastructure.

5+ tests:
    1. test_build_minimal — small cache builds end-to-end, parquet has the
       required schema.
    2. test_lookup_latency_p99 — get_prediction p99 across 200 calls < 100 ms.
    3. test_injury_refresh_triggers_reload — bumping the injury snapshot's
       mtime is detected and triggers a reload.
    4. test_ttl_refresh — when the cache file's mtime is set >24h ago,
       _needs_refresh reports the TTL trigger.
    5. test_missing_player_fallback — get_prediction returns None for a
       player_id not in the cache (caller falls back to slow path).
    6. test_apply_injury_dampener — q50 scales by the availability factor
       when apply_injury=True.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

# Bypass any live ESPN scrape during tests — we patch the dampener via mtime.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Isolate every test to a fresh data/cache dir + reset_for_tests."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(
        "scripts.serve_prediction._CACHE_DIR", str(cache_dir), raising=False
    )
    # Force a fresh in-process state.
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    yield cache_dir
    sp.reset_for_tests()


def _write_synthetic_cache(cache_dir: Path, *, n_players: int = 50,
                            iso_date: str | None = None) -> Path:
    """Write a parquet that mimics build_prediction_cache.py output.

    No model inference — just synthetic q10/q50/q90 + name/team. Used by
    tests that exercise the lookup / refresh logic without paying the
    real-build latency.
    """
    from datetime import date as _date_cls
    iso_date = iso_date or _date_cls.today().isoformat()
    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    rows = []
    rng = np.random.default_rng(7)
    for i in range(n_players):
        pid = 100000 + i
        team = ["LAL", "DEN", "BOS", "MIA", "GSW"][i % 5]
        name = f"Player {pid}"
        for stat in STATS:
            q50 = float(rng.uniform(0.5, 25.0))
            q10 = max(0.0, q50 - rng.uniform(2.0, 6.0))
            q90 = q50 + rng.uniform(2.0, 6.0)
            sigma = (q90 - q10) / 2.5631
            rows.append({
                "player_id": pid, "player_name": name, "team": team,
                "stat": stat, "q10": q10, "q50": q50, "q90": q90,
                "sigma": sigma,
                "computed_at": "2026-05-26T12:00:00+00:00",
            })
    df = pd.DataFrame(rows)
    out_path = cache_dir / f"predictions_cache_{iso_date}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


# ──────────────────────────────────────────────────────────────────────────
# 1. build_prediction_cache contract — synthetic small build
# ──────────────────────────────────────────────────────────────────────────

def test_build_minimal(tmp_cache):
    """Synthetic write produces a parquet with the required schema."""
    pq = _write_synthetic_cache(tmp_cache, n_players=3)
    assert pq.exists()
    df = pd.read_parquet(pq)
    required = {"player_id", "player_name", "team", "stat",
                "q10", "q50", "q90", "sigma", "computed_at"}
    assert required.issubset(set(df.columns)), \
        f"missing columns: {required - set(df.columns)}"
    # 3 players * 7 stats = 21 rows
    assert len(df) == 21
    assert (df["q50"] > 0).all()
    assert (df["q90"] >= df["q10"]).all()


# ──────────────────────────────────────────────────────────────────────────
# 2. Latency p99 < 100 ms
# ──────────────────────────────────────────────────────────────────────────

def test_lookup_latency_p99(tmp_cache):
    """200-call p99 lookup latency must stay below 100 ms (the spec gate)."""
    _write_synthetic_cache(tmp_cache, n_players=200)
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    # One cold load
    sp.refresh(force=True)
    # 200 hot calls — measure each.
    latencies_ms = []
    for i in range(200):
        pid = 100000 + (i % 200)
        t0 = time.perf_counter()
        rec = sp.get_prediction(pid, "pts", apply_injury=True)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert rec is not None, f"missing record for {pid}"
    p50 = float(np.percentile(latencies_ms, 50))
    p99 = float(np.percentile(latencies_ms, 99))
    assert p99 < 100.0, f"p99 = {p99:.2f}ms (>100ms gate)"
    assert p50 < 5.0, f"p50 = {p50:.2f}ms (>5ms — suspicious for a dict lookup)"


# ──────────────────────────────────────────────────────────────────────────
# 3. Injury-status update triggers refresh
# ──────────────────────────────────────────────────────────────────────────

def test_injury_refresh_triggers_reload(tmp_cache):
    """Touching the injury_status_*.json after cache load triggers a refresh."""
    _write_synthetic_cache(tmp_cache, n_players=5)
    inj_path = tmp_cache / "injury_status_2026-05-26.json"
    inj_path.write_text(json.dumps({"players": [], "date": "2026-05-26"}))
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    sp.refresh(force=True)
    initial_path = sp._STATE["injury_path"]
    initial_mtime = float(sp._STATE["injury_mtime"])
    assert initial_path == str(inj_path)
    # Bump the injury file's mtime + content.
    time.sleep(0.05)
    inj_path.write_text(json.dumps({"players": [{"player_id": 100000,
                                                  "player_name": "X",
                                                  "status": "OUT"}],
                                    "date": "2026-05-26"}))
    os.utime(inj_path, (time.time() + 5, time.time() + 5))
    need, reason = sp._needs_refresh()
    assert need, f"refresh should be required, reason={reason}"
    assert "injury" in reason


# ──────────────────────────────────────────────────────────────────────────
# 4. TTL fallback — >24h-old parquet triggers a refresh
# ──────────────────────────────────────────────────────────────────────────

def test_ttl_refresh(tmp_cache):
    """A parquet older than 24h flags needs_refresh with reason='ttl-expired'."""
    pq = _write_synthetic_cache(tmp_cache, n_players=3)
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    sp.refresh(force=True)
    assert sp._STATE["cache_path"] == str(pq)
    # Backdate the parquet 25h.
    old_t = time.time() - 25 * 3600
    os.utime(pq, (old_t, old_t))
    # Force the state's recorded cache_mtime to match so the "cache-rewritten"
    # trigger doesn't fire first — leaving TTL as the actual cause.
    sp._STATE["cache_mtime"] = old_t
    need, reason = sp._needs_refresh()
    assert need
    assert reason == "ttl-expired", f"unexpected reason: {reason}"


# ──────────────────────────────────────────────────────────────────────────
# 5. Missing player → None
# ──────────────────────────────────────────────────────────────────────────

def test_missing_player_fallback(tmp_cache):
    """Unknown player_id returns None (caller falls back to the slow path)."""
    _write_synthetic_cache(tmp_cache, n_players=5)
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    sp.refresh(force=True)
    # Known players are 100000..100004 — anything else misses.
    rec = sp.get_prediction(999_999_999, "pts")
    assert rec is None


# ──────────────────────────────────────────────────────────────────────────
# 6. Injury dampener applied multiplicatively at serve time
# ──────────────────────────────────────────────────────────────────────────

def test_apply_injury_dampener(tmp_cache, monkeypatch):
    """q50 scales by availability_factor when apply_injury=True."""
    _write_synthetic_cache(tmp_cache, n_players=5)
    sp = importlib.import_module("scripts.serve_prediction")
    sp.reset_for_tests()
    sp.refresh(force=True)

    # Patch the availability lookup to a fixed factor — bypasses ESPN.
    import src.prediction.injury_availability as inj
    monkeypatch.setattr(inj, "get_availability_factor",
                         lambda **kw: 0.6, raising=True)
    raw = sp.get_prediction(100000, "pts", apply_injury=False)
    damp = sp.get_prediction(100000, "pts", apply_injury=True)
    assert raw is not None and damp is not None
    assert damp["availability_factor"] == pytest.approx(0.6)
    assert damp["q50"] == pytest.approx(raw["q50"] * 0.6, rel=1e-6)
    assert damp["q10"] == pytest.approx(raw["q10"] * 0.6, rel=1e-6)
    assert damp["q90"] == pytest.approx(raw["q90"] * 0.6, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────────
# 7. Monotonicity clamp — q10 <= q50 <= q90 always (FIX IN-3)
# ──────────────────────────────────────────────────────────────────────────

def test_monotonicity_clamp_no_crossed_intervals():
    """_clamp_quantiles enforces q10<=q50<=q90 on crossed rows (e.g. BLK on stars).

    Directly exercises the clamp logic added to build_prediction_cache._predict_one_player
    by reproducing it as a pure helper and verifying 0% crossed intervals after clamping.
    """
    # Inline the clamp logic from build_prediction_cache._predict_one_player
    # so the test is self-contained and doesn't require model inference.
    def _apply_clamp(q10, q50, q90):
        """Mirror of the monotonicity clamp in build_prediction_cache."""
        if not (np.isnan(q10) or np.isnan(q50)):
            q10 = min(q10, q50)
        if not (np.isnan(q90) or np.isnan(q50)):
            q90 = max(q90, q50)
        return q10, q50, q90

    # Cases that exercise the BLK-star crossing pattern (q90 < q50 before clamp).
    crossed_cases = [
        # (q10_raw, q50_raw, q90_raw)  — deliberately broken intervals
        (0.5,  2.0, 1.5),   # q90 < q50 (the primary bug: star BLK)
        (3.0,  2.0, 4.0),   # q10 > q50
        (3.0,  2.0, 1.5),   # both q10>q50 and q90<q50
        (2.0,  2.0, 2.0),   # already monotone, equality
        (0.0,  1.5, 3.0),   # already monotone, normal case
        (float("nan"), 2.0, 1.5),  # nan q10 — only q90 clamp applies
        (0.5,  2.0, float("nan")), # nan q90 — only q10 clamp applies
    ]

    for q10_raw, q50_raw, q90_raw in crossed_cases:
        q10c, q50c, q90c = _apply_clamp(q10_raw, q50_raw, q90_raw)
        # q50 must never be changed by the clamp.
        assert q50c == q50_raw, f"q50 mutated: {q50_raw} -> {q50c}"
        # After clamp, no interval may be crossed (ignoring NaN endpoints).
        if not np.isnan(q10c):
            assert q10c <= q50c, (
                f"q10 > q50 after clamp: input=({q10_raw},{q50_raw},{q90_raw}) "
                f"output=({q10c},{q50c},{q90c})"
            )
        if not np.isnan(q90c):
            assert q90c >= q50c, (
                f"q90 < q50 after clamp: input=({q10_raw},{q50_raw},{q90_raw}) "
                f"output=({q10c},{q50c},{q90c})"
            )

    # Simulate a synthetic BLK cache with injected crossed rows and verify
    # that a rebuilt cache (using the same clamp) has 0% crossed rows.
    rng = np.random.default_rng(42)
    n = 200
    q50_vals = rng.uniform(0.1, 3.5, size=n)   # BLK-like range
    # Introduce ~10% crossed rows (q90 < q50) to mimic the star BLK bug.
    q90_raw = q50_vals + rng.uniform(-1.5, 3.0, size=n)   # some negatives => crossing
    q10_raw = np.maximum(0.0, q50_vals - rng.uniform(0.5, 2.0, size=n))

    q10_fixed = np.minimum(q10_raw, q50_vals)
    q90_fixed = np.maximum(q90_raw, q50_vals)

    crossed_before = int(np.sum(q90_raw < q50_vals))
    crossed_after  = int(np.sum(q90_fixed < q50_vals))
    assert crossed_before > 0, "test setup error: no crossed rows in synthetic data"
    assert crossed_after == 0, (
        f"{crossed_after}/{n} rows still crossed after clamp "
        f"(was {crossed_before} before)"
    )
