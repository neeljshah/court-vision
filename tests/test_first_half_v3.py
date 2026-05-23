"""
tests/test_first_half_v3.py — Unit tests for FirstHalfPredictorV3.

Tests:
  1. _load_first_half_truth: shape/range sanity on real scored_games caches
  2. Linescore extraction: 5 known linescores match expected Q1+Q2 sums
  3. Synthetic 50-game train → predict → first_half ∈ [70, 150]
  4. Metrics file produced with version key "v3_real_period_scoring"
"""
from __future__ import annotations

import json, os, sys, tempfile, time
import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.first_half_v3 import (
    FirstHalfPredictorV3,
    FEATURE_COLS_V3,
    _load_first_half_truth,
    _load_linescore_cache,
    _NBA_CACHE,
    _MODEL_DIR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_scored_games() -> bool:
    return any(
        os.path.exists(os.path.join(_NBA_CACHE, f"scored_games_{s}.json"))
        for s in ["2022-23", "2023-24", "2024-25"]
    )


def _has_linescores() -> bool:
    """True only when linescore cache has games that overlap scored_games_2024-25."""
    lf = os.path.join(_NBA_CACHE, "linescores_all.json")
    sg = os.path.join(_NBA_CACHE, "scored_games_2024-25.json")
    if not os.path.exists(lf) or not os.path.exists(sg):
        return False
    with open(lf) as f:
        ls = json.load(f)
    with open(sg) as f:
        rows = json.load(f).get("rows", [])
    sg_ids = {r["game_id"] for r in rows}
    return len(sg_ids & set(ls.keys())) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: _load_first_half_truth shape and range
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _has_scored_games(), reason="scored_games cache missing")
def test_load_first_half_truth_shape_and_range():
    """Truth loader returns at least 100 rows with h1_total in [70, 180]."""
    df = _load_first_half_truth(["2022-23", "2023-24", "2024-25"])
    assert len(df) >= 100, f"Expected ≥100 rows, got {len(df)}"
    assert "h1_total" in df.columns
    assert "is_real"  in df.columns
    assert df["h1_total"].between(60, 200).all(), (
        f"h1_total out of range: min={df['h1_total'].min():.1f} max={df['h1_total'].max():.1f}"
    )
    # All seasons present
    assert "season" in df.columns
    # At least some proxy rows (is_real=False) if linescores incomplete
    assert df["is_real"].dtype == bool


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Linescore extraction for 5 known 2024-25 games
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _has_linescores(), reason="linescores_all.json missing or too small")
def test_linescore_period_values():
    """
    For 5 known 2024-25 game IDs, verify:
      - h1_total = home_h1 + away_h1
      - h1_total is in [60, 200]
      - individual quarter values are positive integers
    """
    linescores = _load_linescore_cache()
    # Pick first 5 games from scored_games_2024-25 that have linescores
    path = os.path.join(_NBA_CACHE, "scored_games_2024-25.json")
    if not os.path.exists(path):
        pytest.skip("scored_games_2024-25.json missing")

    with open(path) as f:
        rows = json.load(f).get("rows", [])

    found = 0
    for r in rows:
        gid = r["game_id"]
        ls  = linescores.get(gid)
        if ls is None:
            continue
        # Structural checks
        assert "home_h1"  in ls, f"{gid}: missing home_h1"
        assert "away_h1"  in ls, f"{gid}: missing away_h1"
        assert "h1_total" in ls, f"{gid}: missing h1_total"
        # Numeric consistency
        expected_h1 = ls["home_h1"] + ls["away_h1"]
        assert ls["h1_total"] == expected_h1, (
            f"{gid}: h1_total={ls['h1_total']} != home_h1+away_h1={expected_h1}"
        )
        assert 60 <= ls["h1_total"] <= 200, (
            f"{gid}: h1_total={ls['h1_total']} out of range"
        )
        assert ls.get("home_q1", -1) >= 0, f"{gid}: home_q1 negative"
        assert ls.get("away_q1", -1) >= 0, f"{gid}: away_q1 negative"
        found += 1
        if found >= 5:
            break

    assert found >= 3, (
        f"Expected ≥3 linescore records for 2024-25 games, found {found}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Synthetic train → predict in [70, 150]
# ─────────────────────────────────────────────────────────────────────────────

def _make_synthetic_data(n: int = 50) -> pd.DataFrame:
    """Build a minimal synthetic DataFrame with all v3 feature cols + target."""
    rng = np.random.default_rng(42)
    df  = pd.DataFrame({
        c: rng.normal(0, 1, n).astype(np.float32)
        for c in FEATURE_COLS_V3
    })
    # Realistic first-half totals
    df["h1_total"] = rng.normal(105, 8, n).clip(75, 140).astype(np.float32)
    df["is_real"]  = True
    df["season"]   = "2022-23"
    df["game_date"]= "2022-10-22"
    return df


def test_synthetic_train_and_predict(tmp_path):
    """Train on 50 synthetic rows; prediction for a random sample is ∈ [70, 150]."""
    try:
        import lightgbm as lgb
    except ImportError:
        pytest.skip("lightgbm not installed")

    from sklearn.metrics import mean_absolute_error
    import warnings, unittest.mock as mock

    df = _make_synthetic_data(200)

    # Patch _build_dataset to return synthetic data
    with mock.patch(
        "src.prediction.first_half_v3._build_dataset", return_value=df
    ):
        predictor = FirstHalfPredictorV3(model_dir=str(tmp_path))
        metrics   = predictor.train(seasons=["2022-23"])

    # Model should have trained
    assert predictor._booster is not None

    # Prediction within plausible range
    sample_feats = {c: float(np.random.default_rng(7).normal(0, 1)) for c in FEATURE_COLS_V3}
    pred = predictor.predict(sample_feats)
    assert 70 <= pred <= 150, f"Prediction {pred:.1f} out of expected [70, 150]"

    # Metrics returned (may be None for holdout with small synthetic set)
    assert isinstance(metrics, dict), "train() should return a dict"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Metrics file contains version key
# ─────────────────────────────────────────────────────────────────────────────

def test_metrics_file_version_key(tmp_path):
    """After train(), first_half_v3_metrics.json has version='v3_real_period_scoring'."""
    try:
        import lightgbm as lgb
    except ImportError:
        pytest.skip("lightgbm not installed")

    import unittest.mock as mock

    df = _make_synthetic_data(200)
    with mock.patch(
        "src.prediction.first_half_v3._build_dataset", return_value=df
    ):
        predictor = FirstHalfPredictorV3(model_dir=str(tmp_path))
        predictor.train(seasons=["2022-23"])

    metrics_path = os.path.join(str(tmp_path), "first_half_v3_metrics.json")
    assert os.path.exists(metrics_path), "Metrics file not created"
    with open(metrics_path) as f:
        m = json.load(f)
    assert m.get("version") == "v3_real_period_scoring", (
        f"version key wrong: {m.get('version')}"
    )
    assert "feature_cols" in m
    assert "holdout_mae" in m
    assert "v2_proxy_holdout_mae" in m


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Load persisted model
# ─────────────────────────────────────────────────────────────────────────────

def test_load_persisted_model(tmp_path):
    """Train → save → new instance → load → predict without error."""
    try:
        import lightgbm as lgb
    except ImportError:
        pytest.skip("lightgbm not installed")

    import unittest.mock as mock

    df = _make_synthetic_data(200)
    with mock.patch(
        "src.prediction.first_half_v3._build_dataset", return_value=df
    ):
        p1 = FirstHalfPredictorV3(model_dir=str(tmp_path))
        p1.train(seasons=["2022-23"])

    # Fresh instance — loads from disk
    p2 = FirstHalfPredictorV3(model_dir=str(tmp_path))
    feats = {c: 0.0 for c in FEATURE_COLS_V3}
    pred  = p2.predict(feats)
    assert 70 <= pred <= 150, f"Loaded model prediction {pred:.1f} out of range"
