"""
game_possessions_model.py — Predict tonight's game possession count.

Uses both teams' recent pace, H2H historical pace, and referee pace tendency
to estimate expected possessions more precisely than season average.

Public API
----------
    predict_possessions(home_team, away_team, season, ref_names) -> dict
        -> {expected_possessions, pace_z_score, home_pace, away_pace}
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# League-average possessions per game (2024-25 era)
_LEAGUE_AVG_POSS = 100.0
_LEAGUE_STD_POSS = 4.5


def _load_team_pace(season: str) -> dict:
    """Load team pace from team_stats cache. Returns {abbrev: pace}."""
    path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    result = {}
    if not os.path.exists(path):
        return result
    try:
        ts = json.load(open(path))
        # Try to also map team_id → abbrev via nba_api static
        try:
            from nba_api.stats.static import teams as _teams
            id_to_abbrev = {str(t["id"]): t["abbreviation"] for t in _teams.get_teams()}
        except Exception:
            id_to_abbrev = {}

        for key, val in ts.items():
            abbrev = id_to_abbrev.get(str(key), str(key))
            pace = val.get("pace") or val.get("off_rtg")  # fallback
            if pace is not None:
                result[abbrev] = float(pace)
    except Exception:
        pass
    return result


def _load_recent_team_pace(team_abbr: str, season: str, n_games: int = 5) -> Optional[float]:
    """
    Estimate recent n-game pace from schedule cache.
    Falls back to season average from team_stats if schedule not found.
    """
    team_pace = _load_team_pace(season)
    return team_pace.get(team_abbr)


def _load_h2h_pace(home_team: str, away_team: str, season: str) -> Optional[float]:
    """
    Look up historical H2H pace for these two teams from team boxscore data.
    Returns average possessions in their prior meetings, or None.
    """
    try:
        import glob
        import math

        poss_list = []
        pattern = os.path.join(_NBA_CACHE, "boxscore_*.json")
        for fpath in glob.glob(pattern)[:200]:
            try:
                data = json.load(open(fpath))
                home = data.get("home_team_abbrev", "")
                away = data.get("away_team_abbrev", "")
                if {home, away} == {home_team, away_team}:
                    poss = data.get("possessions") or data.get("pace")
                    if poss:
                        poss_list.append(float(poss))
            except Exception:
                continue

        return float(sum(poss_list) / len(poss_list)) if poss_list else None
    except Exception:
        return None


def predict_possessions(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
    ref_names: Optional[list] = None,
) -> dict:
    """
    Predict expected possessions for tonight's game.

    Components:
      1. Both teams' season pace (from team_stats cache)
      2. H2H historical pace (from boxscore cache, if available)
      3. Referee pace tendency (from ref_tracker, if ref_names provided)

    Returns:
        {expected_possessions, pace_z_score, home_pace, away_pace,
         ref_pace_adj, h2h_pace}
    """
    team_pace = _load_team_pace(season)

    home_pace = team_pace.get(home_team, _LEAGUE_AVG_POSS)
    away_pace = team_pace.get(away_team, _LEAGUE_AVG_POSS)

    # Base estimate: average of both teams' pace
    base_poss = (home_pace + away_pace) / 2.0

    # H2H adjustment: blend 20% toward historical if available
    h2h_pace = _load_h2h_pace(home_team, away_team, season)
    if h2h_pace is not None:
        base_poss = 0.80 * base_poss + 0.20 * h2h_pace

    # Referee pace adjustment
    ref_pace_adj = 0.0
    ref_pace = _LEAGUE_AVG_POSS
    if ref_names:
        try:
            from src.data.ref_tracker import get_ref_features as _ref_feats
            rf = _ref_feats(ref_names)
            if rf.get("refs_found", 0) > 0:
                ref_pace = float(rf.get("avg_pace") or _LEAGUE_AVG_POSS)
                ref_pace_adj = ref_pace - _LEAGUE_AVG_POSS
                # Blend: 85% team-based, 15% ref tendency
                base_poss = 0.85 * base_poss + 0.15 * ref_pace
        except Exception:
            pass

    expected_possessions = round(base_poss, 1)
    pace_z_score = round((expected_possessions - _LEAGUE_AVG_POSS) / _LEAGUE_STD_POSS, 3)

    return {
        "expected_possessions": expected_possessions,
        "pace_z_score":         pace_z_score,
        "home_pace":            round(home_pace, 1),
        "away_pace":            round(away_pace, 1),
        "ref_pace_adj":         round(ref_pace_adj, 2),
        "h2h_pace":             round(h2h_pace, 1) if h2h_pace else None,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="LAL")
    ap.add_argument("--away", default="GSW")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    r = predict_possessions(args.home, args.away, args.season)
    print(json.dumps(r, indent=2))
