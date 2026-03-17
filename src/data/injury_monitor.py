"""
injury_monitor.py — NBA player injury status monitor (Phase 3.5).

Fetches current injury statuses from the ESPN public API (no auth required).
Caches to data/nba/injury_report.json with a TTL to avoid over-fetching.

Public API
----------
    refresh()                          -> dict  (raw cache written to disk)
    get_all_injuries()                 -> list  (all current injuries)
    get_injury_status(player_name)     -> dict  (status for one player)
    get_team_injuries(team_abbrev)     -> list  (all injured players on team)
    is_available(player_name)          -> bool  (True if not Out/Doubtful)
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from datetime import datetime, timezone
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH  = os.path.join(PROJECT_DIR, "data", "nba", "injury_report.json")
_CACHE_TTL_SECONDS = 30 * 60   # Re-fetch every 30 minutes

_ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
_ESPN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Status normalisation: ESPN uses varied strings
_STATUS_MAP = {
    "out":          "Out",
    "doubtful":     "Doubtful",
    "questionable": "Questionable",
    "day-to-day":   "Day-To-Day",
    "probable":     "Probable",
    "available":    "Available",
    "active":       "Available",
    "healthy":      "Available",
}


def _norm_name(s: str) -> str:
    """Normalise player name: strip accents, lowercase."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _norm_status(raw: str) -> str:
    """Normalise an ESPN status string to canonical form."""
    key = raw.lower().strip()
    for k, v in _STATUS_MAP.items():
        if k in key:
            return v
    return raw.strip().title()


def _cache_is_fresh() -> bool:
    """Return True if injury_report.json is newer than TTL."""
    if not os.path.exists(_CACHE_PATH):
        return False
    age = time.time() - os.path.getmtime(_CACHE_PATH)
    return age < _CACHE_TTL_SECONDS


def refresh(force: bool = False) -> dict:
    """
    Fetch current injury statuses from ESPN and write to cache.

    Args:
        force: If True, bypass TTL and always re-fetch.

    Returns:
        {
            "fetched_at": str (ISO timestamp),
            "source":     "espn",
            "injuries":   [
                {
                    "player_name":   str,
                    "player_id_espn": str,
                    "team_name":     str,
                    "team_abbrev":   str,
                    "status":        str,   ("Out","Doubtful","Questionable",...)
                    "short_comment": str,
                    "long_comment":  str,
                    "injury_date":   str,
                    "injury_type":   str,
                },
                ...
            ],
        }
    """
    if not force and _cache_is_fresh():
        return _load_cache()

    import requests

    try:
        resp = requests.get(_ESPN_URL, headers=_ESPN_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[injury_monitor] ESPN fetch error: {e}")
        if os.path.exists(_CACHE_PATH):
            print("[injury_monitor] Returning stale cache.")
            return _load_cache()
        return {"fetched_at": "", "source": "espn", "injuries": []}

    injuries = []
    for team_entry in data.get("injuries", []):
        team_name   = team_entry.get("displayName", "")
        # Derive abbreviation from id (ESPN uses team_id that maps to NBA abbreviation)
        # We store the full name and derive abbrev from the team's short display name
        team_id_str = str(team_entry.get("id", ""))

        for player_entry in team_entry.get("injuries", []):
            athlete = player_entry.get("athlete", {})
            raw_status = player_entry.get("status", "")

            # ESPN athlete display name
            player_name = athlete.get("displayName", "") or athlete.get("fullName", "")
            if not player_name:
                continue

            injuries.append({
                "player_name":    player_name,
                "player_id_espn": str(athlete.get("id", "")),
                "team_name":      team_name,
                "team_abbrev":    _espn_team_to_abbrev(team_id_str, team_name),
                "status":         _norm_status(raw_status),
                "short_comment":  player_entry.get("shortComment", ""),
                "long_comment":   player_entry.get("longComment", ""),
                "injury_date":    player_entry.get("date", ""),
                "injury_type":    (player_entry.get("details") or {}).get("type", ""),
            })

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source":     "espn",
        "injuries":   injuries,
    }
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"[injury_monitor] Fetched {len(injuries)} injured players -> {_CACHE_PATH}")
    return result


def get_all_injuries() -> list:
    """Return list of all currently injured players (uses/refreshes cache)."""
    data = refresh()
    return data.get("injuries", [])


def get_injury_status(player_name: str) -> dict:
    """
    Look up injury status for a player by name (fuzzy, accent-insensitive).

    Args:
        player_name: Player name (e.g. "LeBron James", "Nikola Jokic").

    Returns:
        {
            "player_name": str,
            "status":      str,   ("Out","Doubtful","Questionable","Available")
            "comment":     str,
            "team_abbrev": str,
            "found":       bool,
        }
        If not found in injury list, returns Available (healthy assumed).
    """
    query = _norm_name(player_name)
    for inj in get_all_injuries():
        if _norm_name(inj["player_name"]) == query:
            return {
                "player_name": inj["player_name"],
                "status":      inj["status"],
                "comment":     inj["short_comment"],
                "team_abbrev": inj["team_abbrev"],
                "found":       True,
            }
    return {
        "player_name": player_name,
        "status":      "Available",
        "comment":     "",
        "team_abbrev": "",
        "found":       False,
    }


def get_team_injuries(team_abbrev: str) -> list:
    """
    Return all injured players on a team.

    Args:
        team_abbrev: 3-letter abbreviation (e.g. "BOS", "LAL")

    Returns:
        List of injury dicts for that team (empty if none/all healthy).
    """
    abbrev_upper = team_abbrev.upper()
    return [
        inj for inj in get_all_injuries()
        if inj.get("team_abbrev", "").upper() == abbrev_upper
    ]


def is_available(player_name: str) -> bool:
    """Return True if player is NOT Out or Doubtful."""
    status = get_injury_status(player_name)["status"]
    return status not in ("Out", "Doubtful")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    with open(_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


# ESPN team IDs are numeric; map common ones to NBA abbreviations.
# Full mapping built from the team display names returned by the API.
_ESPN_NAME_TO_ABBREV: dict[str, str] = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def _espn_team_to_abbrev(team_id: str, team_name: str) -> str:
    """Map ESPN team name to NBA abbreviation."""
    return _ESPN_NAME_TO_ABBREV.get(team_name, team_name[:3].upper())
