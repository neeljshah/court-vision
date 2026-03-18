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

from src.data.injury_monitor import InjuryMonitor as _InjuryMonitor

_injury_monitor_gp: _InjuryMonitor = _InjuryMonitor()  # module-level singleton


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

    # Adjust for key-player injuries (top-2 scorers per team).
    # Only applied when the injury monitor has already been warmed up; returns 0.0 otherwise
    # so that tests that don't explicitly prime the monitor are unaffected.
    inj_delta  = _injury_prob_adjustment(home_team, away_team, season)
    prob       = float(max(0.05, min(0.95, prob + inj_delta)))
    away_prob  = round(1.0 - prob, 6)

    spread    = round((prob - 0.5) * 30, 1)   # ~1 pt per 3% edge; ±15 pt spread at extremes
    total     = _estimate_total(home_team, away_team, season)
    confidence = "high" if abs(prob - 0.5) > 0.15 else \
                 "medium" if abs(prob - 0.5) > 0.08 else "low"

    return {
        "home_team":        home_team,
        "away_team":        away_team,
        "home_win_prob":    prob,
        "away_win_prob":    away_prob,
        "predicted_winner": home_team if prob >= 0.5 else away_team,
        "spread_est":       spread,
        "total_est":        total,
        "confidence":       confidence,
        "injury_warnings":  wp_result.get("injury_warnings", {}),
        "features":         wp_result["features"],
    }


def predict_spread(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
    game_date: Optional[str] = None,
) -> dict:
    """
    Predict the point-differential spread for a game.

    Uses the win probability model to estimate edge, then converts to point
    differential using the approximation ~1 pt per 3% probability edge.

    Args:
        home_team:  Team abbreviation (e.g. 'GSW').
        away_team:  Team abbreviation (e.g. 'BOS').
        season:     NBA season string.
        game_date:  ISO date string for rest/travel context (optional).

    Returns:
        {
          "home_team":  str,
          "away_team":  str,
          "spread_est": float,   # positive = home favoured by N points
          "home_win_prob": float,
          "confidence": str,
        }
    """
    from src.prediction.win_probability import load as load_wp
    wp_model  = load_wp()
    wp_result = wp_model.predict(home_team, away_team, season, game_date)
    prob   = wp_result["home_win_prob"]
    spread = round((prob - 0.5) * 30, 1)
    confidence = "high" if abs(prob - 0.5) > 0.15 else \
                 "medium" if abs(prob - 0.5) > 0.08 else "low"
    return {
        "home_team":     home_team,
        "away_team":     away_team,
        "spread_est":    spread,
        "home_win_prob": prob,
        "confidence":    confidence,
    }


def predict_total(
    home_team: str,
    away_team: str,
    season: str = "2024-25",
) -> dict:
    """
    Predict the over/under total points for a game.

    Features used:
      - pace_diff:      difference in team pace ratings
      - off_rtg_sum:    sum of home + away offensive ratings
      - def_rtg_sum:    sum of home + away defensive ratings
      - ref_over_rate:  stub 0.51 (placeholder for referee over tendencies)

    Formula:
      avg_pace * (home_off_rtg + away_off_rtg) / 100
      Scaled down by def_rtg_sum to penalise strong defenses.

    Args:
        home_team: Team abbreviation.
        away_team: Team abbreviation.
        season:    NBA season string.

    Returns:
        {
          "home_team":     str,
          "away_team":     str,
          "total_est":     float,
          "over_prob":     float,  # rough probability of going over (0.5 stub)
          "features_used": dict,
        }
    """
    cache_path = os.path.join(_NBA_CACHE, f"team_stats_{season}.json")

    # Defaults
    h_pace, a_pace = 100.0, 100.0
    h_off, a_off   = 112.0, 112.0
    h_def, a_def   = 112.0, 112.0
    ref_over_rate  = 0.51   # league-average stub

    if os.path.exists(cache_path):
        try:
            from nba_api.stats.static import teams
            all_teams = {t["abbreviation"]: t["id"] for t in teams.get_teams()}
            with open(cache_path) as f:
                raw = json.load(f)
            h_id = str(all_teams.get(home_team, 0))
            a_id = str(all_teams.get(away_team, 0))
            ht   = raw.get(h_id, {})
            at   = raw.get(a_id, {})
            if ht and at:
                h_pace = ht.get("pace", h_pace)
                a_pace = at.get("pace", a_pace)
                h_off  = ht.get("off_rtg", h_off)
                a_off  = at.get("off_rtg", a_off)
                h_def  = ht.get("def_rtg", h_def)
                a_def  = at.get("def_rtg", a_def)
        except Exception:
            pass

    avg_pace     = (h_pace + a_pace) / 2
    off_rtg_sum  = h_off + a_off
    def_rtg_sum  = h_def + a_def
    pace_diff    = abs(h_pace - a_pace)

    # Base total from pace × offensive efficiency
    total_raw  = avg_pace * off_rtg_sum / 100
    # Defensive adjustment: strong defenses (high def_rtg = worse defense) need no penalty;
    # low def_rtg_sum means both teams are strong → shave ~2% off total
    def_factor = min(1.0, def_rtg_sum / 224.0)
    total_est  = round(total_raw * def_factor, 1)

    return {
        "home_team":     home_team,
        "away_team":     away_team,
        "total_est":     total_est,
        "over_prob":     ref_over_rate,
        "features_used": {
            "pace_diff":     round(pace_diff, 2),
            "off_rtg_sum":   round(off_rtg_sum, 2),
            "def_rtg_sum":   round(def_rtg_sum, 2),
            "ref_over_rate": ref_over_rate,
        },
    }


def predict_today(
    season: str = "2024-25",
    odds_feed: Optional[dict] = None,
) -> List[dict]:
    """
    Predict all games scheduled for today using win, spread, and total models.

    Fetches today's schedule from NBA API, runs predict_game + predict_spread +
    predict_total on each matchup, merges the results, and returns them ranked
    by edge confidence (|home_win_prob - 0.5| descending).

    Args:
        season:     NBA season string.
        odds_feed:  Optional dict mapping
                    "{player}|{stat}|{line}|{direction}" → American odds (int).
                    Passed to ``find_edges`` to populate ``edge_ev`` and
                    ``betting_edges`` in each game result.
                    When None or empty, ``edge_ev`` defaults to 0.0 and
                    ``betting_edges`` to [].

    Returns:
        List of merged prediction dicts, sorted by edge_confidence descending.
        Each dict contains keys from predict_game plus:
            spread_detail, total_detail, game_id, game_date,
            edge_confidence  — |home_win_prob - 0.5| (win-model edge),
            edge_ev          — max EV from betting edges (0.0 if no odds),
            betting_edges    — list of {player, stat, line, direction, ev, kelly_size}.
    """
    from src.analytics.betting_edge import find_edges

    games = _fetch_today_games(season)
    if not games:
        print("No games found for today.")
        return []

    results = []
    for g in games:
        home = g["home_abbrev"]
        away = g["away_abbrev"]
        try:
            pred = predict_game(
                home_team = home,
                away_team = away,
                season    = season,
                game_date = g.get("game_date"),
            )
        except Exception as e:
            print(f"  [warn] {home} vs {away}: predict_game failed: {e}")
            continue

        # Spread prediction (same model, exposing dedicated endpoint)
        try:
            spread_detail = predict_spread(home, away, season, g.get("game_date"))
        except Exception:
            spread_detail = {"spread_est": pred.get("spread_est"), "confidence": "low"}

        # Total prediction (pace + ratings model)
        try:
            total_detail = predict_total(home, away, season)
        except Exception:
            total_detail = {"total_est": pred.get("total_est"), "over_prob": 0.51}

        pred["game_id"]         = g.get("game_id", "")
        pred["game_date"]       = g.get("game_date", "")
        pred["spread_detail"]   = spread_detail
        pred["total_detail"]    = total_detail
        pred["edge_confidence"] = round(abs(pred["home_win_prob"] - 0.5), 4)

        # ── Betting edge enrichment ───────────────────────────────────────────
        edge_ev       = 0.0
        betting_edges: List[dict] = []
        if odds_feed:
            try:
                # Build a game-level prop stub from the win probability to
                # pass through find_edges when no player props are available.
                # Callers with full prop data should pass a pre-populated
                # props_list via a custom odds_feed.
                home_prob = pred["home_win_prob"]
                props_stub = [
                    {
                        "player":    f"{home} ML",
                        "stat":      "win",
                        "line":      0.5,
                        "direction": "over",
                        "your_prob": home_prob,
                        "bankroll":  1000.0,
                    }
                ]
                edges = find_edges(props_stub, odds_feed)
                betting_edges = [
                    {
                        "player":     e.player,
                        "stat":       e.stat,
                        "line":       e.line,
                        "direction":  e.direction,
                        "ev":         e.ev,
                        "kelly_size": e.kelly_size,
                    }
                    for e in edges
                ]
                edge_ev = max((e.ev for e in edges), default=0.0)
            except Exception as exc:
                print(f"  [warn] find_edges failed for {home} vs {away}: {exc}")

        pred["edge_ev"]       = round(edge_ev, 6)
        pred["betting_edges"] = betting_edges
        results.append(pred)

    results.sort(key=lambda x: x["edge_confidence"], reverse=True)
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


def _injury_prob_adjustment(
    home_team: str,
    away_team: str,
    season: str,
) -> float:
    """
    Return a home-win-probability delta based on top-2 scorer injuries.

    Logic:
      - Home star Out        → -0.04  (home loses strength)
      - Home star Questionable → -0.02
      - Away star Out        → +0.04  (away loses strength → home benefits)
      - Away star Questionable → +0.02
    Caps at ±0.08 in case multiple stars are injured.

    Returns:
        Float delta to add to home_win_prob (may be 0.0 if unavailable).
    """
    try:
        avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(avgs_path):
            return 0.0
        with open(avgs_path) as f:
            avgs = json.load(f)

        # Only apply if the monitor has already been warmed up (non-empty _data).
        # This avoids a disk read on every predict_game() call in test contexts.
        if not _injury_monitor_gp._data:
            return 0.0

        delta = 0.0
        for team, is_home in [(home_team, True), (away_team, False)]:
            team_players = [
                info for info in avgs.values()
                if isinstance(info, dict)
                and info.get("team", "").upper() == team.upper()
            ]
            stars = sorted(team_players, key=lambda x: x.get("pts", 0), reverse=True)[:2]
            for info in stars:
                pid    = int(info.get("player_id", 0))
                status = _injury_monitor_gp.get_status(pid)
                if status == "Out":
                    delta += -0.04 if is_home else +0.04
                elif status in ("Questionable", "GTD"):
                    delta += -0.02 if is_home else +0.02

        return round(max(-0.08, min(0.08, delta)), 4)
    except Exception:
        return 0.0


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
