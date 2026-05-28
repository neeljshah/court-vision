"""probe_R15_curl_cffi_fanduel.py - production FanDuel NJ scraper via curl_cffi.

R15 found FanDuel NJ's content-managed-page endpoint returns 200 + valid JSON
when curl_cffi impersonates chrome120 (vanilla `requests` was 403). DK / MGM /
Caesars stay 403 even with TLS impersonation — their WAF has additional layers
(cookie tokens, IP geo, PerimeterX). FanDuel is the one that cracked.

FanDuel exposes player props as THRESHOLD-style YES odds ('To Score 20+ Points',
'4+ Made Threes'). We canonicalize each threshold as a half-step Over line:
  line = threshold - 0.5
  over_price = the YES American odds
  under_price = None  (book does not publish the NO side on these markets)

That asymmetry is fine for CLV — `src/betting/clv.py` joins by
(book, game, player, stat, line) and tolerates null under_price.

Schema (FanDuel attachments dict):
  events    -> eventId -> {name, openDate, competitionId}
  markets   -> marketId -> {marketType, eventId, runners[{runnerName, isPlayerSelection, winRunnerOdds.americanDisplayOdds.americanOdds}]}
We map only the player-threshold marketTypes; ignore game-line markets.

Writes data/lines/<date>_fd.csv with the canonical CLV schema, then dumps a
small JSON status alongside for the bot loop.

Run modes:
  --once     fetch one snapshot, write CSV, exit
  --daemon   loop forever with --interval seconds between snapshots (default 300)

Output:
  data/lines/<YYYY-MM-DD>_fd.csv
  data/cache/probe_R15_fd_results.json
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
from typing import Any, Dict, List, Optional

from curl_cffi import requests as cf_req

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LINES_DIR, exist_ok=True)

STATUS_PATH = os.path.join(CACHE_DIR, "probe_R15_fd_results.json")

FD_URL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nba&pbHorizontal=false"
    "&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"
)
FD_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.fanduel.com/",
    "Origin": "https://sportsbook.fanduel.com",
    "X-Px-Authorization": "3",
}

# marketType regex -> canonical short stat
THRESHOLD_PATTERNS: List[tuple] = [
    (re.compile(r"^TO_SCORE_(\d+)\+_POINTS$"), "pts"),
    (re.compile(r"^(\d+)\+_MADE_THREES$"), "fg3m"),
    (re.compile(r"^TO_RECORD_(\d+)\+_ASSISTS$"), "ast"),
    (re.compile(r"^TO_RECORD_(\d+)\+_REBOUNDS$"), "reb"),
    (re.compile(r"^TO_RECORD_(\d+)\+_STEALS$"), "stl"),
    (re.compile(r"^TO_RECORD_(\d+)\+_BLOCKS$"), "blk"),
    (re.compile(r"^TO_RECORD_(\d+)\+_TURNOVERS$"), "tov"),
]

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
    "book_selection_id_over", "book_selection_id_under",
]


def _match_threshold(market_type: str) -> Optional[tuple]:
    for pat, stat in THRESHOLD_PATTERNS:
        m = pat.match(market_type or "")
        if m:
            return stat, int(m.group(1))
    return None


def fetch_fd(timeout: int = 20) -> Optional[Dict[str, Any]]:
    """Fetch FanDuel NJ NBA content-managed-page. Returns parsed JSON or None."""
    try:
        r = cf_req.get(FD_URL, headers=FD_HEADERS, impersonate="chrome120", timeout=timeout)
        if r.status_code != 200:
            print(f"[fd] non-200: {r.status_code} len={len(r.content)}", flush=True)
            return None
        return r.json()
    except Exception as exc:
        print(f"[fd] fetch error: {type(exc).__name__}: {exc}", flush=True)
        return None


def normalize_fd(j: Dict[str, Any], captured_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Walk the FD attachments dict and produce canonical rows."""
    if captured_at is None:
        captured_at = datetime.utcnow().replace(microsecond=0).isoformat()
    att = j.get("attachments") or {}
    events = att.get("events") or {}
    markets = att.get("markets") or {}

    rows: List[Dict[str, Any]] = []
    for market_key, m in markets.items():
        match = _match_threshold(m.get("marketType") or "")
        if not match:
            continue
        stat, threshold = match
        ev_id = m.get("eventId")
        ev = events.get(str(ev_id), {}) or {}
        # Skip futures / non-game events
        ev_name = ev.get("name") or ""
        if "@" not in ev_name:
            continue
        start_time = ev.get("openDate")
        # market_key is the FD marketId — needed for addToBetslip deeplink
        fd_market_id = str(market_key)
        for runner in m.get("runners") or []:
            if not runner.get("isPlayerSelection"):
                continue
            odds_block = (runner.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}
            odds = odds_block.get("americanOdds")
            if odds is None:
                continue
            # runner.selectionId is the runnerId for addToBetslip deeplinks
            runner_selection_id = str(runner.get("selectionId") or "")
            rows.append({
                "captured_at": captured_at,
                "book": "fd",
                "game_id": ev_id,
                "player_id": runner_selection_id,
                "player_name": runner.get("runnerName"),
                "stat": stat,
                "line": threshold - 0.5,
                "over_price": int(odds),
                "under_price": "",   # FD does not publish NO on threshold markets
                "start_time": start_time,
                # Deeplink fields: Over is the only side FD publishes on threshold markets
                "book_selection_id_over": f"{fd_market_id}:{runner_selection_id}",
                "book_selection_id_under": "",
            })
    return rows


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Write canonical rows. If file exists, append (snapshot history)."""
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def one_snapshot() -> Dict[str, Any]:
    captured_at = datetime.utcnow().replace(microsecond=0).isoformat()
    j = fetch_fd()
    status = {
        "ran_at": captured_at,
        "rows": 0,
        "by_stat": {},
        "events": 0,
        "ok": False,
        "csv": None,
    }
    if j is None:
        return status
    rows = normalize_fd(j, captured_at=captured_at)
    status["rows"] = len(rows)
    by_stat: Dict[str, int] = {}
    for r in rows:
        by_stat[r["stat"]] = by_stat.get(r["stat"], 0) + 1
    status["by_stat"] = by_stat
    status["events"] = len({r["game_id"] for r in rows})
    today = _date.today().isoformat()
    csv_path = os.path.join(LINES_DIR, f"{today}_fd.csv")
    if rows:
        write_csv(rows, csv_path)
        status["ok"] = True
        status["csv"] = csv_path
    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py.

    Delegates to one_snapshot() which writes data/lines/<date>_fd.csv directly.
    Returns [] to prevent parallel_scraper from double-writing the same rows.
    """
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[fd] scrape_once failed: {type(exc).__name__}: {exc}", flush=True)
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if not args.daemon:
        s = one_snapshot()
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        print(json.dumps(s, indent=2))
        return 0 if s["ok"] else 2

    print(f"[fd-daemon] start interval={args.interval}s", flush=True)
    while True:
        # R19_L3 heartbeat
        _r19_hb('fd_scraper')
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2)
            print(
                f"[fd-daemon] {s['ran_at']} rows={s['rows']} "
                f"events={s['events']} by_stat={s['by_stat']} ok={s['ok']}",
                flush=True,
            )
        except Exception as exc:
            print(f"[fd-daemon] tick error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
