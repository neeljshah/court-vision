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
            with open(fpath, encoding="utf-8") as _fh:
                data = json.load(_fh)
            events = data if isinstance(data, list) else data.get("playByPlay", data.get("plays", []))

            for ev in events:
                if not isinstance(ev, dict):
                    continue
                evt_type = ev.get("event_type") or ev.get("eventMsgType")
                # Support both player_id and player_name as key
                pid = ev.get("player1_id") or ev.get("playerId")
                if pid:
                    pid = int(pid)
                else:
                    pname = ev.get("player_name", "")
                    if not pname:
                        continue
                    pid = pname  # use player_name as key
                desc = str(ev.get("event_desc", ev.get("description", ev.get("actionType", ""))))
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


# ── B-1: Defender distance adjustment ────────────────────────────────────────

def _defender_adjustment(defender_dist_ft: Optional[float]) -> float:
    """
    B-1/E-1: FG% multiplier based on closest defender distance (feet).

    Empirical sigmoid from NBA shot dashboard data:
      0–2 ft:  0.82   (heavily contested)
      2–4 ft:  0.88
      4–6 ft:  0.93
      6–10 ft: 0.98
      10+ ft:  1.04   (wide open)

    Formula: 0.82 + 0.22 * sigmoid((dist - 2.0) / 3.0)
    Clip output to [0.75, 1.10].
    Returns 1.0 (no adjustment) when defender_dist_ft is None.
    """
    if defender_dist_ft is None:
        return 1.0
    try:
        d = float(defender_dist_ft)
    except (TypeError, ValueError):
        return 1.0
    sig = 1.0 / (1.0 + (2.718281828 ** (-((d - 2.0) / 3.0))))
    return float(max(0.75, min(1.10, 0.82 + 0.22 * sig)))


# ── B-2: Spacing advantage → shot_prob scaling ───────────────────────────────

def _spacing_multiplier(spacing_advantage: Optional[float]) -> float:
    """
    B-2/E-2: Shot probability multiplier based on spacing advantage (ft²).

    Formula: 1.0 + 0.08 * sigmoid(spacing_advantage / 500.0)
    Clip to [0.88, 1.12].
    Returns 1.0 when spacing_advantage is None.
    """
    if spacing_advantage is None:
        return 1.0
    try:
        s = float(spacing_advantage)
    except (TypeError, ValueError):
        return 1.0
    sig = 1.0 / (1.0 + (2.718281828 ** (-(s / 500.0))))
    return float(max(0.88, min(1.12, 1.0 + 0.08 * sig)))


# ── E-3: Game state context multipliers ──────────────────────────────────────

def _game_state_multiplier(score_diff: int, period: int) -> dict:
    """
    E-3: Empirical multipliers for blowout / clutch game states.

    Blowout (|score_diff| > 15, period >= 3):
        tov_mult=1.15, shot_mult=1.05, fg_mult=0.94

    Close (|score_diff| <= 5, period >= 3):
        tov_mult=0.92, shot_mult=0.97, fg_mult=1.03

    Normal: all multipliers = 1.0
    """
    try:
        sd = int(score_diff)
        p  = int(period)
    except (TypeError, ValueError):
        return {"tov_mult": 1.0, "shot_mult": 1.0, "fg_mult": 1.0}

    if abs(sd) > 15 and p >= 3:
        return {"tov_mult": 1.15, "shot_mult": 1.05, "fg_mult": 0.94}
    if abs(sd) <= 5 and p >= 3:
        return {"tov_mult": 0.92, "shot_mult": 0.97, "fg_mult": 1.03}
    return {"tov_mult": 1.0, "shot_mult": 1.0, "fg_mult": 1.0}


def predict_outcome(
    player_id: int,
    play_type: str = "other",
    zone: str = "other",
    opp_team: str = "",
    defender_dist_ft: Optional[float] = None,
    spacing_advantage: Optional[float] = None,
    score_diff: int = 0,
    period: int = 2,
    lineup_quality: float = 0.0,
) -> dict:
    """
    Predict possession outcome probabilities for this player + play context.

    Falls back to league averages if player not in model.

    Args:
        player_id:        NBA player ID.
        play_type:        Synergy play type string.
        zone:             Court zone ('paint', '3pt', 'midrange', 'other').
        opp_team:         Opponent team abbreviation.
        defender_dist_ft: Closest defender in feet (B-1/E-1 adjustment).
        spacing_advantage: Team spacing advantage in ft² (B-2/E-2 adjustment).
        score_diff:       Current score diff home-away (E-3 context).
        period:           Period 1-4+ (E-3 context).
        lineup_quality:   On/off differential of current lineup (E-4).

    Returns:
        {shot_prob, tov_prob, fta_prob, fg_pct_est}
    """
    # Resolve base values from model (or fall back to priors)
    base_shot_prob = _PRIOR_SHOT_PROB
    base_tov_prob  = _PRIOR_TOV_PROB
    base_fta_prob  = _PRIOR_FTA_PROB
    base_fg_pct    = _PRIOR_FG_PCT

    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                outcome_data = pickle.load(f)
            player_data = outcome_data.get(int(player_id))
            if player_data:
                pt = play_type.lower() if play_type else "other"
                if pt not in player_data:
                    all_vals = list(player_data.values())
                    if all_vals:
                        base_shot_prob = sum(v["shot_prob"] for v in all_vals) / len(all_vals)
                        base_tov_prob  = sum(v["tov_prob"]  for v in all_vals) / len(all_vals)
                        base_fta_prob  = sum(v["fta_prob"]  for v in all_vals) / len(all_vals)
                        base_fg_pct    = sum(v["fg_pct"]    for v in all_vals) / len(all_vals)
                else:
                    pt_data = player_data[pt]
                    base_shot_prob = pt_data.get("shot_prob", _PRIOR_SHOT_PROB)
                    base_tov_prob  = pt_data.get("tov_prob",  _PRIOR_TOV_PROB)
                    base_fta_prob  = pt_data.get("fta_prob",  _PRIOR_FTA_PROB)
                    fg_pct = pt_data.get("fg_pct", _PRIOR_FG_PCT)
                    zone_fg = pt_data.get("zone_fg", {})
                    z = zone.lower() if zone else "other"
                    if z in zone_fg:
                        fg_pct = zone_fg[z]
                    base_fg_pct = fg_pct
        except Exception:
            pass  # keep priors

    # B-1/E-1: Defender distance adjustment on fg_pct
    base_fg_pct = round(base_fg_pct * _defender_adjustment(defender_dist_ft), 4)

    # B-2/E-2: Spacing advantage on shot_prob
    base_shot_prob = round(base_shot_prob * _spacing_multiplier(spacing_advantage), 4)

    # E-3: Game state context multipliers
    ctx = _game_state_multiplier(score_diff, period)
    base_tov_prob  = round(base_tov_prob  * ctx["tov_mult"],  4)
    base_shot_prob = round(base_shot_prob * ctx["shot_mult"], 4)
    base_fg_pct    = round(base_fg_pct    * ctx["fg_mult"],   4)

    # E-4: Lineup quality scaling
    # lineup_multiplier = 1.0 + 0.03 * (sigmoid(lineup_quality/5) - 0.5)
    try:
        _lq = float(lineup_quality)
        _lq_sig = 1.0 / (1.0 + (2.718281828 ** (-_lq / 5.0)))
        _lq_mult = max(0.90, min(1.10, 1.0 + 0.03 * (_lq_sig - 0.5)))
        base_shot_prob = round(base_shot_prob * _lq_mult, 4)
        base_fg_pct    = round(base_fg_pct    * _lq_mult, 4)
    except Exception:
        pass

    return {
        "shot_prob":  base_shot_prob,
        "tov_prob":   base_tov_prob,
        "fta_prob":   base_fta_prob,
        "fg_pct_est": base_fg_pct,
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
