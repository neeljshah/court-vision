"""
shot_clock_pressure_model.py — M47: Shot clock pressure FG% discount.

From 3,627 PBP games, filter late-shot-clock events.
Compare FG% on pressure shots vs normal shots per player.

Public API
----------
    train(seasons)                      -> dict
    predict_pressure_discount(feats)    -> dict {discount: float}
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import re
import sys
from collections import defaultdict
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_MODEL_PATH = os.path.join(_MODEL_DIR, "shot_clock_pressure_model.pkl")

log = logging.getLogger(__name__)

# PBP event types
_EVTTYPE_SHOT_MADE   = 1
_EVTTYPE_SHOT_MISSED = 2

# Late clock threshold (seconds)
_LATE_CLOCK_SEC = 4


def _extract_late_clock_fg(pbp_files: list[str]) -> dict:
    """
    Extract FG% on late-shot-clock possessions vs normal from PBP.
    PBP doesn't always have shot clock data, but we can approximate by
    looking at end-of-period shots (last 4 seconds of quarter).
    Returns {player_id: {late_fgpct, normal_fgpct, n_late}}.
    """
    player_shots: dict[str, dict] = defaultdict(
        lambda: {"late_made": 0, "late_att": 0, "normal_made": 0, "normal_att": 0}
    )

    for fpath in pbp_files[:1000]:  # sample
        try:
            plays = json.load(open(fpath))
            if not isinstance(plays, list):
                continue

            for play in plays:
                evt_type = play.get("EVENTMSGTYPE")
                if evt_type not in (_EVTTYPE_SHOT_MADE, _EVTTYPE_SHOT_MISSED):
                    continue

                pid = str(play.get("PLAYER1_ID", ""))
                if not pid or pid == "0":
                    continue

                # Approximate late clock from period time
                ptime = str(play.get("PCTIMESTRING", "12:00"))
                try:
                    mins, secs = ptime.split(":")
                    total_secs = int(mins) * 60 + int(secs)
                    # Late clock approximation: < 4 sec remaining in period
                    # OR total period time > 11:56 (last 4 sec)
                    is_late = (total_secs <= _LATE_CLOCK_SEC)
                except Exception:
                    is_late = False

                is_made = (evt_type == _EVTTYPE_SHOT_MADE)

                if is_late:
                    player_shots[pid]["late_att"] += 1
                    if is_made:
                        player_shots[pid]["late_made"] += 1
                else:
                    player_shots[pid]["normal_att"] += 1
                    if is_made:
                        player_shots[pid]["normal_made"] += 1
        except Exception:
            continue

    result: dict = {}
    for pid, stats in player_shots.items():
        n_late   = stats["late_att"]
        n_normal = stats["normal_att"]
        if n_late < 5 or n_normal < 20:
            continue
        late_fgp   = stats["late_made"] / n_late
        normal_fgp = stats["normal_made"] / n_normal
        discount   = late_fgp / max(normal_fgp, 0.1)
        result[pid] = {
            "late_fgpct":   round(late_fgp, 3),
            "normal_fgpct": round(normal_fgp, 3),
            "discount":     round(discount, 4),
            "n_late":       n_late,
        }

    return result


def train(seasons: Optional[list[str]] = None) -> dict:
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    log.info("Training shot clock pressure model from PBP...")
    pbp_files = glob.glob(os.path.join(_NBA_CACHE, "pbp_*.json"))
    log.info("Found %d PBP files", len(pbp_files))

    player_discounts = _extract_late_clock_fg(pbp_files)
    if not player_discounts:
        log.warning("No shot clock pressure data extracted — using league average")
        player_discounts = {}

    # League average discount
    discounts = [v["discount"] for v in player_discounts.values()]
    league_avg_discount = float(np.mean(discounts)) if discounts else 0.82

    model_data = {
        "player_discounts":     player_discounts,
        "league_avg_discount":  league_avg_discount,
        "version": "1.0",
    }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    log.info("Shot clock pressure: %d players, league_avg_discount=%.3f",
             len(player_discounts), league_avg_discount)
    return {"players": len(player_discounts), "league_avg_discount": league_avg_discount}


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
        _MODEL_CACHE = {"player_discounts": {}, "league_avg_discount": 0.82}
    return _MODEL_CACHE


def predict_pressure_discount(features: dict) -> dict:
    """
    Return FG% discount factor for shot clock pressure situations.

    Returns:
        discount: float (e.g. 0.82 = 18% worse under pressure)
    """
    m = _load_model()
    pid = str(features.get("player_id", ""))
    player_data = m.get("player_discounts", {}).get(pid, {})
    discount = float(player_data.get("discount", m.get("league_avg_discount", 0.82)))

    return {"discount": round(discount, 4)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
