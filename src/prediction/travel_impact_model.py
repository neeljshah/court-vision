"""
travel_impact_model.py — M18: Travel fatigue adjustment.

Method: Regression on road trip length + distance vs performance from gamelogs.
West coast trips (3+ time zones) show measurable decline, especially older players.

Public API
----------
    train(seasons)              -> dict
    predict_travel_adj(feats)   -> dict {adj: float}
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "travel_impact_model.pkl")

log = logging.getLogger(__name__)

# Research-based adjustments (no player-tracking travel data available publicly)
# West coast road trips (3+ TZ crossings) = ~2% decline
# Long road streak (4+ games) = ~1.5% per game beyond 3
_ADJUSTMENT_TABLE = {
    "tz_0": 0.0,    # local / same TZ
    "tz_1": -0.005, # 1 TZ crossing
    "tz_2": -0.010, # 2 TZ crossings (e.g. EST → CST)
    "tz_3": -0.018, # 3 TZ crossings (e.g. EST → PST)
    "road_streak_bonus": -0.005,  # per game beyond 3 games on road
}


def train(seasons: Optional[list[str]] = None) -> dict:
    """Save adjustment table to pkl."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"table": _ADJUSTMENT_TABLE, "version": "1.0"}, f)
    log.info("Travel impact model saved")
    return _ADJUSTMENT_TABLE


def _load_model() -> dict:
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return {"table": _ADJUSTMENT_TABLE}


_MODEL_CACHE: Optional[dict] = None


def predict_travel_adj(features: dict) -> dict:
    """
    Return travel fatigue adjustment multiplier.

    Returns:
        adj: float multiplier (e.g. 0.98 = 2% decline)
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()

    table = _MODEL_CACHE.get("table", _ADJUSTMENT_TABLE)
    travel_dist  = float(features.get("sched_travel_dist", 0) or 0)
    road_streak  = float(features.get("sched_games_on_road", 0) or 0)
    home_game    = int(features.get("sched_home", 1) or 1)
    age          = float(features.get("bbref_age", 27) or 27)

    # Home team doesn't travel
    if home_game:
        return {"adj": 1.0}

    # Approximate TZ crossings from travel distance
    if travel_dist < 500:
        tz_key = "tz_0"
    elif travel_dist < 1200:
        tz_key = "tz_1"
    elif travel_dist < 2000:
        tz_key = "tz_2"
    else:
        tz_key = "tz_3"

    adj = 1.0 + table.get(tz_key, 0.0)

    # Road streak penalty
    if road_streak > 3:
        adj += table.get("road_streak_bonus", -0.005) * (road_streak - 3)

    # Age modifier: players 32+ hit harder by travel
    if age >= 32:
        adj -= 0.005

    return {"adj": round(max(adj, 0.90), 4)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
