import asyncio
import json
import logging
import os
import time
from typing import Optional

_STARTUP_TIME = time.time()
log = logging.getLogger(__name__)

# Default to offline mode so API requests never hang on stats.nba.com edge blocks.
# Operators can set NBA_OFFLINE=0 explicitly to allow live fetches.
os.environ.setdefault("NBA_OFFLINE", "1")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.models_router import router as models_router
from api.analytics_router import router as analytics_router
from api.predictions_router import router as predictions_ext_router
from api.stitch_router import router as stitch_router
from api.dashboard_router import router as dashboard_router
from api.devig_router import router as devig_router
from api.clv_router import router as clv_router
from api.live_game_router import router as live_game_router
try:
    from api.courtvision_router import router as courtvision_router
    _COURTVISION_AVAILABLE = True
except Exception as _cv_exc:  # graceful: missing optional deps shouldn't crash boot
    _COURTVISION_AVAILABLE = False
    log.warning("courtvision_router unavailable: %s", _cv_exc)
from pathlib import Path as _Path

from src.prediction.possession_simulator import PossessionSimulator
from src.prediction.prop_model_stack import stack_predict as _stack_predict
from src.prediction.betting_edge import BettingEdge
from src.prediction.win_probability import load as _load_win_prob

try:
    from src.prediction.live_win_probability import load_inference_engine, LiveWinProbInference
    _LIVE_INFERENCE_AVAILABLE = True
except ImportError:
    _LIVE_INFERENCE_AVAILABLE = False

if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=os.environ["SENTRY_DSN"],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.0")),
            environment=os.environ.get("SENTRY_ENV", "prod"),
        )
        log.info("sentry initialized for %s", os.environ.get("SENTRY_ENV", "prod"))
    except Exception as _sentry_exc:
        log.warning("sentry init failed: %s", _sentry_exc)

app = FastAPI(title="NBA AI System — Project Court Vision", version="2.0.0")

# Strong references to background asyncio Tasks.
# asyncio.create_task / create_supervised_task returns a Task that the event loop
# holds only via a WEAK reference.  Without an explicit strong-ref container the
# GC can collect the Task object mid-run, silently killing the WS feed or loop.
# CPython asyncio docs explicitly warn about this pattern.
_BG_TASKS: set = set()


def _find_latest_tracking_csv() -> "Optional[str]":
    """Return most recently modified tracking_data.csv for CV fatigue minutes."""
    tracking_dir = _Path(__file__).resolve().parent.parent / "data" / "tracking"
    if not tracking_dir.exists():
        return None
    csvs = sorted(
        tracking_dir.rglob("tracking_data.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return str(csvs[0]) if csvs else None


_simulator = PossessionSimulator(cv_minutes_csv=_find_latest_tracking_csv())
_betting_edge = BettingEdge()

# ── In-process TTL cache (TTL=300s) ──────────────────────────────────────────
_CACHE: dict = {}
_TTL = 300

def _cget(key):
    entry = _CACHE.get(key)
    return entry[1] if entry and time.time() - entry[0] < _TTL else None

def _cset(key, val):
    _CACHE[key] = (time.time(), val)


def _with_timeout(fn, timeout_sec: float = 8.0):
    """Run fn() on a worker thread and return its result, or raise TimeoutError.

    Prevents individual handlers from stalling the event loop when a downstream
    helper blocks (stats.nba.com, bbref, pinnacle). Windows-friendly — no signals.
    """
    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=1) as _tp:
        fut = _tp.submit(fn)
        return fut.result(timeout=timeout_sec)


class _SimGameRequest(BaseModel):
    team_a: str; team_b: str; n_sims: int = 1000
    team_a_stats: Optional[dict] = None; team_b_stats: Optional[dict] = None


class _OverProbRequest(BaseModel):
    player_id: str; stat: str; line: float
    team_a: str; team_b: str; roster_a: list[str]; roster_b: list[str]
    n_sims: int = 1000; team_a_stats: Optional[dict] = None; team_b_stats: Optional[dict] = None


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

try:
    from starlette.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=500)
    log.info("api.main: GZip middleware registered (minimum_size=500)")
except Exception as _gzip_exc:  # never break boot if starlette.middleware.gzip missing
    log.warning("api.main: GZip middleware unavailable (non-fatal): %s", _gzip_exc)

# Mount /static so the CV simple page (cv_simple.css/js) resolves on api.main:app.
# live_v2_app.py already mounts this for the cloud entrypoint; api.main needs it too.
try:
    from fastapi.staticfiles import StaticFiles
    _static_dir = _Path(__file__).resolve().parent / "static"
    if _static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
        log.info("api.main: mounted /static from %s", _static_dir)
except Exception as _static_exc:  # never let static mounting break boot
    log.warning("api.main: /static mount failed (non-fatal): %s", _static_exc)

app.include_router(models_router,          prefix="/predictions", tags=["predictions"])
app.include_router(predictions_ext_router, prefix="/predictions", tags=["predictions"])
app.include_router(analytics_router,       prefix="/analytics",   tags=["analytics"])
app.include_router(stitch_router,          prefix="/stitch",       tags=["stitch"])
app.include_router(dashboard_router,       tags=["dashboard"])
app.include_router(devig_router,           tags=["devig"])
app.include_router(clv_router,             tags=["clv"])
app.include_router(live_game_router,       tags=["live"])
if _COURTVISION_AVAILABLE:
    app.include_router(courtvision_router, tags=["courtvision"])
    try:
        from api.courtvision_router import register_with_app as _cv_register
        _cv_register(app)
    except Exception as _cv_reg_exc:  # never let middleware-wiring break boot
        log.warning("courtvision middleware wiring failed: %s", _cv_reg_exc)

try:
    from api._risk_router import router as _risk_router
    app.include_router(_risk_router, tags=["risk"])
except Exception as _risk_exc:
    log.warning("risk_router unavailable: %s", _risk_exc)


@app.on_event("startup")
async def _start_ws_subscribers() -> None:
    """Start DK/FD/BR WebSocket prop-odds subscribers as supervised tasks.

    Gated by DK_WS_ENABLED / FD_WS_ENABLED / BR_WS_ENABLED env vars
    (default OFF => byte-identical behaviour to the pre-WS build).
    Each feed writes to a _ws-suffixed CSV file (<date>_dk_ws.csv etc.)
    so there is no dual-writer race with the HTTP scrapers, which remain
    the fallback and the source for pin/bov which have no WS feed.
    Exceptions per-feed are caught and logged; a failure to start one
    feed never blocks the others or crashes the server.
    """
    _WS_TRUTHY = ("1", "true", "yes", "on")

    if os.environ.get("DK_WS_ENABLED", "").strip() in _WS_TRUTHY:
        try:
            from scripts.task_supervisor import create_supervised_task
            from scripts.draftkings_ws import start_dk_ws
            _t = create_supervised_task("dk_ws", start_dk_ws)
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("api.main: DK WS subscriber task started (supervised)")
        except Exception as _dk_exc:  # noqa: BLE001
            log.warning("api.main: DK WS subscriber failed to start (non-fatal): %s", _dk_exc)

    if os.environ.get("FD_WS_ENABLED", "").strip() in _WS_TRUTHY:
        try:
            from scripts.task_supervisor import create_supervised_task
            from scripts.fanduel_ws import start_fd_ws
            _t = create_supervised_task("fd_ws", start_fd_ws)
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("api.main: FD WS subscriber task started (supervised)")
        except Exception as _fd_exc:  # noqa: BLE001
            log.warning("api.main: FD WS subscriber failed to start (non-fatal): %s", _fd_exc)

    if os.environ.get("BR_WS_ENABLED", "").strip() in _WS_TRUTHY:
        try:
            from scripts.task_supervisor import create_supervised_task
            from scripts.betrivers_ws import start_br_ws
            _t = create_supervised_task("br_ws", start_br_ws)
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("api.main: BR WS subscriber task started (supervised)")
        except Exception as _br_exc:  # noqa: BLE001
            log.warning("api.main: BR WS subscriber failed to start (non-fatal): %s", _br_exc)

    # DK in-play WS subscriber — sub-second live prop-line latency during games.
    # Writes data/lines/<date>_dk_inplay_ws.csv (book="dk_inplay").
    # Gated: set DK_INPLAY_WS_ENABLED=1 AND fill _INPLAY_SUBCATEGORY_IDS in
    # scripts/dk_inplay_ws.py (discovered on residential network during live game).
    if os.environ.get("DK_INPLAY_WS_ENABLED", "").strip() in _WS_TRUTHY:
        try:
            from scripts.task_supervisor import create_supervised_task
            from scripts.dk_inplay_ws import start_dk_inplay_ws
            _t = create_supervised_task("dk_inplay_ws", start_dk_inplay_ws)
            _BG_TASKS.add(_t); _t.add_done_callback(_BG_TASKS.discard)
            log.info("api.main: DK in-play WS subscriber task started (supervised)")
        except Exception as _dk_inplay_exc:  # noqa: BLE001
            log.warning(
                "api.main: DK in-play WS subscriber failed to start (non-fatal): %s",
                _dk_inplay_exc,
            )

@app.on_event("startup")
async def _prewarm_cv_board() -> None:
    """Pre-warm the CV board and slate builder in the background so the first page
    load is instant.  Runs concurrently with boot — never blocks or crashes startup.
    """
    async def _warm() -> None:
        try:
            _today = time.strftime("%Y-%m-%d")
            _g4_date = "2026-06-10"
            # Warm build_board for today and the hard-coded G4 date.
            from api._cv_board import build_board as _build_board
            import concurrent.futures as _cf
            _loop = asyncio.get_event_loop()
            _ex = _cf.ThreadPoolExecutor(max_workers=1)
            for _d in dict.fromkeys([_today, _g4_date]):  # dedup, order-preserving
                try:
                    await _loop.run_in_executor(_ex, _build_board, _d)
                    log.info("api.main: pre-warm build_board(%s) done", _d)
                except Exception as _bd_exc:
                    log.warning("api.main: pre-warm build_board(%s) failed (non-fatal): %s", _d, _bd_exc)
            # Best-effort hit the slate builder for today's date.
            if _COURTVISION_AVAILABLE:
                try:
                    from api.courtvision_router import _build_slate
                    await _loop.run_in_executor(_ex, _build_slate, _today)
                    log.info("api.main: pre-warm _build_slate(%s) done", _today)
                except Exception as _sl_exc:
                    log.warning("api.main: pre-warm _build_slate(%s) failed (non-fatal): %s", _today, _sl_exc)
            _ex.shutdown(wait=False)
        except Exception as _warm_exc:
            log.warning("api.main: _prewarm_cv_board background task failed (non-fatal): %s", _warm_exc)

    # Non-blocking: create as a background task so boot is never delayed.
    _t = asyncio.create_task(_warm())
    _BG_TASKS.add(_t)
    _t.add_done_callback(_BG_TASKS.discard)


try:
    from api.lines_router import router as _lines_router
    app.include_router(_lines_router, tags=["lines"])
except Exception as _lines_exc:
    log.warning("lines_router unavailable: %s", _lines_exc)


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

@app.get("/health/ops", tags=["health"])
def health_ops():
    """Operational pipeline metrics: scraper lag, CLV hit rate, drift flags, uptime."""
    root = os.path.dirname(os.path.dirname(__file__))
    mdir = os.path.join(root, "data", "models")
    daily_bet_count, clv_hit_rate, drift_flags, scraper_lag_min = 0, None, [], None
    bet_log = os.path.join(mdir, "bet_log.json")
    if os.path.exists(bet_log):
        try:
            today = time.strftime("%Y-%m-%d")
            bets = json.load(open(bet_log, encoding="utf-8"))
            if isinstance(bets, list):
                daily_bet_count = sum(1 for b in bets if str(b.get("date", "")).startswith(today))
        except Exception: pass
    clv_log = os.path.join(mdir, "clv_log.json")
    if os.path.exists(clv_log):
        try:
            clv_data = json.load(open(clv_log, encoding="utf-8"))
            if clv_data:
                vals = [float(e["clv"]) for e in clv_data if "clv" in e]
                clv_hit_rate = round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None
        except Exception: pass
    qpath = os.path.join(mdir, "quarantine_state.json")
    if os.path.exists(qpath):
        try:
            drift_flags = json.load(open(qpath, encoding="utf-8")).get("quarantined", [])
        except Exception: pass
    db_path = os.path.join(root, "data", "nba_ai.db")
    if os.path.exists(db_path):
        try:
            import sqlite3, datetime as _dt
            with sqlite3.connect(db_path) as _c:
                _row = _c.execute("SELECT MAX(completed_at) FROM scraper_runs WHERE status='done'").fetchone()
            if _row and _row[0]:
                _last = _dt.datetime.fromisoformat(str(_row[0]).replace("Z", "+00:00")).astimezone(_dt.timezone.utc)
                scraper_lag_min = round((_dt.datetime.now(_dt.timezone.utc) - _last).total_seconds() / 60, 1)
        except Exception: pass
    return {"status": "ok",
            "scraper_lag_min": scraper_lag_min, "model_inference_ms_p95": None,
            "daily_bet_count": daily_bet_count, "clv_hit_rate": clv_hit_rate,
            "drift_flags": drift_flags, "last_slate_duration_min": None,
            "uptime_hours": round((time.time() - _STARTUP_TIME) / 3600, 2)}


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
    game_context = {"away_team": opp_team, "season": season}
    try:
        stack = _with_timeout(lambda: _stack_predict(player_id, game_context=game_context), 10.0)
    except Exception as exc:
        return {"player_id": player_id, "opp_team": opp_team, "season": season,
                "error": f"timeout or error: {exc}"}
    result = {k: round(float(v), 3) for k, v in stack.predictions.items()
              if not (isinstance(v, float) and v != v)}
    if not result:
        # stack_predict requires a numeric ID for name lookup — try treating
        # player_id as a display name directly via player_props
        from src.prediction.player_props import predict_props as _pp
        raw = _pp(player_id, opp_team, season=season)
        # Re-stack with the resolved name so micro-signals still apply
        if raw:
            name = raw.get("player_name", player_id)
            from nba_api.stats.static import players as _ps
            matches = [p for p in _ps.get_players()
                       if p["full_name"].lower() == str(name).lower()]
            if matches:
                stack2 = _stack_predict(str(matches[0]["id"]), game_context=game_context)
                result = {k: round(float(v), 3) for k, v in stack2.predictions.items()
                          if not (isinstance(v, float) and v != v)}
            if not result:
                result = {k: round(float(v), 3) for k, v in raw.items()
                          if isinstance(v, (int, float)) and k != "player_name"}
    _cset(key, result)
    return result


@app.get("/edge/{game_id}", tags=["betting"])
def edge(game_id: str, home: str = "", away: str = "",
         home_odds: int = -110, away_odds: int = -110):
    try:
        try:
            _wp = _with_timeout(lambda: _load_win_prob().predict(home, away), 8.0)
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
    """Return win probability for a game. Uses LiveWinProbInference when available."""
    try:
        if _LIVE_INFERENCE_AVAILABLE:
            engine: LiveWinProbInference = load_inference_engine(device="cpu")
            game_dict = {"home_team": home, "away_team": away, "season": season, "possessions": []}
            result = engine.update(game_dict, possession_idx=0)
            wp = float(result.get("win_prob_home", 0.5))
            ci_half = 0.05
            return {
                "game_id": game_id,
                "home_win_prob": round(wp, 4),
                "win_prob_home": round(wp, 4),
                "source": result.get("source", "live_inference"),
                "confidence": result.get("confidence", 1.0),
                "inference_ms": result.get("inference_ms", 0.0),
                "confidence_interval": [round(wp - ci_half, 4), round(wp + ci_half, 4)],
            }
        # Fallback: static XGBoost baseline
        model = _load_win_prob()
        result = _with_timeout(lambda: model.predict(home, away, season=season), 8.0)
        ci_half = 0.05
        wp = result.get("home_win_prob", 0.5)
        return {**result, "game_id": game_id, "source": "xgboost_baseline",
                "confidence_interval": [round(wp - ci_half, 4), round(wp + ci_half, 4)]}
    except Exception as exc:
        return {"game_id": game_id, "win_probability": 0.5, "win_prob_home": 0.5,
                "source": "error", "confidence_interval": [0.45, 0.55], "error": str(exc)}


@app.websocket("/ws/win-prob/{game_id}")
async def ws_win_prob(websocket: WebSocket, game_id: str):
    """Stream live win probability updates per possession.

    Client sends: {"possession_idx": int, "game_dict": {...}}
    Server sends: {"win_prob_home": float, "source": str, "confidence": float, "inference_ms": float}

    WebSocket closes when client disconnects.
    Target latency: <500ms per possession update.
    """
    await websocket.accept()

    if not _LIVE_INFERENCE_AVAILABLE:
        await websocket.send_json({"error": "live_win_probability module not available"})
        await websocket.close()
        return

    engine: LiveWinProbInference = load_inference_engine(device="cpu")

    try:
        while True:
            data = await websocket.receive_json()
            possession_idx: int = int(data.get("possession_idx", 0))
            game_dict: dict = data.get("game_dict", {})

            result = engine.update(game_dict, possession_idx)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("WebSocket win-prob error: %s", e)
        try:
            await websocket.send_json({"error": str(e), "win_prob_home": 0.5})
        except Exception:
            pass


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


# ── CourtVision live-board WebSocket ─────────────────────────────────────────
# Owner WS.  Delegates to api._cv_ws.cv_ws_handler (lazy import so a missing
# _cv_live.py never breaks the rest of the app on cold boot).
@app.websocket("/ws/cv/{game_id}")
async def ws_cv_board(websocket: WebSocket, game_id: str):
    """Push a live board dict every ~10 s (or when snapshot changes).

    Mirrors the contract in api._cv_live.live_board:
      board.live.is_live, .home_score, .away_score, .period, .clock,
      .minutes_remaining, .win_prob_home_live, .snapshot_age_sec, .snapshot_id.
    Falls back to pregame board (live.is_live=false) when no snapshot exists.
    """
    date = "2026-06-10"  # G4 date; extend via query-param when needed
    try:
        from api._cv_ws import cv_ws_handler
        await cv_ws_handler(websocket, game_id=game_id, date=date)
    except WebSocketDisconnect:
        pass
    except Exception as _ws_exc:
        log.warning("ws_cv_board: unhandled error for game %s: %s", game_id, _ws_exc)
        try:
            await websocket.send_json({"error": str(_ws_exc), "live": {"is_live": False}})
        except Exception:
            pass
