"""
substitution_timing_model.py — M69: Per-quarter minutes distribution.

Method: Extract per-player quarter minute patterns from PBP.
Output: expected_minutes_per_quarter, starter vs bench role.

Public API
----------
    train(seasons)              -> dict
    predict_sub_timing(feats)   -> dict {q4_min_pct, starter_pct, ...}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "substitution_timing_model.pkl")

log = logging.getLogger(__name__)


def train(seasons: Optional[list[str]] = None) -> dict:
    """
    Build per-player quarter minute distributions.
    Uses gamelogs (no per-quarter breakdown available without box scores).
    Returns heuristic patterns.
    """
    if seasons is None:
        seasons = ["2024-25"]

    # Compute season-average mins from gamelog
    player_data: dict[str, dict] = {}
    gamelog_files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))

    for fpath in gamelog_files[:200]:
        try:
            pid = os.path.basename(fpath).split("_")[2]
            logs = json.load(open(fpath))
            if not isinstance(logs, list):
                continue

            min_vals = []
            for g in logs:
                m_str = str(g.get("min", "0"))
                if ":" in m_str:
                    parts = m_str.split(":")
                    try:
                        m = float(parts[0]) + float(parts[1]) / 60
                        if m > 0:
                            min_vals.append(m)
                    except Exception:
                        pass

            if not min_vals:
                continue

            avg_min = float(np.mean(min_vals))
            # Estimate per-quarter distribution heuristically from total minutes
            # Typical starter (30+ min): Q1=8, Q2=7, Q3=8, Q4=7
            # Bench (15-25 min): Q1=4, Q2=6, Q3=4, Q4=5
            if avg_min >= 30:
                q_dist = {"q1": 0.27, "q2": 0.23, "q3": 0.27, "q4": 0.23}
            elif avg_min >= 20:
                q_dist = {"q1": 0.22, "q2": 0.28, "q3": 0.22, "q4": 0.28}
            elif avg_min >= 12:
                q_dist = {"q1": 0.20, "q2": 0.30, "q3": 0.20, "q4": 0.30}
            else:
                q_dist = {"q1": 0.25, "q2": 0.25, "q3": 0.25, "q4": 0.25}

            player_data[pid] = {
                "avg_min":   avg_min,
                "q_dist":    q_dist,
                "is_starter": int(avg_min >= 24),
            }
        except Exception:
            continue

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"player_data": player_data, "version": "1.0"}, f)

    log.info("Substitution timing: %d players", len(player_data))
    return {"players": len(player_data)}


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
        _MODEL_CACHE = {"player_data": {}}
    return _MODEL_CACHE


def predict_sub_timing(features: dict) -> dict:
    """
    Predict per-quarter minute allocation and Q4 crunch time probability.

    Returns:
        q4_min_pct:  fraction of expected minutes in Q4
        starter_pct: probability of starting
        q_dist:      per-quarter distribution
    """
    m = _load_model()
    pid  = str(features.get("player_id", ""))
    data = m.get("player_data", {}).get(pid, {})

    avg_min = float(data.get("avg_min", features.get("min_l10", 24)) or 24)
    q_dist  = data.get("q_dist", {"q1": 0.25, "q2": 0.25, "q3": 0.25, "q4": 0.25})

    # In blowout games, Q4 star usage drops
    blowout_prob = float(features.get("blowout_prob", 0.1))
    q4_min_pct   = float(q_dist.get("q4", 0.25))
    if blowout_prob > 0.3:
        q4_min_pct *= (1.0 - blowout_prob * 0.5)

    is_starter = int(data.get("is_starter", int(avg_min >= 24)))

    return {
        "q4_min_pct":   round(float(q4_min_pct), 3),
        "starter_pct":  float(is_starter),
        "q_dist":       q_dist,
    }
