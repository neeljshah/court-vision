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
import time
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


_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 30.0  # short — scrapers tick every ~30-60s


def consolidate(date: str) -> list[dict]:
    """Return all (player, stat, line) props with the per-book ladder attached.

    Cached for 30s per date — covers the burst of requests from /tonight,
    /odds, /arbs, /api/odds/best, etc. all hitting the same date.
    """
    cached = _CACHE.get(date)
    if cached and time.time() - cached[0] < _CACHE_TTL_SEC:
        return cached[1]
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
    _CACHE[date] = (time.time(), out)
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


def summary(date: str) -> dict:
    """One-shot snapshot: counts + freshness for the day. Use for status checks."""
    f = freshness(date)
    props = consolidate(date)
    by_stat: dict[str, int] = defaultdict(int)
    for p in props:
        by_stat[p["stat"]] += 1
    return {
        "date": date,
        "n_props": len(props),
        "n_books": f["n_books"],
        "books": list(f["books"].keys()),
        "n_props_per_stat": dict(by_stat),
        "freshness_by_book": {b: info.get("latest_capture", "")
                              for b, info in f["books"].items()},
    }


def games_index(date: str) -> list[dict]:
    """Distinct game_ids in today's scrape with prop counts + start_time."""
    props = consolidate(date)
    by_game: dict[str, dict] = {}
    for p in props:
        gid = p.get("game_id") or "?"
        g = by_game.setdefault(gid, {
            "game_id": gid, "start_time": p.get("start_time") or "",
            "n_props": 0, "players": set(),
        })
        g["n_props"] += 1
        g["players"].add(p["player"])
    out = []
    for g in by_game.values():
        out.append({
            "game_id": g["game_id"], "start_time": g["start_time"],
            "n_props": g["n_props"], "n_players": len(g["players"]),
        })
    out.sort(key=lambda r: r["start_time"] or "")
    return out


def odds_envelope(date: str) -> dict:
    """Shape for /api/odds/{date}.json."""
    props = consolidate(date)
    books_seen = sorted({b["book"] for p in props for b in p["books"]})
    # Per-book freshness: latest captured_at seen in this date's data.
    book_last_seen: dict[str, str] = {}
    for p in props:
        for b in p["books"]:
            ts = b.get("captured_at") or ""
            if not ts:
                continue
            if ts > book_last_seen.get(b["book"], ""):
                book_last_seen[b["book"]] = ts
    return {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_props": len(props),
        "n_books": len(books_seen),
        "books": [{"id": b, "display": _BOOK_DISPLAY.get(b, b),
                   "last_scrape": book_last_seen.get(b, "")}
                  for b in books_seen],
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


def _american_to_implied(odds: int) -> float:
    """No-vig single-line implied probability from American odds."""
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def line_moves(date: str, window_minutes: int = 60) -> list[dict]:
    """Detect props whose median line moved within `window_minutes` ago.

    Returns rows showing earliest and latest line per (player, stat, book) and
    the delta. Sorted by absolute delta descending. Useful for live-day alerts.
    """
    cutoff_dt = datetime.now(timezone.utc).timestamp() - window_minutes * 60
    # Series of (captured_at, book, player, stat, line) — read all CSV rows
    quotes: dict[tuple, list[tuple]] = defaultdict(list)
    for path in _book_csv_paths(date):
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stat = (r.get("stat") or "").lower()
                player = (r.get("player_name") or "").strip()
                if not player or stat not in _VALID_STATS:
                    continue
                line = _to_float(r.get("line"))
                ts = r.get("captured_at") or ""
                if line is None or not ts:
                    continue
                book = (r.get("book") or path.stem.split("_")[-1]).lower()
                quotes[(player, stat, book)].append((ts, line))
    out: list[dict] = []
    for (player, stat, book), series in quotes.items():
        series.sort()
        if len(series) < 2:
            continue
        # earliest in-window vs latest
        in_window = [(t, l) for t, l in series
                     if _parse_ts(t) and _parse_ts(t) >= cutoff_dt]
        if len(in_window) < 2:
            continue
        first_ts, first_line = in_window[0]
        last_ts, last_line = in_window[-1]
        if first_line == last_line:
            continue
        out.append({
            "player": player, "stat": stat, "book": book,
            "display": _BOOK_DISPLAY.get(book, book),
            "line_open": first_line, "line_close": last_line,
            "delta": round(last_line - first_line, 2),
            "ts_open": first_ts, "ts_close": last_ts,
        })
    out.sort(key=lambda r: -abs(r["delta"]))
    return out


def _parse_ts(ts: str) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError):
            return None


def freshness(date: str) -> dict:
    """Per-book CSV mtime + latest captured_at + row count."""
    import os
    out: dict[str, dict] = {}
    for path in _book_csv_paths(date):
        book = path.stem.split("_")[-1].lower()
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime,
                                            tz=timezone.utc).isoformat()
        except OSError:
            mtime = None
        latest_capture = ""
        n_rows = 0
        try:
            with path.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    n_rows += 1
                    ts = r.get("captured_at") or ""
                    if ts > latest_capture:
                        latest_capture = ts
        except OSError:
            pass
        out[book] = {
            "display": _BOOK_DISPLAY.get(book, book),
            "csv_path": str(path.relative_to(path.parent.parent)),
            "csv_mtime_utc": mtime,
            "n_rows": n_rows,
            "latest_capture": latest_capture,
        }
    return {"date": date, "n_books": len(out), "books": out}


def consolidate_csv(date: str, stat: str | None = None,
                    player: str | None = None) -> str:
    """Render consolidated odds as a CSV string (one row per (player, stat, line, book))."""
    import io
    props = consolidate(date)
    if stat:
        props = [p for p in props if p["stat"] == stat.lower()]
    if player:
        player_l = player.lower()
        props = [p for p in props if player_l in p["player"].lower()]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "player", "stat", "line", "book", "over_price",
                "under_price", "captured_at"])
    for p in props:
        for b in p["books"]:
            w.writerow([date, p["player"], p["stat"], p["line"], b["book"],
                        b.get("over_price") or "", b.get("under_price") or "",
                        b.get("captured_at") or ""])
    return buf.getvalue()


def cross_book_spread(date: str, min_spread_pp: float = 2.0) -> list[dict]:
    """Props where books differ on implied prob — line shop / arb opportunities.

    Returns rows sorted by spread descending. `min_spread_pp` is the min
    spread in percentage points between best and worst book on either side.
    """
    props = consolidate(date)
    out: list[dict] = []
    for p in props:
        if p["n_books"] < 2:
            continue
        over_books = [b for b in p["books"] if b["over_price"] is not None]
        under_books = [b for b in p["books"] if b["under_price"] is not None]
        over_implieds = [_american_to_implied(b["over_price"]) for b in over_books]
        under_implieds = [_american_to_implied(b["under_price"]) for b in under_books]
        over_spread = (max(over_implieds) - min(over_implieds)) * 100 if len(over_implieds) >= 2 else 0
        under_spread = (max(under_implieds) - min(under_implieds)) * 100 if len(under_implieds) >= 2 else 0
        max_spread = max(over_spread, under_spread)
        if max_spread < min_spread_pp:
            continue
        # Two-way arb check: best over implied + best under implied < 100?
        best_over_implied = min(over_implieds) if over_implieds else None
        best_under_implied = min(under_implieds) if under_implieds else None
        arb_sum = (best_over_implied + best_under_implied) * 100 if best_over_implied and best_under_implied else None
        is_arb = arb_sum is not None and arb_sum < 100.0
        out.append({
            "player": p["player"], "stat": p["stat"], "line": p["line"],
            "n_books": p["n_books"], "over_spread_pp": round(over_spread, 2),
            "under_spread_pp": round(under_spread, 2),
            "arb_sum_pct": round(arb_sum, 2) if arb_sum is not None else None,
            "is_arb": is_arb, "books": p["books"],
        })
    out.sort(key=lambda r: -max(r["over_spread_pp"], r["under_spread_pp"]))
    return out


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
