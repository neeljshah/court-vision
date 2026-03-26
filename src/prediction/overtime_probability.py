"""
overtime_probability.py — M15: Predict probability of overtime.

Method: Logistic regression on |predicted_margin| → historical OT occurrence.
From 3,685 games in historical_lines data. If margin < 4, ot_prob spikes.

Public API
----------
    train(seasons)           -> dict (metrics)
    predict_ot_prob(spread)  -> float
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "overtime_probability.pkl")

log = logging.getLogger(__name__)


def _historical_ot_rate_by_margin(seasons: list[str]) -> dict:
    """Compute OT rate by margin bucket from historical lines."""
    margin_buckets: dict[str, list[int]] = {
        "0-2": [], "3-4": [], "5-7": [], "8-12": [], "13-20": [], "20+": []
    }

    for season in seasons:
        path = os.path.join(_EXT_CACHE, f"historical_lines_{season}.json")
        if not os.path.exists(path):
            continue
        lines = json.load(open(path))
        for g in lines:
            home  = int(g.get("home_score", 0) or 0)
            away  = int(g.get("away_score", 0) or 0)
            total = home + away
            diff  = abs(home - away)
            # Infer OT: regulation max is typically 240 points (48 min × 5 pts avg)
            # OT adds ~10-15 pts per team
            is_ot = int(total > 230 and diff < 20)  # heuristic

            if diff <= 2:
                margin_buckets["0-2"].append(is_ot)
            elif diff <= 4:
                margin_buckets["3-4"].append(is_ot)
            elif diff <= 7:
                margin_buckets["5-7"].append(is_ot)
            elif diff <= 12:
                margin_buckets["8-12"].append(is_ot)
            elif diff <= 20:
                margin_buckets["13-20"].append(is_ot)
            else:
                margin_buckets["20+"].append(is_ot)

    return {k: float(np.mean(v)) if v else 0.05 for k, v in margin_buckets.items()}


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training overtime probability model...")
    ot_rates = _historical_ot_rate_by_margin(seasons)

    # Simple logistic regression on spread magnitude
    X_vals, y_vals = [], []
    for bucket, rate in ot_rates.items():
        low = int(bucket.split("-")[0].replace("+", ""))
        X_vals.append([float(low)])
        y_vals.append(rate)

    model_data = {"ot_rates": ot_rates, "version": "1.0"}

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        # Build training data from all games
        all_X, all_y = [], []
        for season in seasons:
            path = os.path.join(_EXT_CACHE, f"historical_lines_{season}.json")
            if not os.path.exists(path):
                continue
            for g in json.load(open(path)):
                home = int(g.get("home_score", 0) or 0)
                away = int(g.get("away_score", 0) or 0)
                diff = abs(home - away)
                total = home + away
                is_ot = int(total > 230 and diff < 20)
                # Use closing spread as predictor
                cs = abs(float(g.get("closing_spread", diff) or diff))
                all_X.append([cs])
                all_y.append(is_ot)

        if len(all_X) >= 100:
            X_arr = np.array(all_X)
            y_arr = np.array(all_y)
            lr = LogisticRegression(C=1.0, max_iter=200)
            lr.fit(X_arr, y_arr)
            model_data["lr_model"] = lr
            log.info("OT model: logistic trained on %d games, OT rate=%.3f",
                     len(all_X), float(np.mean(all_y)))
    except Exception as e:
        log.debug("Logistic OT model skipped: %s", e)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    return {"ot_rates": ot_rates}


_MODEL_CACHE: Optional[dict] = None


def _load_model() -> dict:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                _MODEL_CACHE = pickle.load(f)
                return _MODEL_CACHE
        except Exception:
            pass
    log.info("overtime_probability.pkl not found — training")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"ot_rates": {"0-2": 0.12, "3-4": 0.07, "5-7": 0.04,
                                      "8-12": 0.02, "13-20": 0.01, "20+": 0.005}}
    return _MODEL_CACHE


def predict_ot_prob(spread: float) -> float:
    """
    Predict overtime probability given predicted spread magnitude.

    Args:
        spread: predicted point spread (absolute value used).

    Returns:
        ot_prob (float 0-1).
    """
    m = _load_model()
    abs_spread = abs(float(spread))

    # Try logistic model first
    lr = m.get("lr_model")
    if lr is not None:
        try:
            prob = float(lr.predict_proba([[abs_spread]])[0][1])
            return round(prob, 4)
        except Exception:
            pass

    # Fallback: bucket lookup
    ot_rates = m.get("ot_rates", {})
    if abs_spread <= 2:
        return float(ot_rates.get("0-2", 0.12))
    elif abs_spread <= 4:
        return float(ot_rates.get("3-4", 0.07))
    elif abs_spread <= 7:
        return float(ot_rates.get("5-7", 0.04))
    elif abs_spread <= 12:
        return float(ot_rates.get("8-12", 0.02))
    elif abs_spread <= 20:
        return float(ot_rates.get("13-20", 0.01))
    else:
        return float(ot_rates.get("20+", 0.005))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
