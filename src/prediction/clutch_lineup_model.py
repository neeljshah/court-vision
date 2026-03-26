"""
clutch_lineup_model.py — M72: Predict probability player is on court in clutch situations.

Method: Extract clutch lineups from PBP (last 5 min, margin <= 5).
Which 5 players appear most in clutch time per team?

Public API
----------
    train(seasons)               -> dict
    predict_clutch_prob(feats)   -> dict {prob: float}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sys
from collections import Counter, defaultdict
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "clutch_lineup_model.pkl")

log = logging.getLogger(__name__)

_CLUTCH_MARGIN    = 5   # within 5 points
_CLUTCH_Q4_SEC    = 300  # last 5 minutes of Q4 (300 seconds)
_EVTTYPE_FIELD    = 1   # made shot
_EVTTYPE_MISS     = 2   # missed shot
_EVTTYPE_FT       = 3   # free throw


def _extract_clutch_players(pbp_files: list[str]) -> dict:
    """
    Count player appearances in clutch situations from PBP.
    Returns {player_id: {clutch_appearances, total_games}}.
    """
    clutch_counts: Counter = Counter()
    total_appearances: Counter = Counter()

    for fpath in pbp_files[:500]:
        try:
            plays = json.load(open(fpath))
            if not isinstance(plays, list):
                continue

            for play in plays:
                # Clutch: Q4 (period=4), last 5 min (PCTIMESTRING <= 5:00), close margin
                period = int(play.get("PERIOD", 0))
                if period != 4:
                    continue

                ptime = str(play.get("PCTIMESTRING", "12:00"))
                try:
                    mins, secs = ptime.split(":")
                    remaining_secs = int(mins) * 60 + int(secs)
                except Exception:
                    continue

                if remaining_secs > _CLUTCH_Q4_SEC:
                    continue

                # Check margin
                margin_str = str(play.get("SCOREMARGIN", "20"))
                try:
                    margin = abs(int(margin_str)) if margin_str != "TIE" else 0
                except Exception:
                    continue

                if margin > _CLUTCH_MARGIN:
                    continue

                # Count player involvement
                for pid_key in ("PLAYER1_ID", "PLAYER2_ID"):
                    pid = play.get(pid_key)
                    if pid and int(pid) > 0:
                        clutch_counts[str(pid)] += 1
                        total_appearances[str(pid)] += 1

            # Count all player appearances (Q4 total)
            for play in plays:
                period = int(play.get("PERIOD", 0))
                if period != 4:
                    continue
                for pid_key in ("PLAYER1_ID",):
                    pid = play.get(pid_key)
                    if pid and int(pid) > 0:
                        total_appearances[str(pid)] += 1

        except Exception:
            continue

    result: dict = {}
    for pid, clutch in clutch_counts.items():
        total = total_appearances.get(pid, 1)
        prob  = clutch / max(total, 1)
        result[pid] = {
            "clutch_appearances": clutch,
            "total_appearances":  total,
            "clutch_prob":        round(min(prob * 2, 1.0), 3),  # scale up
        }

    return result


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training clutch lineup model from PBP...")
    pbp_files = glob.glob(os.path.join(_NBA_CACHE, "pbp_*.json"))

    clutch_data = _extract_clutch_players(pbp_files)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"clutch_data": clutch_data, "version": "1.0"}, f)

    log.info("Clutch lineup model: %d players with clutch data", len(clutch_data))
    return {"players": len(clutch_data)}


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
    log.info("clutch_lineup_model.pkl not found — training")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
    else:
        _MODEL_CACHE = {"clutch_data": {}}
    return _MODEL_CACHE


def predict_clutch_prob(features: dict) -> dict:
    """
    Predict probability player is on court in clutch situations tonight.

    Returns:
        prob: float (0-1)
    """
    m = _load_model()
    pid = str(features.get("player_id", ""))
    player_clutch = m.get("clutch_data", {}).get(pid, {})

    # Base probability from historical clutch data
    base_prob = float(player_clutch.get("clutch_prob", 0.5))

    # Adjust for blowout — stars sit, less clutch needed
    blowout_prob = float(features.get("blowout_prob", 0.1))
    prob = base_prob * (1.0 - blowout_prob * 0.5)

    # If player is a star (high minutes), boost clutch probability
    proj_min = float(features.get("proj_min", 24) or 24)
    if proj_min >= 30:
        prob = max(prob, 0.60)
    elif proj_min >= 24:
        prob = max(prob, 0.40)

    return {"prob": round(min(1.0, max(0.0, float(prob))), 3)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
