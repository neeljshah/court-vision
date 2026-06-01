"""pointsbet_scraper.py — direct PointsBet AU NBA player-prop scraper.

Base: `https://api.au.pointsbet.com`. No auth required. Two calls per scrape:
  1. GET /api/mes/v3/events/featured/competition/7176?page=1  → event list
  2. GET /api/mes/v3/events/{eventKey}                        → markets + outcomes

Stats detected via market.eventName:
    Player Points Over/Under → pts  |  Player Rebounds Over/Under → reb
    Player Assists Over/Under → ast |  Player 3-Pointers Made → fg3m

Composite markets skipped. Decimal odds converted to American.
Output: data/lines/<YYYY-MM-DD>_pointsbet.csv (canonical schema).
See `.planning/courtvision-odds/research_pointsbet.md` for probe notes.
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
from datetime import datetime, date as _date, timezone
from typing import Any, Dict, List, Optional

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

STATUS_PATH = os.path.join(CACHE_DIR, "pointsbet_results.json")

_BASE = "https://api.au.pointsbet.com"
_NBA_COMPETITION_KEY = "7176"
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# eventName (exact) → canonical stat code.  Composite markets are absent.
_STAT_MAP: Dict[str, str] = {
    "Player Points Over/Under":    "pts",
    "Player Rebounds Over/Under":  "reb",
    "Player Assists Over/Under":   "ast",
    "Player 3-Pointers Made":      "fg3m",
    # Some AU slates use these alternate spellings — keep both.
    "Player 3-Pointers Over/Under": "fg3m",
    "Player Threes Over/Under":     "fg3m",
}

# Regex to strip trailing " Over X.X" / " Under X.X" from outcome names.
_STRIP_SIDE = re.compile(r"\s+(Over|Under)\s+\d+(\.\d+)?$", re.IGNORECASE)

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
    "book_selection_id_over", "book_selection_id_under",
]


# ── helpers ──────────────────────────────────────────────────────────────

def decimal_to_american(d: float) -> Optional[int]:
    """Convert decimal odds to American odds (rounded integer).

    Returns None for d <= 1.0 (implies guaranteed or invalid payout)
    to avoid ZeroDivisionError.
    """
    if d <= 1.0:
        return None
    if d >= 2.0:
        return int(round((d - 1.0) * 100))
    return int(round(-100.0 / (d - 1.0)))


def _get(path: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    """GET `_BASE + path`, return parsed JSON or None on error."""
    url = f"{_BASE}{path}"
    try:
        r = cf_req.get(url, headers=_HEADERS, impersonate="chrome120", timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[pb] fetch error {path}: {type(exc).__name__}: {exc}", flush=True)
        return None
    if r.status_code != 200:
        print(f"[pb] non-200 {path}: {r.status_code} len={len(r.content)}", flush=True)
        return None
    try:
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[pb] json parse error {path}: {exc}", flush=True)
        return None


# ── fetch layer ──────────────────────────────────────────────────────────

def fetch_event_keys() -> List[str]:
    """Return list of eventKey strings for today's NBA slate."""
    payload = _get(
        f"/api/mes/v3/events/featured/competition/{_NBA_COMPETITION_KEY}?page=1"
    )
    if not payload:
        return []
    events = payload.get("events") or []
    keys = []
    for ev in events:
        k = ev.get("key") or ev.get("eventKey") or ev.get("id")
        if k:
            keys.append(str(k))
    return keys


def fetch_event(event_key: str) -> Optional[Dict[str, Any]]:
    """Return the omnibus event payload (markets + outcomes) or None."""
    return _get(f"/api/mes/v3/events/{event_key}")


# ── normalisation ────────────────────────────────────────────────────────

def normalize_event(ev: Dict[str, Any], captured_at: str) -> List[Dict[str, Any]]:
    """Walk one event's fixedOddsMarkets and emit canonical rows.

    Each market contains many outcomes. We group by (playerId, points) to
    pair the Over and Under, then emit one row per pair.
    """
    event_key = str(ev.get("key") or ev.get("eventKey") or ev.get("id") or "")
    starts_at = ev.get("startsAt") or ""
    markets = ev.get("fixedOddsMarkets") or []

    rows: List[Dict[str, Any]] = []
    for market in markets:
        if not (market.get("isOpenForBetting", True)):
            continue
        event_name = (market.get("eventName") or "").strip()
        stat = _STAT_MAP.get(event_name)
        if stat is None:
            continue  # composite or unrecognised market — skip

        # Market key used for the /markets/<key> deeplink URL segment.
        market_key: str = str(market.get("key") or market.get("id") or "")

        outcomes = market.get("outcomes") or []
        # Group outcomes by (playerId, points) → {player_id: {points: {over/under: price}}}
        groups: Dict[tuple, Dict[str, Any]] = {}
        for oc in outcomes:
            if not oc.get("isOpenForBetting", True):
                continue
            player_id = str(oc.get("playerId") or "")
            points_raw = oc.get("points")
            if points_raw is None:
                continue
            try:
                line = float(points_raw)
            except (TypeError, ValueError):
                continue
            price_dec = oc.get("price")
            if price_dec is None:
                continue
            try:
                price_dec = float(price_dec)
            except (TypeError, ValueError):
                continue

            # Derive player name by stripping " Over/Under X.X" suffix.
            raw_name = oc.get("name") or ""
            player_name = _STRIP_SIDE.sub("", raw_name).strip()

            # Determine over/under from name suffix (NOT 'side' field — that is
            # home/away team affiliation, a documented gotcha in the research notes).
            name_lower = raw_name.lower()
            if " over " in name_lower:
                side = "over"
            elif " under " in name_lower:
                side = "under"
            else:
                continue  # can't classify → skip

            key = (player_id, line)
            if key not in groups:
                groups[key] = {"player_name": player_name, "player_id": player_id,
                               "line": line, "over": None, "under": None,
                               "market_key": market_key}
            # Store the player name even if already set (in case first oc had empty name)
            if player_name:
                groups[key]["player_name"] = player_name
            am = decimal_to_american(price_dec)
            if am is None:
                continue  # d <= 1.0 — invalid odds, skip this outcome
            groups[key][side] = am

        for (player_id, line), g in groups.items():
            if g["over"] is None and g["under"] is None:
                continue
            player_name = g["player_name"]
            if not player_name:
                continue
            # book_selection_id_over stores the market key so the deeplink builder
            # can construct /markets/<key> URLs (per-market, not per-outcome).
            rows.append({
                "captured_at": captured_at,
                "book": "pointsbet",
                "game_id": event_key,
                "player_id": player_id,
                "player_name": player_name,
                "stat": stat,
                "line": line,
                "over_price":  g["over"]  if g["over"]  is not None else "",
                "under_price": g["under"] if g["under"] is not None else "",
                "start_time": starts_at,
                "book_selection_id_over":  g.get("market_key") or "",
                "book_selection_id_under": "",
            })
    return rows


# ── CSV persistence ───────────────────────────────────────────────────────

def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Append rows; dedup by (captured_at[:16], player_name, stat, line) so
    re-runs within the same minute don't produce duplicates. Header written
    only when the file is new or empty."""
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    existing_keys: set = set()
    if not new_file:
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    existing_keys.add((
                        (r.get("captured_at") or "")[:16],
                        r.get("player_name") or "",
                        r.get("stat") or "",
                        str(r.get("line") or ""),
                    ))
        except OSError:
            new_file = True
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            key = (r["captured_at"][:16], r["player_name"], r["stat"], str(r["line"]))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            w.writerow(r)


# ── snapshot orchestration ───────────────────────────────────────────────

def one_snapshot() -> Dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    today = _date.today().isoformat()
    status: Dict[str, Any] = {
        "ran_at": captured_at, "rows": 0, "by_stat": {}, "events": 0,
        "ok": False, "csv": None,
    }

    event_keys = fetch_event_keys()
    if not event_keys:
        print("[pb] no NBA events found", flush=True)
        return status

    all_rows: List[Dict[str, Any]] = []
    for key in event_keys:
        ev = fetch_event(key)
        if ev is None:
            continue
        try:
            rows = normalize_event(ev, captured_at)
        except Exception as exc:  # noqa: BLE001
            print(f"[pb] normalize_event error for event {key}: {type(exc).__name__}: {exc}",
                  flush=True)
            continue
        all_rows.extend(rows)

    if all_rows:
        csv_path = os.path.join(LINES_DIR, f"{today}_pointsbet.csv")
        write_csv(all_rows, csv_path)
        status["csv"] = csv_path
        status["ok"] = True
        status["rows"] = len(all_rows)
        status["events"] = len({r["game_id"] for r in all_rows})
        by_stat: Dict[str, int] = {}
        for r in all_rows:
            by_stat[r["stat"]] = by_stat.get(r["stat"], 0) + 1
        status["by_stat"] = by_stat

    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for `parallel_scraper._fetch_pointsbet`. Writes CSV; returns []."""
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[pb] scrape_once failed: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
    return []


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()

    if not args.daemon:
        s = one_snapshot()
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        print(json.dumps(s, indent=2))
        return 0 if s["ok"] else 2

    print(f"[pb-daemon] start interval={args.interval}s", flush=True)
    while True:
        _hb("pointsbet_scraper")
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2)
            print(
                f"[pb-daemon] {s['ran_at']} rows={s['rows']} "
                f"events={s['events']} by_stat={s['by_stat']} ok={s['ok']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[pb-daemon] tick error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
