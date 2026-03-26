"""
altitude_model.py — M19: Denver altitude adjustment for road teams.

Method: Filter gamelogs to Denver road games.
        Compare performance vs season average per position.
        Small effect (~2%) but easy to implement.

Public API
----------
    train(seasons)              -> dict
    predict_altitude_adj(feats) -> dict {adj: float}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "altitude_model.pkl")

log = logging.getLogger(__name__)

_DENVER_TEAMS = {"DEN", "DENVER", "Denver Nuggets"}
_ALTITUDE_ADJ = -0.018  # ~1.8% performance decline at altitude for road teams


def _compute_denver_adjustments(seasons: list[str]) -> dict:
    """
    Compare road team performance in Denver vs overall road performance.
    Returns per-stat adjustment ratios.
    """
    den_stats: dict[str, list] = {s: [] for s in ("pts", "reb", "ast")}
    road_stats: dict[str, list] = {s: [] for s in ("pts", "reb", "ast")}

    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))
    for fpath in gamelog_files:
        try:
            logs = json.load(open(fpath))
            if not isinstance(logs, list):
                continue
            for g in logs:
                matchup = g.get("matchup", "")
                min_val = 0.0
                m_str = str(g.get("min", "0"))
                if ":" in m_str:
                    p = m_str.split(":")
                    try:
                        min_val = float(p[0]) + float(p[1]) / 60
                    except Exception:
                        continue
                elif m_str:
                    try:
                        min_val = float(m_str)
                    except Exception:
                        continue

                if min_val <= 0:
                    continue

                # Road game: matchup contains "@"
                is_road = "@" in matchup
                is_denver_road = is_road and "DEN" in matchup

                for stat in ("pts", "reb", "ast"):
                    val = float(g.get(stat, 0) or 0)
                    if is_denver_road:
                        den_stats[stat].append(val)
                    elif is_road:
                        road_stats[stat].append(val)
        except Exception:
            continue

    adjustments: dict = {}
    for stat in ("pts", "reb", "ast"):
        den_avg  = float(np.mean(den_stats[stat])) if den_stats[stat] else 0.0
        road_avg = float(np.mean(road_stats[stat])) if road_stats[stat] else 1.0
        ratio = den_avg / max(road_avg, 0.1) if road_avg > 0 else 1.0
        adjustments[stat] = {
            "den_avg":  round(den_avg, 2),
            "road_avg": round(road_avg, 2),
            "ratio":    round(ratio, 4),
            "n_den":    len(den_stats[stat]),
            "n_road":   len(road_stats[stat]),
        }

    log.info("Altitude adjustments: %s", {k: v["ratio"] for k, v in adjustments.items()})
    return adjustments


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training altitude model...")
    adjustments = _compute_denver_adjustments(seasons)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"adjustments": adjustments, "version": "1.0"}, f)

    return adjustments


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
        _MODEL_CACHE = {"adjustments": {
            "pts": {"ratio": 1.0 + _ALTITUDE_ADJ},
            "reb": {"ratio": 1.0 + _ALTITUDE_ADJ},
            "ast": {"ratio": 1.0 + _ALTITUDE_ADJ},
        }}
    return _MODEL_CACHE


def predict_altitude_adj(features: dict) -> dict:
    """
    Apply altitude adjustment if game is in Denver and player is on road team.

    Returns:
        adj: float multiplier (e.g. 0.982 for Denver road)
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()

    opp_team  = str(features.get("opp_team", "") or "")
    home_game = int(features.get("sched_home", 1) or 1)

    # Altitude only affects road team playing at Denver
    is_denver_road = (opp_team == "DEN") and not home_game

    if not is_denver_road:
        return {"adj": 1.0}

    adjustments = _MODEL_CACHE.get("adjustments", {})
    pts_ratio = float(adjustments.get("pts", {}).get("ratio", 1.0 + _ALTITUDE_ADJ))
    avg_adj   = round(pts_ratio, 4)

    return {"adj": avg_adj}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
