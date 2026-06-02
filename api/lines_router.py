"""lines_router.py — multi-book line scanner.

Exposes:
    GET /api/lines/scan?date=YYYY-MM-DD&stat=pts&min_books=2&sort=edge
        JSON envelope of consolidated props with best/worst book per side
        and a "best_combined_edge" metric for shopping value.
    GET /scan
        HTML UI page rendered from templates/scan.html.

Reads from api._courtvision_odds.consolidate(date) — already groups per-book
CSVs into (player, stat, line) rows with a `books` array attached.

Edge metric (per row):
    over_spread_cents  = best_over_price  − worst_over_price  (American odds)
    under_spread_cents = best_under_price − worst_under_price
    best_combined_edge = max(implied_diff_over, implied_diff_under)  (percentage points)
The implied-diff is computed via `_american_to_implied`; bigger spread =
more shopping value across books.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from api._courtvision_odds import (
    _american_to_implied,
    best_price,
    consolidate,
    steam_lookup,
)

_HERE = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))

router = APIRouter()

_VALID_SORTS = {"edge", "player", "stat", "line"}


def _today() -> str:
    """Return today's date anchored to ET (UTC-4 EDT fallback).

    Uses UTC-4 to match api/live_game_router._today_et — prevents returning
    TOMORROW's date on a UTC host during the ET evening window (00:00-04:00 UTC).
    """
    return (datetime.now(timezone.utc) + timedelta(hours=-4)).strftime("%Y-%m-%d")


def _book_entry(book_row: dict, side: str) -> Optional[dict]:
    """Convert a books[] entry from consolidate into a {book,price,deeplink} dict."""
    if not book_row:
        return None
    if side == "over":
        price = book_row.get("over_price")
        deeplink = book_row.get("deeplink_over_web") or ""
    else:
        price = book_row.get("under_price")
        deeplink = book_row.get("deeplink_under_web") or ""
    return {
        "book": book_row.get("book"),
        "display": book_row.get("display") or book_row.get("book"),
        "price": price,
        "deeplink": deeplink,
    }


def _worst_price(prop: dict, side: str) -> Optional[dict]:
    """Find the least favorable book on a given side. Lower American odds = worse."""
    key = "over_price" if side == "over" else "under_price"
    books = [b for b in prop.get("books", []) if b.get(key) is not None]
    if not books:
        return None
    return min(books, key=lambda b: b[key])


def _spread_cents(best: Optional[dict], worst: Optional[dict], price_key: str) -> int:
    if not best or not worst:
        return 0
    b = best.get(price_key)
    w = worst.get(price_key)
    if b is None or w is None:
        return 0
    return int(b - w)


def _implied_diff(best: Optional[dict], worst: Optional[dict], price_key: str) -> float:
    """Implied-prob diff in percentage points: worst_implied - best_implied.

    Worst book has lower American odds → higher implied prob; best book has the
    higher American odds → lower implied prob. So worst_implied - best_implied
    is always >= 0 and represents pp of shopping edge.
    """
    if not best or not worst:
        return 0.0
    b = best.get(price_key)
    w = worst.get(price_key)
    if b is None or w is None:
        return 0.0
    return round((_american_to_implied(w) - _american_to_implied(b)) * 100.0, 3)


def _scan_rows(date: str, stat: Optional[str], min_books: int) -> list[dict]:
    out: list[dict] = []
    steam_map = steam_lookup(date)
    for prop in consolidate(date):
        if stat and prop.get("stat") != stat.lower():
            continue
        if prop.get("n_books", 0) < min_books:
            continue
        best_over = best_price(prop, "OVER")
        best_under = best_price(prop, "UNDER")
        worst_over = _worst_price(prop, "over")
        worst_under = _worst_price(prop, "under")

        over_spread_cents = _spread_cents(best_over, worst_over, "over_price")
        under_spread_cents = _spread_cents(best_under, worst_under, "under_price")
        over_edge = _implied_diff(best_over, worst_over, "over_price")
        under_edge = _implied_diff(best_under, worst_under, "under_price")
        best_combined_edge = max(over_edge, under_edge)

        # Slim books list for client (drop heavy deeplink_*_app fields)
        slim_books = [{
            "book": b.get("book"),
            "display": b.get("display") or b.get("book"),
            "over": b.get("over_price"),
            "under": b.get("under_price"),
            "deeplink_over": b.get("deeplink_over_web") or "",
            "deeplink_under": b.get("deeplink_under_web") or "",
        } for b in prop.get("books", [])]

        # Steam (sharp-money) annotation — only render badge when <10 min old.
        # steam_lookup indexes events under (player_lower, stat_lower, round(line,2)).
        _player = (prop.get("player") or "").lower()
        _stat = (prop.get("stat") or "").lower()
        try:
            _line_r = round(float(prop.get("line")), 2)
        except (TypeError, ValueError):
            _line_r = None
        steam_event = steam_map.get((_player, _stat, _line_r)) if _line_r is not None else None
        # Strip the internal _ts_unix marker before returning to client.
        if steam_event is not None:
            steam_event = {k: v for k, v in steam_event.items() if not k.startswith("_")}

        out.append({
            "player": prop.get("player"),
            "stat": prop.get("stat"),
            "line": prop.get("line"),
            "game_id": prop.get("game_id") or "",
            "start_time": prop.get("start_time") or "",
            "n_books": prop.get("n_books", 0),
            "best_over": _book_entry(best_over, "over"),
            "worst_over": _book_entry(worst_over, "over"),
            "best_under": _book_entry(best_under, "under"),
            "worst_under": _book_entry(worst_under, "under"),
            "over_spread_cents": over_spread_cents,
            "under_spread_cents": under_spread_cents,
            "best_combined_edge": best_combined_edge,
            "steam": steam_event,
            "books": slim_books,
        })
    return out


def _sort_rows(rows: list[dict], sort: str) -> list[dict]:
    if sort == "player":
        rows.sort(key=lambda r: (r.get("player") or "", r.get("stat") or "",
                                  r.get("line") or 0))
    elif sort == "stat":
        rows.sort(key=lambda r: (r.get("stat") or "", r.get("player") or "",
                                  r.get("line") or 0))
    elif sort == "line":
        rows.sort(key=lambda r: (r.get("line") or 0, r.get("player") or ""))
    else:  # "edge" default — descending
        rows.sort(key=lambda r: -float(r.get("best_combined_edge") or 0))
    return rows


@router.get("/api/lines/scan", tags=["lines"])
def api_lines_scan(
    date: str = Query(default_factory=_today),
    stat: Optional[str] = Query(default=None),
    min_books: int = Query(default=2, ge=1),
    sort: str = Query(default="edge"),
):
    """Multi-book line scanner — best/worst price per side for every (player, stat, line)."""
    sort_key = sort if sort in _VALID_SORTS else "edge"
    rows = _scan_rows(date, stat, min_books)
    rows = _sort_rows(rows, sort_key)
    n_steam = sum(1 for r in rows if r.get("steam"))
    return JSONResponse({
        "date": date,
        "stat": stat or "",
        "min_books": min_books,
        "sort": sort_key,
        "n_props": len(rows),
        "n_steam": n_steam,
        "props": rows,
    })


@router.get("/scan", response_class=HTMLResponse, tags=["lines"])
def scan_page(
    request: Request,
    date: str = Query(default_factory=_today),
    stat: Optional[str] = Query(default=None),
    min_books: int = Query(default=2, ge=1),
    sort: str = Query(default="edge"),
):
    """HTML UI for the multi-book line scanner."""
    sort_key = sort if sort in _VALID_SORTS else "edge"
    rows = _scan_rows(date, stat, min_books)
    rows = _sort_rows(rows, sort_key)
    n_steam = sum(1 for r in rows if r.get("steam"))
    return _TEMPLATES.TemplateResponse("scan.html", {
        "request": request,
        "date": date,
        "stat": stat or "",
        "min_books": min_books,
        "sort": sort_key,
        "n_props": len(rows),
        "n_steam": n_steam,
        "props": rows,
    })
