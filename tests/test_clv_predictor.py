"""
test_clv_predictor.py -- Tests for the XGBoost CLV predictor (16.5-02).

Acceptance criterion: clv_predictor trains on clv_training_data.csv, achieves
>=60% accuracy on a held-out split, and serialises the model to a pkl.
"""

from __future__ import annotations

import csv
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import clv_predictor  # noqa: E402
from src.prediction.clv_predictor import (  # noqa: E402
    FEATURE_COLUMNS,
    load_model,
    predict_clv,
    predict_clv_prob,
    train,
)


def _write_learnable_csv(path: str, n: int = 320, seed: int = 7) -> None:
    """Write a synthetic CLV CSV with a learnable signal.

    clv_label is driven by our_edge + pinnacle_delta plus modest noise, so a
    competent classifier should comfortably beat the 60% accuracy bar.
    """
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        edge = rng.uniform(-0.08, 0.10)
        pin = rng.uniform(-1.0, 1.0)
        public = rng.uniform(0.2, 0.8)
        ttg = rng.uniform(0.5, 24.0)
        fresh = rng.uniform(0.0, 120.0)
        mv2h = rng.uniform(-1.5, 1.5)
        score = edge * 30 + pin + rng.gauss(0, 0.4)
        label = 1 if score > 0 else 0
        rows.append({
            "bet_id": f"s{i}",
            "our_edge": round(edge, 4),
            "pinnacle_delta": round(pin, 4),
            "public_pct": round(public, 4),
            "time_to_game": round(ttg, 4),
            "lineup_freshness": round(fresh, 4),
            "line_movement_last_2h": round(mv2h, 4),
            "clv_label": label,
        })
    cols = ["bet_id"] + FEATURE_COLUMNS + ["clv_label"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with no cached model bundle."""
    clv_predictor.clear_cache()
    yield
    clv_predictor.clear_cache()


def test_train_achieves_60pct_accuracy(tmp_path):
    """Trained model clears the >=60% held-out accuracy acceptance bar."""
    csv_path = str(tmp_path / "clv_training_data.csv")
    model_path = str(tmp_path / "clv_predictor.pkl")
    _write_learnable_csv(csv_path)

    metrics = train(csv_path, model_path)
    assert metrics["accuracy"] >= 0.60, f"accuracy {metrics['accuracy']} below 0.60"
    assert metrics["n_test"] > 0


def test_model_serialized_to_pkl(tmp_path):
    """train() writes a loadable pkl bundle with model + feature columns."""
    csv_path = str(tmp_path / "clv_training_data.csv")
    model_path = str(tmp_path / "clv_predictor.pkl")
    _write_learnable_csv(csv_path)

    train(csv_path, model_path)
    assert os.path.exists(model_path)

    clv_predictor.clear_cache()
    bundle = load_model(model_path)
    assert "model" in bundle
    assert bundle["feature_columns"] == FEATURE_COLUMNS


def test_predict_clv_returns_valid_probability(tmp_path):
    """predict_clv yields a probability in [0,1] and a consistent label."""
    csv_path = str(tmp_path / "clv_training_data.csv")
    model_path = str(tmp_path / "clv_predictor.pkl")
    _write_learnable_csv(csv_path)
    train(csv_path, model_path)

    result = predict_clv(
        {"our_edge": 0.08, "pinnacle_delta": 0.7, "public_pct": 0.4,
         "time_to_game": 3.0, "lineup_freshness": 10.0,
         "line_movement_last_2h": 0.5},
        model_path,
    )
    assert 0.0 <= result["clv_prob"] <= 1.0
    assert result["clv_label"] in (0, 1)
    assert result["clv_label"] == int(result["clv_prob"] >= 0.5)


def test_predict_handles_missing_features(tmp_path):
    """A sparse feature dict still produces a valid probability."""
    csv_path = str(tmp_path / "clv_training_data.csv")
    model_path = str(tmp_path / "clv_predictor.pkl")
    _write_learnable_csv(csv_path)
    train(csv_path, model_path)

    prob = predict_clv_prob({"our_edge": 0.05}, model_path)
    assert 0.0 <= prob <= 1.0


def test_train_raises_on_insufficient_rows(tmp_path):
    """A near-empty CSV raises a clear error instead of fitting noise."""
    csv_path = str(tmp_path / "clv_training_data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bet_id"] + FEATURE_COLUMNS + ["clv_label"])
        w.writeheader()
        w.writerow({"bet_id": "x", "our_edge": 0.0, "pinnacle_delta": 0.0,
                    "public_pct": 0.5, "time_to_game": 1.0,
                    "lineup_freshness": 0.0, "line_movement_last_2h": 0.0,
                    "clv_label": 1})
    with pytest.raises(ValueError, match="rows"):
        train(csv_path, str(tmp_path / "m.pkl"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
