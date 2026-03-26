"""
foul_trouble_predictor.py — M05: Predict foul trouble probability and minute impact.

Inputs: historical foul rate per player (PBP), opponent foul-drawing rate, ref tendency
Output: foul_out_prob, expected_foul_count, min_reduction_if_foul_trouble

Public API
----------
    train(season)                           -> dict (metrics)
    predict_foul_trouble(player_id, feats)  -> dict
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import pickle
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "foul_trouble.pkl")

log = logging.getLogger(__name__)

# Personal foul event type in PBP
_PBP_FOUL_EVTTYPE = 6
_FOUL_OUT_LIMIT = 6


def _extract_foul_rates(seasons: list[str]) -> dict:
    """
    Extract per-player foul rates from PBP data.
    Returns {player_id: {avg_fouls_per_game, foul_out_rate, games_played}}.
    """
    foul_games: dict[int, list] = {}

    for season in seasons:
        pbp_files = glob.glob(os.path.join(_NBA_CACHE, f"pbp_*.json"))
        season_count = 0
        for fpath in pbp_files[:500]:  # sample for speed
            try:
                with open(fpath) as f:
                    plays = json.load(f)
                if not isinstance(plays, list):
                    continue

                # Count fouls per player in this game
                game_fouls: dict[int, int] = {}
                for play in plays:
                    if play.get("EVENTMSGTYPE") == _PBP_FOUL_EVTTYPE:
                        pid = play.get("PLAYER1_ID")
                        if pid and int(pid) > 0:
                            game_fouls[int(pid)] = game_fouls.get(int(pid), 0) + 1

                for pid, fcount in game_fouls.items():
                    if pid not in foul_games:
                        foul_games[pid] = []
                    foul_games[pid].append(fcount)
                season_count += 1
            except Exception:
                continue

    result: dict = {}
    for pid, foul_list in foul_games.items():
        if len(foul_list) < 5:
            continue
        arr = np.array(foul_list)
        result[str(pid)] = {
            "avg_fouls_per_game": float(np.mean(arr)),
            "foul_out_rate":      float(np.mean(arr >= _FOUL_OUT_LIMIT)),
            "pct_2plus":          float(np.mean(arr >= 2)),
            "pct_3plus":          float(np.mean(arr >= 3)),
            "games_played":       len(foul_list),
        }
    return result


def train(seasons: Optional[list[str]] = None) -> dict:
    """Train foul trouble predictor from PBP data."""
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training foul trouble predictor...")
    foul_rates = _extract_foul_rates(seasons)

    if not foul_rates:
        log.warning("No foul data found — saving empty model")
        foul_rates = {}

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump({"foul_rates": foul_rates, "version": "1.0"}, f)

    log.info("Foul trouble model trained: %d players", len(foul_rates))
    return {"players": len(foul_rates)}


def _load_model() -> dict:
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    # Auto-train if missing
    log.info("foul_trouble.pkl not found — training now")
    train()
    if os.path.exists(_MODEL_PATH):
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return {"foul_rates": {}}


_MODEL_CACHE: Optional[dict] = None


def predict_foul_trouble(player_id: int, features: dict) -> dict:
    """
    Predict foul trouble probability for tonight.

    Returns:
        foul_out_prob:      probability of fouling out
        expected_foul_count: expected fouls in game
        min_reduction:      expected minutes lost to foul trouble
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _load_model()

    foul_rates = _MODEL_CACHE.get("foul_rates", {})
    rates = foul_rates.get(str(player_id), {})

    # Historical base rate
    avg_fouls = rates.get("avg_fouls_per_game", 2.5)
    foul_out_rate = rates.get("foul_out_rate", 0.03)

    # Adjust for opponent foul-drawing tendency
    opp_foul_draw = float(features.get("opp_foul_draw_rate", 1.0))
    ref_foul_adj  = float(features.get("ref_foul_adj", 1.0))

    adj_fouls = avg_fouls * opp_foul_draw * ref_foul_adj
    adj_fout  = foul_out_rate * opp_foul_draw * ref_foul_adj

    # Minute reduction if in foul trouble:
    # Coaches restrict 3-foul players — estimate ~4 min lost per foul above 3
    pct_3plus = rates.get("pct_3plus", 0.25)
    min_reduction = pct_3plus * 4.0 * max(adj_fouls - 2.5, 0.0)

    return {
        "foul_out_prob":       min(float(adj_fout), 0.5),
        "expected_foul_count": round(float(adj_fouls), 2),
        "min_reduction":       round(float(min_reduction), 2),
        "pct_3plus":           round(float(pct_3plus), 3),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        metrics = train()
        print("Trained:", metrics)
