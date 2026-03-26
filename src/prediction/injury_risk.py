"""
injury_risk.py -- Phase E3: In-season injury risk predictor.

Scores players 0-1 on injury risk based on:
  - Minutes workload (cumulative + recent spike)
  - Usage rate vs historical average
  - Age
  - Injury history
  - Back-to-back schedule density

Public API
----------
    get_injury_risk(player_name, season)   -> dict
    get_high_risk_players(season, top_n)   -> list[dict]
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Risk weight factors (linear model, no training needed at this stage)
_WEIGHTS = {
    "age_factor":         0.15,  # per year over 30
    "minutes_spike":      0.20,  # (recent_min - season_avg_min) / season_avg_min
    "cumulative_load":    0.10,  # games_played / 82
    "usage_spike":        0.15,  # (recent_usg - season_avg_usg) / season_avg_usg
    "injury_history":     0.20,  # games missed last season / 82
    "b2b_density":        0.20,  # b2b games in last 2 weeks / 14
}


def get_injury_risk(
    player_name: str,
    season: str = "2024-25",
) -> dict:
    """
    Compute injury risk score for a player.

    Returns:
        {
            "player":       str,
            "risk_score":   float,    # 0-1
            "risk_level":   str,      # "Low" | "Medium" | "High" | "Critical"
            "drivers":      dict,     # top contributing factors
        }
    """
    components: dict = {}
    raw_feats:  dict = {}

    # Age factor
    age = 0.0
    try:
        from src.data.player_scraper import get_player_profile
        profile = get_player_profile(player_name)
        if profile:
            age = float(profile.get("age", 0) or 0)
            season_min = float(profile.get("min", 0) or 0)
            season_usg = float(profile.get("usg_pct", 0) or 0)
            games_played = float(profile.get("gp", 0) or 0)

            raw_feats["age"] = age
            raw_feats["season_min"] = season_min
            raw_feats["season_usg"] = season_usg

            # Age factor: risk increases for players 30+
            age_factor = max(0.0, (age - 30) / 10.0)
            components["age_factor"] = age_factor * _WEIGHTS["age_factor"]

            # Cumulative load
            cum_load = games_played / 82.0
            components["cumulative_load"] = cum_load * _WEIGHTS["cumulative_load"]
    except Exception:
        pass

    # Recent workload spike (last 5 games vs season avg)
    try:
        from src.data.nba_stats import get_player_recent_games
        recent = get_player_recent_games(player_name, n=5, season=season)
        if recent:
            recent_min = sum(g.get("min", 0) or 0 for g in recent) / len(recent)
            s_avg = raw_feats.get("season_min", recent_min)
            spike = (recent_min - s_avg) / max(s_avg, 1.0)
            raw_feats["minutes_spike"] = spike
            components["minutes_spike"] = max(0.0, spike) * _WEIGHTS["minutes_spike"]

            recent_usg = sum(g.get("usg_pct", 0) or 0 for g in recent) / len(recent)
            u_avg = raw_feats.get("season_usg", recent_usg)
            u_spike = (recent_usg - u_avg) / max(u_avg, 1.0)
            components["usage_spike"] = max(0.0, u_spike) * _WEIGHTS["usage_spike"]
    except Exception:
        pass

    # Injury history (games missed last season)
    try:
        bbref_path = os.path.join(PROJECT_DIR, "data", "external", "bbref_advanced_2023-24.json")
        data = json.load(open(bbref_path))
        for entry in data:
            if player_name.lower() in (entry.get("player_name") or "").lower():
                games_missed = 82 - float(entry.get("g", 82) or 82)
                hist_factor = games_missed / 82.0
                components["injury_history"] = hist_factor * _WEIGHTS["injury_history"]
                break
    except Exception:
        pass

    # B2B density
    try:
        from src.data.schedule_context import get_player_schedule_context
        sched = get_player_schedule_context(player_name, season)
        if sched:
            b2b_count = float(sched.get("b2b_last_14", 0) or 0)
            b2b_density = b2b_count / 7.0
            components["b2b_density"] = min(b2b_density, 1.0) * _WEIGHTS["b2b_density"]
    except Exception:
        pass

    risk_score = min(1.0, sum(components.values()))

    if risk_score >= 0.60:
        risk_level = "Critical"
    elif risk_score >= 0.40:
        risk_level = "High"
    elif risk_score >= 0.20:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # Top drivers = components sorted by contribution
    drivers = dict(sorted(components.items(), key=lambda x: -x[1])[:3])

    return {
        "player":     player_name,
        "risk_score": round(risk_score, 4),
        "risk_level": risk_level,
        "drivers":    {k: round(v, 4) for k, v in drivers.items()},
        "features":   raw_feats,
    }


def get_high_risk_players(
    season: str = "2024-25",
    top_n: int = 10,
    min_risk: float = 0.30,
) -> list:
    """
    Return top-N highest injury risk players from the current roster.

    Returns:
        list of {player, risk_score, risk_level, drivers}
    """
    try:
        from src.data.nba_stats import get_active_players
        players = get_active_players(season)
    except Exception:
        return []

    results = []
    for name in players[:100]:   # cap to avoid long runtimes
        try:
            r = get_injury_risk(name, season)
            if r["risk_score"] >= min_risk:
                results.append(r)
        except Exception:
            pass

    results.sort(key=lambda x: -x["risk_score"])
    return results[:top_n]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--player",  default="LeBron James")
    parser.add_argument("--top",     type=int, default=None)
    parser.add_argument("--season",  default="2024-25")
    args = parser.parse_args()

    if args.top:
        results = get_high_risk_players(args.season, top_n=args.top)
        for r in results:
            print(f"  {r['player']:25s}  risk={r['risk_score']:.3f}  [{r['risk_level']}]  "
                  f"drivers={list(r['drivers'].keys())}")
    else:
        import json
        result = get_injury_risk(args.player, args.season)
        print(json.dumps(result, indent=2))
