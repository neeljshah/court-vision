"""
schedule_context.py — NBA schedule context features for ML models.

Provides per-game context: rest days, back-to-back flags, home/away,
and travel distance between arenas. These are among the strongest
features for pre-game win probability models.

All data cached under data/nba/schedule/ as JSON.

Public API
----------
    get_game_context(game_id, team_abbrev)     -> dict
    get_season_schedule(team_abbrev, season)   -> List[dict]
    compute_travel_distance(city_a, city_b)    -> float  (miles)
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "schedule")
os.makedirs(_CACHE_DIR, exist_ok=True)

_API_DELAY = 0.6  # seconds between NBA API calls (rate limit protection)
_SCHEDULE_VERSION = 2  # bump when schedule entry schema changes
_SCHEDULE_TTL_HOURS = 24  # re-fetch after 24h so new games appear during active seasons


# ─────────────────────────────────────────────────────────────────────────────
# Arena coordinates (lat, lon) for travel distance calculation
# ─────────────────────────────────────────────────────────────────────────────

ARENA_COORDS: dict[str, tuple[float, float]] = {
    "ATL": (33.7573, -84.3963),   # State Farm Arena
    "BOS": (42.3662, -71.0621),   # TD Garden
    "BKN": (40.6826, -73.9754),   # Barclays Center
    "CHA": (35.2251, -80.8392),   # Spectrum Center
    "CHI": (41.8807, -87.6742),   # United Center
    "CLE": (41.4965, -81.6882),   # Rocket Mortgage FieldHouse
    "DAL": (32.7905, -96.8103),   # American Airlines Center
    "DEN": (39.7487, -105.0077),  # Ball Arena
    "DET": (42.3410, -83.0553),   # Little Caesars Arena
    "GSW": (37.7680, -122.3877),  # Chase Center
    "HOU": (29.7508, -95.3621),   # Toyota Center
    "IND": (39.7640, -86.1555),   # Gainbridge Fieldhouse
    "LAC": (34.0430, -118.2673),  # Crypto.com Arena
    "LAL": (34.0430, -118.2673),  # Crypto.com Arena
    "MEM": (35.1382, -90.0505),   # FedExForum
    "MIA": (25.7814, -80.1870),   # Kaseya Center
    "MIL": (43.0450, -87.9170),   # Fiserv Forum
    "MIN": (44.9795, -93.2760),   # Target Center
    "NOP": (29.9490, -90.0812),   # Smoothie King Center
    "NYK": (40.7505, -73.9934),   # Madison Square Garden
    "OKC": (35.4634, -97.5151),   # Paycom Center
    "ORL": (28.5392, -81.3839),   # Kia Center
    "PHI": (39.9012, -75.1720),   # Wells Fargo Center
    "PHX": (33.4457, -112.0712),  # Footprint Center
    "POR": (45.5316, -122.6668),  # Moda Center
    "SAC": (38.5805, -121.4994),  # Golden 1 Center
    "SAS": (29.4270, -98.4375),   # AT&T Center
    "TOR": (43.6435, -79.3791),   # Scotiabank Arena
    "UTA": (40.7683, -111.9011),  # Delta Center
    "WAS": (38.8981, -77.0209),   # Capital One Arena
}


def compute_travel_distance(team_a: str, team_b: str) -> float:
    """
    Haversine distance in miles between two teams' arenas.

    Args:
        team_a: Team abbreviation (e.g. "GSW")
        team_b: Team abbreviation (e.g. "BOS")

    Returns:
        Distance in miles, or 0.0 if either team is unknown.
    """
    if team_a not in ARENA_COORDS or team_b not in ARENA_COORDS:
        return 0.0
    lat1, lon1 = ARENA_COORDS[team_a]
    lat2, lon2 = ARENA_COORDS[team_b]
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ─────────────────────────────────────────────────────────────────────────────
# NBA API helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    """Return cache file path for a given cache key."""
    safe = key.replace("/", "_").replace(" ", "_")
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _load_cache(key: str, ttl_hours: Optional[float] = None) -> Optional[dict]:
    """Load cached data if it exists and is within the TTL window.

    Args:
        key:       Cache key string.
        ttl_hours: If provided, discard cache files older than this many hours.
                   None means no expiry (cache lives forever).
    """
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    if ttl_hours is not None:
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours > ttl_hours:
            return None
    with open(path, "r") as f:
        return json.load(f)


def _save_cache(key: str, data: dict) -> None:
    """Save data to cache."""
    with open(_cache_path(key), "w") as f:
        json.dump(data, f, indent=2)


def get_season_schedule(team_abbrev: str, season: str = "2024-25") -> list[dict]:
    """
    Fetch full season schedule for a team, with rest/travel context per game.

    Args:
        team_abbrev: NBA team abbreviation (e.g. "GSW", "BOS")
        season: NBA season string (e.g. "2024-25")

    Returns:
        List of dicts, one per game, sorted by date:
        {
            "game_id": str,
            "date": str (YYYY-MM-DD),
            "home": bool,
            "opponent": str,
            "rest_days": int,          # days since last game (99 for first game)
            "back_to_back": bool,      # rest_days == 1
            "second_of_three_in_four": bool,  # 2nd game in a 3-in-4-day stretch
            "travel_miles": float,     # miles from previous game city to this arena
            "opponent_is_home": bool,  # True if opponent is hosting
        }
    """
    cache_key = f"schedule_{team_abbrev}_{season}_v{_SCHEDULE_VERSION}"
    cached = _load_cache(cache_key, ttl_hours=_SCHEDULE_TTL_HOURS)
    if cached:
        return cached

    try:
        from nba_api.stats.endpoints import teamgamelog
        from nba_api.stats.static import teams as nba_teams_static
    except ImportError:
        print("[schedule_context] nba_api not installed — returning empty schedule")
        return []

    # Get team ID
    matches = [t for t in nba_teams_static.get_teams() if t["abbreviation"] == team_abbrev]
    if not matches:
        print(f"[schedule_context] Unknown team: {team_abbrev}")
        return []
    team_id = matches[0]["id"]

    time.sleep(_API_DELAY)
    try:
        log = teamgamelog.TeamGameLog(team_id=team_id, season=season)
        games_df = log.get_data_frames()[0]
    except Exception as e:
        print(f"[schedule_context] API error: {e}")
        return []

    # Sort ascending by date
    games_df["GAME_DATE"] = games_df["GAME_DATE"].apply(
        lambda d: datetime.strptime(d, "%b %d, %Y")
    )
    games_df = games_df.sort_values("GAME_DATE").reset_index(drop=True)

    result = []
    prev_date = None
    prev_city = team_abbrev  # first game: assume home (no prior travel)

    for _, row in games_df.iterrows():
        game_date = row["GAME_DATE"]
        matchup = row["MATCHUP"]  # e.g. "GSW vs. BOS" or "GSW @ BOS"
        is_home = "vs." in matchup
        opp = matchup.split()[-1]  # last token is opponent abbrev

        # Rest days
        if prev_date is None:
            rest_days = 99
        else:
            rest_days = (game_date - prev_date).days

        back_to_back = (rest_days == 1)

        # Travel: previous city → this game's city
        this_city = team_abbrev if is_home else opp
        travel_miles = compute_travel_distance(prev_city, this_city)

        wl = str(row.get("WL", "")).strip().upper()
        entry = {
            "game_id": str(row["Game_ID"]),
            "date": game_date.strftime("%Y-%m-%d"),
            "home": is_home,
            "opponent": opp,
            "rest_days": rest_days,
            "back_to_back": back_to_back,
            "second_of_three_in_four": False,  # computed in post-pass below
            "travel_miles": round(travel_miles, 1),
            "opponent_is_home": not is_home,
            "wl": wl,  # "W" or "L" or "" for unplayed games
        }
        result.append(entry)
        prev_date = game_date
        prev_city = this_city

    # Post-pass: mark second_of_three_in_four
    for i in range(1, len(result) - 1):
        d0 = datetime.strptime(result[i - 1]["date"], "%Y-%m-%d")
        d1 = datetime.strptime(result[i]["date"], "%Y-%m-%d")
        d2 = datetime.strptime(result[i + 1]["date"], "%Y-%m-%d")
        if (d2 - d0).days <= 3:
            result[i]["second_of_three_in_four"] = True

    _save_cache(cache_key, result)
    return result


def get_game_context(game_id: str, team_abbrev: str, season: str = "2024-25") -> dict:
    """
    Return schedule context features for a specific game and team.

    Args:
        game_id: NBA game ID string (e.g. "0022300001")
        team_abbrev: Team abbreviation
        season: NBA season string

    Returns:
        Dict with context features, or empty dict if game not found:
        {
            "game_id": str,
            "date": str,
            "home": bool,
            "opponent": str,
            "rest_days": int,
            "back_to_back": bool,
            "second_of_three_in_four": bool,
            "travel_miles": float,
            "opponent_is_home": bool,
        }
    """
    schedule = get_season_schedule(team_abbrev, season)
    for game in schedule:
        if game["game_id"] == game_id:
            return game
    return {}


def get_recent_form(team_abbrev: str, game_id: str, n: int = 5, season: str = "2024-25") -> dict:
    """
    Compute recent form metrics for a team over the last N games before game_id.

    Args:
        team_abbrev: Team abbreviation
        game_id: The target game ID (excluded from form window)
        n: Window size (default 5 games)
        season: NBA season

    Returns:
        {
            "wins_last_n": int,
            "win_pct_last_n": float,
            "back_to_backs_last_n": int,
            "avg_rest_last_n": float,
            "avg_travel_last_n": float,
        }
    """
    schedule = get_season_schedule(team_abbrev, season)
    target_idx = next((i for i, g in enumerate(schedule) if g["game_id"] == game_id), None)
    if target_idx is None or target_idx == 0:
        return {
            "wins_last_n": 0,
            "win_pct_last_n": 0.5,
            "back_to_backs_last_n": 0,
            "avg_rest_last_n": 3.0,
            "avg_travel_last_n": 0.0,
        }

    window = schedule[max(0, target_idx - n):target_idx]
    b2b = sum(1 for g in window if g["back_to_back"])
    rested = [g for g in window if g["rest_days"] < 99]
    avg_rest = sum(g["rest_days"] for g in rested) / max(1, len(rested))
    avg_travel = sum(g["travel_miles"] for g in window) / max(1, len(window))

    # Count wins from the W/L column stored in each schedule entry
    played = [g for g in window if g.get("wl") in ("W", "L")]
    wins = sum(1 for g in played if g.get("wl") == "W")
    win_pct = round(wins / len(played), 3) if played else 0.5

    return {
        "wins_last_n": wins,
        "win_pct_last_n": win_pct,
        "back_to_backs_last_n": b2b,
        "avg_rest_last_n": round(avg_rest, 2),
        "avg_travel_last_n": round(avg_travel, 1),
    }
