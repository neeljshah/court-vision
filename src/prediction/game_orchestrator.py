"""
game_orchestrator.py — Prompt 4: Unified game prediction orchestrator.

Combines win probability, game models, player props, and betting edges
into a single predict_game() call.

Public API
----------
    predict_game(home_team, away_team, season, player_ids, lines, bankroll) -> dict

CLI
---
    python -m src.prediction.game_orchestrator --home LAL --away BOS
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_PREDICTIONS_DIR = os.path.join(PROJECT_DIR, "data", "predictions")
_DEFAULT_BANKROLL = 10_000.0
_MIN_EDGE_TO_SIZE = 0.03  # only Kelly-size edges above 3%


def _get_starters(home_team: str, away_team: str, season: str) -> List[str]:
    """Return player_ids for both teams' starters from nba_api, or [] on failure."""
    try:
        from nba_api.stats.endpoints import commonteamroster
        ids: List[str] = []
        for team in (home_team, away_team):
            try:
                roster = commonteamroster.CommonTeamRoster(
                    team_id=_team_abbr_to_id(team), season=season, timeout=10
                )
                df = roster.get_data_frames()[0]
                # Take first 5 — rough proxy for starters
                ids.extend([str(pid) for pid in df["PLAYER_ID"].head(5).tolist()])
            except Exception:
                pass
        return ids
    except Exception:
        return []


def _team_abbr_to_id(abbr: str) -> int:
    """Return NBA team_id from abbreviation via nba_api static data."""
    try:
        from nba_api.stats.static import teams
        matches = [t for t in teams.get_teams() if t["abbreviation"].upper() == abbr.upper()]
        return matches[0]["id"] if matches else 0
    except Exception:
        return 0


def predict_game(
    home_team: str,
    away_team: str,
    season: str = "2025-26",
    player_ids: Optional[List[str]] = None,
    lines: Optional[Dict[str, Dict[str, float]]] = None,
    bankroll: float = _DEFAULT_BANKROLL,
    game_date: Optional[str] = None,
    save: bool = True,
) -> dict:
    """
    Full prediction for a single game combining all models.

    Args:
        home_team:  Team abbreviation e.g. 'LAL'.
        away_team:  Team abbreviation e.g. 'BOS'.
        season:     NBA season string e.g. '2025-26'.
        player_ids: List of player IDs to predict props for. If None, pulls starters.
        lines:      {player_id: {stat: line}} for edge calculation.
        bankroll:   Current bankroll for Kelly sizing.
        game_date:  ISO date for rest/travel context (defaults to today).
        save:       Whether to save prediction to data/predictions/.

    Returns:
        Unified dict with win_prob, game_models, props, edges.
    """
    game_date = game_date or str(date.today())
    lines = lines or {}
    result: dict = {
        "home_team": home_team,
        "away_team": away_team,
        "season": season,
        "game_date": game_date,
        "win_probability": {},
        "game_models": {},
        "props": [],
        "edges": [],
    }

    # 1. Win probability
    try:
        from src.prediction import win_probability as wp_module
        wp_model = wp_module.load()
        wp = wp_model.predict(home_team, away_team, season=season, game_date=game_date)
        result["win_probability"] = wp
    except Exception as e:
        result["win_probability"] = {"error": str(e)}

    win_prob_home = result["win_probability"].get("home_win_prob", 0.5)

    # 2. Game models (spread, total, blowout, pace, first_half)
    try:
        from src.prediction import game_models as gm_module
        gm_pred = gm_module.predict(home_team, away_team, season=season, game_date=game_date)
        # Wire win_prob_home from step 1 into features for context
        if "features" in gm_pred:
            gm_pred["features"]["win_prob_home_live"] = win_prob_home
        result["game_models"] = gm_pred
    except Exception as e:
        result["game_models"] = {"error": str(e)}

    # Build game_context for prop models
    game_context: dict = {
        "home_team": home_team,
        "away_team": away_team,
        "season": season,
        "game_date": game_date,
        "win_prob_home": win_prob_home,
        "total_est": result["game_models"].get("total_est", 220.0),
        "pace_est": result["game_models"].get("pace_est", 100.0),
    }

    # 3. Player props for key players
    if player_ids is None:
        player_ids = _get_starters(home_team, away_team, season)

    from src.prediction.prop_model_stack import stack_predict
    from src.prediction.betting_portfolio import kelly_corr

    prop_results = []
    edge_plays = []

    for pid in player_ids:
        player_lines = lines.get(str(pid), {})
        try:
            stack = stack_predict(str(pid), game_context=game_context, lines=player_lines)
        except Exception:
            continue

        prop_entry = {
            "player_id": stack.player_id,
            "player_name": stack.player_name,
            "suppressed": stack.suppressed,
            "suppression_reason": stack.suppression_reason,
            "predictions": stack.predictions,
            "confidence": stack.confidence,
            "edges": {k: v for k, v in stack.edges.items() if v == v},  # drop NaN
        }
        prop_results.append(prop_entry)

        # 4. Betting edges — Kelly size any prop with edge > threshold
        if not stack.suppressed:
            for stat, edge in stack.edges.items():
                if edge != edge:  # NaN check
                    continue
                if abs(edge) < _MIN_EDGE_TO_SIZE:
                    continue
                line = player_lines.get(stat, 0.0)
                if not line:
                    continue
                direction = "over" if edge > 0 else "under"
                kelly_size = kelly_corr(
                    edge=abs(edge),
                    odds=-110,  # standard juice; caller can override
                    bankroll=bankroll,
                )
                confidence = stack.confidence.get(stat, 0.0)
                edge_plays.append({
                    "player_id": stack.player_id,
                    "player_name": stack.player_name,
                    "stat": stat,
                    "direction": direction,
                    "line": line,
                    "pred": stack.predictions.get(stat),
                    "edge_pct": round(edge, 4),
                    "confidence": confidence,
                    "kelly_size_usd": kelly_size,
                })

    result["props"] = prop_results
    result["edges"] = sorted(edge_plays, key=lambda x: abs(x["edge_pct"]), reverse=True)

    # Save prediction + log to tracker
    if save:
        os.makedirs(_PREDICTIONS_DIR, exist_ok=True)
        fname = f"{game_date}_{home_team}_{away_team}.json"
        fpath = os.path.join(_PREDICTIONS_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        try:
            from src.prediction.prediction_tracker import log_prediction
            log_prediction(result)
        except Exception:
            pass

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Game prediction orchestrator")
    parser.add_argument("--home", required=True, help="Home team abbreviation (e.g. LAL)")
    parser.add_argument("--away", required=True, help="Away team abbreviation (e.g. BOS)")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--date", dest="game_date", default=None)
    parser.add_argument("--bankroll", type=float, default=_DEFAULT_BANKROLL)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    pred = predict_game(
        home_team=args.home,
        away_team=args.away,
        season=args.season,
        game_date=args.game_date,
        bankroll=args.bankroll,
        save=not args.no_save,
    )

    wp = pred["win_probability"]
    gm = pred["game_models"]
    print(f"\n{args.home} vs {args.away}  ({args.season})")
    print(f"  Win prob home:  {wp.get('home_win_prob', 'n/a')}")
    print(f"  Total est:      {gm.get('total_est', 'n/a')}")
    print(f"  Spread est:     {gm.get('spread_est', 'n/a')}")
    print(f"  Blowout prob:   {gm.get('blowout_prob', 'n/a')}")
    print(f"  Props modeled:  {len(pred['props'])} players")
    print(f"  Edge plays:     {len(pred['edges'])}")
    for ep in pred["edges"][:5]:
        print(f"    {ep['player_name']} {ep['stat']} {ep['direction']} "
              f"{ep['line']} | edge={ep['edge_pct']:.1%} kelly=${ep['kelly_size_usd']:.0f}")
