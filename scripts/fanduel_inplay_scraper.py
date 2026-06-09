"""fanduel_inplay_scraper.py — FanDuel NBA player-prop LIVE (in-play) scraper.

FanDuel exposes in-play markets on the same NJ endpoint used for pregame, but
with `?inPlayOnly=true` appended. The market types and runner structure are
identical to the pregame threshold format so the same normalization logic
applies.

Game-state gate: the response contains market objects with an `inPlay` boolean
field. When no game is live the endpoint still returns 200 but all markets have
`inPlay: false`.  scrape_once() checks this and returns [] (empty) if no live
market exists — no special auth or secondary endpoint required.

FanDuel in-play market structure (same as pregame):
    market.marketType  e.g. "TO_SCORE_25+_POINTS", "6+_MADE_THREES"
    market.inPlay      bool — True only during the game
    runner.isPlayerSelection  True for individual player rows
    runner.winRunnerOdds.americanDisplayOdds.americanOdds  e.g. -150

Normalization: same THRESHOLD_PATTERNS regex table as pregame FD scraper.
    line = threshold - 0.5  (e.g. "25+" → 24.5)
    over_price = the published American odds
    under_price = "" (FD does not publish NO side on threshold markets)

Output: data/lines/<date>_fd_inplay.csv  (book="fd_inplay")

Run modes:
    --once     one snapshot, write CSV, exit
    --daemon   loop forever (default 60s interval — in-play FD is heavy JSON)

See .planning/courtvision-odds/research_inplay.md for probe notes.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, date as _date
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as cf_req

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    from src.monitor.daemon_heartbeat import write_heartbeat as _hb
except Exception:  # noqa: BLE001
    def _hb(_name: str) -> bool:
        return False

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LINES_DIR, exist_ok=True)

STATUS_PATH = os.path.join(CACHE_DIR, "fanduel_inplay_results.json")

# ── constants ────────────────────────────────────────────────────────────────
# Same base URL as pregame; inPlayOnly=true is the only change.
FD_INPLAY_URL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nba&pbHorizontal=false"
    "&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York&inPlayOnly=true"
)
FD_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.fanduel.com/",
    "Origin": "https://sportsbook.fanduel.com",
    "X-Px-Authorization": "3",
}

# Same threshold patterns as probe_R15_curl_cffi_fanduel.py
THRESHOLD_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^TO_SCORE_(\d+)\+_POINTS$"),     "pts"),
    (re.compile(r"^(\d+)\+_MADE_THREES$"),          "fg3m"),
    (re.compile(r"^TO_RECORD_(\d+)\+_ASSISTS$"),    "ast"),
    (re.compile(r"^TO_RECORD_(\d+)\+_REBOUNDS$"),   "reb"),
    (re.compile(r"^TO_RECORD_(\d+)\+_STEALS$"),     "stl"),
    (re.compile(r"^TO_RECORD_(\d+)\+_BLOCKS$"),     "blk"),
    (re.compile(r"^TO_RECORD_(\d+)\+_TURNOVERS$"),  "tov"),
]

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _match_threshold(market_type: str) -> Optional[Tuple[str, int]]:
    for pat, stat in THRESHOLD_PATTERNS:
        m = pat.match(market_type or "")
        if m:
            return stat, int(m.group(1))
    return None


def fetch_fd_inplay(timeout: int = 20) -> Optional[Dict[str, Any]]:
    """Fetch FanDuel NJ NBA in-play content-managed-page. Returns JSON or None."""
    try:
        r = cf_req.get(FD_INPLAY_URL, headers=FD_HEADERS,
                       impersonate="chrome120", timeout=timeout)
        if r.status_code != 200:
            print(f"[fd_inplay] non-200: {r.status_code} len={len(r.content)}",
                  flush=True)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[fd_inplay] fetch error: {type(exc).__name__}: {exc}", flush=True)
        return None


def normalize_fd_inplay(
    j: Dict[str, Any],
    captured_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Walk FD attachments and emit canonical rows for in-play markets only.

    Markets with inPlay=False are skipped so the CSV stays clean during
    off-hours even if the endpoint returns pregame leftovers.
    """
    if captured_at is None:
        captured_at = datetime.utcnow().replace(microsecond=0).isoformat()

    att = j.get("attachments") or {}
    events = att.get("events") or {}
    markets = att.get("markets") or {}

    rows: List[Dict[str, Any]] = []
    for m in markets.values():
        # Only include actively live markets
        if not m.get("inPlay"):
            continue
        match = _match_threshold(m.get("marketType") or "")
        if not match:
            continue
        stat, threshold = match
        ev_id = m.get("eventId")
        ev = events.get(str(ev_id), {}) or {}
        ev_name = ev.get("name") or ""
        if "@" not in ev_name:
            continue  # skip futures / non-game events
        start_time = ev.get("openDate")

        for runner in m.get("runners") or []:
            if not runner.get("isPlayerSelection"):
                continue
            odds_block = (
                (runner.get("winRunnerOdds") or {})
                .get("americanDisplayOdds") or {}
            )
            odds = odds_block.get("americanOdds")
            if odds is None:
                continue
            rows.append({
                "captured_at": captured_at,
                "book": "fd_inplay",
                "game_id": ev_id,
                "player_id": runner.get("selectionId"),
                "player_name": runner.get("runnerName"),
                "stat": stat,
                "line": threshold - 0.5,
                "over_price": int(odds),
                "under_price": "",  # FD threshold markets have no NO side
                "start_time": start_time,
            })
    return rows


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Append rows to CSV (header written when file is new)."""
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def one_snapshot() -> Dict[str, Any]:
    captured_at = datetime.utcnow().replace(microsecond=0).isoformat()
    status: Dict[str, Any] = {
        "ran_at": captured_at, "rows": 0, "by_stat": {},
        "events": 0, "ok": False, "csv": None, "live_game_count": 0,
    }

    j = fetch_fd_inplay()
    if j is None:
        return status

    rows = normalize_fd_inplay(j, captured_at=captured_at)

    # Count distinct live games found (markets with inPlay=True)
    att = j.get("attachments") or {}
    markets = att.get("markets") or {}
    live_count = sum(1 for m in markets.values() if m.get("inPlay"))
    status["live_game_count"] = live_count

    if not rows:
        # No live games right now — expected during off-hours
        print("[fd_inplay] 0 live markets — no rows to write", flush=True)
        status["ok"] = True
        return status

    by_stat: Dict[str, int] = {}
    for r in rows:
        by_stat[r["stat"]] = by_stat.get(r["stat"], 0) + 1
    status["by_stat"] = by_stat
    status["events"] = len({r["game_id"] for r in rows})
    today = _date.today().isoformat()
    csv_path = os.path.join(LINES_DIR, f"{today}_fd_inplay.csv")
    write_csv(rows, csv_path)
    status["ok"] = True
    status["rows"] = len(rows)
    status["csv"] = csv_path
    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py. Writes CSV; returns []."""
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[fd_inplay] scrape_once failed: {type(exc).__name__}: {exc}",
              flush=True)
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    if not args.daemon:
        s = one_snapshot()
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        print(json.dumps(s, indent=2))
        return 0 if s["ok"] else 2

    print(f"[fd_inplay-daemon] start interval={args.interval}s", flush=True)
    while True:
        _hb("fd_inplay_scraper")
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2)
            print(
                f"[fd_inplay-daemon] {s['ran_at']} rows={s['rows']} "
                f"live_games={s['live_game_count']} "
                f"by_stat={s['by_stat']} ok={s['ok']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[fd_inplay-daemon] tick error: {type(exc).__name__}: {exc}",
                  flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
