"""
contested_shot_predictor.py — M39: Predict contested shot % vs tonight's opponent.

Inputs: shot dashboard player contested_pct, opponent hustle stats (deflections, contests),
        opponent defender zone data.
Method: Regression: player_contest_tendency + opp_hustle_rate → contest_rate_tonight.

Public API
----------
    train(seasons)                   -> dict
    predict_contested_shot(feats)    -> dict {contested_pct}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "contested_shot_predictor.pkl")

log = logging.getLogger(__name__)


def _build_training_data(season: str = "2024-25") -> tuple:
    """
    Build training data from shot dashboard + hustle stats.
    X = [player_contest_pct, opp_hustle_deflections, opp_hustle_contests, opp_hustle_box_outs]
    y = actual contest rate (use player's contested_pct as proxy target)
    """
    sd_files = glob.glob(os.path.join(_NBA_CACHE, f"shot_dashboard_*_{season}.json"))
    hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")

    if not os.path.exists(hustle_path):
        return np.zeros((0, 4)), np.zeros(0)

    hustle_data = json.load(open(hustle_path))
    hustle_map: dict[str, dict] = {str(h.get("player_id", "")): h for h in hustle_data}

    # League average hustle (opponent's team hustle averages)
    league_deflections = float(np.mean([
        float(h.get("deflections", 0) or 0) for h in hustle_data
    ])) if hustle_data else 2.5
    league_contests = float(np.mean([
        float(h.get("contested_shots", 0) or 0) for h in hustle_data
    ])) if hustle_data else 5.0

    X_rows, y_vals = [], []
    for fpath in sd_files:
        sd = json.load(open(fpath))
        if not isinstance(sd, dict):
            continue
        player_contest = float(sd.get("contested_pct", 0) or 0)
        if player_contest < 0.05 or player_contest > 0.95:
            continue

        # Use league avg as opponent hustle proxy (no per-matchup data here)
        X_rows.append([
            player_contest,
            league_deflections / 10.0,   # normalize
            league_contests / 20.0,
            0.5,   # neutral matchup
        ])
        y_vals.append(player_contest)

    if not X_rows:
        return np.zeros((0, 4)), np.zeros(0)
    return np.array(X_rows, dtype=float), np.array(y_vals, dtype=float)


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2024-25"]

    log.info("Training contested shot predictor...")
    X, y = _build_training_data(seasons[0])

    if len(X) < 30:
        log.warning("Insufficient data — heuristic")
        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"type": "heuristic", "version": "1.0"}, f)
        return {"rows": len(X)}

    from sklearn.linear_model import Ridge
    model = Ridge(alpha=0.5)
    model.fit(X, y)
    from sklearn.model_selection import cross_val_score
    mae = -float(np.mean(cross_val_score(model, X, y, cv=5,
                                          scoring="neg_mean_absolute_error")))

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"type": "ridge", "model": model, "version": "1.0"}, f)

    log.info("Contested shot predictor: %d rows, MAE=%.4f", len(X), mae)
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
        _MODEL_CACHE = {"type": "heuristic"}
    return _MODEL_CACHE


def predict_contested_shot(features: dict) -> dict:
    """Predict contested shot % for tonight."""
    m = _load_model()

    player_contest = float(features.get("contested_pct", 0.4) or 0.4)
    opp_deflections = float(features.get("opp_hustle_deflections", 2.5) or 2.5)
    opp_contests    = float(features.get("opp_hustle_contests", 5.0) or 5.0)
    def_quality     = float(features.get("matchup_pts_adj", 1.0))
    opp_hustle_adj  = 2.0 - def_quality  # better defense → more contests

    if m.get("type") == "ridge" and m.get("model") is not None:
        X = np.array([[
            player_contest,
            opp_deflections / 10.0,
            opp_contests / 20.0,
            opp_hustle_adj / 2.0,
        ]])
        try:
            contested_pct = float(m["model"].predict(X)[0])
        except Exception:
            contested_pct = player_contest * opp_hustle_adj
    else:
        contested_pct = player_contest * opp_hustle_adj

    return {"contested_pct": round(max(0.1, min(0.9, contested_pct)), 4)}
