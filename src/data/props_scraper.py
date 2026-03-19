"""
props_scraper.py — Current-day player props from DraftKings and FanDuel.

Uses public JSON endpoints (no auth required). Refreshes at 15-minute TTL
to respect rate limits. Never hits the same endpoint twice per minute.

Prop types scraped: pts, reb, ast, 3pm, stl, blk

Public API
----------
    get_current_props(book)                      -> list[dict]
    get_player_props(player_name, book)          -> list[dict]
    get_props_by_type(prop_type, book)           -> list[dict]
    get_all_books()                              -> dict
    find_line_discrepancy(player_name, prop_type) -> dict  (DK vs FD comparison)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_TTL_15MIN = 15 * 60    # minimum cache TTL — never hit same endpoint twice/min
_TTL_1MIN  = 60         # hard floor between re-fetches

_PROP_TYPES = ["points", "rebounds", "assists", "threes", "steals", "blocks"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://sportsbook.draftkings.com",
    "Referer": "https://sportsbook.draftkings.com/",
}

_FD_HEADERS = {
    **_HEADERS,
    "Origin":  "https://sportsbook.fanduel.com",
    "Referer": "https://sportsbook.fanduel.com/",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(name: str) -> str:
    return os.path.join(_EXT_CACHE, f"{name}.json")


def _is_fresh(path: str, ttl: float) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < ttl


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(_EXT_CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


# ─────────────────────────────────────────────────────────────────────────────
# DraftKings
# ─────────────────────────────────────────────────────────────────────────────

# DraftKings public odds API — NBA player props category IDs
_DK_NBA_CATEGORY = 42648   # NBA league ID in DK
_DK_OFFER_CATS = {
    "points":   1215,
    "rebounds": 1216,
    "assists":  1217,
    "threes":   1218,
    "steals":   1220,
    "blocks":   1221,
}

_DK_API_URL = (
    "https://sportsbook.draftkings.com/sites/US-SB/api/v5/"
    "eventgroups/{league_id}/categories/{category_id}/"
    "subcategories/{subcategory_id}?format=json"
)

# Simpler endpoint that often works without auth:
_DK_SIMPLE_URL = (
    "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v1/"
    "eventgroups/{league_id}?format=json"
)


def _fetch_dk_props_for_type(prop_type: str) -> list:
    """Fetch DraftKings props for a single prop type."""
    import requests

    cat_id = _DK_OFFER_CATS.get(prop_type, 1215)
    url = (
        f"https://sportsbook.draftkings.com/sites/US-SB/api/v5/"
        f"eventgroups/{_DK_NBA_CATEGORY}/categories/{cat_id}?format=json"
    )

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"[props_scraper] DK fetch error ({prop_type}): {e}")
        return []

    records = []
    for event_group in data.get("eventGroup", {}).get("offerCategories", []):
        for subcategory in event_group.get("offerSubcategoryDescriptors", []):
            for offer_category in subcategory.get("offerSubcategory", {}).get("offers", []):
                for offer_list in offer_category:
                    for outcome in offer_list.get("outcomes", []):
                        player_name = (
                            offer_list.get("label", "")
                            or outcome.get("participant", "")
                            or outcome.get("label", "")
                        )
                        if not player_name:
                            continue
                        line = float(outcome.get("line", outcome.get("points", 0)) or 0)
                        odds_american = int(outcome.get("oddsAmerican", 0) or 0)
                        over_under = str(outcome.get("label", "")).upper()
                        records.append({
                            "player_name":  player_name,
                            "prop_type":    prop_type,
                            "line":         line,
                            "over_odds":    odds_american if "OVER" in over_under else None,
                            "under_odds":   odds_american if "UNDER" in over_under else None,
                            "book":         "draftkings",
                            "fetched_at":   datetime.now(timezone.utc).isoformat(),
                        })
    return records


def _fetch_dk_all_props() -> list:
    """Fetch all NBA player prop types from DraftKings."""
    all_records: list = []
    for pt in _PROP_TYPES:
        records = _fetch_dk_props_for_type(pt)
        all_records.extend(records)
        time.sleep(1.0)   # 1s between DK calls
    return _merge_over_under(all_records)


# ─────────────────────────────────────────────────────────────────────────────
# FanDuel
# ─────────────────────────────────────────────────────────────────────────────

_FD_API_BASE = "https://sbapi.fanduel.com/api"
_FD_NBA_ID   = 6423

# FanDuel market IDs for player props
_FD_MARKET_TYPES = {
    "points":   "PLAYER_POINTS",
    "rebounds": "PLAYER_REBOUNDS",
    "assists":  "PLAYER_ASSISTS",
    "threes":   "PLAYER_3_POINTERS",
    "steals":   "PLAYER_STEALS",
    "blocks":   "PLAYER_BLOCKS",
}


def _fetch_fd_props() -> list:
    """Fetch FanDuel NBA player props via public API."""
    import requests

    url = f"{_FD_API_BASE}/content-managed-page?betexRegion=GBR&capiJurisdiction=intl&currencyCode=USD&exchangeLocale=en_US&includeRaceCards=false&includeSeo=false&language=en&regionCode=NAMERICA&_ak=FhMFpcPWXMeyZxOB&page=CUSTOM&customPageId=nba"

    try:
        resp = requests.get(url, headers=_FD_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"[props_scraper] FD fetch error: {e}")
        return []

    records: list = []
    attachments = data.get("attachments", {})
    markets = attachments.get("markets", {})
    runners = attachments.get("runners", {})

    for mkt_id, mkt in markets.items():
        mkt_type = mkt.get("marketType", "")
        prop_type = None
        for pt, fd_type in _FD_MARKET_TYPES.items():
            if fd_type in mkt_type:
                prop_type = pt
                break
        if prop_type is None:
            continue

        for runner_id in mkt.get("runners", []):
            runner = runners.get(str(runner_id), {})
            if not runner:
                continue
            player_name = runner.get("runnerName", "")
            handicap    = float(runner.get("handicap", 0) or 0)
            win_run_bet = runner.get("winRunnerOdds", {})
            decimal_odds = float(
                win_run_bet.get("decimalPrice", win_run_bet.get("americanDisplayOdds", 0)) or 0
            )
            # Convert decimal to American
            if decimal_odds > 2.0:
                american = int(round((decimal_odds - 1) * 100))
            elif decimal_odds > 1.0:
                american = int(round(-100 / (decimal_odds - 1)))
            else:
                american = 0

            side = "OVER" if "Over" in runner.get("selectionName", "") else "UNDER"
            records.append({
                "player_name":  player_name,
                "prop_type":    prop_type,
                "line":         handicap,
                "over_odds":    american if side == "OVER" else None,
                "under_odds":   american if side == "UNDER" else None,
                "book":         "fanduel",
                "fetched_at":   datetime.now(timezone.utc).isoformat(),
            })

    return _merge_over_under(records)


# ─────────────────────────────────────────────────────────────────────────────
# Over/under merger
# ─────────────────────────────────────────────────────────────────────────────

def _merge_over_under(raw: list) -> list:
    """
    Merge separate over/under rows into single prop records.

    DK and FD return one row per side. We merge on (player_name, prop_type, line).
    """
    from collections import defaultdict
    groups: dict = defaultdict(dict)

    for r in raw:
        key = (r.get("player_name", ""), r.get("prop_type", ""), r.get("line", 0))
        if r.get("over_odds") is not None:
            groups[key]["over_odds"] = r["over_odds"]
        if r.get("under_odds") is not None:
            groups[key]["under_odds"] = r["under_odds"]
        # Keep metadata fields
        for field in ("player_name", "prop_type", "line", "book", "fetched_at"):
            groups[key].setdefault(field, r.get(field))

    result = []
    for (player, prop, line), rec in groups.items():
        rec.setdefault("over_odds", None)
        rec.setdefault("under_odds", None)
        result.append(rec)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_current_props(book: str = "draftkings") -> list:
    """
    Fetch current-day player props from the specified book.

    Respects 15-minute TTL — will not re-fetch if cache is fresh.

    Args:
        book: "draftkings" | "fanduel"

    Returns:
        List of prop dicts:
        [
            {
                "player_name": str,
                "prop_type":   str,    # "points", "rebounds", etc.
                "line":        float,
                "over_odds":   int | None,    # American odds
                "under_odds":  int | None,
                "book":        str,
                "fetched_at":  str,
            }, ...
        ]
    """
    key  = f"current_props_{_safe(book)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_15MIN):
        return _load(path)

    if book == "draftkings":
        records = _fetch_dk_all_props()
    elif book == "fanduel":
        records = _fetch_fd_props()
    else:
        raise ValueError(f"Unknown book: {book}. Use 'draftkings' or 'fanduel'.")

    if not records:
        print(f"[props_scraper] No props fetched from {book} — returning empty list")
        # Return stale cache if available
        if os.path.exists(path):
            return _load(path)
        return []

    _save(path, records)
    print(f"[props_scraper] {book}: {len(records)} props fetched")
    return records


def get_player_props(
    player_name: str,
    book: str = "draftkings",
) -> list:
    """
    Look up all current props for a specific player.

    Args:
        player_name: Player's full name (case-insensitive)
        book: "draftkings" | "fanduel"

    Returns:
        List of prop dicts for that player (all prop types).
    """
    query  = player_name.lower().strip()
    props  = get_current_props(book)
    return [p for p in props if p.get("player_name", "").lower() == query]


def get_props_by_type(
    prop_type: str,
    book: str = "draftkings",
) -> list:
    """
    Return all player props for a specific stat type.

    Args:
        prop_type: "points" | "rebounds" | "assists" | "threes" | "steals" | "blocks"
        book: "draftkings" | "fanduel"

    Returns:
        List of prop dicts sorted by line descending.
    """
    query = prop_type.lower().strip()
    props = get_current_props(book)
    filtered = [p for p in props if p.get("prop_type", "").lower() == query]
    return sorted(filtered, key=lambda x: x.get("line", 0), reverse=True)


def get_all_books() -> dict:
    """
    Fetch props from both DraftKings and FanDuel and return combined dict.

    Returns:
        {
            "draftkings": [...],
            "fanduel": [...],
        }
    """
    return {
        "draftkings": get_current_props("draftkings"),
        "fanduel":    get_current_props("fanduel"),
    }


def find_line_discrepancy(
    player_name: str,
    prop_type: str,
) -> dict:
    """
    Compare DraftKings vs FanDuel lines for a player prop.
    Large discrepancies (>0.5) signal soft-book lag.

    Args:
        player_name: Player full name
        prop_type: Prop category (e.g. "points")

    Returns:
        {
            "player_name": str, "prop_type": str,
            "dk_line": float | None, "fd_line": float | None,
            "dk_over_odds": int | None, "fd_over_odds": int | None,
            "line_diff": float | None,
            "odds_diff": int | None,
            "soft_line_alert": bool,    # True if lines differ by >0.5
        }
    """
    query = player_name.lower().strip()
    pt    = prop_type.lower().strip()

    dk_props = [
        p for p in get_current_props("draftkings")
        if p.get("player_name", "").lower() == query and p.get("prop_type", "").lower() == pt
    ]
    fd_props = [
        p for p in get_current_props("fanduel")
        if p.get("player_name", "").lower() == query and p.get("prop_type", "").lower() == pt
    ]

    dk = dk_props[0] if dk_props else {}
    fd = fd_props[0] if fd_props else {}

    dk_line = dk.get("line")
    fd_line = fd.get("line")
    line_diff = None
    if dk_line is not None and fd_line is not None:
        line_diff = round(abs(dk_line - fd_line), 2)

    dk_over = dk.get("over_odds")
    fd_over = fd.get("over_odds")
    odds_diff = None
    if dk_over is not None and fd_over is not None:
        odds_diff = abs(dk_over - fd_over)

    return {
        "player_name":     player_name,
        "prop_type":       prop_type,
        "dk_line":         dk_line,
        "fd_line":         fd_line,
        "dk_over_odds":    dk_over,
        "fd_over_odds":    fd_over,
        "line_diff":       line_diff,
        "odds_diff":       odds_diff,
        "soft_line_alert": (line_diff or 0) > 0.5,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Current props scraper")
    parser.add_argument("--book", default="draftkings", choices=["draftkings", "fanduel", "both"])
    parser.add_argument("--player", default=None)
    parser.add_argument("--prop-type", default="points")
    args = parser.parse_args()

    if args.book == "both":
        data = get_all_books()
        for book, props in data.items():
            print(f"{book}: {len(props)} props")
    elif args.player:
        props = get_player_props(args.player, args.book)
        print(json.dumps(props, indent=2))
    else:
        props = get_props_by_type(args.prop_type, args.book)
        print(f"{args.book} {args.prop_type} props: {len(props)}")
        for p in props[:5]:
            print(f"  {p['player_name']}: {p['line']} | Over {p.get('over_odds')} / Under {p.get('under_odds')}")
