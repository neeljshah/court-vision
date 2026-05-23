"""
closing_lines_props.py — Player prop closing lines scraper.

Sources (free, no key required):
  1. PrizePicks public projection API — https://api.prizepicks.com/projections?league_id=7
  2. The-Odds-API player props (optional, requires THE_ODDS_API_KEY)

Output schema per record:
    {
        "player": str, "team": str, "stat": str, "line": float,
        "direction": "over"|"under"|null, "book": str,
        "date": str, "scraped_at": str
    }

Public API
----------
    scrape_props(date_str)  -> list[dict]
    load_cached_props(date_str) -> list[dict] | None
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "closing_lines_props")
_UA = (
    "CourtVision-NBA-AI/1.0 (https://github.com/neel/nba-ai-system; "
    "research/non-commercial; neeljshah22@gmail.com)"
)
_DELAY = 2.5

log = logging.getLogger(__name__)

# PrizePicks NBA league_id
_PP_BASE = "https://api.prizepicks.com"
_PP_PROJ_URL = f"{_PP_BASE}/projections?league_id=7&per_page=250"

# Stat name normalization: PrizePicks → our internal names
_PP_STAT_MAP = {
    "Points": "pts",
    "Rebounds": "reb",
    "Assists": "ast",
    "3-Point Made": "fg3m",
    "Blocks": "blk",
    "Steals": "stl",
    "Turnovers": "tov",
    "Fantasy Score": "fantasy",
    "Pts+Reb+Ast": "pra",
    "Pts+Ast": "pa",
    "Pts+Reb": "pr",
    "Reb+Ast": "ra",
    "FG Made": "fgm",
    "FG Attempted": "fga",
}

_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(date_str: str) -> str:
    return os.path.join(_CACHE_DIR, f"{date_str}.json")


def load_cached_props(date_str: str) -> Optional[list]:
    """Return cached prop lines for date_str or None."""
    path = _cache_path(date_str)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lines", [])
    return None


def _save_cache(date_str: str, lines: list, source: str) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = _cache_path(date_str)
    payload = {
        "date": date_str,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "source": source,
        "lines": lines,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log.info("[props_scraper] cached %d lines for %s", len(lines), date_str)


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get_json(url: str, *, timeout: int = 30) -> Optional[dict]:
    import urllib.request
    import urllib.error

    time.sleep(_DELAY)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        log.warning("[props_scraper] HTTP %s for %s", exc.code, url)
        return None
    except Exception as exc:
        log.warning("[props_scraper] fetch error %s: %s", url, exc)
        return None


# ── Source 1: PrizePicks public API ──────────────────────────────────────────

def _fetch_prizepicks(date_str: str) -> list:
    """Fetch current NBA prop projections from PrizePicks public API.

    NOTE: This endpoint returns TODAY's open lines, not historical closes.
    When called on the same date as the games, these are effectively the
    opening/pre-game lines. Run refresh_closing_lines.py at game-time for
    the closest-to-closing snapshot.
    """
    data = _get_json(_PP_PROJ_URL)
    if not data:
        log.warning("[props_scraper/prizepicks] no response")
        return []

    included = {
        item["id"]: item
        for item in data.get("included", [])
        if item.get("type") == "new_player"
    }

    records = []
    scraped_at = datetime.utcnow().isoformat() + "Z"

    for proj in data.get("data", []):
        if proj.get("type") != "projection":
            continue
        attrs = proj.get("attributes", {})

        # Filter to NBA only (league_id=7 already set, but double-check)
        if str(attrs.get("league_id", "")) not in ("7", "NBA"):
            # Some responses may include other leagues despite the filter
            sport = attrs.get("sport", "")
            if sport.upper() not in ("NBA", ""):
                continue

        raw_stat = attrs.get("stat_type", "")
        stat = _PP_STAT_MAP.get(raw_stat, raw_stat.lower().replace(" ", "_"))
        line = attrs.get("line_score")
        if line is None:
            continue

        # Resolve player name via included
        rels = proj.get("relationships", {})
        player_id = (
            rels.get("new_player", {})
            .get("data", {})
            .get("id", "")
        )
        player_info = included.get(player_id, {}).get("attributes", {})
        player_name = player_info.get("name", attrs.get("description", "unknown"))
        team = player_info.get("team", attrs.get("team", ""))

        records.append({
            "player": player_name,
            "team": team,
            "stat": stat,
            "line": float(line),
            "direction": None,  # PrizePicks is over/under choice by bettor
            "book": "prizepicks",
            "date": date_str,
            "scraped_at": scraped_at,
            "game_time": attrs.get("start_time", ""),
        })

    log.info("[props_scraper/prizepicks] parsed %d projections", len(records))
    return records


# ── Source 2: The-Odds-API player props (optional) ───────────────────────────

_ODDS_API_PROP_MARKETS = [
    "player_points", "player_rebounds", "player_assists",
    "player_threes", "player_blocks", "player_steals",
    "player_turnovers", "player_points_rebounds_assists",
]

_ODDS_API_STAT_MAP = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
    "player_threes": "fg3m",
    "player_blocks": "blk",
    "player_steals": "stl",
    "player_turnovers": "tov",
    "player_points_rebounds_assists": "pra",
}


def _fetch_odds_api_props(date_str: str) -> list:
    """Fetch player props from The-Odds-API (requires API key)."""
    if not _ODDS_API_KEY:
        return []

    # First get event IDs for this date
    iso_date = date_str + "T00:00:00Z"
    iso_end = date_str + "T23:59:59Z"
    events_url = (
        f"https://api.the-odds-api.com/v4/sports/basketball_nba/events"
        f"?apiKey={_ODDS_API_KEY}"
        f"&commenceTimeFrom={iso_date}&commenceTimeTo={iso_end}"
    )
    events_data = _get_json(events_url)
    if not events_data:
        return []

    records = []
    scraped_at = datetime.utcnow().isoformat() + "Z"
    markets_str = ",".join(_ODDS_API_PROP_MARKETS)

    for event in events_data[:10]:  # cap to avoid burning free quota
        eid = event.get("id", "")
        home = event.get("home_team", "")
        away = event.get("away_team", "")

        url = (
            f"https://api.the-odds-api.com/v4/sports/basketball_nba"
            f"/events/{eid}/odds"
            f"?apiKey={_ODDS_API_KEY}"
            f"&regions=us&markets={markets_str}&bookmakers=draftkings"
        )
        data = _get_json(url)
        if not data:
            continue

        for bm in data.get("bookmakers", []):
            for market in bm.get("markets", []):
                stat = _ODDS_API_STAT_MAP.get(market["key"], market["key"])
                for outcome in market.get("outcomes", []):
                    player_name = outcome.get("description", outcome.get("name", ""))
                    line = outcome.get("point")
                    direction = outcome.get("name", "").lower()  # "over"/"under"
                    if line is None:
                        continue
                    records.append({
                        "player": player_name,
                        "team": home if home in player_name else "",
                        "stat": stat,
                        "line": float(line),
                        "direction": direction if direction in ("over", "under") else None,
                        "book": bm.get("key", "odds_api"),
                        "date": date_str,
                        "scraped_at": scraped_at,
                        "odds": outcome.get("price"),
                        "game_id": eid,
                    })
            break  # first bookmaker only

    log.info("[props_scraper/odds_api] fetched %d prop lines for %s", len(records), date_str)
    return records


# ── Main entry point ─────────────────────────────────────────────────────────

def scrape_props(date_str: str, *, force: bool = False) -> list:
    """Scrape all prop sources for date_str. Returns merged list.

    Uses cache unless force=True.
    """
    if not force:
        cached = load_cached_props(date_str)
        if cached is not None:
            log.info("[props_scraper] cache hit for %s (%d records)", date_str, len(cached))
            return cached

    lines: list = []
    source_used = "none"

    # Source 1: PrizePicks (always try — no key needed)
    try:
        pp = _fetch_prizepicks(date_str)
        if pp:
            lines.extend(pp)
            source_used = "prizepicks"
    except Exception as exc:
        log.warning("[props_scraper/prizepicks] error: %s — skipping", exc)

    # Source 2: The-Odds-API props (supplement if key present)
    if _ODDS_API_KEY:
        try:
            api_props = _fetch_odds_api_props(date_str)
            if api_props:
                lines.extend(api_props)
                source_used += "+odds_api"
        except Exception as exc:
            log.warning("[props_scraper/odds_api] error: %s — skipping", exc)

    _save_cache(date_str, lines, source_used)
    return lines


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Scrape NBA prop lines for a date")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    result = scrape_props(args.date, force=args.force)
    print(json.dumps({"date": args.date, "n": len(result), "sample": result[:3]}, indent=2))
