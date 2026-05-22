"""
test_prune_prop_features.py -- Tests for the feature-importance audit (PRED-11).

The audit runs model_explainer over every trained prop model and reports
low-importance features — the ones safe to prune at the next retrain.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from prune_prop_features import analyse_prop_features, cross_stat_prune_list  # noqa: E402


# ── cross_stat_prune_list ─────────────────────────────────────────────────────

def test_cross_stat_prune_is_intersection():
    """Only features low-importance for EVERY stat are returned."""
    per_stat = {
        "pts": {"prune_candidates": ["noise_a", "noise_b", "noise_c"]},
        "reb": {"prune_candidates": ["noise_b", "noise_c", "useful_x"]},
        "ast": {"prune_candidates": ["noise_c", "noise_b"]},
    }
    assert cross_stat_prune_list(per_stat) == ["noise_b", "noise_c"]


def test_cross_stat_ignores_untrained_stats():
    """Stats with no report (prune_candidates=None) don't void the intersection."""
    per_stat = {
        "pts": {"prune_candidates": ["noise_a", "noise_b"]},
        "reb": {"prune_candidates": ["noise_b"]},
        "ast": {"status": "not_trained", "prune_candidates": None},
    }
    assert cross_stat_prune_list(per_stat) == ["noise_b"]


def test_cross_stat_empty_when_no_models():
    """No trained models -> empty prune list, not an error."""
    assert cross_stat_prune_list({"pts": {"prune_candidates": None}}) == []


# ── analyse_prop_features ─────────────────────────────────────────────────────

def test_analyse_handles_missing_models(tmp_path):
    """With no model files, every stat is reported 'not_trained' — no crash."""
    out = tmp_path / "prop_feature_importance.json"
    result = analyse_prop_features(
        model_dir=str(tmp_path), output_path=str(out),
    )
    assert result["n_trained_models"] == 0
    assert out.exists()
    assert all(r["status"] == "not_trained" for r in result["per_stat"].values())


def test_analyse_uses_injected_explain_fn(tmp_path, monkeypatch):
    """A trained model is analysed via the injected importance function."""
    import xgboost as xgb
    import numpy as np
    from src.prediction.player_props import _ALL_FEATS, _PROP_STATS

    # Train a tiny real XGBoost model and save it as props_pts.json so the
    # audit finds and loads it.
    n_feat = len([c for c in _ALL_FEATS if c != "season_pts"])
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, n_feat))
    y = X[:, 0] * 2.0 + rng.normal(size=60)
    m = xgb.XGBRegressor(n_estimators=10, max_depth=2)
    m.fit(X, y)
    m.save_model(str(tmp_path / "props_pts.json"))

    captured = {}

    def fake_explain(model, X, feature_names, model_name):
        captured["model_name"] = model_name
        captured["n_features"] = len(feature_names)
        return {"method": "tree_importances",
                "prune_candidates": list(feature_names[:3])}

    out = tmp_path / "report.json"
    result = analyse_prop_features(
        model_dir=str(tmp_path), output_path=str(out), explain_fn=fake_explain,
    )
    assert captured["model_name"] == "props_pts"
    assert captured["n_features"] == n_feat
    assert result["per_stat"]["pts"]["status"] == "analysed"
    assert result["per_stat"]["pts"]["n_low_importance"] == 3
    saved = json.loads(out.read_text())
    assert saved["n_trained_models"] == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
