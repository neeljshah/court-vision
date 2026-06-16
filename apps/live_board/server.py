"""FastAPI server for the live multi-sport board.

Decision support, not a money machine: model win-prob where in-corpus,
devigged market-implied otherwise, source badged per row. No $ edge claimed.

Endpoints:
  GET /                 -> the single-page board (templates/board.html)
  GET /api/board        -> {sport, generated_at, rows:[BoardRow]} (~20s cache)
  GET /api/health       -> {ok: true}

build_board is imported LAZILY inside the handler so module import stays fast
(predictors are expensive to build; the predictor factory caches them).
"""

import os
import time
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Live Multi-Sport Board")

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOARD_HTML = os.path.join(_HERE, "templates", "board.html")

# Per-(sport, leagues) in-process cache with a short TTL so we never hammer
# ESPN (the feed itself caches ~20s) and never rebuild predictors per request.
_CACHE_TTL = 20.0  # seconds
_cache = {}        # key -> (expires_at, payload)
_cache_lock = threading.Lock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _cache_get(key):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    return None


def _cache_put(key, payload):
    with _cache_lock:
        _cache[key] = (time.time() + _CACHE_TTL, payload)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/")
def index():
    if os.path.exists(_BOARD_HTML):
        return FileResponse(_BOARD_HTML, media_type="text/html")
    # Defensive fallback if the template agent has not landed the file yet.
    return JSONResponse(
        {"error": "board.html not found", "expected": _BOARD_HTML},
        status_code=503,
    )


@app.get("/api/board")
def api_board(
    sport: str = Query("mlb"),
    leagues: str = Query(None),
):
    sport = (sport or "mlb").strip().lower()
    leagues_csv = (leagues or "").strip()
    key = (sport, leagues_csv)

    cached = _cache_get(key)
    if cached is not None:
        return cached

    league_list = None
    if leagues_csv:
        league_list = [s.strip() for s in leagues_csv.split(",") if s.strip()]

    rows = []
    error = None
    try:
        # Lazy import: keeps server import fast and avoids hard-failing at
        # startup if a sibling module is still being built.
        from apps.live_board.board import build_board
        rows = build_board(sport, leagues=league_list)
    except Exception as exc:  # never 500 the board; degrade to empty + note
        error = "{}: {}".format(type(exc).__name__, exc)

    payload = {
        "sport": sport,
        "leagues": league_list,
        "generated_at": _now_iso(),
        "rows": rows,
    }
    if error:
        payload["error"] = error

    _cache_put(key, payload)
    return payload
