"""
test_prop_stacker.py — Tests for the linear meta-learner (prop_stacker.py).

Coverage
--------
1. Module is importable without CatBoost.
2. fit_stacker() on synthetic data: produces a StackerResult, persists .pkl file.
3. R² gain >= 0.01 on a signal-rich synthetic dataset.
4. load_stacker() / predict_ensemble() round-trip.
5. CatBoost graceful degradation: stacker works with only XGB + LGB.
6. train_stacker_all() integration: all 7 stats trained, metrics JSON written.
7. _apply_stacker() in run_daily_slate is non-fatal when no models present.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _synthetic_data(
    n_train: int = 300,
    n_holdout: int = 100,
    n_feats: int = 10,
    rng_seed: int = 0,
) -> tuple:
    """Return (X_train, y_train, X_holdout, y_holdout) with a learnable signal."""
    rng = np.random.default_rng(rng_seed)
    X_train   = rng.normal(0, 1, (n_train,   n_feats))
    X_holdout = rng.normal(0, 1, (n_holdout, n_feats))
    w = rng.normal(0, 1, n_feats)
    y_train   = X_train   @ w + rng.normal(0, 0.5, n_train)
    y_holdout = X_holdout @ w + rng.normal(0, 0.5, n_holdout)
    return X_train, y_train, X_holdout, y_holdout


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_prop_stacker_importable() -> None:
    """prop_stacker imports cleanly."""
    from src.prediction.prop_stacker import (  # noqa: F401
        fit_stacker,
        load_stacker,
        predict_ensemble,
        train_stacker_all,
        STATS,
        StackerResult,
    )
    assert len(STATS) == 7


def test_fit_stacker_returns_result(tmp_path: Path) -> None:
    """fit_stacker() returns a StackerResult with sensible fields."""
    from src.prediction.prop_stacker import fit_stacker

    X_train, y_train, X_hold, y_hold = _synthetic_data()
    result = fit_stacker(X_train, y_train, X_hold, y_hold, "pts", str(tmp_path))

    assert result.stat == "pts"
    assert isinstance(result.meta_r2, float)
    assert isinstance(result.best_base_r2, float)
    assert isinstance(result.r2_gain, float)
    assert len(result.learners_used) >= 2   # at minimum XGB + LGB
    assert result.n_train == len(X_train)
    assert result.n_holdout == len(X_hold)

    # Saved model file must exist
    model_path = tmp_path / "props_stacker_pts.pkl"
    assert model_path.exists(), "Stacker model .pkl not written"


def test_fit_stacker_r2_gain_on_signal_data(tmp_path: Path) -> None:
    """Ensemble R² beats best single base learner by >= 0.01 on signal-rich data."""
    from src.prediction.prop_stacker import fit_stacker

    # Use a larger dataset so all learners have enough data for reliable R²
    X_train, y_train, X_hold, y_hold = _synthetic_data(
        n_train=400, n_holdout=100, n_feats=15, rng_seed=77
    )
    result = fit_stacker(X_train, y_train, X_hold, y_hold, "pts", str(tmp_path))

    # R² gain of at least 0.01 on structured data
    assert result.r2_gain >= 0.01, (
        f"Expected R² gain >= 0.01, got {result.r2_gain:.4f}. "
        f"meta_r2={result.meta_r2:.4f} best_base={result.best_base_r2:.4f}"
    )


def test_load_stacker_round_trip(tmp_path: Path) -> None:
    """load_stacker() retrieves the meta model fitted by fit_stacker()."""
    from src.prediction.prop_stacker import fit_stacker, load_stacker

    X_train, y_train, X_hold, y_hold = _synthetic_data(rng_seed=3)
    fit_stacker(X_train, y_train, X_hold, y_hold, "reb", str(tmp_path))

    bundle = load_stacker("reb", str(tmp_path))
    assert bundle is not None
    assert "meta" in bundle
    assert "learners" in bundle
    assert len(bundle["learners"]) >= 2


def test_load_stacker_returns_none_when_missing(tmp_path: Path) -> None:
    """load_stacker() returns None when no model file exists."""
    from src.prediction.prop_stacker import load_stacker

    result = load_stacker("ast", str(tmp_path))
    assert result is None


def test_predict_ensemble_fallback_no_stacker(tmp_path: Path, monkeypatch) -> None:
    """predict_ensemble() returns an array without crashing when stacker is absent."""
    from src.prediction.prop_stacker import predict_ensemble
    import src.prediction.prop_stacker as stacker_mod

    monkeypatch.setattr(stacker_mod, "_MODELS_DIR", str(tmp_path))

    # Monkeypatch predict_base_learner to return a constant so no real model is needed
    import src.prediction.prop_model_stack as stack_mod
    monkeypatch.setattr(stack_mod, "predict_base_learner",
                        lambda name, stat, X: 12.5)

    X = np.zeros((3, 5))
    out = predict_ensemble(X, "pts", str(tmp_path))
    assert isinstance(out, np.ndarray)
    assert len(out) == 3


def test_catboost_graceful_degradation(tmp_path: Path, monkeypatch) -> None:
    """Stacker works with only XGB + LGB when CatBoost is unavailable."""
    import src.prediction.prop_stacker as stacker_mod

    # Pretend CatBoost is not installed
    monkeypatch.setattr(stacker_mod, "_CATBOOST_AVAILABLE", False)

    from src.prediction.prop_stacker import fit_stacker

    X_train, y_train, X_hold, y_hold = _synthetic_data(rng_seed=7)
    result = fit_stacker(X_train, y_train, X_hold, y_hold, "ast", str(tmp_path))

    assert "catboost" not in result.learners_used
    assert "xgboost" in result.learners_used
    assert "lightgbm" in result.learners_used
    assert result.meta_r2 is not None


def test_train_stacker_all_synthetic(monkeypatch, tmp_path: Path) -> None:
    """train_stacker_all() trains all 7 stats and writes metrics JSON."""
    import src.prediction.player_props as pp_mod
    import src.prediction.prop_stacker as stacker_mod

    rng = np.random.default_rng(42)
    import pandas as pd

    n_train, n_test = 220, 70
    n_total = n_train + n_test
    pts_roll = rng.normal(15.0, 4.0, n_total)

    data: dict = {}
    for feat in pp_mod._ALL_FEATS:
        data[feat] = rng.normal(0.5, 0.2, n_total)
    data["pts_roll"] = pts_roll
    data["season_pts"]  = 0.7 * pts_roll + rng.normal(0, 3.0, n_total)
    data["season_reb"]  = rng.normal(5.0, 1.5, n_total)
    data["season_ast"]  = rng.normal(4.0, 1.5, n_total)
    data["season_fg3m"] = rng.normal(1.5, 0.5, n_total).clip(0)
    data["season_stl"]  = rng.normal(1.0, 0.3, n_total).clip(0)
    data["season_blk"]  = rng.normal(0.6, 0.3, n_total).clip(0)
    data["season_tov"]  = rng.normal(2.0, 0.5, n_total).clip(0)
    data["data_confidence"] = rng.uniform(0.5, 1.0, n_total)

    df = pd.DataFrame(data)
    train_df = df.iloc[:n_train].reset_index(drop=True)
    test_df  = df.iloc[n_train:].reset_index(drop=True)

    monkeypatch.setattr(
        pp_mod, "_build_prop_training_frame",
        lambda *a, **kw: (train_df, test_df, list(pp_mod._ALL_FEATS)),
    )
    monkeypatch.setattr(stacker_mod, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(stacker_mod, "_STACKER_METRICS",
                        str(tmp_path / "prop_stacker_metrics.json"))

    results = stacker_mod.train_stacker_all(force=True, models_dir=str(tmp_path))

    assert len(results) == 7, f"Expected 7 stat results, got {len(results)}"
    for stat in stacker_mod.STATS:
        assert stat in results, f"Missing stat {stat}"
        pkl = tmp_path / f"props_stacker_{stat}.pkl"
        assert pkl.exists(), f"Missing model file for {stat}"

    metrics_path = tmp_path / "prop_stacker_metrics.json"
    assert metrics_path.exists(), "Metrics JSON not written"
    with open(metrics_path) as f:
        metrics = json.load(f)
    assert metrics["model"] == "linear_stacker"
    assert "stats" in metrics


def test_apply_stacker_nonfatal_no_models(monkeypatch) -> None:
    """_apply_stacker() in run_daily_slate returns preds unchanged when no models."""
    import scripts.run_daily_slate as slate

    preds = [
        {"player": "Test Player", "pts": 20.0, "reb": 5.0, "ast": 3.0,
         "fg3m": 1.0, "stl": 1.0, "blk": 0.5, "tov": 2.0,
         "proj_pts": 20.0, "proj_min": 30.0, "dnp_prob": 0.05,
         "team": "LAL", "opp_team": "BOS", "game_id": "001",
         "player_id": 1234, "confidence": "medium"},
    ]

    # Monkeypatch load_stacker to always return None so no model files are needed
    import src.prediction.prop_stacker as stacker_mod
    monkeypatch.setattr(stacker_mod, "load_stacker", lambda *a, **kw: None)

    result = slate._apply_stacker(preds)
    assert result is not None
    assert len(result) == 1
    # Original projection should be unchanged
    assert result[0]["pts"] == 20.0
