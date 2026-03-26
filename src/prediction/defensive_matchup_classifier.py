"""
defensive_matchup_classifier.py — Classify the specific defender a player will draw tonight.

Sources:
  1. Matchup data (matchups_{season}.json): most frequent defender against this player
  2. Position tendency: coach assigns specific players to guard PG/SG/SF/PF/C
  3. Fallback: team's best defender by def_rtg

Replaces the team-average opp_def_rtg with person-specific defender quality.

Public API
----------
    predict_defender(player_name, opp_team, season) -> dict
        -> {likely_defender_id, likely_defender_name, defender_def_rtg,
            defender_foul_rate, matchup_fg_pct_hist, confidence}
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Minimum possessions to trust a matchup record
_MIN_POSS_THRESHOLD = 5

# League-average defender quality (def_rtg)
_LEAGUE_AVG_DEF_RTG   = 113.0
_LEAGUE_AVG_FOUL_RATE = 2.8   # personal fouls per game


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _load_matchup_records(player_id: int, opp_team: str, season: str) -> list:
    """Load matchup records where this player is on offense vs opp_team defenders."""
    try:
        path = os.path.join(_NBA_CACHE, f"matchups_{season}.json")
        rows = json.load(open(path))
        return [
            r for r in rows
            if r.get("off_player_id") == player_id
            and str(r.get("team_abbreviation", "")).upper() == opp_team.upper()
        ]
    except Exception:
        return []


def _get_defender_stats(defender_id: int, season: str) -> dict:
    """Get defender's defensive stats from hustle/on-off cache."""
    result = {
        "def_rtg":    _LEAGUE_AVG_DEF_RTG,
        "foul_rate":  _LEAGUE_AVG_FOUL_RATE,
        "on_off_diff": 0.0,
    }
    try:
        hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
        if os.path.exists(hustle_path):
            records = json.load(open(hustle_path))
            for r in records:
                if r.get("player_id") == defender_id:
                    result["foul_rate"] = float(r.get("personal_fouls_pg", _LEAGUE_AVG_FOUL_RATE) or _LEAGUE_AVG_FOUL_RATE)
                    break
    except Exception:
        pass

    try:
        on_off_path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
        if os.path.exists(on_off_path):
            records = json.load(open(on_off_path))
            for r in records:
                if r.get("player_id") == defender_id:
                    result["on_off_diff"] = float(r.get("on_off_diff", 0.0) or 0.0)
                    # Estimate def_rtg from on_off: better on-off → lower def_rtg
                    result["def_rtg"] = _LEAGUE_AVG_DEF_RTG - result["on_off_diff"] * 0.4
                    break
    except Exception:
        pass

    return result


def _get_player_info(player_id: int, season: str) -> dict:
    """Get player name from avgs cache."""
    try:
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        avgs = json.load(open(avgs_path))
        for name, data in avgs.items():
            if data.get("player_id") == player_id:
                return {"name": name, "position": data.get("position", "G")}
    except Exception:
        pass
    return {"name": f"player_{player_id}", "position": "G"}


def _get_opp_best_defender(opp_team: str, season: str) -> Optional[int]:
    """Get the opponent's best defender by on/off splits."""
    try:
        on_off_path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
        avgs_path   = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(on_off_path) or not os.path.exists(avgs_path):
            return None

        on_off = json.load(open(on_off_path))
        avgs   = json.load(open(avgs_path))

        # Build set of player_ids on the opponent team
        opp_ids = {
            data.get("player_id")
            for name, data in avgs.items()
            if str(data.get("team", "")).upper() == opp_team.upper()
            and data.get("player_id")
        }

        # Find best defender (most negative on_off_diff = good defense) on that team
        best_id = None
        best_ood = float("inf")
        for r in on_off:
            pid = r.get("player_id")
            if pid in opp_ids:
                ood = float(r.get("on_off_diff", 0.0) or 0.0)
                if ood < best_ood:
                    best_ood = ood
                    best_id = pid

        return best_id
    except Exception:
        return None


def predict_defender(
    player_name: str,
    opp_team: str,
    season: str = "2024-25",
) -> dict:
    """
    Predict the most likely specific defender Player A will draw tonight.

    Priority:
      1. Matchup data (most possessions defended in current season)
      2. Opponent's best defender (from on/off cache)
      3. League average fallback

    Returns:
        {likely_defender_id, likely_defender_name, defender_def_rtg,
         defender_foul_rate, matchup_fg_pct_hist, confidence}
    """
    default = {
        "likely_defender_id":   None,
        "likely_defender_name": "unknown",
        "defender_def_rtg":     _LEAGUE_AVG_DEF_RTG,
        "defender_foul_rate":   _LEAGUE_AVG_FOUL_RATE,
        "matchup_fg_pct_hist":  0.46,
        "confidence":           "league_avg",
    }

    # Resolve player_id
    player_id = None
    try:
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        avgs = json.load(open(avgs_path))
        key = _norm(player_name)
        norm_avgs = {_norm(k): v for k, v in avgs.items()}
        pdata = norm_avgs.get(key, {})
        player_id = pdata.get("player_id")
    except Exception:
        pass

    if not player_id:
        return default

    # ── 1. Matchup data: find who defends this player most ─────────────────
    matchup_rows = _load_matchup_records(int(player_id), opp_team, season)

    if matchup_rows:
        # Group by defender_id and sum partial_possessions
        defender_poss: dict = defaultdict(float)
        defender_fg:   dict = defaultdict(list)

        for r in matchup_rows:
            def_id = r.get("def_player_id") or r.get("defender_id")
            poss   = float(r.get("partial_possessions", 1) or 1)
            fg_pct = float(r.get("matchup_fg_pct", 0.46) or 0.46)
            if def_id:
                defender_poss[int(def_id)] += poss
                defender_fg[int(def_id)].append((fg_pct, poss))

        if defender_poss:
            # Most possessions defended = primary defender
            primary_def_id = max(defender_poss, key=defender_poss.get)
            total_poss = defender_poss[primary_def_id]

            if total_poss >= _MIN_POSS_THRESHOLD:
                # Weighted avg FG% in this matchup
                fg_pairs = defender_fg[primary_def_id]
                w_fg = sum(p * poss for p, poss in fg_pairs) / sum(poss for _, poss in fg_pairs)

                def_stats = _get_defender_stats(primary_def_id, season)
                def_info  = _get_player_info(primary_def_id, season)

                return {
                    "likely_defender_id":   primary_def_id,
                    "likely_defender_name": def_info["name"],
                    "defender_def_rtg":     round(def_stats["def_rtg"], 2),
                    "defender_foul_rate":   round(def_stats["foul_rate"], 2),
                    "matchup_fg_pct_hist":  round(w_fg, 4),
                    "confidence":           "matchup_data",
                }

    # ── 2. Fallback: opponent's best defender ──────────────────────────────
    best_def_id = _get_opp_best_defender(opp_team, season)
    if best_def_id:
        def_stats = _get_defender_stats(best_def_id, season)
        def_info  = _get_player_info(best_def_id, season)

        return {
            "likely_defender_id":   best_def_id,
            "likely_defender_name": def_info["name"],
            "defender_def_rtg":     round(def_stats["def_rtg"], 2),
            "defender_foul_rate":   round(def_stats["foul_rate"], 2),
            "matchup_fg_pct_hist":  0.46,  # no matchup-specific history
            "confidence":           "best_defender",
        }

    return default


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("player")
    ap.add_argument("--opp", default="GSW")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    r = predict_defender(args.player, args.opp, args.season)
    print(json.dumps(r, indent=2))
