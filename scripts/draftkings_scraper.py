"""draftkings_scraper.py — direct DraftKings NBA player-prop scraper.

DK's legacy `sportsbook.draftkings.com/sites/US-SB/api/v5/...` returns 403
(Akamai), but `sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1/...`
returns 200 + valid JSON when curl_cffi impersonates chrome120. No cookie
priming is required.

NBA leagueId = 42648. For each canonical stat we hit the (category, subcategory)
pair that hosts the over/under line:

    pts  → cat 1215 / subId 12488 (Points O/U)
    reb  → cat 1216 / subId 12492 (Rebounds O/U)
    ast  → cat 1217 / subId 12495 (Assists O/U)
    fg3m → cat 1218 / subId 12497 (Threes O/U)

STL/BLK/TOV are not exposed as dedicated DK subcategories (matches what the
the_odds_api reference feed reports for DK on most slates) — skip in v1.

Each market has exactly two selections (Over + Under). We canonicalise to
one row per (game, player, stat, line) and write to
`data/lines/<date>_dk.csv` in the schema other CourtVision components
already consume.

Run modes:
    --once     fetch one snapshot, write CSV, exit
    --daemon   loop forever with --interval seconds between snapshots (default 30)

Live-gate invariant (Bug A fix, 2026-05-31; data-loss-safe revision)
--------------------------------------------------------------------
The "live" category IDs (1686-1689) serve DK's in-play O/U markets; the
"legacy" IDs (1215-1218) serve pre-game O/U markets.  When any NBA event is
currently IN_PROGRESS / STARTED on DK, fetching the live categories yields
IN-PLAY prices that must NOT appear in the pre-game book="dk" CSV — they
would contaminate pregame edges / arb detection.

The naive fix (drop 1686-1689 entirely, fetch only legacy 1215-1218) carries
a DATA-LOSS risk we cannot verify offline: if DK's legacy 1215 category is
EMPTY/403 pre-tip (the original code used 1686 as PRIMARY with 1215 only as a
fallback, hinting they may have migrated pregame lines onto 1686), the naive
fix would silently produce ZERO DK pregame lines — a worse, silent regression
than the contamination bug.

Data-loss-safe gate (this revision).  ``one_snapshot`` calls
``_live_event_ids()`` once up front; if that call raises/times out we treat
liveness as UNKNOWN and behave as the NO-live branch so a detection failure
never costs us data:

  * NO game live (pre-tip / off-hours / detection failure): for each stat,
    fetch the legacy 1215-1218 category PRIMARY.  If a stat's legacy payload
    yields ZERO rows, FALL BACK to that stat's live category (1686-1689) and
    use whatever it returns.  Pre-tip the "live" category serves pregame
    lines, so this recovers coverage if the legacy category is dead — DK
    pregame coverage is never reduced vs. the original.

  * A game IS live: fetch ONLY the legacy 1215-1218 categories.  NEVER touch
    1686-1689 — that is precisely the in-play contamination we are preventing.
    If a legacy category is empty for a live game we write nothing for it (the
    in-play scraper handles live games on the 1686-1689 path).

Net invariant: 1686-1689 (live) data is NEVER fetched/written under book="dk"
WHILE A GAME IS LIVE.  Pre-tip, 1686-1689 may be used as an empty-fallback so
pregame coverage is never reduced.  The ``_DK_LIVE_CAT_IDS`` assert canary
enforces "no live cat fetched while a game is live" (not "never fetched at
all"), since pre-tip 1686-as-fallback is now allowed.  The in-play scraper
(draftkings_inplay_scraper.py) remains the correct and sole consumer of
1686-1689 for actual in-play prices.

See `.planning/courtvision-odds/research_dk.md` for full probe notes.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
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

STATUS_PATH = os.path.join(CACHE_DIR, "draftkings_results.json")

# (categoryId, subcategoryId) per canonical stat — the LEGACY PREGAME O/U
# categories. Fetched PRIMARY in all cases.
_DK_STAT_PATHS: Dict[str, tuple[int, int]] = {
    "pts":  (1215, 12488),  # Points O/U (pregame)
    "reb":  (1216, 12492),  # Rebounds O/U (pregame)
    "ast":  (1217, 12495),  # Assists O/U (pregame)
    "fg3m": (1218, 12497),  # Threes O/U (pregame)
}
# (categoryId, subcategoryId) per canonical stat — the LIVE in-play O/U
# categories.  Used ONLY as an empty-fallback when (a) NO game is live AND
# (b) the legacy pregame category above returned zero rows for that stat.
# Pre-tip these "live" categories serve pregame lines, so falling back to them
# recovers coverage if the legacy category is dead.  They are NEVER fetched
# while a game is live (would contaminate book="dk" with in-play prices).
# Mirrors draftkings_inplay_scraper._DK_INPLAY_PATHS for the four O/U stats.
_DK_LIVE_FALLBACK_PATHS: Dict[str, tuple[int, int]] = {
    "pts":  (1686, 16413),  # Points O/U (live; pregame-fallback only)
    "ast":  (1687, 16414),  # Assists O/U (live; pregame-fallback only)
    "reb":  (1688, 16415),  # Rebounds O/U (live; pregame-fallback only)
    "fg3m": (1689, 16416),  # Threes O/U (live; pregame-fallback only)
}
# Live category IDs — exclusion guard. one_snapshot() asserts none of these
# are fetched under book="dk" WHILE A GAME IS LIVE (pre-tip fallback is OK).
_DK_LIVE_CAT_IDS: frozenset = frozenset({1686, 1687, 1688, 1689})
_NBA_LEAGUE_ID = 42648
_BASE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1"
_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.draftkings.com/",
    "Origin": "https://sportsbook.draftkings.com",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
}

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
    "book_selection_id_over", "book_selection_id_under",
]


def _parse_odds(american: Optional[str]) -> Optional[int]:
    """DK displayOdds.american may contain U+2212 (true minus) rather than ASCII '-'."""
    if not american:
        return None
    s = american.replace("−", "-").replace("+", "").strip()
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def fetch_subcategory(cat_id: int, sub_id: int,
                       timeout: int = 15) -> Optional[Dict[str, Any]]:
    """Fetch one (cat, subcat) under leagueId=42648. Returns parsed JSON or None."""
    url = f"{_BASE}/leagues/{_NBA_LEAGUE_ID}/categories/{cat_id}/subcategories/{sub_id}"
    try:
        r = cf_req.get(url, headers=_HEADERS, impersonate="chrome120", timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[dk] fetch error cat={cat_id} sub={sub_id}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return None
    if r.status_code != 200:
        print(f"[dk] non-200 cat={cat_id} sub={sub_id}: "
              f"{r.status_code} len={len(r.content)}", flush=True)
        return None
    try:
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[dk] json parse error cat={cat_id}: {exc}", flush=True)
        return None


def normalize(payload: Dict[str, Any], stat: str,
              captured_at: str) -> List[Dict[str, Any]]:
    """Walk one subcategory payload and emit canonical rows.

    Each market has 0..2 selections with label='Over'/'Under'. We assemble
    over+under into one row per (market). Markets with no over/under price
    on either side are skipped.
    """
    events = {e["id"]: e for e in payload.get("events") or []}
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
        ev = events.get(ev_id) or {}
        start_time = ev.get("startEventDate") or ""

        # Find the player participant (skip multi-player Combined / H2H markets)
        player_name = ""
        player_id: Any = ""
        for s in sels:
            parts = [p for p in (s.get("participants") or [])
                     if (p.get("type") == "Player")]
            if len(parts) != 1:
                continue
            player_name = parts[0].get("name") or ""
            player_id = parts[0].get("id") or ""
            break
        if not player_name:
            continue

        line: Optional[float] = None
        over_price: Optional[int] = None
        under_price: Optional[int] = None
        sel_id_over: str = ""
        sel_id_under: str = ""
        for s in sels:
            label = (s.get("label") or "").strip().lower()
            pts = s.get("points")
            if pts is None:
                continue  # skip threshold-style "Milestones" selections
            try:
                pts_f = float(pts)
            except (TypeError, ValueError):
                continue
            price = _parse_odds((s.get("displayOdds") or {}).get("american"))
            sel_id = str(s.get("id") or "")
            if label == "over":
                line = pts_f
                over_price = price
                sel_id_over = sel_id
            elif label == "under":
                line = pts_f
                under_price = price
                sel_id_under = sel_id
        if line is None or (over_price is None and under_price is None):
            continue
        rows.append({
            "captured_at": captured_at,
            "book": "dk",
            "game_id": ev_id,
            "player_id": player_id,
            "player_name": player_name,
            "stat": stat,
            "line": line,
            "over_price": over_price if over_price is not None else "",
            "under_price": under_price if under_price is not None else "",
            "start_time": start_time,
            "book_selection_id_over": sel_id_over,
            "book_selection_id_under": sel_id_under,
        })
    return rows


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Append rows, dedup by (captured_at[:16], player, stat, line) so re-runs
    in the same minute do not duplicate. Header written when file is new."""
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


def one_snapshot() -> Dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    today = _date.today().isoformat()
    status: Dict[str, Any] = {
        "ran_at": captured_at, "rows": 0, "by_stat": {}, "events": 0,
        "ok": False, "csv": None, "live_games_detected": 0,
    }

    # Live-gate (Bug A fix, data-loss-safe revision): detect live NBA events
    # via the inplay scraper's helper.  Liveness controls whether the live
    # categories (1686-1689) may be used as an empty-fallback:
    #   * a_game_live == True  -> legacy ONLY; never touch 1686-1689.
    #   * a_game_live == False -> legacy primary, live-cat empty-fallback OK.
    # If detection raises/times out we treat liveness as UNKNOWN and behave as
    # the NO-live branch (fallback allowed) so a detection failure never costs
    # us pregame data.  See module docstring for the full invariant.
    a_game_live = False
    try:
        from draftkings_inplay_scraper import _live_event_ids
        live_ids = _live_event_ids()
        a_game_live = bool(live_ids)
        status["live_games_detected"] = len(live_ids)
    except Exception:  # noqa: BLE001
        # Detection failure -> unknown -> behave as NO-live (fallback allowed).
        status["live_games_detected"] = 0
    status["fallback_allowed"] = not a_game_live
    if a_game_live:
        print(
            f"[dk] {status['live_games_detected']} NBA game(s) live — fetching "
            f"LEGACY pregame categories only (1215-1218); live cats 1686-1689 "
            f"are NOT used (in-play prices go to dk_inplay).",
            flush=True,
        )

    all_rows: List[Dict[str, Any]] = []
    used_fallback: List[str] = []
    for stat, (cat_id, sub_id) in _DK_STAT_PATHS.items():
        # Legacy pregame category is always the PRIMARY fetch.
        payload = fetch_subcategory(cat_id, sub_id)
        rows = normalize(payload, stat, captured_at) if payload else []

        # Empty-fallback to the live category, ONLY when no game is live.
        # This recovers pregame coverage if the legacy category is dead pre-tip.
        if not rows and not a_game_live:
            fb = _DK_LIVE_FALLBACK_PATHS.get(stat)
            if fb is not None:
                fb_cat, fb_sub = fb
                # Invariant: a live cat may be fetched ONLY when no game is live.
                assert not a_game_live or fb_cat not in _DK_LIVE_CAT_IDS, (
                    f"BUG: attempted to fetch live cat {fb_cat} under book='dk' "
                    f"WHILE A GAME IS LIVE — would contaminate pregame CSV."
                )
                fb_payload = fetch_subcategory(fb_cat, fb_sub)
                fb_rows = normalize(fb_payload, stat, captured_at) if fb_payload else []
                if fb_rows:
                    rows = fb_rows
                    used_fallback.append(stat)

        all_rows.extend(rows)
        status["by_stat"][stat] = len(rows)
    if used_fallback:
        status["fallback_stats"] = used_fallback
        print(
            f"[dk] legacy categories empty for {used_fallback}; recovered "
            f"pregame lines from live categories (no game live).",
            flush=True,
        )
    if all_rows:
        csv_path = os.path.join(LINES_DIR, f"{today}_dk.csv")
        write_csv(all_rows, csv_path)
        status["csv"] = csv_path
        status["ok"] = True
        status["rows"] = len(all_rows)
        status["events"] = len({r["game_id"] for r in all_rows})
    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for `parallel_scraper.py`. Writes CSV directly; returns []."""
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[dk] scrape_once failed: {type(exc).__name__}: {exc}", flush=True)
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

    print(f"[dk-daemon] start interval={args.interval}s", flush=True)
    while True:
        _hb("dk_scraper")
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2)
            print(
                f"[dk-daemon] {s['ran_at']} rows={s['rows']} "
                f"events={s['events']} by_stat={s['by_stat']} ok={s['ok']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[dk-daemon] tick error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
