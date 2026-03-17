"""
prop_validator.py — Validate player prop predictions against official box scores.

Loads the full boxscore (via fetch_full_boxscore) and compares season-average
predictions to actual game performance. Produces a report with MAE and
over/under accuracy per stat line.

Public API
----------
    validate_game(game_id, season)         -> dict  (per-player breakdown)
    validate_batch(game_ids, season)       -> dict  (aggregate metrics)
    write_report(results, out_path)        -> str   (path to written JSON)
"""

from __future__ import annotations

import json
import os
import unicodedata
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")
_REPORT_DIR   = os.path.join(PROJECT_DIR, "data", "model_reports")

# Stat lines to validate
_STAT_KEYS = ["pts", "reb", "ast"]


def _norm(s: str) -> str:
    """Normalize player name for fuzzy matching (strip accents, lowercase)."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _load_season_avgs(season: str) -> dict:
    """Load cached season-average predictions keyed by normalized player name."""
    path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = json.load(f)
    # Keys may already be normalized (from player_props.py) or raw names
    return {_norm(k): v for k, v in raw.items()}


def validate_game(game_id: str, season: str = "2024-25") -> dict:
    """
    Compare season-average predictions vs actual box score for one game.

    For each player with minutes played, looks up their season-to-date averages
    (as proxy for the prop line) and computes:
      - error = actual - predicted (positive = over, negative = under)
      - abs_error = |error|

    Args:
        game_id: NBA game ID (e.g. "0022400430")
        season:  Season string matching the player_avgs cache (e.g. "2024-25")

    Returns:
        {
            "game_id": str,
            "season": str,
            "players": [
                {
                    "player_name": str,
                    "team": str,
                    "actual": {"pts": int, "reb": int, "ast": int},
                    "predicted": {"pts": float, "reb": float, "ast": float},
                    "error": {"pts": float, "reb": float, "ast": float},
                    "over_under": {"pts": "over"|"under"|"push",
                                   "reb": ..., "ast": ...},
                    "matched": bool,   # False if player not found in season avgs
                },
                ...
            ],
            "summary": {
                "n_matched": int,
                "mae": {"pts": float, "reb": float, "ast": float},
                "over_rate": {"pts": float, "reb": float, "ast": float},
                "rmse": {"pts": float, "reb": float, "ast": float},
            },
        }
    """
    from src.data.nba_stats import fetch_full_boxscore

    box = fetch_full_boxscore(game_id)
    if not box or not box.get("players"):
        return {"game_id": game_id, "error": "boxscore unavailable"}

    avgs = _load_season_avgs(season)

    player_results = []
    for p in box["players"]:
        if p["min"] < 1.0:          # skip DNPs
            continue

        name_norm = _norm(p["player_name"])
        avg = avgs.get(name_norm)
        matched = avg is not None

        actual = {k: p.get(k, 0) for k in _STAT_KEYS}
        predicted = {k: round(float(avg.get(k, 0)), 2) for k in _STAT_KEYS} if matched else \
                    {k: 0.0 for k in _STAT_KEYS}

        error = {k: round(actual[k] - predicted[k], 2) for k in _STAT_KEYS}
        over_under = {}
        for k in _STAT_KEYS:
            if abs(error[k]) < 0.5:
                over_under[k] = "push"
            elif error[k] > 0:
                over_under[k] = "over"
            else:
                over_under[k] = "under"

        player_results.append({
            "player_name": p["player_name"],
            "team":        p["team_abbreviation"],
            "min":         p["min"],
            "actual":      actual,
            "predicted":   predicted,
            "error":       error,
            "over_under":  over_under,
            "matched":     matched,
        })

    # Aggregate only matched players
    matched_players = [r for r in player_results if r["matched"]]
    n = len(matched_players)

    mae = {}
    rmse = {}
    over_rate = {}
    for k in _STAT_KEYS:
        if n == 0:
            mae[k] = rmse[k] = over_rate[k] = 0.0
            continue
        errors = [r["error"][k] for r in matched_players]
        abs_errors = [abs(e) for e in errors]
        mae[k]      = round(sum(abs_errors) / n, 3)
        rmse[k]     = round((sum(e**2 for e in errors) / n) ** 0.5, 3)
        over_rate[k] = round(sum(1 for e in errors if e > 0.5) / n, 3)

    return {
        "game_id":  game_id,
        "season":   season,
        "matchup":  f"{box.get('home_team', '?')} vs {box.get('away_team', '?')}",
        "score":    f"{box.get('home_score', 0)}-{box.get('away_score', 0)}",
        "players":  player_results,
        "summary": {
            "n_total":   len(player_results),
            "n_matched": n,
            "mae":       mae,
            "rmse":      rmse,
            "over_rate": over_rate,
        },
    }


def validate_batch(game_ids: list, season: str = "2024-25") -> dict:
    """
    Run validate_game across multiple games and aggregate results.

    Args:
        game_ids: List of NBA game IDs
        season:   Season string

    Returns:
        {
            "games_processed": int,
            "total_player_games": int,
            "total_matched": int,
            "match_rate": float,
            "mae": {"pts": float, "reb": float, "ast": float},
            "over_rate": {"pts": float, "reb": float, "ast": float},
            "per_game": [validate_game result, ...],
        }
    """
    results = []
    for gid in game_ids:
        r = validate_game(gid, season)
        if "error" not in r:
            results.append(r)

    if not results:
        return {"error": "no valid games"}

    all_matched = [p for r in results for p in r["players"] if p["matched"]]
    total_players = sum(r["summary"]["n_total"] for r in results)
    total_matched = len(all_matched)

    agg_mae = {}
    agg_over = {}
    for k in _STAT_KEYS:
        errors = [p["error"][k] for p in all_matched]
        n = len(errors)
        if n == 0:
            agg_mae[k] = agg_over[k] = 0.0
            continue
        agg_mae[k]  = round(sum(abs(e) for e in errors) / n, 3)
        agg_over[k] = round(sum(1 for e in errors if e > 0.5) / n, 3)

    return {
        "games_processed":   len(results),
        "total_player_games": total_players,
        "total_matched":     total_matched,
        "match_rate":        round(total_matched / max(1, total_players), 3),
        "mae":               agg_mae,
        "over_rate":         agg_over,
        "per_game":          results,
    }


def write_report(results: dict, label: str = "prop_validation") -> str:
    """
    Write validation results to data/model_reports/{label}.json.

    Args:
        results: Output from validate_game or validate_batch
        label:   Filename stem

    Returns:
        Absolute path to the written file.
    """
    os.makedirs(_REPORT_DIR, exist_ok=True)
    out_path = os.path.join(_REPORT_DIR, f"{label}.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    return out_path
