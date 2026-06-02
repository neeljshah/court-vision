"""
predictions_router.py — Phase E5 extended prediction endpoints.

Routes:
    POST /predictions/injury-risk          Injury risk + load management
    POST /predictions/breakout             Breakout potential score
    POST /predictions/lineup-optimizer     DFS lineup optimizer
    GET  /predictions/today                Tonight's game predictions
    GET  /predictions/props/{player_id}    Per-player prop projections
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()


# ── Pydantic request models ───────────────────────────────────────────────────

class InjuryRiskRequest(BaseModel):
    player_id: int
    season: str = "2025-26"


class BreakoutRequest(BaseModel):
    player_id: int
    opponent_team: Optional[str] = None
    season: str = "2025-26"


class LineupOptimizerRequest(BaseModel):
    game_ids: List[str]
    budget: float = 50000.0
    platform: str = "draftkings"


class PropsRequest(BaseModel):
    player_id: int
    opp_team: Optional[str] = None
    season: str = "2025-26"


class GamePredictionRequest(BaseModel):
    home_team: str
    away_team: str
    season: str = "2025-26"
    player_ids: Optional[List[str]] = None
    lines: Optional[dict] = None
    bankroll: float = 10_000.0
    game_date: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _player_name_from_id(player_id: int) -> Optional[str]:
    """Resolve NBA player_id to display name via nba_api."""
    try:
        from nba_api.stats.endpoints import commonplayerinfo
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        row = info.common_player_info.get_data_frame()
        if row.empty:
            return None
        return str(row.iloc[0]["DISPLAY_FIRST_LAST"])
    except Exception:
        pass
    # Fallback: scan local cached box scores
    try:
        import glob as _glob
        import json as _json
        nba_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "nba",
        )
        for path in _glob.glob(os.path.join(nba_dir, "**", "*.json"), recursive=True):
            try:
                with open(path) as fh:
                    obj = _json.load(fh)
                if isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict) and item.get("player_id") == player_id:
                            return item.get("player_name") or item.get("name")
                elif isinstance(obj, dict):
                    if obj.get("player_id") == player_id:
                        return obj.get("player_name") or obj.get("name")
            except Exception:
                continue
    except Exception:
        pass
    return None


# ── POST /predictions/injury-risk ────────────────────────────────────────────

@router.post("/injury-risk")
def injury_risk(req: InjuryRiskRequest):
    """Injury risk score + load management probability for a player."""
    player_name = _player_name_from_id(req.player_id)
    if player_name is None:
        raise HTTPException(status_code=404, detail=f"Player {req.player_id} not found")

    from src.prediction.injury_risk import get_injury_risk
    from src.prediction.load_management import predict_load_management

    risk_data = get_injury_risk(player_name, season=req.season)
    load_data = predict_load_management(player_name, season=req.season)

    return {
        "player_id":           req.player_id,
        "player_name":         player_name,
        "injury_risk_score":   float(risk_data.get("risk_score", 0.0)),
        "risk_level":          risk_data.get("risk_level", "Low"),
        "load_management_prob": float(load_data.get("load_mgmt_prob", 0.0)),
        "games_missed_recent": int(risk_data.get("games_missed_recent", 0)),
        "drivers":             risk_data.get("drivers", {}),
    }


# ── POST /predictions/breakout ────────────────────────────────────────────────

@router.post("/breakout")
def breakout(req: BreakoutRequest):
    """Breakout potential score and key driving signals."""
    player_name = _player_name_from_id(req.player_id)
    if player_name is None:
        raise HTTPException(status_code=404, detail=f"Player {req.player_id} not found")

    from src.prediction.breakout_predictor import predict_breakout

    result = predict_breakout(
        player_name,
        opponent_team=req.opponent_team,
        season=req.season,
    )

    signals = result.get("signals", {})
    avgs    = result.get("season_avgs", {})
    avg_pts = float(avgs.get("pts", 0.0))
    score   = float(result.get("breakout_score", 0.0))

    return {
        "player_id":              req.player_id,
        "player_name":            player_name,
        "breakout_score":         round(score, 4),
        "predicted_pts_above_avg": round(score * avg_pts * 0.3, 2),
        "key_factors":            [k for k, v in signals.items() if v and float(v) > 0.05],
        "signals":                signals,
    }


# ── POST /predictions/lineup-optimizer ───────────────────────────────────────

@router.post("/lineup-optimizer")
def lineup_optimizer(req: LineupOptimizerRequest):
    """
    Simple greedy DFS lineup optimizer.
    Requires at least one game_id from tonight's slate.
    """
    try:
        players: list = []
        try:
            from src.data.nba_stats import NBAStats
            stats = NBAStats()
            for gid in req.game_ids:
                try:
                    boxscore = stats.get_box_score(gid)
                    if boxscore:
                        players.extend(boxscore)
                except Exception:
                    pass
        except Exception:
            pass

        if not players:
            # Return a minimal valid response when no data is available
            return {
                "optimal_lineup":  [],
                "total_salary":    0.0,
                "projected_total": 0.0,
                "platform":        req.platform,
                "note":            "No box score data available for provided game IDs",
            }

        # Greedy fill: sort by projected value, respect salary cap
        lineup: list = []
        total_sal   = 0.0
        total_pts   = 0.0
        for p in sorted(players, key=lambda x: x.get("pts", 0.0), reverse=True):
            sal = float(p.get("salary", 5000))
            if total_sal + sal <= req.budget:
                lineup.append(p)
                total_sal += sal
                total_pts += float(p.get("pts", 0.0))
            if len(lineup) >= 8:
                break

        return {
            "optimal_lineup":  lineup,
            "total_salary":    round(total_sal, 2),
            "projected_total": round(total_pts, 2),
            "platform":        req.platform,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /predictions/game ────────────────────────────────────────────────────

@router.post("/game")
def predict_game_endpoint(req: GamePredictionRequest):
    """Full game prediction: win prob + game models + player props + Kelly edges."""
    try:
        from src.prediction.game_orchestrator import predict_game
        result = predict_game(
            home_team=req.home_team,
            away_team=req.away_team,
            season=req.season,
            player_ids=req.player_ids,
            lines=req.lines,
            bankroll=req.bankroll,
            game_date=req.game_date,
            save=True,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /predictions/today ────────────────────────────────────────────────────

@router.get("/today")
def predictions_today(season: str = "2025-26"):
    """Win probabilities and top props for tonight's games via orchestrator."""
    try:
        from src.prediction.game_orchestrator import predict_game

        # Fetch tonight's matchups from nba_api scoreboard
        matchups: list = []
        try:
            from nba_api.stats.endpoints import scoreboard
            sb = scoreboard.Scoreboard()
            games_df = sb.game_header.get_data_frame()
            for _, row in games_df.iterrows():
                matchups.append({
                    "home_team": str(row.get("HOME_TEAM_ABBREVIATION", "")),
                    "away_team": str(row.get("VISITOR_TEAM_ABBREVIATION", "")),
                })
        except Exception:
            matchups = []

        if not matchups:
            # Fallback to legacy predict_today if no scoreboard data
            from src.prediction.game_prediction import predict_today
            games = predict_today(season=season)
            return {"games": games if isinstance(games, list) else [games], "season": season}

        results = []
        for m in matchups:
            if not m["home_team"] or not m["away_team"]:
                continue
            try:
                pred = predict_game(
                    home_team=m["home_team"],
                    away_team=m["away_team"],
                    season=season,
                    save=True,
                )
                results.append(pred)
            except Exception:
                results.append(m)

        return {"games": results, "season": season}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /predictions/props/{player_id} ───────────────────────────────────────

@router.get("/props/{player_id}")
def props_by_id(player_id: int, season: str = "2025-26", opp_team: str = ""):
    """Prop projections (pts/reb/ast/fg3m/stl/blk/tov) for a single player."""
    player_name = _player_name_from_id(player_id)
    if player_name is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    try:
        from src.prediction.prop_model_stack import stack_predict
        from src.prediction.dnp_predictor import predict_dnp
        from src.prediction.injury_risk import get_injury_risk

        # Build game_context so all micro-model signals (CV, matchup, etc.) flow in
        game_context = {
            "home_team": opp_team or "OPP",
            "away_team": opp_team or "OPP",
            "season": season,
        }
        stack = stack_predict(str(player_id), game_context=game_context)

        dnp_raw = predict_dnp(player_name, season=season)
        dnp_prob = float(dnp_raw) if not isinstance(dnp_raw, dict) else float(dnp_raw.get("dnp_prob", 0.0))

        injury_risk = 0.0
        try:
            injury_raw = get_injury_risk(player_name, season=season)
            injury_risk = float(injury_raw.get("risk_score", 0.0)) if isinstance(injury_raw, dict) else 0.0
        except Exception:
            injury_risk = 0.0

        return {
            "player_id":    player_id,
            "player_name":  player_name,
            "props":        {k: (None if v is None or (isinstance(v, float) and v != v)
                                 else round(float(v), 3))
                             for k, v in stack.predictions.items()},
            "dnp_prob":     round(dnp_prob, 4),
            "injury_risk":  round(injury_risk, 4),
            "suppressed":   stack.suppressed,
            "suppression_reason": stack.suppression_reason,
            "confidence":   stack.confidence,
            "edges":        {k: (None if isinstance(v, float) and v != v else v)
                             for k, v in stack.edges.items()},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
