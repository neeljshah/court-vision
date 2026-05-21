"""
test_prop_lightgbm.py — Tests for LightGBM prop trainer and base-learner registry.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.prediction.player_props as player_props


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_synthetic_frames(rng: np.random.Generator) -> tuple:
    """Build synthetic (train_df, test_df) covering all _ALL_FEATS columns."""
    n_train = 220
    n_test  = 70
    n_total = n_train + n_test

    # Use one reference feature for correlated labels
    pts_roll_vals = rng.normal(15.0, 4.0, n_total)

    data: dict = {}
    for feat in player_props._ALL_FEATS:
        data[feat] = rng.normal(0.5, 0.2, n_total)

    # Override pts_roll with our reference feature so labels can correlate
    data["pts_roll"] = pts_roll_vals

    # Correlated labels (loose — r2 finite but low is fine; exact value not asserted)
    noise_scale = 3.0
    data["season_pts"]  = 0.7 * pts_roll_vals + rng.normal(0, noise_scale, n_total)
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
    return train_df, test_df


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_lightgbm_importable() -> None:
    """train_props_lightgbm and _build_prop_training_frame are importable."""
    from src.prediction.player_props import train_props_lightgbm, _build_prop_training_frame  # noqa: F401


def test_base_learner_registry() -> None:
    """BASE_LEARNERS contains both xgboost and lightgbm entries."""
    from src.prediction.prop_model_stack import (
        BASE_LEARNERS,
        predict_base_learner,
        base_learner_available,
    )
    assert "lightgbm" in BASE_LEARNERS
    assert "xgboost" in BASE_LEARNERS
    # Verify helpers are callable
    assert callable(predict_base_learner)
    assert callable(base_learner_available)


def test_train_lightgbm_synthetic(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """train_props_lightgbm produces correct outputs on synthetic data."""
    rng = np.random.default_rng(99)
    synthetic_train, synthetic_test = _make_synthetic_frames(rng)

    # Monkeypatch the data-prep helper so no NBA API calls are made
    monkeypatch.setattr(
        player_props,
        "_build_prop_training_frame",
        lambda *args, **kwargs: (
            synthetic_train,
            synthetic_test,
            list(player_props._ALL_FEATS),
        ),
    )
    # Redirect model output to tmp_path
    monkeypatch.setattr(player_props, "_MODEL_DIR", str(tmp_path))

    result = player_props.train_props_lightgbm(force=True)

    # Result must contain all 7 stats
    for stat in player_props._PROP_STATS:
        assert stat in result, f"Missing stat in result: {stat}"
        assert isinstance(result[stat]["mae"], float), f"{stat} mae not float"
        assert isinstance(result[stat]["r2"], float),  f"{stat} r2 not float"

    # All 7 pkl files must exist
    for stat in player_props._PROP_STATS:
        pkl_path = tmp_path / f"props_lgb_{stat}.pkl"
        assert pkl_path.exists(), f"Missing model file: {pkl_path}"

    # Metrics JSON must exist
    metrics_path = tmp_path / "props_lgb_metrics.json"
    assert metrics_path.exists(), "props_lgb_metrics.json not written"

    import json
    with open(metrics_path) as f:
        metrics = json.load(f)
    assert metrics["model"] == "lightgbm"
    assert "trained_at" in metrics
    assert "stats" in metrics
