"""_courtvision_odds.py — multi-book odds consolidator + public-API helpers.

Reads per-book CSVs at data/lines/<date>_<book>.csv (written by parallel_scraper)
and merges them into one consolidated view grouped by (player, stat, line).

Per-book CSV schema:
    captured_at, book, game_id, player_id, player_name, stat, line,
    over_price, under_price, start_time

Public API:
    consolidate(date)        -> list[ConsolidatedProp]
    consolidate_for_slate(date) -> list[dict]  # grouped-by-(player,stat,line) shape
                                                # matching api._courtvision_data.load_lines_csv
    odds_envelope(date)      -> dict   # the /api/odds/{date}.json response
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

_LINES_DIR = Path(__file__).resolve().parent.parent / "data" / "lines"
_BOOKS = ("pin", "bov", "fd", "pp")  # add scrapers as they come online
_BOOK_DISPLAY = {"pin": "Pinnacle", "bov": "Bovada", "fd": "FanDuel",
                 "pp": "PrizePicks", "dk": "DraftKings", "mgm": "BetMGM"}
_VALID_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}


def _book_csv_paths(date: str) -> list[Path]:
    """All per-book CSVs for the given date that exist on disk."""
    out: list[Path] = []
    for book in _BOOKS:
        p = _LINES_DIR / f"{date}_{book}.csv"
        if p.exists():
            out.append(p)
    return out


def _to_int(s) -> int | None:
    if s is None or s == "":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _to_float(s) -> float | None:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # filter NaN


def read_book_csv(path: Path) -> list[dict]:
    """Parse a single <date>_<book>.csv. Yields the *latest* quote per
    (player, stat, line, book) so the line-shop view is freshness-correct."""
    latest: dict[tuple, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            stat = (r.get("stat") or "").lower()
            if stat not in _VALID_STATS:
                continue
            line = _to_float(r.get("line"))
            if line is None:
                continue
            book = (r.get("book") or path.stem.split("_")[-1]).lower()
            player = (r.get("player_name") or "").strip()
            if not player:
                continue
            key = (player.lower(), stat, round(line, 2), book)
            existing = latest.get(key)
            captured_at = r.get("captured_at") or ""
            if existing and existing["captured_at"] >= captured_at:
                continue
            latest[key] = {
                "captured_at": captured_at,
                "book": book,
                "player": player,
                "player_id": _to_int(r.get("player_id")),
                "stat": stat,
                "line": line,
                "over_price": _to_int(r.get("over_price")),
                "under_price": _to_int(r.get("under_price")),
                "game_id": r.get("game_id") or "",
                "start_time": r.get("start_time") or "",
            }
    return list(latest.values())


def consolidate(date: str) -> list[dict]:
    """Return all (player, stat, line) props with the per-book ladder attached."""
    grouped: dict[tuple, dict] = {}
    for path in _book_csv_paths(date):
        for row in read_book_csv(path):
            key = (row["player"].lower(), row["stat"], round(row["line"], 2))
            base = grouped.setdefault(key, {
                "player": row["player"], "player_id": row["player_id"],
                "stat": row["stat"], "line": row["line"],
                "game_id": row["game_id"], "start_time": row["start_time"],
                "books": [],
            })
            base["books"].append({
                "book": row["book"], "display": _BOOK_DISPLAY.get(row["book"], row["book"]),
                "over_price": row["over_price"], "under_price": row["under_price"],
                "captured_at": row["captured_at"],
            })
    out = list(grouped.values())
    for prop in out:
        prop["n_books"] = len(prop["books"])
        prop["books"].sort(key=lambda b: b["book"])
    out.sort(key=lambda p: (p["player"], p["stat"], p["line"]))
    return out


def consolidate_for_slate(date: str) -> list[dict]:
    """Drop-in replacement for load_lines_csv. Same shape it produces:
    one row per (player, stat, line) with `books: [{book, over_odds, under_odds}]`."""
    out: list[dict] = []
    for prop in consolidate(date):
        out.append({
            "player": prop["player"], "stat": prop["stat"], "line": prop["line"],
            "opp": "", "venue": "",  # not in scrape CSVs; courtvision_data falls back
            "books": [{
                "book": _BOOK_DISPLAY.get(b["book"], b["book"]),
                "over_odds": b["over_price"] if b["over_price"] is not None else -110,
                "under_odds": b["under_price"] if b["under_price"] is not None else -110,
            } for b in prop["books"] if b["over_price"] or b["under_price"]],
        })
    return [p for p in out if p["books"]]


def odds_envelope(date: str) -> dict:
    """Shape for /api/odds/{date}.json."""
    props = consolidate(date)
    books_seen = sorted({b["book"] for p in props for b in p["books"]})
    return {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_props": len(props),
        "n_books": len(books_seen),
        "books": [{"id": b, "display": _BOOK_DISPLAY.get(b, b)} for b in books_seen],
        "props": props,
    }


def best_price(prop: dict, side: str) -> dict | None:
    """Find the most favorable book on a given side. Higher American odds = better."""
    key = "over_price" if side.upper() == "OVER" else "under_price"
    books = [b for b in prop.get("books", []) if b.get(key) is not None]
    if not books:
        return None
    return max(books, key=lambda b: b[key])


def filter_props(props: Iterable[dict], stat: str | None = None,
                 player: str | None = None) -> list[dict]:
    out = []
    for p in props:
        if stat and p["stat"] != stat.lower():
            continue
        if player and player.lower() not in p["player"].lower():
            continue
        out.append(p)
    return out


def odds_env(date: str, stat: str = "", player: str = "") -> dict:
    """Build the /api/odds/{date}.json envelope with optional filters."""
    env = odds_envelope(date)
    if stat or player:
        env["props"] = filter_props(env["props"], stat=stat or None, player=player or None)
        env["n_props"] = len(env["props"])
    return env


def best_book_envelope(date: str) -> dict:
    """One row per (player, stat, line) with the best book per side highlighted."""
    props = consolidate(date)
    out = []
    for p in props:
        bo = best_price(p, "OVER")
        bu = best_price(p, "UNDER")
        out.append({
            "player": p["player"], "stat": p["stat"], "line": p["line"],
            "n_books": p["n_books"],
            "best_over": {"book": bo["display"], "price": bo["over_price"]} if bo else None,
            "best_under": {"book": bu["display"], "price": bu["under_price"]} if bu else None,
        })
    return {"date": date, "n_props": len(out), "props": out}


def line_history(date: str, player: str, stat: str) -> list[dict]:
    """All quotes for one (player, stat) across the day — every captured_at row.

    Returns rows sorted by captured_at, useful for plotting line movement.
    """
    player_l, stat_l = player.lower(), stat.lower()
    rows: list[dict] = []
    for path in _book_csv_paths(date):
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("player_name") or "").lower() != player_l:
                    continue
                if (r.get("stat") or "").lower() != stat_l:
                    continue
                rows.append({
                    "captured_at": r.get("captured_at"),
                    "book": (r.get("book") or path.stem.split("_")[-1]).lower(),
                    "line": _to_float(r.get("line")),
                    "over_price": _to_int(r.get("over_price")),
                    "under_price": _to_int(r.get("under_price")),
                })
    rows.sort(key=lambda r: (r["captured_at"] or "", r["book"]))
    return rows
