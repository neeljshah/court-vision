"""
home_away_model.py — M32: Home/away performance splits.

Method: Split gamelogs by home vs road. Compute per-player per-stat delta.
Store as lookup: {player_id: {pts: +1.2, reb: -0.3, ...}} home boost.

Public API
----------
    train(seasons)               -> dict
    predict_home_away(features)  -> dict {pts, reb, ast, ...}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from collections import defaultdict
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "home_away_model.pkl")

log = logging.getLogger(__name__)


def _parse_min(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    if s in ("", "None", "null", "0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def build_splits(seasons: Optional[list[str]] = None) -> dict:
    """
    Build per-player home/road splits.
    Returns {player_id: {stat: home_boost}}.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    player_home: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    player_road: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    for fpath in gamelog_files:
        try:
            pid = os.path.basename(fpath).split("_")[2]
            logs = json.load(open(fpath))
            if not isinstance(logs, list):
                continue
            for g in logs:
                min_val = _parse_min(g.get("min", 0))
                if min_val < 5:
                    continue
                matchup = g.get("matchup", "")
                is_home = int("vs." in matchup)
                for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                    val = float(g.get(stat, 0) or 0)
                    if is_home:
                        player_home[pid][stat].append(val)
                    else:
                        player_road[pid][stat].append(val)
        except Exception:
            continue

    splits: dict = {}
    league_home_boosts: dict[str, list] = defaultdict(list)

    for pid in set(player_home.keys()) | set(player_road.keys()):
        home_d = player_home.get(pid, {})
        road_d = player_road.get(pid, {})
        splits[pid] = {}
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
            h_vals = home_d.get(stat, [])
            r_vals = road_d.get(stat, [])
            if len(h_vals) >= 5 and len(r_vals) >= 5:
                h_avg = float(np.mean(h_vals))
                r_avg = float(np.mean(r_vals))
                boost = h_avg - r_avg
                splits[pid][stat] = round(boost, 3)
                league_home_boosts[stat].append(boost)
            else:
                splits[pid][stat] = 0.0

    # Compute league averages as fallback
    league_avg: dict[str, float] = {}
    for stat, boosts in league_home_boosts.items():
        league_avg[stat] = round(float(np.mean(boosts)), 3) if boosts else 0.0

    log.info("Home/away splits: %d players, league_avg_pts_boost=%.2f",
             len(splits), league_avg.get("pts", 0))

    return {"splits": splits, "league_avg": league_avg, "version": "1.0"}


def train(seasons: Optional[list[str]] = None) -> dict:
    data = build_splits(seasons)
    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(data, f)
    return {"players": len(data["splits"]), "league_avg": data["league_avg"]}


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
    log.info("home_away_model.pkl not found — training")
    data = train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"splits": {}, "league_avg": {}}
    return _MODEL_CACHE


def predict_home_away(features: dict) -> dict:
    """
    Return per-stat home boost (positive = home advantage, negative = road penalty).
    Returns the road value when player is away (boost is already the difference).

    Call this and add to projections when is_home=1, subtract when is_home=0.
    """
    m = _load_model()
    player_id = str(features.get("player_id", ""))
    is_home   = int(features.get("sched_home", 1) or 1)
    splits    = m.get("splits", {})
    league_avg = m.get("league_avg", {})

    player_splits = splits.get(player_id, {})

    result: dict = {}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        boost = float(player_splits.get(stat, league_avg.get(stat, 0.0)))
        # Return as signed boost: positive when home, negative when road
        result[stat] = round(boost if is_home else -boost, 3)

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
