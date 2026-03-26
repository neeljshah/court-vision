"""
contested_rate_model.py — M49: Expected contested rate for tonight's game.

Inputs: shot dashboard contested_pct vs opponent defense.
Method: player_base_contested + opp_hustle_factor → tonight_contested.

Public API
----------
    train(seasons)                   -> dict
    predict_contested_rate(feats)    -> dict {rate: float}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "contested_rate_model.pkl")

log = logging.getLogger(__name__)


def train(seasons: Optional[list[str]] = None) -> dict:
    """Compute league-average contested rate and variance from shot dashboard."""
    if seasons is None:
        seasons = ["2024-25"]

    sd_files = glob.glob(os.path.join(_NBA_CACHE, f"shot_dashboard_*_{seasons[0]}.json"))
    hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{seasons[0]}.json")

    contested_rates = []
    for fpath in sd_files:
        sd = json.load(open(fpath))
        if isinstance(sd, dict):
            c = float(sd.get("contested_pct", 0) or 0)
            if 0 < c < 1:
                contested_rates.append(c)

    team_hustle: list[float] = []
    if os.path.exists(hustle_path):
        hustle = json.load(open(hustle_path))
        for h in hustle:
            n_contests = float(h.get("contested_shots", 0) or 0)
            gp = float(h.get("games_played", 1) or 1)
            if gp > 0:
                team_hustle.append(n_contests / gp)

    league_contested = float(np.mean(contested_rates)) if contested_rates else 0.42
    league_hustle    = float(np.mean(team_hustle)) if team_hustle else 5.0

    model_data = {
        "league_contested_pct": league_contested,
        "league_hustle_rate":   league_hustle,
        "version": "1.0",
    }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    log.info("Contested rate model: league_avg=%.3f, hustle=%.1f", league_contested, league_hustle)
    return model_data


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
        _MODEL_CACHE = {"league_contested_pct": 0.42, "league_hustle_rate": 5.0}
    return _MODEL_CACHE


def predict_contested_rate(features: dict) -> dict:
    """
    Predict contested shot rate for tonight.

    Returns:
        rate: float (fraction of shots that will be contested)
    """
    m = _load_model()
    league_contested = float(m.get("league_contested_pct", 0.42))

    player_base = float(features.get("contested_pct", league_contested) or league_contested)
    opp_hustle  = float(features.get("hustle_contested_shots", 5.0) or 5.0)
    league_h    = float(m.get("league_hustle_rate", 5.0))

    # Hustle ratio: how much more/less does opponent contest vs league avg
    hustle_ratio = opp_hustle / max(league_h, 0.5)
    hustle_ratio = max(0.5, min(2.0, hustle_ratio))  # cap effect

    contested_tonight = player_base * hustle_ratio

    return {"rate": round(max(0.1, min(0.95, contested_tonight)), 4)}
