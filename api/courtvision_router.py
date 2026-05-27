"""courtvision_router.py — CourtVision UI routes.

Routes: /tonight, /parlays, /share/{slug} (+ qr.svg), /plus_ev, /healthz,
        /api/{slate, bet/{id}, parlays, plus_ev}.
Helpers in api._courtvision_data. Parlay engine in src.prediction.parlay_engine.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from api._courtvision_data import (
    grade_bet, load_lines_csv, load_slate_csv, slate_no_lines,
)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    _public_limit = _limiter.limit("60/minute")
except Exception:
    _limiter = None
    _public_limit = lambda f: f  # noqa: E731

def register_with_app(app) -> None:
    from api._courtvision_middleware import install; install(app, _limiter)
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))
_PRED_DIR = _ROOT / "data" / "predictions"
_LINES_DIR = _ROOT / "data" / "lines"
_BANKROLL_DEFAULT, _TOP_N, _TTL_SEC, _SHARE_TOP_N = 100.0, 15, 300, 8
_PUBLIC_BASE_URL = __import__("os").environ.get("COURTVISION_PUBLIC_URL", "").rstrip("/")
_STAT_SIGMA = {"pts": 5.79, "reb": 2.38, "ast": 1.70, "fg3m": 1.12, "stl": 0.90, "blk": 0.55, "tov": 1.12}  # ~ MAE x 1.253
_STATS = tuple(_STAT_SIGMA.keys())

router = APIRouter()
_CACHE: dict = {}


def _today_et() -> str:
    """Default date: today (US/Eastern), else fall back to most recent slate."""
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    return today if _slate_csv_path(today) else (_latest_slate_date() or today)


def _slate_csv_path(date: str) -> Optional[Path]:
    for name in (f"slate_{date}_post_inj_refresh.csv", f"slate_{date}.csv"):
        p = _PRED_DIR / name
        if p.exists():
            return p
    return None


def _lines_csv_path(date: str) -> Optional[Path]:
    p = _LINES_DIR / f"lines_{date}.csv"
    return p if p.exists() else None


def _latest_slate_date() -> Optional[str]:
    if not _PRED_DIR.exists():
        return None
    dates = set()
    for p in _PRED_DIR.glob("slate_*.csv"):
        parts = p.stem.split("_")
        if len(parts) >= 2 and len(parts[1]) == 10:
            dates.add(parts[1])
    return max(dates) if dates else None


def _build_slate(date: str) -> dict:
    """Cached slate builder. Returns the JSON envelope dict."""
    cache_key = ("slate", date)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC:
        return entry[1]

    slate_path = _slate_csv_path(date)
    if slate_path is None:
        envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
            "bankroll_default_dollars": _BANKROLL_DEFAULT, "stale_data": True,
            "has_lines": False, "latest_available": _latest_slate_date(),
            "summary": {"n_bets": 0, "avg_ev_pct": 0.0, "n_over": 0, "n_under": 0},
            "bets": []}
        _CACHE[cache_key] = (time.time(), envelope)
        return envelope

    slate_rows = load_slate_csv(slate_path, _STATS)
    # Lines source order: live consolidated (multi-book scrapers) > manual CSV.
    from api._courtvision_odds import consolidate_for_slate
    line_rows = consolidate_for_slate(date)
    lines_path = _lines_csv_path(date)
    if not line_rows and lines_path is not None:
        line_rows = load_lines_csv(lines_path)
    has_lines = bool(line_rows)
    if has_lines:
        ps_idx = {(r["player_name"].lower(), r["stat"]): r for r in slate_rows.values()}
        bets = [grade_bet(ps_idx[(ln["player"].lower(), ln["stat"])], ln,
                          _STAT_SIGMA, _BANKROLL_DEFAULT)
                for ln in line_rows
                if ln["stat"] in _STATS and (ln["player"].lower(), ln["stat"]) in ps_idx]
        bets.sort(key=lambda b: (b["ev_pct"] is None, -(b["ev_pct"] or 0.0)))
        bets = bets[:_TOP_N]
    else:
        bets = slate_no_lines(slate_rows, _STATS, _TOP_N)

    _log = __import__("logging").getLogger(__name__)
    try: from api._courtvision_form import attach_form; attach_form(bets)
    except Exception as exc: _log.warning("attach_form: %s", exc)
    try: from src.llm.bet_narrator import narrate_slate; narrate_slate(bets, date)
    except Exception as exc: _log.warning("narrate_slate: %s", exc)

    evs = [b["ev_pct"] for b in bets if b.get("ev_pct") is not None]
    envelope = {"date": date, "generated_at": datetime.utcnow().isoformat() + "Z",
        "bankroll_default_dollars": _BANKROLL_DEFAULT,
        "stale_data": date != _today_et(),
        "has_lines": has_lines, "latest_available": _latest_slate_date(),
        "summary": {"n_bets": len(bets), "avg_ev_pct": round(sum(evs)/len(evs), 2) if evs else 0.0,
                    "n_over": sum(1 for b in bets if b["side"] == "OVER"),
                    "n_under": sum(1 for b in bets if b["side"] == "UNDER")},
        "bets": bets}
    _CACHE[cache_key] = (time.time(), envelope)
    return envelope


def _build_parlays(date: str, max_legs: int, min_ev_pct: float, seed: int = 0) -> dict:
    cache_key = ("parlays", date, max_legs, min_ev_pct, seed)
    entry = _CACHE.get(cache_key)
    if entry and time.time() - entry[0] < _TTL_SEC: return entry[1]
    env = _build_slate(date); bets = env.get("bets", []); has_lines = env.get("has_lines", False)
    gen_at = datetime.utcnow().isoformat() + "Z"
    if not bets or not has_lines:
        out = {"date": date, "generated_at": gen_at, "n_parlays": 0, "has_lines": has_lines, "parlays": []}
    else:
        from src.prediction.parlay_engine import ParlayEngine
        parlays = ParlayEngine(bets, rng_seed=seed).enumerate_parlays(max_legs=max_legs, min_ev_pct=min_ev_pct)
        out = {"date": date, "generated_at": gen_at, "n_parlays": len(parlays), "has_lines": True, "parlays": parlays}
    _CACHE[cache_key] = (time.time(), out)
    return out


# ── routes ───────────────────────────────────────────────────────────────────
@router.get("/tonight", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def tonight(request: Request, date: str = Query(default_factory=_today_et),
            side: str = Query("ALL"), min_ev: float = Query(-999.0)):
    slate = _build_slate(date)
    side_u = (side or "ALL").upper()
    if side_u in ("OVER", "UNDER") or min_ev > -999.0:
        bets = [b for b in slate["bets"]
                if (side_u == "ALL" or b["side"] == side_u)
                and (b.get("ev_pct") is None or b["ev_pct"] >= min_ev)]
        slate = {**slate, "bets": bets}
    return _TEMPLATES.TemplateResponse("tonight.html",
        {"request": request, "slate": slate, "side": side_u, "min_ev": min_ev})


@router.get("/api/slate", tags=["courtvision"])
def api_slate(date: str = Query(default_factory=_today_et)):
    return JSONResponse(_build_slate(date))


@router.get("/api/bet/{bet_id}", tags=["courtvision"])
def api_bet(bet_id: str, request: Request, date: str = Query(default_factory=_today_et),
            partial: int = 0):
    m = next((b for b in _build_slate(date)["bets"] if b["bet_id"] == bet_id), None)
    if m is None:
        if partial: return HTMLResponse('<div class="pending">not found</div>', 404)
        raise HTTPException(404, detail="bet not found")
    return (_TEMPLATES.TemplateResponse("_bet_card_reasoning.html",
            {"request": request, "bet": m}) if partial else JSONResponse(m))


@router.get("/api/parlays", tags=["courtvision"])
def api_parlays(date: str = Query(default_factory=_today_et),
                max_legs: int = Query(5, ge=2, le=5),
                min_ev_pct: float = Query(5.0, ge=-100.0, le=500.0),
                seed: int = Query(0, ge=0, le=10**9)):
    return JSONResponse(_build_parlays(date, max_legs, min_ev_pct, seed))


@router.get("/api/auto_parlay", tags=["courtvision"])
def api_auto_parlay(date: str = Query(default_factory=_today_et),
                    stake: float = Query(20.0, ge=1.0, le=10000.0),
                    max_legs: int = Query(5, ge=2, le=5)):
    """Highest-EV parlay whose Kelly stake fits the requested $stake."""
    c = [p for p in _build_parlays(date, max_legs, 5.0, 0).get("parlays", [])
         if p["kelly_stake_dollars"] <= stake]
    return JSONResponse({"date": date, "stake": stake, "max_legs": max_legs,
                         "pick": c[0] if c else None, "n_candidates_under_stake": len(c)})


_SHARE_HIDE = ("kelly_stake_dollars", "kelly_pct", "market_prob", "model_prob")

@router.get("/share/{slug}", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def share(slug: str, request: Request):
    slate = _build_slate(slug)
    if not slate.get("bets"):
        raise HTTPException(status_code=404, detail="no slate for this slug")
    shown = [{k: v for k, v in b.items() if k not in _SHARE_HIDE}
             for b in slate["bets"][:_SHARE_TOP_N]]
    evs = [b.get("ev_pct") for b in shown if b.get("ev_pct") is not None]
    avg_ev = round(sum(evs) / len(evs), 2) if evs else 0.0
    from api._courtvision_data import share_text
    return _TEMPLATES.TemplateResponse("share.html",
        {"request": request, "slate": slate, "shown": shown,
         "avg_ev": avg_ev, "share_text": share_text(slate, shown)})


@router.get("/share/{slug}/qr.svg", tags=["courtvision"])
def share_qr(slug: str, request: Request):
    import io, qrcode
    from qrcode.image.svg import SvgPathImage
    base = _PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    q = qrcode.QRCode(box_size=8, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(f"{base}/share/{slug}"); q.make(fit=True)
    buf = io.BytesIO(); q.make_image(image_factory=SvgPathImage).save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/healthz", tags=["courtvision"])
def healthz():
    from api._courtvision_data import healthz_payload
    return JSONResponse(healthz_payload(_ROOT, _latest_slate_date()))


@router.get("/cv", tags=["courtvision"])
def cv_shortlink(): return RedirectResponse(url="/tonight", status_code=307)


@router.get("/api/odds/{date}.json", tags=["courtvision"])
def api_odds_for_date(date: str, stat: str = Query(""), player: str = Query("")):
    """Multi-book scraped prop odds for `date`. Filterable by stat + player."""
    from api._courtvision_odds import odds_env
    return JSONResponse(odds_env(date, stat, player))

@router.get("/api/odds", tags=["courtvision"])
def api_odds_today(stat: str = Query(""), player: str = Query("")):
    from api._courtvision_odds import odds_env
    return JSONResponse(odds_env(_today_et(), stat, player))

@router.get("/odds", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def odds_page(request: Request, date: str = Query(default_factory=_today_et),
              stat: str = Query(""), player: str = Query("")):
    from api._courtvision_odds import odds_env
    return _TEMPLATES.TemplateResponse("odds.html",
        {"request": request, "env": odds_env(date, stat, player),
         "stat": stat, "player": player})

@router.get("/api/docs", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def api_docs(request: Request):
    return _TEMPLATES.TemplateResponse("api_docs.html", {"request": request})

@router.get("/api/odds/best/{date}.json", tags=["courtvision"])
def api_odds_best(date: str):
    """Best (most favorable) book per (player, stat, line) per side."""
    from api._courtvision_odds import best_book_envelope
    return JSONResponse(best_book_envelope(date))

@router.get("/api/odds/history/{player}/{stat}", tags=["courtvision"])
def api_odds_history(player: str, stat: str,
                     date: str = Query(default_factory=_today_et)):
    """Every captured quote for one (player, stat) — useful for line-movement charts."""
    from api._courtvision_odds import line_history
    rows = line_history(date, player, stat)
    return JSONResponse({"date": date, "player": player, "stat": stat,
                         "n": len(rows), "history": rows})

def _spread_env(date: str, min_spread_pp: float) -> dict:
    from api._courtvision_odds import cross_book_spread
    rows = cross_book_spread(date, min_spread_pp=min_spread_pp)
    return {"date": date, "min_spread_pp": min_spread_pp, "n": len(rows),
            "n_arbs": sum(1 for r in rows if r["is_arb"]), "rows": rows}

@router.get("/api/odds/spread/{date}.json", tags=["courtvision"])
def api_odds_spread(date: str, min_spread_pp: float = Query(2.0, ge=0.0, le=50.0)):
    return JSONResponse(_spread_env(date, min_spread_pp))

@router.get("/arbs", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def arbs_page(request: Request, date: str = Query(default_factory=_today_et),
              min_spread_pp: float = Query(2.0, ge=0.0, le=50.0)):
    return _TEMPLATES.TemplateResponse("arbs.html",
        {"request": request, "env": _spread_env(date, min_spread_pp)})


@router.get("/api/today_summary", tags=["courtvision"])
def api_today_summary(date: str = Query(default_factory=_today_et), n: int = Query(3, ge=1, le=10)):
    s = _build_slate(date); bets = s.get("bets", [])[:n]
    return JSONResponse({"date": s["date"], "generated_at": s["generated_at"],
        "n_total": s["summary"]["n_bets"], "avg_ev_pct": s["summary"]["avg_ev_pct"],
        "top": [{"player": b["player_name"], "team": b["team"], "opp": b["opp"],
                 "prop": f"{b['prop_stat']} {'o' if b['side']=='OVER' else 'u'}{b['line']:g}",
                 "ev_pct": b.get("ev_pct"), "book": b.get("best_book"),
                 "price": b.get("best_price")} for b in bets],
        "share_url": f"{_PUBLIC_BASE_URL or ''}/share/{s['date']}"})


@router.get("/sse/live_edges", tags=["courtvision"])
async def sse_live_edges(request: Request):
    from api._courtvision_live import live_edge_stream
    return await live_edge_stream(request)

@router.get("/live", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def live(request: Request, date: str = Query(default_factory=_today_et)):
    return _TEMPLATES.TemplateResponse("live.html", {"request": request, "date": date})


@router.get("/api/plus_ev", tags=["courtvision"])
def api_plus_ev(date: str = Query(default_factory=_today_et),
                min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    r = plus_ev_rows(_build_slate(date), min_ev_pct)
    return JSONResponse({"date": date, "n": len(r), "rows": r})


@router.get("/plus_ev", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def plus_ev(request: Request,
            date: str = Query(default_factory=_today_et),
            min_ev_pct: float = Query(2.0, ge=-100.0, le=500.0)):
    from api._courtvision_data import plus_ev_rows
    rows = plus_ev_rows(_build_slate(date), min_ev_pct)
    return _TEMPLATES.TemplateResponse("plus_ev.html",
        {"request": request, "date": date, "rows": rows, "min_ev_pct": min_ev_pct})


@router.get("/parlays", response_class=HTMLResponse, tags=["courtvision"])
@_public_limit
def parlays(request: Request,
            date: str = Query(default_factory=_today_et),
            max_legs: int = Query(5, ge=2, le=5),
            min_ev_pct: float = Query(5.0, ge=-100.0, le=500.0),
            limit: int = Query(25, ge=1, le=100)):
    envelope = _build_parlays(date, max_legs, min_ev_pct, seed=0)
    leg_meta = {b["bet_id"]: b for b in _build_slate(date).get("bets", [])}
    return _TEMPLATES.TemplateResponse("parlays.html",
        {"request": request, "envelope": envelope,
         "shown": envelope.get("parlays", [])[:limit],
         "leg_meta": leg_meta, "min_ev_pct": min_ev_pct, "max_legs": max_legs})
