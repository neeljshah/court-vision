"""
execution_router.py — 13 thin wrapper endpoints for the quant dashboard.

Routes:
    GET  /api/portfolio/summary      betting_portfolio.get_portfolio_summary()
    GET  /api/portfolio/open         betting_portfolio.get_open_bets()
    POST /api/portfolio/log          betting_portfolio.log_bet()
    POST /api/portfolio/close        betting_portfolio.record_clv()
    GET  /api/alt-ladder/{player}/{stat}   alt_line_ladder.build_alt_line_ladder()
    POST /api/signals/route          signal_router.route(slate)
    GET  /api/pricing/distribution   PropPricingEngine.get_distribution()
    POST /api/pricing/vs-line        PropPricingEngine.price_vs_line()
    POST /api/arb/detect             ArbDetector.detect()
    POST /api/arb/middles            ArbDetector.detect_middles()
    GET  /api/corr-matrix            prop_corr_matrix.json
    POST /api/execution/quote        execution.route_order()
    POST /api/execution/submit       router.run() (DRY_RUN)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["execution"])

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MODELS_DIR = _DATA_DIR / "models"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_portfolio():
    from src.prediction.betting_portfolio import BettingPortfolio
    return BettingPortfolio()


# ── 1. Portfolio summary ───────────────────────────────────────────────────────

@router.get("/portfolio/summary")
def portfolio_summary():
    try:
        portfolio = _load_portfolio()
        return portfolio.get_portfolio_summary()
    except Exception as exc:
        # Return safe defaults when portfolio has no history yet
        return {
            "bankroll": 10000,
            "total_pnl": 0.0,
            "roi": 0.0,
            "clv_avg": 0.0,
            "open_count": 0,
            "drawdown_pct": 0.0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "_note": str(exc),
        }


# ── 2. Open bets ───────────────────────────────────────────────────────────────

@router.get("/portfolio/open")
def portfolio_open():
    try:
        portfolio = _load_portfolio()
        bets = portfolio.get_open_bets()
        return {"bets": bets if isinstance(bets, list) else []}
    except Exception as exc:
        return {"bets": [], "_note": str(exc)}


# ── 3. Log bet ─────────────────────────────────────────────────────────────────

class LogBetRequest(BaseModel):
    player: str
    stat: str
    direction: str
    line: float
    stake: float
    odds: int = -110
    game_id: Optional[str] = None


@router.post("/portfolio/log")
def portfolio_log(req: LogBetRequest):
    try:
        portfolio = _load_portfolio()
        bet_id = portfolio.log_bet(
            player=req.player,
            stat=req.stat,
            direction=req.direction,
            line=req.line,
            stake=req.stake,
            odds=req.odds,
            game_id=req.game_id,
        )
        return {"id": str(bet_id), "status": "logged"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 4. Close / record CLV ─────────────────────────────────────────────────────

class CloseBetRequest(BaseModel):
    id: str
    result: float
    closing_line: float


@router.post("/portfolio/close")
def portfolio_close(req: CloseBetRequest):
    try:
        portfolio = _load_portfolio()
        result = portfolio.record_clv(
            bet_id=req.id,
            result=req.result,
            closing_line=req.closing_line,
        )
        return result if isinstance(result, dict) else {"clv": result, "pnl": req.result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 5. Alt line ladder ────────────────────────────────────────────────────────

@router.get("/alt-ladder/{player}/{stat}")
def alt_ladder(player: str, stat: str):
    try:
        from src.prediction.alt_line_ladder import build_alt_line_ladder
        rows = build_alt_line_ladder(player, stat)
        if hasattr(rows, "__iter__") and not isinstance(rows, dict):
            rows_list = list(rows)
        else:
            rows_list = rows if isinstance(rows, list) else []
        return {"player": player, "stat": stat, "rows": rows_list}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 6. Signal router ──────────────────────────────────────────────────────────

class SignalRouteRequest(BaseModel):
    slate: List[Any] = []


@router.post("/signals/route")
def signals_route(req: SignalRouteRequest):
    try:
        from src.prediction.signal_router import SignalRouter
        router_obj = SignalRouter()
        signals = router_obj.route(req.slate)
        return {"signals": signals if isinstance(signals, list) else [], "count": len(signals) if isinstance(signals, list) else 0}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 7. Pricing: distribution ──────────────────────────────────────────────────

@router.get("/pricing/distribution")
def pricing_distribution(player: str, stat: str, season: str = "2025-26"):
    try:
        from src.prediction.prop_pricing_engine import PropPricingEngine
        engine = PropPricingEngine()
        dist = engine.get_distribution(player, stat, season=season)
        return dist if isinstance(dist, dict) else {"distribution": dist}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 8. Pricing: vs line ───────────────────────────────────────────────────────

class PriceVsLineRequest(BaseModel):
    player: str
    stat: str
    line: float
    season: str = "2025-26"


@router.post("/pricing/vs-line")
def pricing_vs_line(req: PriceVsLineRequest):
    try:
        from src.prediction.prop_pricing_engine import PropPricingEngine
        engine = PropPricingEngine()
        result = engine.price_vs_line(req.player, req.stat, req.line, season=req.season)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 9. Arb detect ─────────────────────────────────────────────────────────────

class ArbRequest(BaseModel):
    markets: List[Any] = []


@router.post("/arb/detect")
def arb_detect(req: ArbRequest):
    try:
        from src.prediction.betting_edge import ArbDetector
        detector = ArbDetector()
        arbs = detector.detect(req.markets)
        return {"arbs": arbs if isinstance(arbs, list) else [], "count": len(arbs) if isinstance(arbs, list) else 0}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 10. Arb middles ───────────────────────────────────────────────────────────

@router.post("/arb/middles")
def arb_middles(req: ArbRequest):
    try:
        from src.prediction.betting_edge import ArbDetector
        detector = ArbDetector()
        middles = detector.detect_middles(req.markets)
        return {"middles": middles if isinstance(middles, list) else [], "count": len(middles) if isinstance(middles, list) else 0}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 11. Correlation matrix ────────────────────────────────────────────────────

@router.get("/corr-matrix")
def corr_matrix():
    path = _MODELS_DIR / "prop_corr_matrix.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="prop_corr_matrix.json not found. Run: python -m src.prediction.betting_portfolio --compute-corr"
        )
    try:
        with open(path) as f:
            data = json.load(f)
        # Normalise: expect either {"stats": [...], "matrix": [[...]]} or a raw dict
        if isinstance(data, dict) and "matrix" in data:
            return data
        # Build from flat dict
        stats = list(data.keys())
        matrix = [[data.get(r, {}).get(c, 0.0) for c in stats] for r in stats]
        return {"stats": stats, "matrix": matrix}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 12. Execution quote ───────────────────────────────────────────────────────

class ExecutionQuoteRequest(BaseModel):
    player: str
    stat: str
    direction: str
    stake: float
    line: float
    venue: Optional[str] = None


@router.post("/execution/quote")
def execution_quote(req: ExecutionQuoteRequest):
    try:
        from court_vision_router.execution import route_order
        result = route_order(
            player=req.player,
            stat=req.stat,
            direction=req.direction,
            stake=req.stake,
            line=req.line,
        )
        return result if isinstance(result, dict) else {"result": result}
    except ImportError:
        return {
            "venues": [{"venue": "polymarket", "available": req.stake, "price": 0.5, "slippage_bps": 0}],
            "total_fillable": req.stake,
            "weighted_price": 0.5,
            "_note": "court_vision_router not available (DRY_RUN)",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 13. Execution submit ──────────────────────────────────────────────────────

@router.post("/execution/submit")
def execution_submit(req: ExecutionQuoteRequest):
    try:
        from court_vision_router.router import run as _run
        result = _run(
            player=req.player,
            stat=req.stat,
            direction=req.direction,
            stake=req.stake,
            line=req.line,
            dry_run=True,
        )
        return result if isinstance(result, dict) else {"status": "submitted", "dry_run": True}
    except ImportError:
        return {
            "status": "dry_run",
            "dry_run": True,
            "order_id": None,
            "_note": "court_vision_router not available",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
