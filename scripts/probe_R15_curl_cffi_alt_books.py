"""probe_R15_curl_cffi_alt_books.py - retry R14 H1 books with curl_cffi.

R14 H1 found that DK / FD / MGM / Caesars all returned 403/500 via vanilla
`requests` — root cause is Cloudflare / Akamai JA3 TLS fingerprinting. They
detect non-browser TLS clients.

curl_cffi wraps libcurl-impersonate to produce byte-perfect Chrome TLS
handshakes. Many bookmaker WAFs that 403 vanilla requests will 200 on
curl_cffi.

For each book, retry with chrome120, chrome116, safari17_0, firefox133.
Log status_code / content_length / first 500 chars of body.

If >=1 book returns 200 + valid JSON with NBA data, identify schema and
write production scraper. Else write the failure matrix and stop.

Output: data/cache/probe_R15_curl_cffi_results.json
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from curl_cffi import requests as cf_req
except Exception as exc:
    print(f"curl_cffi import failed: {exc}", file=sys.stderr)
    sys.exit(1)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LINES_DIR, exist_ok=True)

RESULTS_PATH = os.path.join(CACHE_DIR, "probe_R15_curl_cffi_results.json")

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

STAT_MAP = {
    "points": "pts",
    "player points": "pts",
    "points scored": "pts",
    "rebounds": "reb",
    "player rebounds": "reb",
    "total rebounds": "reb",
    "assists": "ast",
    "player assists": "ast",
    "3-pt made": "fg3m",
    "threes made": "fg3m",
    "three pointers made": "fg3m",
    "3 pointers made": "fg3m",
    "steals": "stl",
    "player steals": "stl",
    "blocks": "blk",
    "player blocks": "blk",
    "turnovers": "tov",
    "player turnovers": "tov",
}

# Endpoints to retry (from R14 H1 working list).
ENDPOINTS = [
    {
        "book": "dk",
        "name": "DraftKings eventgroup 42648",
        "url": "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/42648?format=json",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://sportsbook.draftkings.com/",
            "Origin": "https://sportsbook.draftkings.com",
        },
    },
    {
        "book": "dk_pts",
        "name": "DraftKings eventgroup 42648 / category 583 (player points)",
        "url": "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/42648/categories/583?format=json",
        "headers": {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://sportsbook.draftkings.com/",
            "Origin": "https://sportsbook.draftkings.com",
        },
    },
    {
        "book": "fd",
        "name": "FanDuel NJ NBA event-page",
        # NBA league page on FanDuel NJ
        "url": (
            "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
            "?page=CUSTOM&customPageId=nba&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"
        ),
        "headers": {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://sportsbook.fanduel.com/",
            "Origin": "https://sportsbook.fanduel.com",
            "X-Px-Authorization": "3",
        },
    },
    {
        "book": "mgm",
        "name": "BetMGM NJ basketball fixtures",
        "url": (
            "https://sports.nj.betmgm.com/cds-api/bettingoffer/fixtures"
            "?x-bwin-accessId=ABCDE&lang=en-us&country=US&userCountry=US&subdivision=US-NJ"
            "&fixtureTypes=Standard&state=Latest&offerMapping=Filtered"
            "&offerCategories=Gridable&fixtureCategories=Gridable,NonGridable,Other"
            "&competitionIds=103"
        ),
        "headers": {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://sports.nj.betmgm.com/en/sports/basketball-7/betting/usa-9/nba-6004",
            "Origin": "https://sports.nj.betmgm.com",
        },
    },
    {
        "book": "czr",
        "name": "Caesars NJ basketball schedule",
        "url": (
            "https://api.americanwagering.com/regions/us/locations/nj/brands/czr/"
            "sb/v3/sports/basketball/events/schedule"
        ),
        "headers": {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.williamhill.com/us/nj/bet/basketball",
            "Origin": "https://www.williamhill.com",
        },
    },
]

# Order matters: chrome120 first (most modern), then fallbacks.
IMPERSONATIONS = ["chrome120", "chrome116", "safari17_0", "firefox133"]


def _try(url: str, headers: Dict[str, str], impersonate: str, timeout: int = 15) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "impersonate": impersonate,
        "status_code": None,
        "content_length": 0,
        "body_head": "",
        "error": None,
        "is_json": False,
        "elapsed_s": None,
    }
    t0 = time.time()
    try:
        r = cf_req.get(url, headers=headers, impersonate=impersonate, timeout=timeout)
        out["status_code"] = int(r.status_code)
        body = r.content or b""
        out["content_length"] = len(body)
        try:
            out["body_head"] = body[:500].decode("utf-8", errors="replace")
        except Exception:
            out["body_head"] = repr(body[:500])
        # Sniff JSON
        try:
            j = r.json()
            out["is_json"] = True
            out["_json"] = j
        except Exception:
            out["is_json"] = False
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["elapsed_s"] = round(time.time() - t0, 3)
    return out


def _row_count_dk(j: Any) -> int:
    """Rough DK row counter: count offers across all offerCategories."""
    try:
        eg = j.get("eventGroup", {})
        n = 0
        for cat in eg.get("offerCategories", []) or []:
            for sub in cat.get("offerSubcategoryDescriptors", []) or []:
                osc = sub.get("offerSubcategory") or {}
                for offers in osc.get("offers", []) or []:
                    for offer in offers or []:
                        for outcome in offer.get("outcomes", []) or []:
                            n += 1
        return n
    except Exception:
        return 0


def _row_count_generic(j: Any) -> int:
    """Walk the JSON tree and count leaves that look like odds entries."""
    n = 0

    def _walk(x: Any) -> None:
        nonlocal n
        if isinstance(x, dict):
            keys_lower = {k.lower() for k in x.keys()}
            if {"line", "overprice"} <= keys_lower or {"point", "price"} <= keys_lower:
                n += 1
            for v in x.values():
                _walk(v)
        elif isinstance(x, list):
            for item in x:
                _walk(item)

    try:
        _walk(j)
    except Exception:
        pass
    return n


def main() -> int:
    print(f"[probe_R15] curl_cffi version: {cf_req.__name__} loaded", flush=True)
    results: Dict[str, Any] = {
        "probe": "R15_curl_cffi_alt_books",
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "endpoints": [],
        "any_cracked": False,
        "winners": [],
    }

    for ep in ENDPOINTS:
        ep_result: Dict[str, Any] = {
            "book": ep["book"],
            "name": ep["name"],
            "url": ep["url"],
            "attempts": [],
            "best": None,
        }
        print(f"\n=== {ep['book']} :: {ep['name']} ===", flush=True)
        best: Optional[Dict[str, Any]] = None
        for imp in IMPERSONATIONS:
            res = _try(ep["url"], ep["headers"], imp)
            print(
                f"  [{imp:>12s}] status={res['status_code']} "
                f"len={res['content_length']:>7d} "
                f"json={res['is_json']} err={res['error']}",
                flush=True,
            )
            # Trim json from per-attempt log (keep on best only)
            log_entry = {k: v for k, v in res.items() if k != "_json"}
            ep_result["attempts"].append(log_entry)
            if res["status_code"] == 200 and res["is_json"]:
                if best is None or res["content_length"] > best["content_length"]:
                    best = res
                    best["_imp"] = imp
        if best is not None:
            j = best.pop("_json", None)
            # Count rows
            if ep["book"].startswith("dk"):
                rows = _row_count_dk(j)
            else:
                rows = _row_count_generic(j)
            best_log = {k: v for k, v in best.items() if k != "_json"}
            best_log["row_count_est"] = rows
            ep_result["best"] = best_log
            print(
                f"  WINNER imp={best['_imp']} rows~={rows} "
                f"len={best['content_length']}",
                flush=True,
            )
            if rows > 0:
                results["any_cracked"] = True
                results["winners"].append({
                    "book": ep["book"],
                    "impersonate": best["_imp"],
                    "rows_est": rows,
                })
                # Dump the raw JSON for downstream schema-mapping work
                raw_path = os.path.join(CACHE_DIR, f"probe_R15_raw_{ep['book']}.json")
                try:
                    with open(raw_path, "w", encoding="utf-8") as f:
                        json.dump(j, f)
                    print(f"  raw JSON -> {raw_path}", flush=True)
                except Exception as exc:
                    print(f"  raw JSON write failed: {exc}", flush=True)
        results["endpoints"].append(ep_result)

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[probe_R15] wrote {RESULTS_PATH}", flush=True)
    print(f"[probe_R15] any_cracked={results['any_cracked']} winners={results['winners']}", flush=True)
    return 0 if results["any_cracked"] else 2


if __name__ == "__main__":
    sys.exit(main())
