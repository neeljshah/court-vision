"""
breakout_predictor.py -- Phase E3: Identify players primed for stat spike.

Detects players where:
  - Recent trend significantly above season average
  - Role expanding (minutes/usage trending up)
  - Matchup is favorable
  - Market hasn't priced in the spike yet

Public API
----------
    predict_breakout(player_name, season)    -> dict
    get_breakout_candidates(season, top_n)   -> list[dict]
"""
from __future__ import annotations

import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)


def _compute_trend(values: list) -> float:
    """Compute linear trend slope normalized by mean. Positive = trending up."""
    if len(values) < 2:
        return 0.0
    mean_v = sum(values) / len(values) or 1.0
    n = len(values)
    x_mean = (n - 1) / 2.0
    cov = sum((i - x_mean) * (v - mean_v) for i, v in enumerate(values))
    var = sum((i - x_mean) ** 2 for i in range(n))
    slope = cov / var if var > 0 else 0.0
    return slope / mean_v


def predict_breakout(
    player_name: str,
    opponent_team: Optional[str] = None,
    season: str = "2024-25",
) -> dict:
    """
    Score a player's breakout potential for tonight's game.

    Returns:
        {
            "player":           str,
            "breakout_score":   float,    # 0-1
            "signals":          dict,     # what's driving the score
            "projected_boost":  dict,     # {stat: % above season avg}
        }
    """
    signals: dict = {}
    season_avgs: dict = {}
    recent_avgs: dict = {}

    try:
        from src.data.player_scraper import get_player_profile
        profile = get_player_profile(player_name)
        if profile:
            for stat in ("pts", "reb", "ast", "min", "usg_pct"):
                season_avgs[stat] = float(profile.get(stat, 0) or 0)
    except Exception:
        pass

    # Recent 5-game trend
    try:
        from src.data.nba_stats import get_player_recent_games
        recent = get_player_recent_games(player_name, n=5, season=season)
        if recent:
            for stat in ("pts", "reb", "ast", "min", "usg_pct"):
                vals = [float(g.get(stat, 0) or 0) for g in recent]
                if vals:
                    recent_avgs[stat] = sum(vals) / len(vals)
                    trend = _compute_trend(vals)
                    if trend > 0.05:
                        signals[f"{stat}_trend_up"] = round(trend, 3)
    except Exception:
        pass

    # Minutes expanding signal
    if "min" in season_avgs and "min" in recent_avgs:
        min_expansion = (recent_avgs["min"] - season_avgs["min"]) / max(season_avgs["min"], 1.0)
        if min_expansion > 0.10:
            signals["minutes_expanding"] = round(min_expansion, 3)

    # Usage spike signal
    if "usg_pct" in season_avgs and "usg_pct" in recent_avgs:
        usg_spike = (recent_avgs["usg_pct"] - season_avgs["usg_pct"]) / max(season_avgs["usg_pct"], 1.0)
        if usg_spike > 0.05:
            signals["usage_spike"] = round(usg_spike, 3)

    # Favorable matchup
    if opponent_team:
        try:
            from src.prediction.matchup_model import get_matchup_features
            matchup = get_matchup_features(player_name, opponent_team, season)
            if matchup and matchup.get("matchup_pts_poss_vs_opp", 0) > 1.1:
                signals["favorable_matchup"] = round(matchup["matchup_pts_poss_vs_opp"], 3)
        except Exception:
            pass

    # Composite score
    breakout_score = min(1.0, sum(abs(v) * 2 for v in signals.values()))

    # Projected boost per stat
    projected_boost: dict = {}
    for stat in ("pts", "reb", "ast"):
        if stat in season_avgs and season_avgs[stat] > 0:
            boost_pct = breakout_score * 15.0   # up to 15% boost at score=1
            projected_boost[stat] = round(boost_pct, 1)

    return {
        "player":          player_name,
        "opponent":        opponent_team,
        "breakout_score":  round(breakout_score, 4),
        "signals":         signals,
        "projected_boost": projected_boost,
        "season_avgs":     {k: round(v, 2) for k, v in season_avgs.items()},
    }


def get_breakout_candidates(
    season: str = "2024-25",
    top_n:  int = 10,
    min_score: float = 0.25,
) -> list:
    """Return top-N breakout candidates for tonight."""
    try:
        from src.data.nba_stats import get_active_players
        players = get_active_players(season)
    except Exception:
        return []

    results = []
    for name in players[:100]:
        try:
            r = predict_breakout(name, season=season)
            if r["breakout_score"] >= min_score:
                results.append(r)
        except Exception:
            pass

    results.sort(key=lambda x: -x["breakout_score"])
    return results[:top_n]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--player",   default="Tyrese Haliburton")
    parser.add_argument("--opponent", default=None)
    parser.add_argument("--top",      type=int, default=None)
    parser.add_argument("--season",   default="2024-25")
    args = parser.parse_args()

    if args.top:
        results = get_breakout_candidates(args.season, top_n=args.top)
        for r in results:
            print(f"  {r['player']:25s}  score={r['breakout_score']:.3f}  "
                  f"signals={list(r['signals'].keys())}")
    else:
        import json
        result = predict_breakout(args.player, args.opponent, args.season)
        print(json.dumps(result, indent=2))
