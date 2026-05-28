"""the_odds_api_scraper.py — pulls NBA player-prop odds from the-odds-api.com.

Env-gated: requires THE_ODDS_API_KEY (free tier 500 req/month at
https://the-odds-api.com). When set, writes per-book rows in the
canonical data/lines/<date>_<bookkey>.csv schema so the existing
courtvision odds consolidator picks them up automatically.

Books available via this API (when in regions=us):
    DraftKings, FanDuel, BetMGM, Caesars, PointsBet, BetRivers,
    Bet365, Pinnacle, plus a handful of state-specific books.

Run on a schedule (e.g. every 5 min) via:
    python scripts/the_odds_api_scraper.py --markets pts,reb,ast,fg3m,stl,blk,tov

Exits 0 on success, 1 on missing API key or HTTP failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
LINES_DIR = ROOT / "data" / "lines"
QUOTA_PATH = ROOT / "data" / "cache" / "oddsapi_quota.json"

_API_BASE = "https://api.the-odds-api.com/v4/sports/basketball_nba"
_STAT_MAP = {
    "pts": "player_points", "reb": "player_rebounds", "ast": "player_assists",
    "fg3m": "player_threes", "stl": "player_steals", "blk": "player_blocks",
    "tov": "player_turnovers",
}
# Default markets — 3 stats only (pts/reb/ast). pts/reb/ast are the high-volume
# liquid markets every book carries. Skipping fg3m/stl/blk/tov saves ~57% of
# the quota cost (cost = regions × markets). Override via ODDSAPI_MARKETS env.
_DEFAULT_MARKETS = ["pts", "reb", "ast"]
_BOOK_KEY = {  # normalize bookmaker.key → our short code
    "draftkings": "dk", "fanduel": "fd", "betmgm": "mgm",
    "williamhill_us": "caesars", "pointsbetus": "pointsbet",
    "betrivers": "betrivers", "bet365": "bet365", "pinnacle": "pin",
    "bovada": "bov", "betonlineag": "betonline", "espnbet": "espnbet",
}
_CSV_COLUMNS = ["captured_at", "book", "game_id", "player_id", "player_name",
                "stat", "line", "over_price", "under_price", "start_time"]


def _http_get(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body), r.headers
        except json.JSONDecodeError:
            log.warning("non-JSON body: %s", body[:200])
            return None, r.headers


def list_events(api_key: str) -> list[dict]:
    url = f"{_API_BASE}/events?apiKey={api_key}"
    events, _ = _http_get(url)
    return events or []


def fetch_event_odds(api_key: str, event_id: str, markets: list[str]) -> dict | None:
    qs = urllib.parse.urlencode({
        "apiKey": api_key, "regions": "us",
        "markets": ",".join(markets), "oddsFormat": "american",
    })
    url = f"{_API_BASE}/events/{event_id}/odds?{qs}"
    odds, _ = _http_get(url)
    return odds


def normalize(event: dict, payload: dict, captured_at: str) -> list[dict]:
    rows: list[dict] = []
    if not payload:
        return rows
    inv_stat = {v: k for k, v in _STAT_MAP.items()}
    game_id = event.get("id") or payload.get("id") or ""
    commence = event.get("commence_time") or payload.get("commence_time") or ""
    for bm in payload.get("bookmakers", []):
        book_raw = (bm.get("key") or "").lower()
        book = _BOOK_KEY.get(book_raw, book_raw)
        for mk in bm.get("markets", []):
            stat = inv_stat.get(mk.get("key"))
            if not stat:
                continue
            # outcomes: list of {name: "Over"|"Under", description: <player>, price: ..., point: ...}
            grouped: dict[tuple, dict] = {}
            for o in mk.get("outcomes", []):
                player = o.get("description") or ""
                side = (o.get("name") or "").strip().lower()
                point = o.get("point")
                price = o.get("price")
                if not player or point is None or price is None or side not in ("over", "under"):
                    continue
                key = (player, float(point))
                base = grouped.setdefault(key, {
                    "captured_at": captured_at, "book": book, "game_id": game_id,
                    "player_id": "", "player_name": player, "stat": stat,
                    "line": float(point), "over_price": "", "under_price": "",
                    "start_time": commence,
                })
                base["over_price" if side == "over" else "under_price"] = int(price)
            rows.extend(grouped.values())
    return rows


def write_csv(rows: list[dict], book: str, date: str) -> Path:
    LINES_DIR.mkdir(parents=True, exist_ok=True)
    path = LINES_DIR / f"{date}_{book}.csv"
    existing: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    seen = {(r["captured_at"][:16], r["player_name"], r["stat"], r["line"])
            for r in existing}
    new = [r for r in rows if (r["captured_at"][:16], r["player_name"], r["stat"], r["line"]) not in seen]
    if not new:
        return path
    with path.open("a" if existing else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        if not existing:
            w.writeheader()
        for r in new:
            w.writerow(r)
    return path


def scrape_once(markets: list[str] | None = None) -> dict:
    """Entry point matching parallel_scraper's interface."""
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        log.info("THE_ODDS_API_KEY not set; skipping the_odds_api_scraper.")
        return {"ok": False, "reason": "no_key", "rows": 0}
    markets = markets or list(_STAT_MAP.keys())
    odds_markets = [_STAT_MAP[m] for m in markets if m in _STAT_MAP]
    captured_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    date = captured_at[:10]
    total = 0
    per_book: dict[str, int] = {}
    try:
        events = list_events(api_key)
    except Exception as exc:
        log.warning("list_events failed: %s", exc)
        return {"ok": False, "reason": str(exc), "rows": 0}
    for ev in events:
        try:
            payload = fetch_event_odds(api_key, ev.get("id", ""), odds_markets)
        except Exception as exc:
            log.warning("event %s odds failed: %s", ev.get("id"), exc)
            continue
        if not payload:
            continue
        rows = normalize(ev, payload, captured_at)
        # bucket by book and write
        by_book: dict[str, list[dict]] = {}
        for r in rows:
            by_book.setdefault(r["book"], []).append(r)
        for book, brows in by_book.items():
            write_csv(brows, book, date)
            per_book[book] = per_book.get(book, 0) + len(brows)
            total += len(brows)
        time.sleep(0.3)  # politeness; the-odds-api allows ~1 req/sec on free tier
    return {"ok": True, "rows": total, "per_book": per_book, "date": date}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default="pts,reb,ast,fg3m,stl,blk,tov")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
    result = scrape_once([m.strip() for m in args.markets.split(",") if m.strip()])
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
