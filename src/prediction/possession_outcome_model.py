"""
possession_outcome_model.py — Per-player possession outcome rates from PBP.

SIMULATOR PREREQUISITE: Core of Phase 8 Monte Carlo simulator chain.

From 3,627 PBP games, computes per-player-per-play-type:
  P(shot_attempt | play_type)
  P(turnover | play_type)
  P(foul_drawn | play_type)
  P(made | shot_attempted, play_type, zone)

Public API
----------
    train(seasons, force)                                -> dict
    predict_outcome(player_id, play_type, zone, opp_team) -> dict
        -> {shot_prob, tov_prob, fta_prob, fg_pct_est}
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import sys
from collections import defaultdict
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_PATH = os.path.join(_MODEL_DIR, "possession_outcome.pkl")

# Play type event descriptions (PBP)
_PLAY_TYPES = ("pullup", "catch_shoot", "drive", "post", "cut", "spot_up", "transition", "other")

# League-average priors (Laplace smoothing base)
_PRIOR_SHOT_PROB = 0.52
_PRIOR_TOV_PROB  = 0.14
_PRIOR_FTA_PROB  = 0.22
_PRIOR_FG_PCT    = 0.46
_LAPLACE_K       = 10  # pseudo-count for smoothing


def _classify_play_type(desc: str) -> str:
    desc = str(desc).lower()
    if "pullup" in desc or "pull-up" in desc or "dribble" in desc:
        return "pullup"
    elif "catch" in desc and "shoot" in desc:
        return "catch_shoot"
    elif "drive" in desc or "driv" in desc:
        return "drive"
    elif "post" in desc:
        return "post"
    elif "cut" in desc or "cutting" in desc:
        return "cut"
    elif "spot" in desc:
        return "spot_up"
    elif "transition" in desc or "fastbreak" in desc or "fast break" in desc:
        return "transition"
    return "other"


def _classify_zone(desc: str) -> str:
    desc = str(desc).lower()
    if "3pt" in desc or "three" in desc or "3-pt" in desc or "above" in desc:
        return "3pt"
    elif "paint" in desc or "restricted" in desc or "layup" in desc or "dunk" in desc:
        return "paint"
    elif "mid" in desc or "midrange" in desc or "mid-range" in desc:
        return "midrange"
    return "other"


def _parse_pbp_outcomes(seasons: list) -> dict:
    """
    Parse PBP files to build per-player possession outcome counts.

    Returns:
        {player_id: {play_type: {possessions, shots, tov, fta, made}}}
    """
    stats: dict = defaultdict(lambda: defaultdict(lambda: {
        "poss": 0, "shots": 0, "tov": 0, "fta": 0, "made": 0,
        "zones": defaultdict(lambda: {"shots": 0, "made": 0}),
    }))

    pbp_pattern = os.path.join(_NBA_CACHE, "pbp_*.json")
    files = glob.glob(pbp_pattern)[:500]
    print(f"  [possession_outcome] Parsing {len(files)} PBP files...")

    for fpath in files:
        try:
            data = json.load(open(fpath))
            events = data if isinstance(data, list) else data.get("playByPlay", data.get("plays", []))

            for ev in events:
                if not isinstance(ev, dict):
                    continue
                evt_type = ev.get("eventMsgType") or ev.get("event_type")
                pid = ev.get("player1_id") or ev.get("playerId")
                if not pid:
                    continue
                pid = int(pid)
                desc = str(ev.get("description", ev.get("actionType", "")))
                play_type = _classify_play_type(desc)
                zone = _classify_zone(desc)

                if evt_type in (1, "1"):  # made FG
                    s = stats[pid][play_type]
                    s["poss"] += 1
                    s["shots"] += 1
                    s["made"] += 1
                    s["zones"][zone]["shots"] += 1
                    s["zones"][zone]["made"] += 1

                elif evt_type in (2, "2"):  # missed FG
                    s = stats[pid][play_type]
                    s["poss"] += 1
                    s["shots"] += 1
                    s["zones"][zone]["shots"] += 1

                elif evt_type in (3, "3"):  # free throw
                    stats[pid][play_type]["fta"] += 1

                elif evt_type in (5, "5"):  # turnover
                    s = stats[pid][play_type]
                    s["poss"] += 1
                    s["tov"] += 1

        except Exception:
            continue

    # Convert to regular dicts + compute rates with Laplace smoothing
    result = {}
    for pid, play_data in stats.items():
        result[pid] = {}
        for pt, s in play_data.items():
            poss = s["poss"] + _LAPLACE_K
            result[pid][pt] = {
                "shot_prob": round((s["shots"] + _LAPLACE_K * _PRIOR_SHOT_PROB) / poss, 4),
                "tov_prob":  round((s["tov"]   + _LAPLACE_K * _PRIOR_TOV_PROB)  / poss, 4),
                "fta_prob":  round((s["fta"]   + _LAPLACE_K * _PRIOR_FTA_PROB)  / poss, 4),
                "fg_pct":    round(
                    (s["made"] + _LAPLACE_K * _PRIOR_FG_PCT)
                    / (s["shots"] + _LAPLACE_K), 4
                ),
                "zone_fg": {
                    z: round(
                        (zv["made"] + _LAPLACE_K * 0.5)
                        / (zv["shots"] + _LAPLACE_K), 4
                    )
                    for z, zv in s["zones"].items()
                },
                "sample_poss": s["poss"],
            }

    return result


def train(seasons: list = None, force: bool = False) -> dict:
    """
    Parse PBP data to build possession outcome lookup and save to pkl.

    Returns: {n_players, avg_shot_prob, avg_tov_prob}
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and os.path.exists(_MODEL_PATH):
        print("[possession_outcome] Model exists. Use force=True to retrain.")
        return {}

    outcome_data = _parse_pbp_outcomes(seasons)

    if not outcome_data:
        print("[possession_outcome] No PBP data found — saving empty model.")
        outcome_data = {}

    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(outcome_data, f)

    n = len(outcome_data)
    avg_shot_prob = 0.0
    avg_tov_prob  = 0.0
    if n > 0:
        all_shot = [v.get("shot_prob", _PRIOR_SHOT_PROB)
                    for d in outcome_data.values()
                    for v in d.values()]
        all_tov  = [v.get("tov_prob", _PRIOR_TOV_PROB)
                    for d in outcome_data.values()
                    for v in d.values()]
        avg_shot_prob = round(sum(all_shot) / len(all_shot), 4) if all_shot else _PRIOR_SHOT_PROB
        avg_tov_prob  = round(sum(all_tov)  / len(all_tov),  4) if all_tov  else _PRIOR_TOV_PROB

    print(f"  [possession_outcome] {n} players, avg shot_prob={avg_shot_prob:.3f}")
    return {"n_players": n, "avg_shot_prob": avg_shot_prob, "avg_tov_prob": avg_tov_prob}


def predict_outcome(
    player_id: int,
    play_type: str = "other",
    zone: str = "other",
    opp_team: str = "",
) -> dict:
    """
    Predict possession outcome probabilities for this player + play context.

    Falls back to league averages if player not in model.

    Returns:
        {shot_prob, tov_prob, fta_prob, fg_pct_est}
    """
    default = {
        "shot_prob": _PRIOR_SHOT_PROB,
        "tov_prob":  _PRIOR_TOV_PROB,
        "fta_prob":  _PRIOR_FTA_PROB,
        "fg_pct_est": _PRIOR_FG_PCT,
    }

    if not os.path.exists(_MODEL_PATH):
        return default

    try:
        with open(_MODEL_PATH, "rb") as f:
            outcome_data = pickle.load(f)
    except Exception:
        return default

    player_data = outcome_data.get(int(player_id))
    if not player_data:
        return default

    pt = play_type.lower() if play_type else "other"
    if pt not in player_data:
        # Average over all play types for this player
        all_vals = list(player_data.values())
        if not all_vals:
            return default
        return {
            "shot_prob":  round(sum(v["shot_prob"] for v in all_vals) / len(all_vals), 4),
            "tov_prob":   round(sum(v["tov_prob"]  for v in all_vals) / len(all_vals), 4),
            "fta_prob":   round(sum(v["fta_prob"]  for v in all_vals) / len(all_vals), 4),
            "fg_pct_est": round(sum(v["fg_pct"]    for v in all_vals) / len(all_vals), 4),
        }

    pt_data = player_data[pt]

    # Use zone-specific FG% if available
    fg_pct = pt_data.get("fg_pct", _PRIOR_FG_PCT)
    zone_fg = pt_data.get("zone_fg", {})
    z = zone.lower() if zone else "other"
    if z in zone_fg:
        fg_pct = zone_fg[z]

    return {
        "shot_prob":  pt_data.get("shot_prob", _PRIOR_SHOT_PROB),
        "tov_prob":   pt_data.get("tov_prob",  _PRIOR_TOV_PROB),
        "fta_prob":   pt_data.get("fta_prob",  _PRIOR_FTA_PROB),
        "fg_pct_est": round(fg_pct, 4),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--player-id", type=int, default=2544)
    ap.add_argument("--play-type", default="drive")
    ap.add_argument("--zone", default="paint")
    args = ap.parse_args()
    if args.train:
        r = train(force=args.force)
        print(json.dumps(r, indent=2))
    else:
        r = predict_outcome(args.player_id, args.play_type, args.zone)
        print(json.dumps(r, indent=2))
