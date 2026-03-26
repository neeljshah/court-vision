"""
foul_draw_rate_model.py — Player FTA rate model by shot zone and defender type.

Computes per-player FTA rates from PBP data, broken down by:
  - Shot area (paint vs perimeter)
  - Opponent foul tendency (high-foul defenders from ref_tendencies)
  - Drive frequency proxy (from synergy PRBallHandler freq)

Public API
----------
    train(seasons, force)                              -> dict
    predict_fta_rate(player_id, opp_team, season)      -> dict
        -> {fta_rate, paint_fta_rate, peri_fta_rate, fta_boost_vs_opp}
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

_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_PATH = os.path.join(_MODEL_DIR, "foul_draw_rate.pkl")

# League-average FTA rate (FTA per field goal attempt)
_LEAGUE_AVG_FTA_RATE  = 0.26
_LEAGUE_AVG_PAINT_FTA = 0.38
_LEAGUE_AVG_PERI_FTA  = 0.12


def _parse_pbp_fta_rates(seasons: list) -> dict:
    """
    Parse PBP JSON files to compute per-player FTA rates by zone.

    Returns:
        {player_id: {fta_rate, paint_fta_rate, peri_fta_rate, fga, fta, paint_fga, peri_fga}}
    """
    player_stats: dict = defaultdict(lambda: {
        "fta": 0, "fga": 0, "paint_fta": 0, "paint_fga": 0,
        "peri_fta": 0, "peri_fga": 0,
    })

    pbp_pattern = os.path.join(_NBA_CACHE, "pbp_*.json")
    files = glob.glob(pbp_pattern)[:500]

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

                # FGA: event type 1 (made FG) or 2 (missed FG)
                if evt_type in (1, 2, "1", "2"):
                    desc = str(ev.get("description", ev.get("actionType", ""))).lower()
                    player_stats[pid]["fga"] += 1
                    if "paint" in desc or "layup" in desc or "dunk" in desc or "hook" in desc:
                        player_stats[pid]["paint_fga"] += 1
                    else:
                        player_stats[pid]["peri_fga"] += 1

                # FTA: event type 3
                elif evt_type in (3, "3"):
                    desc = str(ev.get("description", ev.get("actionType", ""))).lower()
                    player_stats[pid]["fta"] += 1
                    if "paint" in desc or "layup" in desc or "dunk" in desc:
                        player_stats[pid]["paint_fta"] += 1
                    else:
                        player_stats[pid]["peri_fta"] += 1
        except Exception:
            continue

    # Compute rates
    result = {}
    for pid, s in player_stats.items():
        fga = max(s["fga"], 1)
        paint_fga = max(s["paint_fga"], 1)
        peri_fga = max(s["peri_fga"], 1)
        result[pid] = {
            "fta_rate":       round(s["fta"]       / fga,       4),
            "paint_fta_rate": round(s["paint_fta"]  / paint_fga, 4),
            "peri_fta_rate":  round(s["peri_fta"]   / peri_fga,  4),
            "fta_count":      s["fta"],
            "fga_count":      s["fga"],
        }

    return result


def _compute_opp_foul_tendency(opp_team: str, season: str) -> float:
    """
    Get opponent team's FTA allowed rate (their defenders' foul tendency).
    Higher = more fouling defense = higher fta_boost_vs_opp.
    """
    # Use ref_tracker as proxy for foul tendency, or team defensive stats
    try:
        path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
        if os.path.exists(path):
            ts = json.load(open(path))
            try:
                from nba_api.stats.static import teams as _teams
                abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
                tid = abbrev_to_id.get(opp_team)
                if tid and tid in ts:
                    # fta_rate_allowed: teams that foul a lot allow more FTA
                    # Use def_rtg as proxy — worse defense = more fouls
                    def_rtg = float(ts[tid].get("def_rtg", 113.0))
                    # +1 foul tendency for every 2 pts of def_rtg above league avg
                    boost = (def_rtg - 113.0) * 0.01
                    return round(boost, 4)
            except Exception:
                pass
    except Exception:
        pass
    return 0.0


def train(seasons: list = None, force: bool = False) -> dict:
    """
    Build FTA rate lookup from PBP data and save to pkl.

    Returns: {n_players, avg_fta_rate}
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    os.makedirs(_MODEL_DIR, exist_ok=True)

    if not force and os.path.exists(_MODEL_PATH):
        print("[foul_draw_rate] Model exists. Use force=True to retrain.")
        return {}

    print("[foul_draw_rate] Parsing PBP data for FTA rates...")
    rates = _parse_pbp_fta_rates(seasons)

    if not rates:
        print("[foul_draw_rate] No PBP data found — saving empty model.")
        rates = {}

    with open(_MODEL_PATH, "wb") as f:
        pickle.dump(rates, f)

    avg_fta = (sum(v["fta_rate"] for v in rates.values()) / len(rates)) if rates else 0.0
    print(f"  [foul_draw_rate] {len(rates)} players, avg FTA rate={avg_fta:.3f}")
    return {"n_players": len(rates), "avg_fta_rate": round(avg_fta, 4)}


def predict_fta_rate(
    player_id: int,
    opp_team: str,
    season: str = "2024-25",
) -> dict:
    """
    Predict player's FTA rate tonight, adjusted for opponent foul tendency.

    Falls back to PBP features cache (fta_rate_pbp), then league averages.

    Returns:
        {fta_rate, paint_fta_rate, peri_fta_rate, fta_boost_vs_opp}
    """
    rates = {}

    # Try trained model first
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                lookup = pickle.load(f)
            rates = lookup.get(int(player_id), {})
        except Exception:
            pass

    # Fallback to PBP features cache
    if not rates:
        try:
            path = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
            d = json.load(open(path))
            row = d.get(str(player_id), {})
            if row:
                rates = {
                    "fta_rate":       float(row.get("fta_rate_pbp", _LEAGUE_AVG_FTA_RATE)),
                    "paint_fta_rate": _LEAGUE_AVG_PAINT_FTA,
                    "peri_fta_rate":  _LEAGUE_AVG_PERI_FTA,
                }
        except Exception:
            pass

    fta_rate       = float(rates.get("fta_rate",       _LEAGUE_AVG_FTA_RATE))
    paint_fta_rate = float(rates.get("paint_fta_rate", _LEAGUE_AVG_PAINT_FTA))
    peri_fta_rate  = float(rates.get("peri_fta_rate",  _LEAGUE_AVG_PERI_FTA))

    # Opponent foul tendency adjustment
    opp_boost = _compute_opp_foul_tendency(opp_team, season)
    fta_boost_vs_opp = round(fta_rate * (1.0 + opp_boost) - fta_rate, 4)

    return {
        "fta_rate":          round(fta_rate, 4),
        "paint_fta_rate":    round(paint_fta_rate, 4),
        "peri_fta_rate":     round(peri_fta_rate, 4),
        "fta_boost_vs_opp":  round(fta_boost_vs_opp, 4),
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--player-id", type=int, default=2544)
    ap.add_argument("--opp", default="GSW")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    if args.train:
        r = train(force=True)
        print(json.dumps(r, indent=2))
    else:
        r = predict_fta_rate(args.player_id, args.opp, args.season)
        print(json.dumps(r, indent=2))
