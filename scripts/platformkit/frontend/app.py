"""scripts.platformkit.frontend.app — self-contained HONEST betting frontend.

A SEPARATE FastAPI() instance from api/main.py (the human's live app).  This
module NEVER imports api.main and defaults to a DISTINCT port 8099 (override via
BOARD_APP_PORT) so it cannot collide with the live app on 8077.

HONEST throughout: markets are efficient — NO model edge is claimed.  Value
shown = line-shopping / devig / CLV.  Arb / CLV stay dormant until a live
multi-book feed (The Odds API) is wired — THE UNLOCK IS DATA.

The fastapi import is guarded so a missing dependency yields a clear error
rather than an import crash.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except Exception as exc:  # pragma: no cover - dependency guard
    raise ImportError(
        "scripts.platformkit.frontend.app requires fastapi. "
        "Install it (pip install fastapi uvicorn) and retry."
    ) from exc

from scripts.platformkit.frontend.board import (
    HONEST_NOTE,
    _SPORT_REGISTRY,
    build_all_board,
)
from scripts.platformkit.frontend.board_html import render_board_html
from scripts.platformkit.frontend.feed import OddsFeed, get_feed

APP_BANNER = (
    "Honest multi-sport board. Markets are efficient — NO model edge claimed. "
    "Value = line-shopping / devig / CLV. "
)

# Surfaced at /api/feed/status — what the human must do to go live.
BLOCKED_CHECKLIST: List[str] = [
    "1. Human rotates the leaked Odds API key and provisions a fresh one.",
    "2. Set ODDS_API_KEY (or THE_ODDS_API_KEY) in env — never hardcode.",
    "3. Confirm the plan tier / unit budget (MAX_UNITS = 20000).",
    "4. Choose regions + markets (us; h2h, spreads, totals).",
    "5. Restart the app -> get_feed auto-returns the live feed -> arb/CLV light up.",
]

_INDEX_HTML = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
    "<title>Honest Board (platformkit)</title></head><body>"
    "<h1>Honest Board (platformkit)</h1>"
    "<p>{banner}</p>"
    "<ul>"
    "<li><a href='/board.html'>/board.html</a> — rendered board</li>"
    "<li><a href='/api/board'>/api/board</a> — full board JSON</li>"
    "<li><a href='/api/feed/status'>/api/feed/status</a> — feed status</li>"
    "<li><a href='/healthz'>/healthz</a> — health</li>"
    "</ul></body></html>"
)


def create_app(
    repo_root: Optional[Path] = None,
    *,
    feed: Optional[OddsFeed] = None,
    max_rows_per_sport: int = 200,
) -> FastAPI:
    """Build a self-contained FastAPI app.  Inject `feed` for fast network-free tests."""
    app = FastAPI(title="Honest Board (platformkit)", version="0.1.0")
    _feed: OddsFeed = feed or get_feed(repo_root)

    def _banner() -> str:
        return APP_BANNER + _feed.note

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML.format(banner=_banner())

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {"status": "ok", "feed": _feed.name, "live": _feed.is_live()}

    @app.get("/api/feed/status")
    def feed_status() -> Dict[str, Any]:
        return {
            "configured": _feed.is_live(),
            "name": _feed.name,
            "note": _feed.note,
            "blocked": [] if _feed.is_live() else list(BLOCKED_CHECKLIST),
        }

    @app.get("/api/board")
    def api_board() -> Dict[str, Any]:
        board = build_all_board(repo_root, max_rows_per_sport=max_rows_per_sport)
        return {"_banner": _banner(), "honest_note": HONEST_NOTE, "board": board}

    @app.get("/api/board/{sport}")
    def api_board_sport(sport: str) -> Dict[str, Any]:
        if sport not in _SPORT_REGISTRY:
            return {
                "error": f"unknown sport {sport!r}",
                "known": sorted(_SPORT_REGISTRY.keys()),
                "note": HONEST_NOTE,
            }
        board = build_all_board(repo_root, max_rows_per_sport=max_rows_per_sport)
        return {"_banner": _banner(), "sport": sport, "rows": board.get(sport, [])}

    @app.get("/board.html", response_class=HTMLResponse)
    def board_html() -> str:
        board = build_all_board(repo_root, max_rows_per_sport=max_rows_per_sport)
        return render_board_html(board, honest_note=HONEST_NOTE)

    @app.get("/api/ev")
    def api_ev() -> Dict[str, Any]:
        board = build_all_board(repo_root, max_rows_per_sport=max_rows_per_sport)
        rows: List[Dict[str, Any]] = []
        for sport_rows in board.values():
            rows.extend(r for r in sport_rows if r.get("line_shop_ev") is not None)
        note = HONEST_NOTE
        if not rows and not _feed.is_live():
            note = (
                "No line-shopping EV: " + _feed.note
                + " (single book -> no cross-book value)."
            )
        return {"_banner": _banner(), "rows": rows, "note": note}

    @app.get("/api/arb")
    def api_arb() -> Dict[str, Any]:
        return {
            "_banner": _banner(),
            "rows": [],
            "status": "dormant",
            "note": "needs live multi-book feed",
        }

    @app.get("/api/clv")
    def api_clv() -> Dict[str, Any]:
        return {
            "_banner": _banner(),
            "rows": [],
            "status": "dormant",
            "note": "needs live multi-book feed (forward CLV requires real captured prices)",
        }

    return app


app = create_app()


def main() -> None:
    """Run the self-contained app on port 8099 (override BOARD_APP_PORT)."""
    import uvicorn

    port = int(os.environ.get("BOARD_APP_PORT", "8099"))
    uvicorn.run(
        "scripts.platformkit.frontend.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
