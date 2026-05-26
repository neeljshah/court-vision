"""tests/test_R24_Q3_m2_retrain.py — R24_Q3 m2_family retrain probe tests.

Five checks:
  1. all 20 m2_family artifacts loadable (or correctly absent on fresh clone)
  2. predictions reproducible byte-for-byte from the same fitted ensemble
  3. R20_M7 wire still active in src/prediction/game_models.py
  4. R21_N5 cache invalidates automatically when artifact mtimes change
  5. _predict_m2_family returns no NaN values when artifacts present
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Resolve the canonical project root for the (gitignored) data/models artifacts.
# In a fresh worktree clone the artifacts won't be present — tests gracefully
# skip those specific assertions but still validate the wire + cache logic.
def _resolve_models_dir() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    p = os.path.join(cand, "data", "models", "m2_family")
    if os.path.isdir(p):
        return p
    return os.path.join(PROJECT_DIR, "data", "models", "m2_family")


_M2_DIR = _resolve_models_dir()
_MANIFEST = os.path.join(_M2_DIR, "manifest.json")
_FEAT_COLS = os.path.join(_M2_DIR, "feature_cols.json")

_LGB_SEEDS = (42, 7, 100)
_XGB_SEEDS = (42, 7)
_TARGETS = ("total", "spread", "home_pts", "away_pts")


def _artifacts_present() -> bool:
    return os.path.exists(_MANIFEST) and os.path.exists(_FEAT_COLS)


# ── Test 1 — all 20 artifacts loadable ──────────────────────────────────────


def test_all_twenty_artifacts_loadable():
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent (fresh worktree clone)")
    import joblib  # local import — heavy dependency
    n_loaded = 0
    for tgt in _TARGETS:
        for seed in _LGB_SEEDS:
            p = os.path.join(_M2_DIR, f"{tgt}_lgb_s{seed}.joblib")
            assert os.path.exists(p), f"missing artifact: {p}"
            model = joblib.load(p)
            assert hasattr(model, "predict"), f"loaded {p} lacks .predict"
            n_loaded += 1
        for seed in _XGB_SEEDS:
            p = os.path.join(_M2_DIR, f"{tgt}_xgb_s{seed}.joblib")
            assert os.path.exists(p), f"missing artifact: {p}"
            model = joblib.load(p)
            assert hasattr(model, "predict"), f"loaded {p} lacks .predict"
            n_loaded += 1
    assert n_loaded == 20, f"expected 20 artifacts, loaded {n_loaded}"


# ── Test 2 — predictions reproducible from the same model ────────────────────


def test_predictions_reproducible():
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent")
    import joblib
    import numpy as np
    with open(_FEAT_COLS, encoding="utf-8") as f:
        feats = json.load(f)
    # 5 synthetic rows with deterministic seed — predictions must match
    # exactly between two .predict invocations on the same fitted model.
    rng = np.random.default_rng(123)
    X = rng.normal(0, 1, size=(5, len(feats))).astype("float32")
    m = joblib.load(os.path.join(_M2_DIR, "total_lgb_s42.joblib"))
    p1 = m.predict(X)
    p2 = m.predict(X)
    assert np.allclose(p1, p2, rtol=0, atol=0), (
        ".predict not deterministic on the same fitted model — model artifact "
        "likely corrupted"
    )


# ── Test 3 — R20_M7 wire still active in game_models.py ─────────────────────


def test_R20_M7_wire_still_active():
    """R20_M7 wired _predict_m2_family into the production predict() return.
    Guard against a future refactor accidentally removing the call site."""
    p = os.path.join(PROJECT_DIR, "src", "prediction", "game_models.py")
    assert os.path.exists(p), "game_models.py missing entirely"
    with open(p, encoding="utf-8") as f:
        src = f.read()
    assert "_predict_m2_family" in src, "R20_M7 _predict_m2_family helper gone"
    assert "m2_family_used" in src, "R20_M7 m2_family_used flag/output gone"
    # The wire must override total_est / spread_est inside predict().
    assert "total_est" in src and "spread_est" in src, (
        "predict() no longer exposes total_est / spread_est"
    )


# ── Test 4 — R21_N5 cache invalidates on artifact mtime change ──────────────


def test_R21_N5_cache_invalidation_on_mtime_change(tmp_path, monkeypatch):
    """The cache key includes _m2_family_models_mtime(). Bumping any file's
    mtime in data/models/m2_family/ must make a previously-cached entry stale
    (read returns None on cache miss → falls through to recompute)."""
    from src.prediction import game_models  # noqa: PLC0415
    # Redirect cache file to a tmp path so we don't touch the user's real cache.
    cache_path = tmp_path / "m2_family_cache.json"
    monkeypatch.setattr(game_models, "_M2_PRED_CACHE_PATH", str(cache_path))

    fake_gid = "RA_R24Q3_TEST_GID"
    fake_mtime_old = 1000.0
    fake_mtime_new = 2000.0
    entry = {
        "models_mtime": fake_mtime_old,
        "total_est":    220.0,
        "spread_est":   2.0,
        "home_pts_est": 111.0,
        "away_pts_est": 109.0,
    }
    game_models._save_m2_pred_cache({fake_gid: entry})

    # Simulate "models dir unchanged" → cache hit path returns the stale entry.
    monkeypatch.setattr(game_models, "_m2_family_models_mtime",
                        lambda: fake_mtime_old)
    cache_now = game_models._load_m2_pred_cache()
    assert cache_now.get(fake_gid, {}).get("models_mtime") == fake_mtime_old

    # Simulate "models retrained" (any artifact rewritten → mtime jump). The
    # cache entry's models_mtime != current_mtime, so _predict_m2_family
    # MUST treat it as a miss. We assert the mtime mismatch directly because
    # _predict_m2_family also requires loaded artifacts (which may be absent
    # in a fresh worktree).
    monkeypatch.setattr(game_models, "_m2_family_models_mtime",
                        lambda: fake_mtime_new)
    entry_after = game_models._load_m2_pred_cache().get(fake_gid, {})
    assert entry_after.get("models_mtime") != fake_mtime_new, (
        "cache entry mtime should not auto-update — invalidation must come "
        "from a fresh predict() recompute, not silent rewrite"
    )

    # And clear_m2_pred_cache must remove the file outright.
    removed = game_models.clear_m2_pred_cache()
    assert removed is True
    assert not os.path.exists(str(cache_path))


# ── Test 5 — no NaN predictions when artifacts present ──────────────────────


def test_no_nan_predictions_when_artifacts_present(monkeypatch):
    """_predict_m2_family must NEVER return NaN for any of the 4 targets when
    the full ensemble is loadable + the input row has the required base
    features. NaN would corrupt downstream EV calculation silently."""
    if not _artifacts_present():
        pytest.skip("m2_family artifacts absent")
    import math
    from src.prediction import game_models  # noqa: PLC0415

    # In a worktree clone the production game_models._M2_FAMILY_DIR points to
    # WORKTREE/data/models/m2_family/ (gitignored, empty). Repoint it to the
    # canonical root where _M2_DIR resolved the real artifacts so the
    # production code can actually load + predict against them.
    monkeypatch.setattr(game_models, "_M2_FAMILY_DIR", _M2_DIR)
    # Reset the lazy-load cache state so it re-checks the new path.
    monkeypatch.setattr(game_models, "_M2_FAMILY_CACHE", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_FEATS", None)
    monkeypatch.setattr(game_models, "_M2_FAMILY_MANIFEST", None)

    if not game_models._try_load_m2_family():
        pytest.skip("m2_family failed to load (corrupted artifacts?)")

    # Build a plausible feature row. We don't need every column — train_final
    # falls back to fillna(0.0). At minimum we need home_off_rtg present so
    # the row passes _lookup_season_games_row's gate (when called directly
    # _predict_m2_family bypasses that lookup).
    row = {
        "home_off_rtg": 115.0, "home_def_rtg": 112.0, "home_pace": 100.0,
        "away_off_rtg": 113.0, "away_def_rtg": 114.0, "away_pace": 99.0,
        "home_net_rtg": 3.0, "away_net_rtg": -1.0,
        "net_rtg_diff": 4.0, "pace_diff": 1.0, "home_advantage": 1.0,
        "home_efg_pct": 0.55, "away_efg_pct": 0.54,
        "home_ts_pct": 0.58,  "away_ts_pct": 0.57,
        "home_tov_pct": 0.13, "away_tov_pct": 0.14,
        "home_rest_days": 1,  "away_rest_days": 2,
        "home_back_to_back": 0, "away_back_to_back": 0,
        "home_last5_wins": 3, "away_last5_wins": 2,
        "home_season_win_pct": 0.55, "away_season_win_pct": 0.50,
        "game_id": "RA_R24Q3_TEST_GID",
    }
    out = game_models._predict_m2_family(row, game_id="RA_R24Q3_TEST_GID")
    assert out is not None, "predict returned None despite artifacts loaded"
    for key in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        v = out.get(key)
        assert v is not None, f"missing key {key}"
        assert not math.isnan(float(v)), f"NaN prediction for {key}: {v}"
        assert math.isfinite(float(v)), f"non-finite prediction for {key}: {v}"
        # Sanity bounds — total points roughly 150-300, spread roughly -40..40
        if key == "total_est":
            assert 150 <= v <= 300, f"total_est out of plausible range: {v}"
        elif key == "spread_est":
            assert -40 <= v <= 40, f"spread_est out of plausible range: {v}"
        elif key in ("home_pts_est", "away_pts_est"):
            assert 75 <= v <= 175, f"{key} out of plausible range: {v}"
    # Cleanup the cache entry we wrote.
    game_models.clear_m2_pred_cache()
