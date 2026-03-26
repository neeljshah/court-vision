"""
true_shooting_model.py — M28: Project TS% for tonight.

Inputs: shot dashboard (contested_pct, pull_up_pct, catch_shoot_pct, avg_defender_dist),
        zone tendency, historical TS%, matchup defender quality.
Method: Ridge regression.

Public API
----------
    train(seasons)          -> dict
    predict_ts(features)    -> dict {proj_ts_pct}
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
_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "true_shooting_model.pkl")

log = logging.getLogger(__name__)


def _build_training_data(season: str = "2024-25") -> tuple:
    """
    Build X=shot_dashboard features, y=season_ts_pct.
    """
    bbref_path = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
    if not os.path.exists(bbref_path):
        return np.zeros((0, 6)), np.zeros(0)

    bbref = {p["player_name"]: p for p in json.load(open(bbref_path)) if p.get("player_name")}

    # Load shot dashboard files
    sd_files = glob.glob(os.path.join(_NBA_CACHE, f"shot_dashboard_*_{season}.json"))
    X_rows, y_vals = [], []

    for fpath in sd_files:
        sd = json.load(open(fpath))
        if not isinstance(sd, dict):
            continue
        pid = sd.get("player_id", "")
        # Find player name by matching player_id in hustle stats
        hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
        player_name = ""
        if os.path.exists(hustle_path):
            hustle = json.load(open(hustle_path))
            for h in hustle:
                if str(h.get("player_id", "")) == str(pid):
                    player_name = h.get("player_name", "")
                    break

        if not player_name:
            continue

        bb = bbref.get(player_name, {})
        target_ts = float(bb.get("ts_pct", 0) or 0)
        if target_ts < 0.3 or target_ts > 0.75:
            continue

        feats = [
            float(sd.get("catch_and_shoot_pct", 0) or 0),
            float(sd.get("pull_up_pct", 0) or 0),
            float(sd.get("contested_pct", 0) or 0),
            float(sd.get("uncontested_pct", 0) or 0),
            float(sd.get("avg_defender_dist_contested", 4) or 4),
            float(sd.get("avg_defender_dist_catch_shoot", 5) or 5),
        ]
        X_rows.append(feats)
        y_vals.append(target_ts)

    if not X_rows:
        return np.zeros((0, 6)), np.zeros(0)
    return np.array(X_rows, dtype=float), np.array(y_vals, dtype=float)


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2024-25"]

    log.info("Training true shooting model...")
    X, y = _build_training_data(seasons[0])

    if len(X) < 50:
        log.warning("Insufficient data (%d rows) — heuristic", len(X))
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "heuristic", "mean_ts": 0.565, "version": "1.0"}, f)
        return {"rows": len(X), "type": "heuristic"}

    from sklearn.linear_model import Ridge
    from sklearn.model_selection import cross_val_score

    model = Ridge(alpha=1.0)
    model.fit(X, y)
    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    mae = -float(np.mean(scores))

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"type": "ridge", "model": model, "mean_ts": float(np.mean(y)), "version": "1.0"}, f)

    log.info("TS model: %d players, MAE=%.4f, mean_ts=%.3f", len(X), mae, float(np.mean(y)))
    return {"rows": len(X), "mae": mae}


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
        _MODEL_CACHE = {"type": "heuristic", "mean_ts": 0.565}
    return _MODEL_CACHE


def predict_ts(features: dict) -> dict:
    """
    Predict true shooting % for tonight.

    Returns:
        proj_ts_pct: float (typically 0.45-0.70)
    """
    m = _load_model()
    mean_ts = float(m.get("mean_ts", 0.565))

    # Historical baseline
    hist_ts = float(features.get("bbref_ts_pct", mean_ts) or mean_ts)

    if m.get("type") == "ridge" and m.get("model") is not None:
        X = np.array([[
            float(features.get("catch_and_shoot_pct", 0.3) or 0.3),
            float(features.get("pull_up_pct", 0.4) or 0.4),
            float(features.get("contested_pct", 0.4) or 0.4),
            float(features.get("uncontested_pct", 0.6) or 0.6),
            float(features.get("avg_defender_dist_contested", 4) or 4),
            float(features.get("avg_defender_dist_catch_shoot", 5) or 5),
        ]])
        try:
            proj_ts = float(m["model"].predict(X)[0])
        except Exception:
            proj_ts = hist_ts
    else:
        proj_ts = hist_ts

    # Adjust for tonight's matchup
    matchup_adj = float(features.get("matchup_pts_adj", 1.0))
    proj_ts *= matchup_adj

    # Clip
    proj_ts = max(0.30, min(0.75, proj_ts))

    return {"proj_ts_pct": round(proj_ts, 4)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
