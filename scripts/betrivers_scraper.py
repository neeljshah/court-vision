"""betrivers_scraper.py — direct BetRivers NBA player-prop scraper.

KAMBI offering API, operator key ``rsiusia`` (2026). 1 event-list call + N
per-event betoffer calls. betOfferType.id==127 ("Player Occurrence Line")
carries O/U lines. Line + odds in milli-units (÷1000). STL/BLK/TOV not
exposed as O/U. See .planning/courtvision-odds/research_betrivers.md.
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

LINES_DIR   = os.path.join(PROJECT_DIR, "data", "lines")
CACHE_DIR   = os.path.join(PROJECT_DIR, "data", "cache")
STATUS_PATH = os.path.join(CACHE_DIR, "betrivers_results.json")
os.makedirs(LINES_DIR, exist_ok=True); os.makedirs(CACHE_DIR, exist_ok=True)

_BASE = "https://eu.offering-api.kambicdn.com/offering/v2018/rsiusia"
_QS, _NBA_GROUP, _MAX_EVENTS, _PLAYER_OFFER_TYPE = (
    "lang=en_US&market=US-IA&client_id=2", 1000093652, 10, 127)
# Fallback operators tried when rsiusia returns 404 / empty. rsiusva (US-VA)
# tends to surface the same KAMBI event catalog when IA cache misses.
# Verified 2026-05-28: rsiusia + rsiusva both expose group 1000093652 with
# identical event lists when up.
_FALLBACK_OPERATORS: list[tuple[str, str]] = [
    ("rsiusia", "US-IA"),
    ("rsiusva", "US-VA"),
    ("rsiuspa", "US-PA"),
    ("rsiusmi", "US-MI"),
]
# Polite cap on fallback retries within one snapshot.
_MAX_OPERATOR_RETRY = 3

_HEADERS: Dict[str, str] = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.betrivers.com/",
    "Origin": "https://www.betrivers.com",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
}

# Ordered — "3-point" must precede "points" to avoid fg3m routing to pts.
_LABEL_STAT: list[tuple[str, str]] = [
    ("3-point",  "fg3m"),
    ("three",    "fg3m"),
    ("points",   "pts"),
    ("rebounds", "reb"),
    ("assists",  "ast"),
]

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
    "book_selection_id_over", "book_selection_id_under",
]


def _get(url: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    """GET url with KAMBI headers; return parsed JSON or None."""
    try:
        r = cf_req.get(url, headers=_HEADERS, impersonate="chrome120", timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"[br] fetch error: {type(exc).__name__}: {exc}", flush=True)
        return None
    if r.status_code != 200:
        print(f"[br] HTTP {r.status_code} {url[:80]}", flush=True)
        return None
    try:
        return r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"[br] json parse error: {exc}", flush=True)
        return None


def _stat_for_label(label: str) -> Optional[str]:
    low = label.lower()
    for fragment, stat in _LABEL_STAT:
        if fragment in low:
            return stat
    return None


def _parse_american(s: Optional[str]) -> Optional[int]:
    """Strip leading '+', cast to int. KAMBI uses ASCII minus."""
    if not s:
        return None
    try:
        return int(s.lstrip("+"))
    except (TypeError, ValueError):
        return None


def _operator_url(operator: str, market: str, path: str) -> str:
    """Build a KAMBI URL for an arbitrary operator + market code."""
    qs = f"lang=en_US&market={market}&client_id=2"
    return f"https://eu.offering-api.kambicdn.com/offering/v2018/{operator}{path}?{qs}"


def fetch_event_ids() -> tuple[List[Dict[str, Any]], str]:
    """Return ([{id, start}], operator_key) for upcoming NBA events.

    KAMBI's IA endpoint flaps between 200 (with events) and 404
    ("No events found") on the same group ID. We try a sequence of US
    operators that share the same NBA group catalog until one responds with
    an event list — preserves uptime when one regional cache misses.
    """
    results: List[Dict[str, Any]] = []
    chosen_op = "rsiusia"
    for operator, market in _FALLBACK_OPERATORS[:_MAX_OPERATOR_RETRY]:
        url = _operator_url(operator, market, f"/event/group/{_NBA_GROUP}.json")
        data = _get(url)
        if data is None:
            continue
        events = data.get("events") or []
        if not events:
            continue
        for ev in events:
            # KAMBI sometimes wraps each event under an "event" key in listView
            # responses; defensively unwrap.
            evo = ev.get("event") if isinstance(ev, dict) and "event" in ev else ev
            if not isinstance(evo, dict):
                continue
            ev_id = evo.get("id")
            state = (evo.get("state") or evo.get("status") or "").upper()
            if state in ("FINISHED", "CLOSED", "CANCELLED"):
                continue
            if ev_id:
                results.append({"id": ev_id, "start": evo.get("start") or ""})
        if results:
            chosen_op = operator
            break
    return results[:_MAX_EVENTS], chosen_op


def fetch_event_offers(event_id: int, operator: str = "rsiusia",
                       market: str = "US-IA") -> Optional[Dict[str, Any]]:
    url = _operator_url(operator, market,
                        f"/betoffer/event/{event_id}.json") + "&includeParticipants=true"
    return _get(url)


def parse_offers(payload: Dict[str, Any], event_id: str,
                 start_time: str, captured_at: str,
                 seen_labels: set) -> List[Dict[str, Any]]:
    """Walk one event's betOffers; emit canonical rows. seen_labels mutated."""
    rows: List[Dict[str, Any]] = []
    for offer in payload.get("betOffers") or []:
        if (offer.get("betOfferType") or {}).get("id") != _PLAYER_OFFER_TYPE:
            continue
        eng_label = (offer.get("criterion") or {}).get("englishLabel") or ""
        seen_labels.add(eng_label)
        stat = _stat_for_label(eng_label)
        if stat is None:
            continue
        outcomes = offer.get("outcomes") or []
        if len(outcomes) < 2:
            continue
        over: Optional[Dict] = None
        under: Optional[Dict] = None
        for oc in outcomes:
            if (oc.get("status") or "").upper() != "OPEN":
                continue
            lbl = (oc.get("label") or "").strip().lower()
            if lbl == "over":
                over = oc
            elif lbl == "under":
                under = oc
        if over is None or under is None:
            continue
        raw_line = over.get("line")
        if raw_line is None:
            continue
        try:
            line = float(raw_line) / 1000.0
        except (TypeError, ValueError):
            continue
        player_name = str(over.get("participant") or "").strip()
        player_id   = str(over.get("participantId") or "").strip()
        if not player_name:
            continue
        over_price  = _parse_american(over.get("oddsAmerican"))
        under_price = _parse_american(under.get("oddsAmerican"))
        if over_price is None and under_price is None:
            continue
        # KAMBI outcome IDs — used to build event-page deeplink via event_id.
        # BetRivers doesn't expose per-outcome bet-slip deeplinks publicly,
        # but event_id routes to the correct game page on betrivers.com.
        sel_id_over  = str(over.get("id")  or "")
        sel_id_under = str(under.get("id") or "")
        rows.append({
            "captured_at":             captured_at,
            "book":                    "betrivers",
            "game_id":                 event_id,
            "player_id":               player_id,
            "player_name":             player_name,
            "stat":                    stat,
            "line":                    line,
            "over_price":              over_price if over_price is not None else "",
            "under_price":             under_price if under_price is not None else "",
            "start_time":              start_time,
            "book_selection_id_over":  sel_id_over,
            "book_selection_id_under": sel_id_under,
        })
    return rows


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """Append rows, dedup by (captured_at[:16], player_name, stat, line)."""
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
        "ok": False, "csv": None, "unique_labels": [],
    }
    event_stubs, operator = fetch_event_ids()
    market = next((mk for op, mk in _FALLBACK_OPERATORS if op == operator), "US-IA")
    if not event_stubs:
        print("[br] no upcoming NBA events found (tried "
              f"{_MAX_OPERATOR_RETRY} operators)", flush=True)
        return status
    print(f"[br] using operator={operator} events={len(event_stubs)}", flush=True)
    all_rows: List[Dict[str, Any]] = []
    seen_labels: set = set()
    no_prop_events = 0
    for stub in event_stubs:
        payload = fetch_event_offers(stub["id"], operator, market)
        if payload is not None:
            before = len(all_rows)
            all_rows.extend(parse_offers(payload, str(stub["id"]),
                                         stub["start"], captured_at, seen_labels))
            if len(all_rows) == before:
                no_prop_events += 1
    if no_prop_events:
        print(f"[br] {no_prop_events}/{len(event_stubs)} events had no "
              f"type-{_PLAYER_OFFER_TYPE} player-prop offers (book hasn't "
              f"posted props yet)", flush=True)
    status["unique_labels"] = sorted(seen_labels)
    if all_rows:
        csv_path = os.path.join(LINES_DIR, f"{today}_betrivers.csv")
        write_csv(all_rows, csv_path)
        by_stat: Dict[str, int] = {}
        for r in all_rows:
            by_stat[r["stat"]] = by_stat.get(r["stat"], 0) + 1
        status.update(csv=csv_path, ok=True, rows=len(all_rows),
                      events=len({r["game_id"] for r in all_rows}),
                      by_stat=by_stat)
    return status


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py. Writes CSV directly; returns []."""
    try:
        one_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[br] scrape_once failed: {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon",   action="store_true")
    ap.add_argument("--interval", type=int, default=30)
    args = ap.parse_args()
    if not args.daemon:
        s = one_snapshot()
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2, default=str)
        print(json.dumps(s, indent=2, default=str))
        return 0 if s["ok"] else 2
    print(f"[br-daemon] start interval={args.interval}s", flush=True)
    while True:
        _hb("betrivers_scraper")
        try:
            s = one_snapshot()
            with open(STATUS_PATH, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2, default=str)
            print(f"[br-daemon] {s['ran_at']} rows={s['rows']} "
                  f"events={s['events']} by_stat={s['by_stat']} ok={s['ok']}",
                  flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[br-daemon] tick error: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
