"""draftkings_inplay_scraper.py — DraftKings NBA player-prop LIVE (in-play) scraper.

DK in-play props use "Milestone" markets (threshold-style: "Score 25+ Points").
In-play subcategoryIds (leagueId=42648):
    pts → cat 1215 / subId 16477 | reb → cat 1216 / subId 16479
    ast → cat 1217 / subId 16478 | fg3m → cat 1218 / subId 16480

Gate: fetches event list first; skips prop calls if no event has status=IN_PROGRESS.
Output: data/lines/<date>_dk_inplay.csv  book="dk_inplay"
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

STATUS_PATH = os.path.join(CACHE_DIR, "draftkings_inplay_results.json")

_NBA_LEAGUE_ID = 42648
_BASE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1"
_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.draftkings.com/",
    "Origin": "https://sportsbook.draftkings.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# (categoryId, subcategoryId) for milestone in-play props
# Live in-play player-prop O/U (category, subcategory). DK rotated these from
# the old milestone IDs (1215/16477...); discovered 2026-05-30 from the league
# /leagues/{id} categories+subcategories list (Live-tagged "X O/U" subs).
_DK_INPLAY_PATHS: Dict[str, tuple] = {
    "pts":  (1686, 16413),   # Points O/U
    "ast":  (1687, 16414),   # Assists O/U
    "reb":  (1688, 16415),   # Rebounds O/U
    "fg3m": (1689, 16416),   # Threes O/U
    "blk":  (1691, 16418),   # Blocks O/U
    "stl":  (1691, 16419),   # Steals O/U
}
_MILESTONE_RE = re.compile(r"^(\d+(?:\.\d+)?)\+$")

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]


def _parse_odds(american: Optional[str]) -> Optional[int]:
    """DK displayOdds.american may use U+2212 (true minus) instead of ASCII '-'."""
    if not american:
        return None
    s = str(american).replace("−", "-").replace("+", "").strip()
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _live_event_ids(timeout: int = 10) -> List[str]:
    """Return DK eventIds whose status == 'IN_PROGRESS'.

    Fetches the league event list (lightweight, no markets). Returns empty list
    if the request fails or no games are currently live.
    """
    url = f"{_BASE}/leagues/{_NBA_LEAGUE_ID}"
    try:
        r = cf_req.get(url, headers=_HEADERS, impersonate="chrome120",
                       timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[dk_inplay] event list fetch error: {exc}", flush=True)
        return []
    if r.status_code != 200:
        return []
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        return []
    # DK reports a live game as status "STARTED" (observed Game 7 2026-05-30);
    # older docs used "IN_PROGRESS". Accept all live-state strings so in-play
    # props are actually fetched once the game tips.
    _LIVE = {"IN_PROGRESS", "STARTED", "LIVE", "IN_PLAY"}
    return [
        e["id"] for e in (j.get("events") or [])
        if e.get("status") in _LIVE
    ]


def fetch_subcategory(cat_id: int, sub_id: int,
                      timeout: int = 15) -> Optional[Dict[str, Any]]:
    """Fetch one in-play milestone subcategory. Returns parsed JSON or None."""
    url = (f"{_BASE}/leagues/{_NBA_LEAGUE_ID}"
           f"/categories/{cat_id}/subcategories/{sub_id}")
    try:
        r = cf_req.get(url, headers=_HEADERS, impersonate="chrome120",
                       timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[dk_inplay] fetch error cat={cat_id} sub={sub_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return None
    if r.status_code != 200:
        print(f"[dk_inplay] non-200 cat={cat_id} sub={sub_id}: "
              f"{r.status_code}", flush=True)
        return None
    try:
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[dk_inplay] json parse error cat={cat_id}: {exc}", flush=True)
        return None


def normalize_milestones(
    payload: Dict[str, Any],
    stat: str,
    captured_at: str,
    live_event_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Walk milestone subcategory payload → canonical rows.

    label="25+" → line=24.5, over_price=odds, under_price="".
    If live_event_ids provided, restricts to those events only.
    """
    events = {e["id"]: e for e in (payload.get("events") or [])}
    markets = payload.get("markets") or []
    selections = payload.get("selections") or []

    sel_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for s in selections:
        mid = s.get("marketId")
        if mid:
            sel_by_market.setdefault(mid, []).append(s)

    rows: List[Dict[str, Any]] = []
    for m in markets:
        mid = m.get("id")
        sels = sel_by_market.get(mid, [])
        if not sels:
            continue
        ev_id = m.get("eventId") or ""
        # Game-state filter: if caller supplied live IDs, restrict to them
        if live_event_ids is not None and ev_id not in live_event_ids:
            continue
        ev = events.get(ev_id) or {}
        start_time = ev.get("startEventDate") or ""

        # Identify player from any selection's participants list
        player_name = ""
        player_id: Any = ""
        for s in sels:
            parts = [p for p in (s.get("participants") or [])
                     if p.get("type") == "Player"]
            if len(parts) != 1:
                continue
            player_name = parts[0].get("name") or ""
            player_id = parts[0].get("id") or ""
            break
        if not player_name:
            continue

        # Emit one row per threshold selection
        for s in sels:
            label = (s.get("label") or "").strip()
            m_match = _MILESTONE_RE.match(label)
            if not m_match:
                continue  # skip non-threshold labels
            threshold = float(m_match.group(1))
            line = threshold - 0.5   # e.g. "25+" → line 24.5
            price = _parse_odds(
                (s.get("displayOdds") or {}).get("american")
            )
            if price is None:
                continue
            rows.append({
                "captured_at": captured_at,
                "book": "dk_inplay",
                "game_id": ev_id,
                "player_id": player_id,
                "player_name": player_name,
                "stat": stat,
                "line": line,
                "over_price": price,
                "under_price": "",  # DK does not publish under on milestone markets
                "start_time": start_time,
            })
    return rows


def _dk_american(sel: Dict[str, Any]) -> "int | None":
    """Parse a DK selection's American odds. DK renders the minus sign as a
    UNICODE minus (U+2212), so str()->int() fails without normalisation."""
    raw = ((sel.get("displayOdds") or {}).get("american") or "").strip()
    raw = raw.replace("−", "-").replace("+", "")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _is_main_selection(s: Dict[str, Any]) -> bool:
    """Return True if this selection is DK's main/primary line.

    DK marks the canonical line with main==True and/or a 'MainPointLine' tag.
    Alt rungs (alternate lines) have main==False and lack that tag.
    """
    if s.get("main") is True:
        return True
    tags = s.get("tags") or []
    return "MainPointLine" in tags


def normalize_ou(payload: Dict[str, Any], stat: str, captured_at: str,
                 live_event_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Parse a live 'X O/U' subcategory (cat 1686-1691) into prop rows with BOTH
    over_price and under_price. DK's live player props are two-way O/U markets
    (line + Over/Under), not the old one-way milestone format.

    Deduplication rule: when a player/stat has multiple point lines (main line +
    alt rungs), prefer the selection with main==True or tag 'MainPointLine'.
    Only fall back to all lines if no selection carries a main flag, ensuring the
    output contains at most ONE row per (player, stat).
    """
    markets = payload.get("markets") or []
    selections = payload.get("selections") or []
    mkt_event = {str(m.get("id")): str(m.get("eventId") or "") for m in markets}
    live = set(live_event_ids or [])

    # First pass: collect all valid selections grouped by (ev_id, player, line).
    # Track whether any selection per (ev_id, player) is flagged as main.
    # grp keys: (ev_id, pname, line) -> row dict
    # main_keys: (ev_id, pname) -> set of lines that are flagged main
    grp: Dict[tuple, Dict[str, Any]] = {}
    main_keys: Dict[tuple, set] = {}  # (ev_id, pname) -> {line, ...}

    for s in selections:
        mid = str(s.get("marketId") or "")
        ev_id = mkt_event.get(mid, "")
        if live and ev_id not in live:
            continue
        parts = s.get("participants") or []
        if not parts:
            continue
        pname = parts[0].get("name") or ""
        pid = parts[0].get("id") or ""
        try:
            line = float(s.get("points"))
        except (TypeError, ValueError):
            continue
        odds = _dk_american(s)
        side = (s.get("outcomeType") or s.get("label") or "").lower()
        if not pname or odds is None or side not in ("over", "under"):
            continue

        is_main = _is_main_selection(s)
        player_key = (ev_id, pname)
        line_key = (ev_id, pname, line)

        row = grp.setdefault(line_key, {
            "captured_at": captured_at, "book": "dk_inplay", "game_id": ev_id,
            "player_id": pid, "player_name": pname, "stat": stat, "line": line,
            "over_price": "", "under_price": "", "start_time": "",
            "_is_main": False,
        })
        row["over_price" if side == "over" else "under_price"] = odds
        if is_main:
            row["_is_main"] = True
            main_keys.setdefault(player_key, set()).add(line)

    # Second pass: for each (ev_id, player), keep only the main line(s).
    # If no main flags exist for that player, keep all lines (fallback).
    result: List[Dict[str, Any]] = []
    seen_player: set = set()
    # Sort so main-flagged rows come first within each player group
    sorted_rows = sorted(
        grp.values(),
        key=lambda r: (r["game_id"], r["player_name"],
                       0 if r["_is_main"] else 1, r["line"]),
    )
    for row in sorted_rows:
        player_key = (row["game_id"], row["player_name"])
        has_any_main = bool(main_keys.get(player_key))
        # Skip alt rungs when a main line exists for this player
        if has_any_main and not row["_is_main"]:
            continue
        # Deduplicate to one row per (player, stat): take the first (lowest line
        # for non-main fallback; main line for main-flagged players)
        if player_key in seen_player:
            continue
        seen_player.add(player_key)
        # Strip internal sentinel before emitting
        out = {k: v for k, v in row.items() if k != "_is_main"}
        if out["over_price"] != "" or out["under_price"] != "":
            result.append(out)

    return result


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Append rows with dedup on (captured_at[:16], player, stat, line)."""
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
            key = (r["captured_at"][:16], r["player_name"],
                   r["stat"], str(r["line"]))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            w.writerow(r)


def one_snapshot() -> Dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    today = _date.today().isoformat()
    status: Dict[str, Any] = {
        "ran_at": captured_at, "rows": 0, "by_stat": {},
        "events": 0, "ok": False, "csv": None,
        "live_game_count": 0,
    }

    # Gate: check for live games first
    live_ids = _live_event_ids()
    status["live_game_count"] = len(live_ids)
    if not live_ids:
        print("[dk_inplay] no games IN_PROGRESS — skipping prop endpoints",
              flush=True)
        status["ok"] = True   # not a failure; expected during off-hours
        return status

    print(f"[dk_inplay] {len(live_ids)} game(s) live: {live_ids}", flush=True)

    all_rows: List[Dict[str, Any]] = []
    for stat, (cat_id, sub_id) in _DK_INPLAY_PATHS.items():
        payload = fetch_subcategory(cat_id, sub_id)
        if payload is None:
            continue
        rows = normalize_ou(payload, stat, captured_at,
                            live_event_ids=live_ids)
        all_rows.extend(rows)
        status["by_stat"][stat] = len(rows)

    if all_rows:
        csv_path = os.path.join(LINES_DIR, f"{today}_dk_inplay.csv")
        write_csv(all_rows, csv_path)
        status["csv"] = csv_path
        status["ok"] = True
        status["rows"] = len(all_rows)
        status["events"] = len({r["game_id"] for r in all_rows})
    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py. Writes CSV; returns []."""
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[dk_inplay] scrape_once failed: {type(exc).__name__}: {exc}",
              flush=True)
        traceback.print_exc()
    return []


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

    print(f"[dk_inplay-daemon] start interval={args.interval}s", flush=True)
    while True:
        _hb("dk_inplay_scraper")
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2)
            print(
                f"[dk_inplay-daemon] {s['ran_at']} rows={s['rows']} "
                f"live_games={s['live_game_count']} "
                f"by_stat={s['by_stat']} ok={s['ok']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[dk_inplay-daemon] tick error: {type(exc).__name__}: {exc}",
                  flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
