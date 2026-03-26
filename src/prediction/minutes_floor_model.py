"""
minutes_floor_model.py — M07: Precise minutes projection model.

Inputs: proj_min_base (gamelogs), dnp_prob (M01), load_risk (M02),
        foul_rate, b2b flag, coach_sub_patterns (from PBP)
Output: proj_min (float) — more precise than base minutes average.

Method: XGBoost regression on historical gamelogs where target = actual_min.
        Uses last-5/10/20 game min averages + rest + b2b + opponent pace.

Public API
----------
    train(seasons)                         -> dict (metrics)
    predict_minutes(player_id, features)   -> dict {proj_min}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "minutes_floor.pkl")

log = logging.getLogger(__name__)


def _parse_min(val) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip()
    if s in ("", "None", "null", "0", "0:00"):
        try:
            return float(s.replace(":", ""))
        except Exception:
            return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _build_training_data(seasons: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Build X, y from gamelog files for minutes regression."""
    X_rows, y_vals = [], []

    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    for fpath in gamelog_files:
        try:
            logs = json.load(open(fpath))
            if not isinstance(logs, list) or len(logs) < 10:
                continue
            logs = sorted(logs, key=lambda g: g.get("game_date", ""))

            for i in range(10, len(logs)):
                row = logs[i]
                target = _parse_min(row.get("min", 0))
                if target != target or target <= 0:  # NaN or DNP
                    continue

                window = [g for g in logs[:i] if _parse_min(g.get("min", 0)) > 0]
                if len(window) < 5:
                    continue

                def avg_n(n: int, field: str) -> float:
                    vals = [float(g.get(field, 0) or 0) for g in window[-n:]]
                    return float(np.mean(vals)) if vals else 0.0

                # Previous-game date for rest calc
                prev_date = window[-1].get("game_date", "") if window else ""
                curr_date = row.get("game_date", "")
                try:
                    from datetime import datetime
                    days_rest = (
                        datetime.strptime(curr_date[:10], "%Y-%m-%d") -
                        datetime.strptime(prev_date[:10], "%Y-%m-%d")
                    ).days - 1
                except Exception:
                    days_rest = 1

                feats = [
                    avg_n(5,  "min"),
                    avg_n(10, "min"),
                    avg_n(20, "min"),
                    min(max(days_rest, 0), 5),
                    int(days_rest == 0),   # b2b
                ]
                X_rows.append(feats)
                y_vals.append(target)
        except Exception:
            continue

    if not X_rows:
        return np.zeros((0, 5)), np.zeros(0)
    return np.array(X_rows, dtype=float), np.array(y_vals, dtype=float)


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training minutes floor model...")
    X, y = _build_training_data(seasons)

    if len(X) < 100:
        log.warning("Insufficient training data (%d rows) — using heuristic", len(X))
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "heuristic", "version": "1.0"}, f)
        return {"rows": len(X), "type": "heuristic"}

    try:
        from xgboost import XGBRegressor
        from sklearn.model_selection import cross_val_score

        model = XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42
        )
        model.fit(X, y)

        scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
        mae = -float(np.mean(scores))

        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "xgb", "model": model, "version": "1.0"}, f)

        log.info("Minutes floor model trained: %d rows, MAE=%.2f", len(X), mae)
        return {"rows": len(X), "mae": mae}

    except ImportError:
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
        model.fit(X, y)
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "ridge", "model": model, "version": "1.0"}, f)
        return {"rows": len(X), "type": "ridge"}


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
    log.info("minutes_floor.pkl not found — training now")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"type": "heuristic"}
    return _MODEL_CACHE


def predict_minutes(player_id: int, features: dict) -> dict:
    """
    Predict projected minutes for tonight.

    Returns:
        proj_min: float — expected playing time
    """
    m = _load_model()

    # Build features
    min_l5  = float(features.get("min_l5",  features.get("season_avg_min", 24.0)) or 24.0)
    min_l10 = float(features.get("min_l10", min_l5) or min_l5)
    min_l20 = float(features.get("min_l20", min_l10) or min_l10)
    rest    = min(max(float(features.get("days_rest", 1) or 1), 0), 5)
    is_b2b  = int(features.get("is_b2b", 0) or 0)

    if m.get("type") in ("xgb", "ridge") and m.get("model") is not None:
        X = np.array([[min_l5, min_l10, min_l20, rest, is_b2b]])
        try:
            proj_min = float(m["model"].predict(X)[0])
        except Exception:
            proj_min = min_l5
    else:
        # Heuristic: rolling avg with adjustments
        proj_min = min_l5

    # Apply downstream adjustments
    proj_min *= float(features.get("b2b_min_mult", 1.0))
    proj_min -= float(features.get("min_reduction_load", 0.0))
    proj_min -= float(features.get("min_reduction_foul", 0.0))
    proj_min -= float(features.get("garbage_time_min_lost", 0.0))
    proj_min += float(features.get("min_boost_from_star_dnp", 0.0))

    # Clip to realistic bounds
    proj_min = max(0.0, min(42.0, proj_min))

    # DNP probability reduces expected min
    dnp_prob = float(features.get("dnp_prob", 0.05))
    proj_min *= (1.0 - dnp_prob)

    return {"proj_min": round(proj_min, 1)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
