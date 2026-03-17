"""
game_prediction.py — Pre-game game prediction wrapper (Phase 3).

Combines win probability + point total model into a single prediction
output ready for the betting dashboard and API.

Public API
----------
    predict_game(home_team, away_team, season, game_date) -> dict
    predict_today(season)                                 -> List[dict]
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")


def predict_game(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
    game_date: Optional[str] = None,
) -> dict:
    """
    Full pre-game prediction for a single matchup.

    Args:
        home_team:  Team abbreviation (e.g. 'GSW').
        away_team:  Team abbreviation (e.g. 'BOS').
        season:     NBA season string.
        game_date:  ISO date string for rest/travel context (optional).

    Returns:
        {
          "home_team": str,
          "away_team": str,
          "home_win_prob": float,
          "away_win_prob": float,
          "predicted_winner": str,
          "spread_est": float,       # positive = home favoured by N points
          "total_est": float,        # estimated total points
          "confidence": str,         # "high" / "medium" / "low"
          "features": dict,
        }
    """
    from src.prediction.win_probability import load as load_wp

    wp_model  = load_wp()
    wp_result = wp_model.predict(home_team, away_team, season, game_date)

    prob      = wp_result["home_win_prob"]
    spread    = round((prob - 0.5) * 30, 1)   # ~1 pt per 3% edge; ±15 pt spread at extremes
    total     = _estimate_total(home_team, away_team, season)
    confidence = "high" if abs(prob - 0.5) > 0.15 else \
                 "medium" if abs(prob - 0.5) > 0.08 else "low"

    return {
        "home_team":        home_team,
        "away_team":        away_team,
        "home_win_prob":    prob,
        "away_win_prob":    wp_result["away_win_prob"],
        "predicted_winner": wp_result["predicted_winner"],
        "spread_est":       spread,
        "total_est":        total,
        "confidence":       confidence,
        "injury_warnings":  wp_result.get("injury_warnings", {}),
        "features":         wp_result["features"],
    }


def predict_today(season: str = "2024-25") -> List[dict]:
    """
    Predict all games scheduled for today.

    Fetches today's schedule from NBA API and runs predict_game on each.

    Args:
        season: NBA season string.

    Returns:
        List of prediction dicts, sorted by confidence descending.
    """
    games = _fetch_today_games(season)
    if not games:
        print("No games found for today.")
        return []

    results = []
    for g in games:
        try:
            pred = predict_game(
                home_team  = g["home_abbrev"],
                away_team  = g["away_abbrev"],
                season     = season,
                game_date  = g.get("game_date"),
            )
            pred["game_id"]   = g.get("game_id", "")
            pred["game_date"] = g.get("game_date", "")
            results.append(pred)
        except Exception as e:
            print(f"  [warn] {g['home_abbrev']} vs {g['away_abbrev']}: {e}")

    results.sort(key=lambda x: abs(x["home_win_prob"] - 0.5), reverse=True)
    return results


# ── Helpers ────────────────────────────────────────────────────────────────────

def _estimate_total(home_team: str, away_team: str, season: str) -> float:
    """
    Estimate game total from team pace and offensive ratings.

    Formula: (home_pace + away_pace) / 2 * (home_off_rtg + away_off_rtg) / 200
    Approximates possessions × points_per_possession for each team.
    """
    cache_path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")
    if not os.path.exists(cache_path):
        return 224.0   # league average total

    with open(cache_path) as f:
        raw = json.load(f)

    # team_stats keyed by TEAM_ID (str) — find by abbreviation via nba_api
    try:
        from nba_api.stats.static import teams
        all_teams = {t["abbreviation"]: t["id"] for t in teams.get_teams()}
        h_id = str(all_teams.get(home_team, 0))
        a_id = str(all_teams.get(away_team, 0))
        ht   = raw.get(h_id, {})
        at   = raw.get(a_id, {})
        if not ht or not at:
            return 224.0
        # Each team uses the average pace (both teams share the same possession count).
        # Points = possessions × (off_rtg / 100).  Sum both teams for the game total.
        avg_pace = (ht["pace"] + at["pace"]) / 2
        total    = round(avg_pace * (ht["off_rtg"] + at["off_rtg"]) / 100, 1)
        return total
    except Exception:
        return 224.0


def _fetch_today_games(season: str) -> List[dict]:
    """
    Fetch today's NBA schedule.

    Primary: cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json
    Fallback: stats.nba.com ScoreboardV2 (often rate-limited).
    """
    from datetime import date
    import requests

    _CDN_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    _CDN_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.nba.com/",
    }

    # ── Primary: cdn.nba.com ──────────────────────────────────────────────────
    try:
        resp = requests.get(_CDN_URL, headers=_CDN_HEADERS, timeout=15)
        resp.raise_for_status()
        cdn_games = resp.json().get("scoreboard", {}).get("games", [])
        games = []
        for g in cdn_games:
            games.append({
                "game_id":     g.get("gameId", ""),
                "game_date":   str(date.today()),
                "home_abbrev": g["homeTeam"]["teamTricode"],
                "away_abbrev": g["awayTeam"]["teamTricode"],
                "status":      g.get("gameStatusText", ""),
            })
        return [g for g in games if g["home_abbrev"] and g["away_abbrev"]]
    except Exception as cdn_err:
        print(f"  [warn] cdn.nba.com scoreboard error: {cdn_err}")

    # ── Fallback: stats.nba.com ───────────────────────────────────────────────
    try:
        from nba_api.stats.endpoints import scoreboardv2
        time.sleep(0.5)
        sb  = scoreboardv2.ScoreboardV2(game_date=date.today().strftime("%m/%d/%Y"))
        dfs = sb.get_data_frames()
        if not dfs or dfs[0].empty:
            return []
        gdf = dfs[0]
        seen = set()
        games = []
        for _, row in gdf.iterrows():
            gid = row.get("GAME_ID", "")
            if gid in seen:
                continue
            seen.add(gid)
            games.append({
                "game_id":     gid,
                "game_date":   str(date.today()),
                "home_abbrev": _team_id_to_abbrev(int(row.get("HOME_TEAM_ID", 0))),
                "away_abbrev": _team_id_to_abbrev(int(row.get("VISITOR_TEAM_ID", 0))),
            })
        return [g for g in games if g["home_abbrev"] and g["away_abbrev"]]
    except Exception as e:
        print(f"  [warn] Could not fetch today's schedule: {e}")
        return []


def _team_id_to_abbrev(team_id: int) -> str:
    """Convert NBA team ID to abbreviation."""
    try:
        from nba_api.stats.static import teams
        lookup = {t["id"]: t["abbreviation"] for t in teams.get_teams()}
        return lookup.get(team_id, "")
    except Exception:
        return ""


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA Game Prediction")
    ap.add_argument("--predict", nargs=2, metavar=("HOME", "AWAY"),
                    help="Predict a specific matchup")
    ap.add_argument("--today",  action="store_true",
                    help="Predict all games today")
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()

    if args.predict:
        result = predict_game(args.predict[0], args.predict[1], args.season)
        print(json.dumps({k: v for k, v in result.items() if k != "features"},
                         indent=2))
    elif args.today:
        games = predict_today(args.season)
        for g in games:
            print(f"  {g['away_team']} @ {g['home_team']}  "
                  f"home_win_prob={g['home_win_prob']:.3f}  "
                  f"spread={g['spread_est']:+.1f}  "
                  f"total={g['total_est']:.1f}  "
                  f"[{g['confidence']}]")
    else:
        ap.print_help()
