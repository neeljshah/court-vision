import time
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.models_router import router as models_router
from api.analytics_router import router as analytics_router
from api.predictions_router import router as predictions_ext_router
from api.stitch_router import router as stitch_router
from api.dashboard_router import router as dashboard_router
from src.prediction.possession_simulator import PossessionSimulator
from src.prediction.prop_model_stack import stack_predict as _stack_predict
from src.prediction.betting_edge import BettingEdge
from src.prediction.win_probability import load as _load_win_prob

app = FastAPI(title="NBA AI System — Project Court Vision", version="2.0.0")
_simulator = PossessionSimulator()
_betting_edge = BettingEdge()

# ── In-process TTL cache (TTL=300s) ──────────────────────────────────────────
_CACHE: dict = {}
_TTL = 300

def _cget(key):
    entry = _CACHE.get(key)
    return entry[1] if entry and time.time() - entry[0] < _TTL else None

def _cset(key, val):
    _CACHE[key] = (time.time(), val)


class _SimGameRequest(BaseModel):
    team_a: str; team_b: str; n_sims: int = 1000
    team_a_stats: Optional[dict] = None; team_b_stats: Optional[dict] = None


class _OverProbRequest(BaseModel):
    player_id: str; stat: str; line: float
    team_a: str; team_b: str; roster_a: list[str]; roster_b: list[str]
    n_sims: int = 1000; team_a_stats: Optional[dict] = None; team_b_stats: Optional[dict] = None


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(models_router,          prefix="/predictions", tags=["predictions"])
app.include_router(predictions_ext_router, prefix="/predictions", tags=["predictions"])
app.include_router(analytics_router,       prefix="/analytics",   tags=["analytics"])
app.include_router(stitch_router,          prefix="/stitch",       tags=["stitch"])
app.include_router(dashboard_router,       tags=["dashboard"])


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "model_status": {
        "possession_simulator": "loaded",
        "player_props": "available",
        "betting_edge": "loaded",
        "win_probability": "available",
        "tracking": "available",
        "re_id": "available",
    }}


@app.post("/simulate_game", tags=["simulation"])
def simulate_game(req: _SimGameRequest):
    return _simulator.simulate_game(
        req.team_a, req.team_b, n_sims=req.n_sims,
        team_a_stats=req.team_a_stats, team_b_stats=req.team_b_stats,
    )


@app.post("/over_prob", tags=["simulation"])
def over_prob(req: _OverProbRequest):
    result = _simulator.simulate_game(
        req.team_a, req.team_b, n_sims=req.n_sims,
        team_a_stats=req.team_a_stats, team_b_stats=req.team_b_stats,
        player_stats={req.team_a: req.roster_a, req.team_b: req.roster_b},
        _return_raw=True,
    )
    stat_dist = result.get("player_distributions", {}).get(req.player_id, {}).get(req.stat, {})
    vals = stat_dist.get("_values")
    prob = float((vals > req.line).mean()) if vals is not None else 0.5
    return {"player_id": req.player_id, "stat": req.stat, "line": req.line,
            "over_prob": round(prob, 4), "mean": stat_dist.get("mean", 0.0)}


class _SimRequest(BaseModel):
    team_a: str; team_b: str; n_sims: int = 1000
    player_stats: Optional[dict] = None


@app.post("/simulate", tags=["simulation"])
def simulate(req: _SimRequest):
    key = (req.team_a, req.team_b, req.n_sims)
    cached = _cget(key)
    if cached is not None:
        return cached
    result = _simulator.simulate_game(
        req.team_a, req.team_b, n_sims=req.n_sims, player_stats=req.player_stats,
    )
    result.setdefault("player_distributions", {})
    _cset(key, result)
    return result


@app.get("/props/{player_id}", tags=["props"])
def props(player_id: str, opp_team: str = "GSW", season: str = "2025-26"):
    key = ("props", player_id, opp_team, season)
    cached = _cget(key)
    if cached is not None:
        return cached
    stack = _stack_predict(player_id, game_context={"away_team": opp_team, "season": season})
    result = {k: round(float(v), 3) for k, v in stack.predictions.items()
              if not (isinstance(v, float) and v != v)}
    if not result:
        # player_id may be a name rather than a numeric ID; fall back to predict_props
        from src.prediction.player_props import predict_props as _pp
        result = _pp(player_id, opp_team, season=season)
    _cset(key, result)
    return result


@app.get("/edge/{game_id}", tags=["betting"])
def edge(game_id: str, home: str = "", away: str = "",
         home_odds: int = -110, away_odds: int = -110):
    try:
        try:
            _wp = _load_win_prob().predict(home, away)
            home_win_prob = float(_wp.get("home_win_prob", 0.5))
        except Exception:
            home_win_prob = 0.5
        bets = []
        for team, odds, prob_key in [
            (home, home_odds, "home"), (away, away_odds, "away")
        ]:
            if not team:
                continue
            team_prob = home_win_prob if prob_key == "home" else 1.0 - home_win_prob
            ev = _betting_edge.evaluate(team_prob, odds)
            if ev.get("edge", 0) > 0:
                bets.append({"team": team, **ev})
        return {"game_id": game_id, "edges": bets}
    except Exception as exc:
        return {"game_id": game_id, "edges": [], "error": str(exc)}


@app.get("/win-prob/{game_id}", tags=["predictions"])
def win_prob_game(game_id: str, home: str = "", away: str = "", season: str = "2025-26"):
    try:
        model = _load_win_prob()
        result = model.predict(home, away, season=season)
        ci_half = 0.05
        wp = result.get("home_win_prob", 0.5)
        return {**result, "game_id": game_id,
                "confidence_interval": [round(wp - ci_half, 4), round(wp + ci_half, 4)]}
    except Exception as exc:
        return {"game_id": game_id, "win_probability": 0.5,
                "confidence_interval": [0.45, 0.55], "error": str(exc)}


@app.get("/lineup/{team}", tags=["lineup"])
def lineup(team: str):
    from src.data.injury_monitor import InjuryMonitor
    try:
        monitor = InjuryMonitor()
        injured = {p.get("player_name", "") for p in monitor.get_team_injuries(team)
                   if p.get("status") in ("Out", "Doubtful")}
        return {"team": team, "dnp": sorted(injured),
                "active_count": "unknown — filter applied"}
    except Exception as exc:
        return {"team": team, "dnp": [], "error": str(exc)}


_BACKTEST_CACHE: dict = {}
_BACKTEST_TTL = 86400  # 24 hours


class _BacktestRequest(BaseModel):
    seasons: Optional[list] = None
    edge_threshold: float = 0.04


@app.post("/backtest/{stat}", tags=["backtest"])
def backtest_stat(stat: str, req: _BacktestRequest = None):
    """Run prop backtest for a stat. Returns mae, hit_rate_over, roi. Cached 24h."""
    from fastapi import HTTPException
    from src.prediction.prop_backtester import backtest_props, STATS
    if stat not in STATS:
        raise HTTPException(status_code=400, detail=f"stat must be one of {STATS}")
    req = req or _BacktestRequest()
    cache_key = (stat, tuple(req.seasons or []), req.edge_threshold)
    entry = _BACKTEST_CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _BACKTEST_TTL:
        return entry[1]
    result = backtest_props(seasons=req.seasons, stat=stat, edge_threshold=req.edge_threshold)
    n_over = result.wins
    n_bets = result.n_bets
    payload = {
        "stat":            stat,
        "n":               result.n_predictions,
        "mae":             round(result.mae, 4),
        "hit_rate_over":   round(n_over / max(n_bets, 1), 4),
        "roi_at_break_even_odds": round(result.roi_pct, 4),
        "passed_gate":     result.passed_gate,
        "edge_buckets":    result.edge_buckets,
    }
    _BACKTEST_CACHE[cache_key] = (time.time(), payload)
    return payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
