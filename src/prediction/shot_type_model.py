"""
shot_type_model.py — M48: Shot type mix prediction + FG% adjustment.

Inputs: shot dashboard (pull_up_pct, catch_shoot_pct), matchup defense style.
Output: expected shot type mix + FG% adjustment.

Public API
----------
    train(seasons)              -> dict
    predict_shot_type_adj(feats) -> dict {fg_adj, pull_up_pct, catch_shoot_pct}
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
_MODEL_PATH = os.path.join(_MODEL_DIR, "shot_type_model.pkl")

log = logging.getLogger(__name__)

# FG% by shot type (league averages 2024-25)
_SHOT_TYPE_FG = {
    "catch_shoot":   0.415,   # catch-and-shoot 3pt
    "pull_up":       0.360,   # pull-up jumper
    "paint":         0.600,   # paint touches
    "post":          0.460,   # post-up
}

# Scheme adjustment: how scheme affects shot mix
# {scheme: {pull_up_mult, catch_shoot_mult}}
_SCHEME_MIX_ADJ = {
    "MAN":          {"pull_up": 1.0, "catch_shoot": 1.0},
    "SWITCH_HEAVY": {"pull_up": 0.90, "catch_shoot": 1.15},  # switches → more spot-ups
    "DROP":         {"pull_up": 1.15, "catch_shoot": 0.95},  # drop → more pull-ups
    "ZONE":         {"pull_up": 0.95, "catch_shoot": 0.90},  # zone → fewer clean looks
    "HEDGE":        {"pull_up": 0.92, "catch_shoot": 1.05},
    "ICE":          {"pull_up": 1.10, "catch_shoot": 0.98},
}


def train(seasons: Optional[list[str]] = None) -> dict:
    """Compute league-average shot type FG% splits from shot dashboard data."""
    if seasons is None:
        seasons = ["2024-25"]

    season = seasons[0]
    sd_files = glob.glob(os.path.join(_NBA_CACHE, f"shot_dashboard_*_{season}.json"))
    log.info("Training shot type model from %d shot dashboard files", len(sd_files))

    cs_pcts, pu_pcts = [], []
    for fpath in sd_files:
        sd = json.load(open(fpath))
        if not isinstance(sd, dict):
            continue
        cs = float(sd.get("catch_and_shoot_pct", 0) or 0)
        pu = float(sd.get("pull_up_pct", 0) or 0)
        if 0 < cs < 1:
            cs_pcts.append(cs)
        if 0 < pu < 1:
            pu_pcts.append(pu)

    league_cs = float(np.mean(cs_pcts)) if cs_pcts else 0.38
    league_pu = float(np.mean(pu_pcts)) if pu_pcts else 0.35

    model_data = {
        "league_catch_shoot_pct": league_cs,
        "league_pull_up_pct":     league_pu,
        "shot_type_fg":           _SHOT_TYPE_FG,
        "scheme_mix_adj":         _SCHEME_MIX_ADJ,
        "version": "1.0",
    }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(model_data, f)

    log.info("Shot type model: league_cs=%.3f, league_pu=%.3f", league_cs, league_pu)
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
        _MODEL_CACHE = {
            "league_catch_shoot_pct": 0.38,
            "league_pull_up_pct": 0.35,
            "shot_type_fg": _SHOT_TYPE_FG,
            "scheme_mix_adj": _SCHEME_MIX_ADJ,
        }
    return _MODEL_CACHE


def predict_shot_type_adj(features: dict) -> dict:
    """
    Predict shot type mix and FG% adjustment for tonight.

    Returns:
        fg_adj: multiplier on expected FG%
        pull_up_pct_tonight: expected pull-up shot fraction
        catch_shoot_pct_tonight: expected C&S fraction
    """
    m = _load_model()

    player_cs = float(features.get("catch_and_shoot_pct",
                       m.get("league_catch_shoot_pct", 0.38)) or 0.38)
    player_pu = float(features.get("pull_up_pct",
                       m.get("league_pull_up_pct", 0.35)) or 0.35)
    scheme    = str(features.get("opp_def_scheme", "MAN"))

    scheme_adj = m.get("scheme_mix_adj", _SCHEME_MIX_ADJ).get(scheme, {"pull_up": 1.0, "catch_shoot": 1.0})
    pu_tonight = player_pu * float(scheme_adj.get("pull_up", 1.0))
    cs_tonight = player_cs * float(scheme_adj.get("catch_shoot", 1.0))

    # Compute weighted FG% adjustment
    shot_fg = m.get("shot_type_fg", _SHOT_TYPE_FG)
    base_fg = (player_cs * shot_fg["catch_shoot"] +
               player_pu * shot_fg["pull_up"] +
               (1 - player_cs - player_pu) * 0.45)
    adj_fg  = (cs_tonight * shot_fg["catch_shoot"] +
               pu_tonight * shot_fg["pull_up"] +
               (1 - cs_tonight - pu_tonight) * 0.45)

    fg_mult = adj_fg / max(base_fg, 0.3)

    return {
        "fg_adj":                  round(float(fg_mult), 4),
        "pull_up_pct_tonight":     round(float(pu_tonight), 3),
        "catch_shoot_pct_tonight": round(float(cs_tonight), 3),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        print(train())
