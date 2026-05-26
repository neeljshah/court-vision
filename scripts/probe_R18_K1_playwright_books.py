"""probe_R18_K1_playwright_books.py - crack DK / Caesars / MGM via Playwright stealth.

Why
---
R15 cracked FanDuel with curl_cffi (TLS impersonation alone was enough).
DK / BetMGM / Caesars still 403 because their WAF (Akamai + PerimeterX)
requires real-browser JavaScript execution to mint `sensor_data` cookies.

Approach
--------
Launch headless Chromium with playwright-stealth (patches navigator.webdriver,
chrome runtime, plugins, languages, permissions), navigate to each book's
NBA sportsbook page, listen on `page.on("response", ...)` for the book's own
XHR/fetch calls to its props API, then parse the JSON payloads.

Order (stop at first success):
  1. DraftKings    https://sportsbook.draftkings.com/leagues/basketball/nba
  2. Caesars       https://sportsbook.caesars.com/us/nj/bet/basketball?id=...
  3. BetMGM        https://sports.nj.betmgm.com/en/sports/basketball-7/betting/usa-9/nba-6004

Success = >= 100 normalized rows for that book on a single page load.

Output
------
  data/cache/probe_R18_K1_playwright_results.json   per-book status, schema obs
  data/lines/<date>_<book>.csv                       if rows extracted

Schema matches the canonical 10-col CSV (FD/bov producers):
  captured_at, book, game_id, player_id, player_name, stat, line,
  over_price, under_price, start_time
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

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LINES_DIR, exist_ok=True)

RESULTS_PATH = os.path.join(CACHE_DIR, "probe_R18_K1_playwright_results.json")

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

# --- stat label heuristics (case-insensitive substring match) ------------
_STAT_KEYS: List[Tuple[str, str]] = [
    ("three pointer", "fg3m"),
    ("3-pointer",      "fg3m"),
    ("threes made",    "fg3m"),
    ("made threes",    "fg3m"),
    ("3pt made",       "fg3m"),
    ("turnover",       "tov"),
    ("rebound",        "reb"),
    ("assist",         "ast"),
    ("steal",          "stl"),
    ("block",          "blk"),
    ("point",          "pts"),
]


def _label_to_stat(label: str) -> Optional[str]:
    s = (label or "").lower()
    for k, v in _STAT_KEYS:
        if k in s:
            return v
    return None


# ============================================================
# DraftKings
# ============================================================
# DK's frontend hits `*/v1/leagues/.../categories/.../subcategories/...`
# under hostname `sportsbook-nash.draftkings.com` (or the `*-staging` variant).
# The JSON is a deeply-nested events/markets/selections graph.
_DK_HOST_PATTERNS = re.compile(
    r"https://sportsbook-nash[a-z0-9\-]*\.draftkings\.com/api/sportscontent/.*",
    re.IGNORECASE,
)
_DK_PROP_KEYWORDS = re.compile(
    r"(points|rebounds|assists|threes|steals|blocks|turnovers)",
    re.IGNORECASE,
)
DK_URL = "https://sportsbook.draftkings.com/leagues/basketball/nba"


def _parse_dk_payload(j: Dict[str, Any], captured_at: str) -> List[Dict[str, Any]]:
    """Walk DK's events/markets/selections graph and emit canonical rows.

    DK's payload (sportscontent v1) looks roughly like:
      { "eventGroup": {...},
        "events": [ {"eventId": "...", "name": "TeamA @ TeamB", "startEventDate": "..."} , ...],
        "markets": [ {"id": "...", "name": "Anthony Davis Points O/U", "eventId": "...",
                       "selections":[{"label":"Over","points":"25.5","oddsAmerican":"-110"}, ...] }, ...] }
    """
    rows: List[Dict[str, Any]] = []
    events = j.get("events") or []
    markets = j.get("markets") or []
    if not (events and markets):
        # Newer DK schema nests these under 'eventGroup' -> 'offerCategories'
        return rows
    ev_by_id = {str(e.get("eventId") or e.get("id") or ""): e for e in events}
    for m in markets:
        name = m.get("name") or m.get("marketName") or ""
        stat = _label_to_stat(name)
        if not stat:
            continue
        ev_id = str(m.get("eventId") or m.get("event_id") or "")
        ev = ev_by_id.get(ev_id, {}) or {}
        ev_name = ev.get("name") or ev.get("eventName") or ""
        if "@" not in ev_name and " vs " not in ev_name.lower():
            continue
        start = ev.get("startEventDate") or ev.get("startDate") or ""
        # Player name = market name minus the trailing stat words
        player_name = re.sub(
            r"\s+(points|rebounds|assists|threes|steals|blocks|turnovers).*$",
            "", name, flags=re.IGNORECASE).strip()
        if not player_name:
            continue
        sels = m.get("selections") or m.get("outcomes") or []
        # Group selections into Over/Under pairs by line
        by_line: Dict[float, Dict[str, int]] = {}
        for s in sels:
            label = (s.get("label") or s.get("name") or "").strip().lower()
            try:
                line = float(s.get("points") or s.get("line") or s.get("handicap"))
                odds = int(s.get("oddsAmerican") or s.get("americanOdds") or s.get("price"))
            except (TypeError, ValueError):
                continue
            d = by_line.setdefault(line, {"over": None, "under": None})
            if label.startswith("o"):
                d["over"] = odds
            elif label.startswith("u"):
                d["under"] = odds
        for line, sides in by_line.items():
            rows.append({
                "captured_at": captured_at,
                "book": "dk",
                "game_id": ev_id,
                "player_id": m.get("id") or "",
                "player_name": player_name,
                "stat": stat,
                "line": line,
                "over_price": sides["over"] if sides["over"] is not None else "",
                "under_price": sides["under"] if sides["under"] is not None else "",
                "start_time": start,
            })
    return rows


# ============================================================
# Caesars
# ============================================================
# Caesars NJ public site uses `https://api.americanwagering.com/regions/us/locations/nj/brands/czr/sb/.*/sports/basketball/.*`
_CZR_HOST_PATTERNS = re.compile(
    r"https://(api\.americanwagering\.com|sportsbook\.caesars\.com)/.*basketball.*",
    re.IGNORECASE,
)
CZR_URL = "https://sportsbook.caesars.com/us/nj/bet/basketball?id=007d7c61-07a4-4e1e-8c67-c298b4153a4d"


def _parse_czr_payload(j: Any, captured_at: str) -> List[Dict[str, Any]]:
    """Caesars schema is `competitions -> events -> markets -> selections`. Walk it loosely."""
    rows: List[Dict[str, Any]] = []
    # Support a few shapes
    competitions = []
    if isinstance(j, dict):
        competitions = j.get("competitions") or [j]
    elif isinstance(j, list):
        competitions = j
    for comp in competitions:
        if not isinstance(comp, dict):
            continue
        events = comp.get("events") or comp.get("fixtures") or []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_id = ev.get("id") or ev.get("eventId") or ""
            ev_name = ev.get("name") or ev.get("description") or ""
            if "@" not in ev_name and " vs " not in ev_name.lower():
                continue
            start = ev.get("startTime") or ev.get("scheduledStartTime") or ""
            for mkt in (ev.get("markets") or []):
                m_name = mkt.get("name") or mkt.get("displayName") or ""
                stat = _label_to_stat(m_name)
                if not stat:
                    continue
                # Selections come either as flat list or grouped by line
                sels = mkt.get("selections") or mkt.get("outcomes") or []
                player_name = re.sub(
                    r"\s+(points|rebounds|assists|threes|steals|blocks|turnovers).*$",
                    "", m_name, flags=re.IGNORECASE).strip()
                if not player_name:
                    continue
                by_line: Dict[float, Dict[str, int]] = {}
                for s in sels:
                    label = (s.get("name") or s.get("label") or "").strip().lower()
                    line_val = s.get("handicap") or s.get("line") or s.get("points")
                    odds_val = s.get("americanPrice") or s.get("oddsAmerican") or s.get("price")
                    try:
                        line = float(line_val)
                        odds = int(odds_val)
                    except (TypeError, ValueError):
                        continue
                    d = by_line.setdefault(line, {"over": None, "under": None})
                    if label.startswith("o") or label == "yes":
                        d["over"] = odds
                    elif label.startswith("u") or label == "no":
                        d["under"] = odds
                for line, sides in by_line.items():
                    rows.append({
                        "captured_at": captured_at,
                        "book": "czr",
                        "game_id": ev_id,
                        "player_id": mkt.get("id") or "",
                        "player_name": player_name,
                        "stat": stat,
                        "line": line,
                        "over_price": sides["over"] if sides["over"] is not None else "",
                        "under_price": sides["under"] if sides["under"] is not None else "",
                        "start_time": start,
                    })
    return rows


# ============================================================
# BetMGM
# ============================================================
# BetMGM NJ public site loads from `https://sports.nj.betmgm.com/cds-api/...`
_MGM_HOST_PATTERNS = re.compile(
    r"https://sports(book)?\.[a-z]+\.betmgm\.com/cds-api/.*",
    re.IGNORECASE,
)
MGM_URL = "https://sports.nj.betmgm.com/en/sports/basketball-7/betting/usa-9/nba-6004"


def _parse_mgm_payload(j: Any, captured_at: str) -> List[Dict[str, Any]]:
    """BetMGM payload uses fixtures -> games -> optionMarkets -> options."""
    rows: List[Dict[str, Any]] = []
    items = []
    if isinstance(j, dict):
        items = j.get("fixtures") or j.get("games") or j.get("events") or []
        if not items and isinstance(j.get("payload"), list):
            items = j["payload"]
    elif isinstance(j, list):
        items = j
    for ev in items:
        if not isinstance(ev, dict):
            continue
        ev_id = ev.get("id") or ev.get("fixtureId") or ""
        ev_name = (ev.get("name") or {})
        if isinstance(ev_name, dict):
            ev_name = ev_name.get("value") or ev_name.get("en") or ""
        if not isinstance(ev_name, str) or ("@" not in ev_name and " vs " not in ev_name.lower()):
            continue
        start = ev.get("startDate") or ev.get("startTime") or ""
        for mkt in (ev.get("optionMarkets") or ev.get("markets") or []):
            m_name_raw = mkt.get("name") or {}
            if isinstance(m_name_raw, dict):
                m_name = m_name_raw.get("value") or m_name_raw.get("en") or ""
            else:
                m_name = m_name_raw or ""
            stat = _label_to_stat(m_name)
            if not stat:
                continue
            player_name = re.sub(
                r"\s+(points|rebounds|assists|threes|steals|blocks|turnovers).*$",
                "", m_name, flags=re.IGNORECASE).strip()
            if not player_name:
                continue
            opts = mkt.get("options") or mkt.get("selections") or []
            by_line: Dict[float, Dict[str, int]] = {}
            for s in opts:
                label_raw = s.get("name") or s.get("displayValue") or ""
                if isinstance(label_raw, dict):
                    label = (label_raw.get("value") or label_raw.get("en") or "").strip().lower()
                else:
                    label = str(label_raw or "").strip().lower()
                line_val = s.get("attr") or s.get("handicap") or s.get("line")
                odds_val = (s.get("price") or {}).get("americanOdds") if isinstance(s.get("price"), dict) else s.get("americanOdds")
                try:
                    line = float(line_val)
                    odds = int(odds_val)
                except (TypeError, ValueError):
                    continue
                d = by_line.setdefault(line, {"over": None, "under": None})
                if label.startswith("o") or label == "yes":
                    d["over"] = odds
                elif label.startswith("u") or label == "no":
                    d["under"] = odds
            for line, sides in by_line.items():
                rows.append({
                    "captured_at": captured_at,
                    "book": "mgm",
                    "game_id": ev_id,
                    "player_id": mkt.get("id") or "",
                    "player_name": player_name,
                    "stat": stat,
                    "line": line,
                    "over_price": sides["over"] if sides["over"] is not None else "",
                    "under_price": sides["under"] if sides["under"] is not None else "",
                    "start_time": start,
                })
    return rows


# ============================================================
# Playwright driver
# ============================================================
_BOOKS = [
    {
        "code":      "dk",
        "name":      "DraftKings",
        "url":       DK_URL,
        "host_re":   _DK_HOST_PATTERNS,
        "parser":    _parse_dk_payload,
        "extra_keywords": _DK_PROP_KEYWORDS,
    },
    {
        "code":      "czr",
        "name":      "Caesars",
        "url":       CZR_URL,
        "host_re":   _CZR_HOST_PATTERNS,
        "parser":    _parse_czr_payload,
        "extra_keywords": None,
    },
    {
        "code":      "mgm",
        "name":      "BetMGM",
        "url":       MGM_URL,
        "host_re":   _MGM_HOST_PATTERNS,
        "parser":    _parse_mgm_payload,
        "extra_keywords": None,
    },
]


def _try_book(book: Dict[str, Any], wait_seconds: int) -> Dict[str, Any]:
    """Drive one book through Playwright stealth and return a status dict."""
    from playwright.sync_api import sync_playwright  # local import
    try:
        from playwright_stealth import Stealth
    except Exception:
        Stealth = None  # noqa: N806

    captured_at = datetime.utcnow().replace(microsecond=0).isoformat()
    status: Dict[str, Any] = {
        "code": book["code"],
        "name": book["name"],
        "url": book["url"],
        "captured_at": captured_at,
        "page_status": None,
        "page_error": None,
        "responses_total": 0,
        "responses_matched": 0,
        "candidate_urls": [],   # first 10 hostname-matching URLs (for debug)
        "rows": 0,
        "by_stat": {},
        "events": 0,
        "csv": None,
        "ok": False,
        "errors": [],
    }

    collected: List[Tuple[str, Any]] = []  # (url, json_payload)
    candidate_urls: List[str] = []
    response_count = {"n": 0}

    with sync_playwright() as p:
        try:
            # Prefer the real Chrome channel; fall back to playwright's shipped chromium
            # if not installed. Headless=True works fine for stealth on full Chrome.
            launch_kwargs = dict(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            try:
                browser = p.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception:
                browser = p.chromium.launch(**launch_kwargs)
        except Exception as exc:
            status["page_error"] = f"launch_failed: {type(exc).__name__}: {exc}"
            return status
        try:
            ctx = browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )
            if Stealth is not None:
                try:
                    Stealth().apply_stealth_sync(ctx)
                except Exception:
                    pass
            page = ctx.new_page()

            all_urls: List[str] = []
            api_urls: List[str] = []

            def _on_response(resp):
                try:
                    response_count["n"] += 1
                    url = resp.url
                    if len(all_urls) < 60:
                        all_urls.append(f"{resp.status} {url[:160]}")
                    # Capture every URL that contains 'api' or 'aw.' or 'sb/v' (likely api)
                    if re.search(r"(api\.|/api/|/sb/|/cds-|aw-prod|sportscontent)", url, re.IGNORECASE):
                        if len(api_urls) < 80:
                            api_urls.append(f"{resp.status} {url[:200]}")
                    if not book["host_re"].search(url):
                        return
                    if len(candidate_urls) < 10:
                        candidate_urls.append(url)
                    if book["extra_keywords"] is not None:
                        if not book["extra_keywords"].search(url):
                            return
                    ct = (resp.headers or {}).get("content-type", "")
                    if "json" not in ct.lower():
                        return
                    try:
                        body = resp.json()
                    except Exception:
                        # Some calls are streamed/chunked
                        try:
                            body = json.loads(resp.text())
                        except Exception:
                            return
                    collected.append((url, body))
                except Exception:
                    pass

            page.on("response", _on_response)

            try:
                page.goto(book["url"], timeout=45000, wait_until="domcontentloaded")
                status["page_status"] = "loaded"
            except Exception as exc:
                status["page_error"] = f"goto_error: {type(exc).__name__}: {exc}"

            # Let JS run / XHRs finish
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # Scroll a bit to trigger lazy-loaded prop panels
            try:
                for _ in range(4):
                    page.mouse.wheel(0, 1200)
                    time.sleep(0.4)
            except Exception:
                pass
            # Final settle
            time.sleep(max(0, wait_seconds))

            try:
                title = page.title()
                final_url = page.url
                # Sample of body text (first 300 chars) — diagnoses WAF interstitials
                body_snippet = page.evaluate("() => document.body ? document.body.innerText.slice(0,300) : ''")
                status["page_title"] = title
                status["final_url"] = final_url
                status["body_snippet"] = body_snippet
            except Exception as exc:
                status["errors"].append(f"page_inspect: {type(exc).__name__}: {exc}")

            try:
                ctx.close()
            except Exception:
                pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

    status["responses_total"] = response_count["n"]
    status["responses_matched"] = len(collected)
    status["candidate_urls"] = candidate_urls
    status["all_urls_sample"] = all_urls
    status["api_urls"] = api_urls

    # Parse all collected payloads
    rows_all: List[Dict[str, Any]] = []
    for url, payload in collected:
        try:
            rows_all.extend(book["parser"](payload, captured_at))
        except Exception as exc:
            status["errors"].append(f"parse_err {url[:80]}: {type(exc).__name__}: {exc}")
    # Dedup by (player_name, stat, line)
    seen = set()
    dedup: List[Dict[str, Any]] = []
    for r in rows_all:
        k = (r["player_name"], r["stat"], r["line"], r["game_id"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    status["rows"] = len(dedup)
    by_stat: Dict[str, int] = {}
    for r in dedup:
        by_stat[r["stat"]] = by_stat.get(r["stat"], 0) + 1
    status["by_stat"] = by_stat
    status["events"] = len({r["game_id"] for r in dedup if r.get("game_id")})

    if dedup:
        today = _date.today().isoformat()
        csv_path = os.path.join(LINES_DIR, f"{today}_{book['code']}.csv")
        new_file = not os.path.exists(csv_path)
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CANONICAL_FIELDS)
            if new_file:
                w.writeheader()
            for r in dedup:
                w.writerow(r)
        status["csv"] = csv_path
        status["ok"] = len(dedup) >= 100

    return status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-seconds", type=int, default=10,
                    help="Seconds to keep the page open after networkidle to capture trailing XHRs")
    ap.add_argument("--books", default="dk,czr,mgm",
                    help="Comma-separated subset of books to try (in order)")
    ap.add_argument("--all", action="store_true",
                    help="Try every book even if one cracked (useful for full discovery)")
    args = ap.parse_args()

    wanted = [b for b in args.books.split(",") if b]
    selected = [b for b in _BOOKS if b["code"] in wanted]

    results: Dict[str, Any] = {
        "ran_at": datetime.utcnow().replace(microsecond=0).isoformat(),
        "books": [],
        "winners": [],
    }
    cracked = False
    for book in selected:
        print(f"[probe] trying {book['name']}...", flush=True)
        s = _try_book(book, args.wait_seconds)
        print(json.dumps({k: s[k] for k in
                          ("code", "page_status", "page_error",
                           "responses_total", "responses_matched",
                           "rows", "events", "by_stat", "ok")}, indent=2),
              flush=True)
        results["books"].append(s)
        if s["ok"]:
            results["winners"].append(s["code"])
            cracked = True
            if not args.all:
                break

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"[probe] wrote {RESULTS_PATH}", flush=True)
    return 0 if cracked else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(3)
