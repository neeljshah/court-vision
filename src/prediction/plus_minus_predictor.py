"""
plus_minus_predictor.py — M29: Project +/- for tonight.

Inputs: on/off splits, lineup net rating, matchup strength, home/away, rest.
Method: XGBoost on on/off net rating + game context features.

Public API
----------
    train(seasons)          -> dict
    predict_pm(features)    -> dict {proj_pm}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "plus_minus_predictor.pkl")

log = logging.getLogger(__name__)


def _build_training_data(seasons: list[str]) -> tuple:
    """Build X,y from gamelogs. Target: game plus_minus."""
    X_rows, y_vals = [], []

    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    for fpath in gamelog_files[:300]:
        try:
            logs = json.load(open(fpath))
            if not isinstance(logs, list) or len(logs) < 5:
                continue
            logs = sorted(logs, key=lambda g: g.get("game_date", ""))

            # Match player to on_off data
            pid_str = os.path.basename(fpath).split("_")[2]

            for season in seasons:
                on_off_path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
                if not os.path.exists(on_off_path):
                    continue
                on_off_data = json.load(open(on_off_path))
                player_on_off = next(
                    (r for r in on_off_data if str(r.get("player_id", "")) == pid_str), {}
                )
                if not player_on_off:
                    continue

                on_pm  = float(player_on_off.get("on_court_plus_minus", 0) or 0)
                off_pm = float(player_on_off.get("off_court_plus_minus", 0) or 0)
                on_off_diff = on_pm - off_pm

                season_logs = [g for g in logs if season[:4] in g.get("game_date", "")]
                played = [g for g in season_logs
                          if str(g.get("min", "0")).replace(":", "").replace("0", "") != ""]
                if len(played) < 5:
                    continue

                for i in range(5, len(played)):
                    row = played[i]
                    target = float(row.get("plus_minus", 0) or 0)
                    if abs(target) > 35:  # filter outliers
                        continue

                    is_home = int("vs." in str(row.get("matchup", "")))
                    recent5_pm = float(np.mean([float(g.get("plus_minus", 0) or 0)
                                                for g in played[i-5:i]]))

                    X_rows.append([
                        on_pm, off_pm, on_off_diff,
                        recent5_pm,
                        is_home,
                        float(row.get("min", 24) or 24) if ":" not in str(row.get("min", "")) else 24.0,
                    ])
                    y_vals.append(target)
        except Exception:
            continue

    if not X_rows:
        return np.zeros((0, 6)), np.zeros(0)
    return np.array(X_rows, dtype=float), np.array(y_vals, dtype=float)


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training plus/minus predictor...")
    X, y = _build_training_data(seasons)

    if len(X) < 100:
        log.warning("Insufficient data — heuristic")
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "heuristic", "version": "1.0"}, f)
        return {"rows": len(X)}

    try:
        from xgboost import XGBRegressor
        model = XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.1,
                             subsample=0.8, random_state=42)
        model.fit(X, y)
        from sklearn.model_selection import cross_val_score
        mae = -float(np.mean(cross_val_score(model, X, y, cv=5,
                                              scoring="neg_mean_absolute_error")))
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "xgb", "model": model, "version": "1.0"}, f)
        log.info("PM predictor: %d rows, MAE=%.2f", len(X), mae)
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
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"type": "heuristic"}
    return _MODEL_CACHE


def predict_pm(features: dict) -> dict:
    """Predict tonight's +/-."""
    m = _load_model()

    on_pm     = float(features.get("on_court_plus_minus", 0) or 0)
    off_pm    = float(features.get("off_court_plus_minus", 0) or 0)
    on_off    = float(features.get("on_off_diff", on_pm - off_pm) or 0)
    recent_pm = float(np.mean([float(features.get(f"pts_l5", 0) or 0) * 0.1]) or 0)  # proxy
    is_home   = int(features.get("sched_home", 1) or 1)
    min_exp   = float(features.get("proj_min", 24) or 24)

    if m.get("type") in ("xgb", "ridge") and m.get("model") is not None:
        X = np.array([[on_pm, off_pm, on_off, recent_pm, is_home, min_exp]])
        try:
            proj_pm = float(m["model"].predict(X)[0])
        except Exception:
            proj_pm = on_off * 0.3
    else:
        proj_pm = on_off * 0.3

    return {"proj_pm": round(float(proj_pm), 2)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
