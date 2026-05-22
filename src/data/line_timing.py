"""
line_timing.py — Closing-line prediction (task 16.7-01).

Predicts where a prop/game line will close, so the system can fire early
(value capture) or wait (avoid a bad fill).  A gradient-boosted regression
maps pre-tip market features to the expected closing price.

Training rows come from data/output/line_timing_history.json — a labelled
log of observed (features, closing_price) pairs.  Until that history
accumulates, train()/evaluate() also accept injected rows for testing.

Public API
----------
    build_training_data(history_path)      -> list[dict]
    train(rows, model_path)                -> dict   (metrics incl. mae)
    evaluate(rows, model_path)             -> dict   ({mae, rmse, n})
    predict_closing_price(features)        -> float
    load_model(model_path)                 -> dict
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_HISTORY_PATH = os.path.join(_OUTPUT_DIR, "line_timing_history.json")
_MODEL_PATH   = os.path.join(_MODEL_DIR, "line_timing.pkl")

# Features the closing-price model consumes.  Order is significant — it is
# baked into the serialised bundle and reused at inference time.
FEATURE_COLUMNS = [
    "open_price",
    "time_to_game",
    "lineup_news",
    "public_pct",
    "sharp_pct",
    "line_velocity",
]
_TARGET = "closing_price"

# Minimum labelled rows before a regression is meaningful.
_MIN_ROWS = 20

log = logging.getLogger(__name__)

_CACHED_BUNDLE: Optional[dict] = None


# ── training data ─────────────────────────────────────────────────────────────

def build_training_data(history_path: Optional[str] = None) -> List[Dict]:
    """Load labelled (features, closing_price) rows from the history log.

    The history log is appended to as lines are observed closing across the
    season.  Returns [] when the log is absent — a real but empty dataset is
    a valid (if untrainable) state, not an error.
    """
    path = history_path or _HISTORY_PATH
    if not os.path.exists(path):
        log.info("line_timing history not found (%s) — no training rows yet", path)
        return []
    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read line_timing history: %s", exc)
        return []

    rows: List[Dict] = []
    for rec in records:
        if rec.get(_TARGET) is None or rec.get("open_price") is None:
            continue
        rows.append(rec)
    log.info("line_timing: %d labelled rows from %s", len(rows), path)
    return rows


def record_line_observation(record: Dict, history_path: Optional[str] = None) -> None:
    """Append one observed (features + closing_price) record to the history log."""
    path = history_path or _HISTORY_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: List[Dict] = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:  # noqa: BLE001
            existing = []
    existing.append(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def _xy(rows: List[Dict]):
    """Split rows into an (X, y) pair of plain Python lists."""
    X, y = [], []
    for r in rows:
        feat = []
        ok = True
        for col in FEATURE_COLUMNS:
            val = r.get(col)
            if val is None:
                val = 0.0
            try:
                feat.append(float(val))
            except (TypeError, ValueError):
                ok = False
                break
        target = r.get(_TARGET)
        if not ok or target is None:
            continue
        X.append(feat)
        y.append(float(target))
    return X, y


# ── training ──────────────────────────────────────────────────────────────────

def train(
    rows: Optional[List[Dict]] = None,
    model_path: Optional[str] = None,
    *,
    test_size: float = 0.25,
    seed: int = 42,
) -> dict:
    """Train the closing-price regression and serialise it.

    Args:
        rows:       Labelled training rows.  If None, loaded via build_training_data.
        model_path: Destination pkl (default: data/models/line_timing.pkl).

    Returns:
        Metrics dict: {n_rows, n_train, n_test, mae, rmse}.

    Raises:
        ValueError: when fewer than _MIN_ROWS labelled rows are available.
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.model_selection import train_test_split

    rows = rows if rows is not None else build_training_data()
    model_path = model_path or _MODEL_PATH

    X, y = _xy(rows)
    if len(X) < _MIN_ROWS:
        raise ValueError(
            f"line_timing training set has {len(X)} rows (< {_MIN_ROWS}); "
            f"accumulate more closed lines before training."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed
    )
    model = GradientBoostingRegressor(
        n_estimators=150, max_depth=3, learning_rate=0.1, random_state=seed
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, preds))
    rmse = float(mean_squared_error(y_test, preds) ** 0.5)

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": {
            "n_rows": len(X),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
        },
    }
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(bundle, f)

    global _CACHED_BUNDLE
    _CACHED_BUNDLE = bundle
    log.info("line_timing trained: closing-price MAE=%.4f over %d held-out lines -> %s",
             mae, len(X_test), model_path)
    return bundle["metrics"]


def evaluate(rows: Optional[List[Dict]] = None, model_path: Optional[str] = None) -> dict:
    """Score the trained model on historical rows and log the MAE.

    Returns {mae, rmse, n}.  Used to satisfy the acceptance criterion that
    the closing-price model is evaluated on historical line data.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    rows = rows if rows is not None else build_training_data()
    bundle = load_model(model_path)
    X, y = _xy(rows)
    if not X:
        log.warning("line_timing evaluate: no rows — MAE undefined")
        return {"mae": None, "rmse": None, "n": 0}

    preds = bundle["model"].predict(X)
    mae = float(mean_absolute_error(y, preds))
    rmse = float(mean_squared_error(y, preds) ** 0.5)
    log.info("line_timing evaluation: closing-price MAE=%.4f, RMSE=%.4f over %d historical lines",
             mae, rmse, len(X))
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "n": len(X)}


# ── inference ─────────────────────────────────────────────────────────────────

def load_model(model_path: Optional[str] = None, *, use_cache: bool = True) -> dict:
    """Load the serialised closing-price model bundle (process-cached)."""
    global _CACHED_BUNDLE
    model_path = model_path or _MODEL_PATH
    if use_cache and _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"line_timing model not found: {model_path} — run line_timing.train() first"
        )
    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    if use_cache:
        _CACHED_BUNDLE = bundle
    return bundle


def predict_closing_price(features: Dict, model_path: Optional[str] = None) -> float:
    """Predict the closing price for one line given its pre-tip features."""
    bundle = load_model(model_path)
    cols = bundle["feature_columns"]
    row = [[float(features.get(c, 0.0) or 0.0) for c in cols]]
    return float(bundle["model"].predict(row)[0])


def clear_cache() -> None:
    """Drop the process-level model cache (used by tests after retraining)."""
    global _CACHED_BUNDLE
    _CACHED_BUNDLE = None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Closing-line prediction")
    ap.add_argument("--train", action="store_true", help="Train on line_timing_history.json")
    ap.add_argument("--evaluate", action="store_true", help="Evaluate + log MAE")
    args = ap.parse_args()

    if args.train:
        print(json.dumps(train(), indent=2))
    if args.evaluate:
        print(json.dumps(evaluate(), indent=2))
    if not (args.train or args.evaluate):
        ap.print_help()
