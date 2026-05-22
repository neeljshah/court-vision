"""
clv_predictor.py — XGBoost Closing-Line-Value predictor (task 16.5-02).

Converts CLV from a retrospective metric into a pre-tip signal: given a
proposed bet's features, predict the probability the closing line will move
in our favour.  Used by bet_selector (16.5-03) as a dual edge+CLV gate.

Trains on data/output/clv_training_data.csv (built by clv_tracker.build_clv_training_data)
and serialises the fitted model to data/models/clv_predictor.pkl.

Public API
----------
    train(csv_path, model_path)  -> dict   (metrics: accuracy, n_train, n_test, ...)
    load_model(model_path)       -> dict   (bundle: model, feature_columns, metrics)
    predict_clv(features)        -> dict   ({clv_prob, clv_label, expected_clv})
    predict_clv_prob(features)   -> float  (P(closing line moves favourably))
"""

from __future__ import annotations

import logging
import os
import pickle
import sys
from typing import Dict, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_TRAINING_CSV = os.path.join(_OUTPUT_DIR, "clv_training_data.csv")
_MODEL_PATH   = os.path.join(_MODEL_DIR, "clv_predictor.pkl")

# Feature columns consumed by the model — must match clv_training_data.csv
# (bet_id is a dedup key, clv_label is the target; neither is a feature).
FEATURE_COLUMNS = [
    "our_edge",
    "pinnacle_delta",
    "public_pct",
    "time_to_game",
    "lineup_freshness",
    "line_movement_last_2h",
]
_TARGET = "clv_label"

# Minimum labelled rows required before training is meaningful.
_MIN_ROWS = 20

log = logging.getLogger(__name__)

# Process-level cache so bet_selector does not re-read the pkl per bet.
_CACHED_BUNDLE: Optional[dict] = None


# ── training ──────────────────────────────────────────────────────────────────

def train(
    csv_path: Optional[str] = None,
    model_path: Optional[str] = None,
    *,
    test_size: float = 0.25,
    seed: int = 42,
) -> dict:
    """Train the XGBoost CLV classifier and serialise it to disk.

    Args:
        csv_path:   Training CSV (default: data/output/clv_training_data.csv).
        model_path: Destination pkl (default: data/models/clv_predictor.pkl).
        test_size:  Held-out fraction for the accuracy estimate.
        seed:       RNG seed for the split and the model.

    Returns:
        Metrics dict: {n_rows, n_train, n_test, accuracy, base_rate,
                       mean_positive_clv_proxy}.

    Raises:
        ValueError: if the CSV has fewer than _MIN_ROWS labelled rows or only
                    one class is present (cannot fit a classifier).
    """
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    csv_path = csv_path or _TRAINING_CSV
    model_path = model_path or _MODEL_PATH

    if not os.path.exists(csv_path):
        raise ValueError(f"CLV training CSV not found: {csv_path} — run clv_tracker --build-training first")

    df = pd.read_csv(csv_path)
    if len(df) < _MIN_ROWS:
        raise ValueError(
            f"CLV training set has {len(df)} rows (< {_MIN_ROWS}); "
            f"accumulate more settled bets before training."
        )

    missing = [c for c in FEATURE_COLUMNS + [_TARGET] if c not in df.columns]
    if missing:
        raise ValueError(f"CLV training CSV missing columns: {missing}")

    df = df.dropna(subset=FEATURE_COLUMNS + [_TARGET])
    X = df[FEATURE_COLUMNS].astype(float)
    y = df[_TARGET].astype(int)

    if y.nunique() < 2:
        raise ValueError("CLV training set has only one class — cannot fit a classifier.")

    stratify = y if y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=stratify
    )

    model = XGBClassifier(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=seed,
    )
    model.fit(X_train, y_train)

    accuracy = float((model.predict(X_test) == y_test).mean())
    base_rate = float(y.mean())

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": {
            "n_rows": int(len(df)),
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "accuracy": round(accuracy, 4),
            "base_rate": round(base_rate, 4),
        },
    }

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)

    global _CACHED_BUNDLE
    _CACHED_BUNDLE = bundle

    log.info(
        "clv_predictor trained: accuracy=%.3f on %d held-out rows -> %s",
        accuracy, len(X_test), model_path,
    )
    return bundle["metrics"]


# ── inference ─────────────────────────────────────────────────────────────────

def load_model(model_path: Optional[str] = None, *, use_cache: bool = True) -> dict:
    """Load the serialised CLV model bundle (process-cached by default)."""
    global _CACHED_BUNDLE
    model_path = model_path or _MODEL_PATH

    if use_cache and _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"CLV model not found: {model_path} — run clv_predictor.train() first"
        )
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)

    if use_cache:
        _CACHED_BUNDLE = bundle
    return bundle


def _feature_vector(features: Dict, feature_columns: list) -> list:
    """Build an ordered feature row from a dict, defaulting missing keys to 0.0."""
    row = []
    for col in feature_columns:
        val = features.get(col, 0.0)
        try:
            row.append(float(val) if val is not None else 0.0)
        except (TypeError, ValueError):
            row.append(0.0)
    return row


def predict_clv_prob(features: Dict, model_path: Optional[str] = None) -> float:
    """Return P(closing line moves favourably) for one proposed bet.

    Args:
        features: Dict with any subset of FEATURE_COLUMNS; missing keys -> 0.0.

    Returns:
        Probability in [0, 1].
    """
    import pandas as pd

    bundle = load_model(model_path)
    cols = bundle["feature_columns"]
    row = _feature_vector(features, cols)
    X = pd.DataFrame([row], columns=cols)
    proba = bundle["model"].predict_proba(X)[0]
    # predict_proba column 1 == P(clv_label == 1).
    return float(proba[1]) if len(proba) > 1 else float(proba[0])


def predict_clv(features: Dict, model_path: Optional[str] = None) -> dict:
    """Return the full CLV prediction for one bet.

    Returns:
        {
            "clv_prob":     float,  # P(favourable closing-line move), [0,1]
            "clv_label":    int,    # 1 if clv_prob >= 0.5 else 0
            "expected_clv": float,  # CLV signal strength in percentage points
        }

    ``expected_clv`` is the favourable-move probability expressed as edge over
    a coin flip, in percentage points: ``(clv_prob - 0.5) * 100``.  A value of
    1.5 therefore means the model is 51.5% confident the line moves our way.
    bet_selector's dual gate (16.5-03) compares this against ``clv_min``.
    """
    prob = predict_clv_prob(features, model_path)
    return {
        "clv_prob": round(prob, 4),
        "clv_label": int(prob >= 0.5),
        "expected_clv": round((prob - 0.5) * 100.0, 4),
    }


def clear_cache() -> None:
    """Drop the process-level model cache (used by tests after retraining)."""
    global _CACHED_BUNDLE
    _CACHED_BUNDLE = None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description="XGBoost CLV predictor")
    ap.add_argument("--train", action="store_true", help="Train on clv_training_data.csv")
    ap.add_argument("--csv", default=None, help="Override training CSV path")
    args = ap.parse_args()

    if args.train:
        metrics = train(csv_path=args.csv)
        print(json.dumps(metrics, indent=2))
    else:
        ap.print_help()
