"""
usage_surge_detector.py — Detect when a player's usage should spike tonight.

Triggers:
  1. Key teammate out (injury_monitor) → redistribute their usage%
  2. Weak matchup (opp bottom-10 def_rtg) + team on 3+ game losing streak
  3. Contract year + team eliminated from playoffs = max effort mode

Public API
----------
    predict_surge(player_name, opp_team, season) -> dict
        -> {surge_prob, usage_boost_est, trigger_reason}
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# League-average usage% roughly 20% (1/5 players per possession)
_LEAGUE_AVG_USG = 0.20
# Bottom-10 def_rtg threshold (above = bad defense → favorable matchup)
_WEAK_DEF_RTG_THRESHOLD = 116.0


def _get_teammate_usg_impact(player_name: str, season: str) -> tuple:
    """
    Check if key teammates are out tonight and estimate usage redistribution.

    Returns (usage_boost_est, injured_teammate_name or None).
    """
    try:
        from src.data.injury_monitor import InjuryMonitor
        monitor = InjuryMonitor()

        # Look up the player's team
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(avgs_path):
            return 0.0, None

        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

        avgs = json.load(open(avgs_path))
        key = _norm(player_name)
        norm_avgs = {_norm(k): v for k, v in avgs.items()}
        player_data = norm_avgs.get(key, {})
        team_abbr = player_data.get("team", "")
        player_usage = float(player_data.get("bbref_usg_pct", _LEAGUE_AVG_USG))

        if not team_abbr:
            return 0.0, None

        # Find teammates on same team who are out
        total_boost = 0.0
        injured_names = []
        for name, pdata in avgs.items():
            if _norm(name) == key:
                continue
            if pdata.get("team", "") != team_abbr:
                continue
            teammate_id = pdata.get("player_id")
            if not teammate_id:
                continue
            # Check injury status
            status = monitor.get_status(teammate_id)
            if status in ("Out", "Doubtful"):
                teammate_usg = float(pdata.get("bbref_usg_pct", _LEAGUE_AVG_USG))
                # Stars absorb ~30-40% of absent teammate's usage
                total_boost += teammate_usg * 0.35
                if teammate_usg > 0.22:  # only track meaningful players
                    injured_names.append(name)

        injured_str = ", ".join(injured_names[:2]) if injured_names else None
        return round(total_boost, 4), injured_str

    except Exception:
        return 0.0, None


def _get_opp_def_rank(opp_team: str, season: str) -> float:
    """Return opponent defensive rating. Higher = worse defense."""
    try:
        path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
        if os.path.exists(path):
            ts = json.load(open(path))
            try:
                from nba_api.stats.static import teams as _teams
                abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
                tid = abbrev_to_id.get(opp_team)
                if tid and tid in ts:
                    return float(ts[tid].get("def_rtg", 113.0))
            except Exception:
                pass
    except Exception:
        pass
    return 113.0


def _get_team_losing_streak(team_abbr: str, season: str) -> int:
    """
    Compute current losing streak from schedule cache.
    Returns number of consecutive losses (0 if on winning streak).
    """
    import datetime
    try:
        for suffix in ("_v2", ""):
            path = os.path.join(_NBA_CACHE, "schedule",
                                f"schedule_{team_abbr}_{season}{suffix}.json")
            if os.path.exists(path):
                break
        else:
            return 0

        schedule = json.load(open(path))
        if not isinstance(schedule, list):
            return 0

        today = datetime.date.today()
        past_games = []
        for g in schedule:
            raw_date = g.get("date", "")
            if not raw_date:
                continue
            try:
                d = datetime.date.fromisoformat(str(raw_date)[:10])
            except Exception:
                continue
            if d < today:
                past_games.append((d, g.get("result", g.get("outcome", ""))))

        past_games.sort(key=lambda x: x[0], reverse=True)

        streak = 0
        for _, result in past_games:
            res = str(result).upper()
            if "L" in res or "LOSS" in res:
                streak += 1
            elif "W" in res or "WIN" in res:
                break
        return streak
    except Exception:
        return 0


def _is_season_eliminated(team_abbr: str, season: str) -> bool:
    """Check if team is eliminated from playoff contention (late season proxy)."""
    import datetime
    today = datetime.date.today()
    # Rough proxy: after April 1 and team not in top 10 seeds
    if today.month < 4:
        return False
    try:
        path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
        if not os.path.exists(path):
            return False
        ts = json.load(open(path))
        try:
            from nba_api.stats.static import teams as _teams
            abbrev_to_id = {t["abbreviation"]: str(t["id"]) for t in _teams.get_teams()}
            tid = abbrev_to_id.get(team_abbr)
            if tid and tid in ts:
                wins = float(ts[tid].get("wins", 20))
                return wins < 25  # rough elimination threshold
        except Exception:
            pass
    except Exception:
        pass
    return False


def predict_surge(
    player_name: str,
    opp_team: str,
    season: str = "2024-25",
) -> dict:
    """
    Detect usage surge probability for tonight.

    Returns:
        {surge_prob, usage_boost_est, trigger_reason}
    """
    triggers = []
    total_boost = 0.0

    # Trigger 1: Teammate out → usage redistribution
    teammate_boost, injured_name = _get_teammate_usg_impact(player_name, season)
    if teammate_boost > 0.03:
        triggers.append(f"teammate_out:{injured_name or 'key_player'}")
        total_boost += teammate_boost

    # Trigger 2: Weak matchup + losing streak
    opp_def_rtg = _get_opp_def_rank(opp_team, season)
    losing_streak = _get_team_losing_streak(_get_player_team(player_name, season), season)
    if opp_def_rtg >= _WEAK_DEF_RTG_THRESHOLD and losing_streak >= 3:
        triggers.append(f"weak_matchup+losing_streak:{losing_streak}")
        total_boost += 0.04  # ~4% usage boost

    # Trigger 3: Contract year + eliminated
    try:
        from src.data.contracts_scraper import is_contract_year as _is_cy
        is_cy = _is_cy(player_name, season)
    except Exception:
        is_cy = False

    if is_cy and _is_season_eliminated(_get_player_team(player_name, season), season):
        triggers.append("contract_year+eliminated")
        total_boost += 0.03

    # Surge probability: logistic-style mapping from boost magnitude
    import math
    surge_prob = round(1.0 / (1.0 + math.exp(-15.0 * (total_boost - 0.05))), 4)

    return {
        "surge_prob":       surge_prob,
        "usage_boost_est":  round(total_boost, 4),
        "trigger_reason":   " | ".join(triggers) if triggers else "none",
    }


def _get_player_team(player_name: str, season: str) -> str:
    """Quick lookup of player's team abbreviation from avgs cache."""
    try:
        import unicodedata
        def _norm(s):
            return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()

        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        avgs = json.load(open(avgs_path))
        key = _norm(player_name)
        norm_avgs = {_norm(k): v for k, v in avgs.items()}
        return norm_avgs.get(key, {}).get("team", "")
    except Exception:
        return ""


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("player")
    ap.add_argument("--opp", default="GSW")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    r = predict_surge(args.player, args.opp, args.season)
    print(json.dumps(r, indent=2))
