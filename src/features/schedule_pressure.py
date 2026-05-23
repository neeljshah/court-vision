"""
schedule_pressure.py — Schedule-density and travel-fatigue features for NBA models.

Computes rolling game density, cumulative travel mileage, time-zone crossing,
and road/home streak features for a team up to a given game date.

Re-uses arena coordinates already defined in src/data/schedule_context.py.

Public API
----------
    get_team_schedule_features(team_id, game_date, season) -> dict
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCHED_DIR   = os.path.join(_PROJECT_DIR, "data", "nba", "schedule")
_API_DELAY   = 0.7

# ── Arena geo: (lat, lon, timezone_offset_from_ET) ────────────────────────────
# timezone_offset: ET=0, CT=1, MT=2, PT=3
_ARENA_GEO: Dict[str, Tuple[float, float, int]] = {
    "ATL": (33.7573, -84.3963, 0),
    "BOS": (42.3662, -71.0621, 0),
    "BKN": (40.6826, -73.9754, 0),
    "CHA": (35.2251, -80.8392, 0),
    "CHI": (41.8807, -87.6742, 1),
    "CLE": (41.4965, -81.6882, 0),
    "DAL": (32.7905, -96.8103, 1),
    "DEN": (39.7487, -105.0077, 2),
    "DET": (42.3410, -83.0553, 0),
    "GSW": (37.7679, -122.3874, 3),
    "HOU": (29.7508, -95.3621, 1),
    "IND": (39.7639, -86.1555, 0),
    "LAC": (34.0430, -118.2673, 3),
    "LAL": (34.0430, -118.2673, 3),
    "MEM": (35.1382, -90.0505, 1),
    "MIA": (25.7814, -80.1870, 0),
    "MIL": (43.0451, -87.9168, 1),
    "MIN": (44.9795, -93.2760, 1),
    "NOP": (29.9490, -90.0812, 1),
    "NYK": (40.7505, -73.9934, 0),
    "OKC": (35.4634, -97.5151, 1),
    "ORL": (28.5392, -81.3837, 0),
    "PHI": (39.9012, -75.1720, 0),
    "PHX": (33.4457, -112.0712, 2),
    "POR": (45.5316, -122.6668, 3),
    "SAC": (38.5802, -121.4996, 3),
    "SAS": (29.4270, -98.4375, 1),
    "TOR": (43.6435, -79.3791, 0),
    "UTA": (40.7683, -111.9011, 2),
    "WAS": (38.8981, -77.0209, 0),
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles."""
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _miles_between(abbr_a: str, abbr_b: str) -> float:
    if abbr_a not in _ARENA_GEO or abbr_b not in _ARENA_GEO:
        return 0.0
    lat1, lon1, _ = _ARENA_GEO[abbr_a]
    lat2, lon2, _ = _ARENA_GEO[abbr_b]
    return round(_haversine(lat1, lon1, lat2, lon2), 1)


def _tz_offset(abbr: str) -> int:
    return _ARENA_GEO.get(abbr, (0, 0, 0))[2]


def _get_schedule_cache_path(team_abbrev: str, season: str) -> str:
    return os.path.join(_SCHED_DIR, f"schedule_{team_abbrev}_{season}_v2.json")


def _load_schedule(team_abbrev: str, season: str) -> List[dict]:
    """Load schedule from cache; fetch via NBA API if missing."""
    path = _get_schedule_cache_path(team_abbrev, season)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if data:
                return data
        except Exception:
            pass

    # Fetch via existing schedule_context module
    try:
        import sys
        sys.path.insert(0, _PROJECT_DIR)
        from src.data.schedule_context import get_season_schedule  # type: ignore
        return get_season_schedule(team_abbrev, season)
    except Exception as exc:
        log.warning("schedule fetch failed %s %s: %s", team_abbrev, season, exc)
        return []


def _get_team_abbrev(team_id: int) -> Optional[str]:
    try:
        from nba_api.stats.static import teams as nba_teams  # type: ignore
        matches = [t for t in nba_teams.get_teams() if t["id"] == team_id]
        return matches[0]["abbreviation"] if matches else None
    except Exception:
        return None


def get_team_schedule_features(
    team_id: int,
    game_date: str,
    season: str,
) -> dict:
    """
    Return schedule-pressure features for a team on game_date.

    Args:
        team_id:   NBA team ID integer.
        game_date: ISO date string "YYYY-MM-DD" of the target game.
        season:    Season string "YYYY-YY" (e.g. "2024-25").

    Returns:
        dict with keys:
            games_in_last_7d, games_in_last_14d,
            miles_traveled_last_7d, miles_traveled_last_14d,
            time_zones_crossed_last_7d,
            consecutive_road_games, consecutive_home_games,
            days_since_last_game, days_until_next_game,
            is_4in6, is_5in7,
            cross_country_flag,
            team_id, game_date
    """
    target_dt = datetime.strptime(game_date, "%Y-%m-%d")

    abbrev = _get_team_abbrev(team_id)
    if abbrev is None:
        log.warning("schedule_pressure: unknown team_id %d", team_id)
        return _default_features(team_id, game_date)

    games = _load_schedule(abbrev, season)
    if not games:
        return _default_features(team_id, game_date)

    # Sort by date ascending
    def _parse(g: dict) -> Optional[datetime]:
        try:
            return datetime.strptime(g["date"], "%Y-%m-%d")
        except Exception:
            return None

    games_dated = [(g, _parse(g)) for g in games]
    games_dated = [(g, d) for g, d in games_dated if d is not None]
    games_dated.sort(key=lambda x: x[1])

    # Find target game index
    target_idx: Optional[int] = None
    for i, (g, d) in enumerate(games_dated):
        if d.date() == target_dt.date():
            target_idx = i
            break

    if target_idx is None:
        # Use games before target date
        prior = [(g, d) for g, d in games_dated if d < target_dt]
    else:
        prior = games_dated[:target_idx]

    future = [(g, d) for g, d in games_dated
              if d > target_dt or (target_idx is not None and games_dated.index((g, d)) > target_idx
                                   if (g, d) in games_dated else d > target_dt)]
    # Simpler: everything after target_idx
    if target_idx is not None:
        future_games = [(g, d) for g, d in games_dated if games_dated.index((g, d)) > target_idx]
    else:
        future_games = [(g, d) for g, d in games_dated if d >= target_dt]

    # ── Rolling windows ────────────────────────────────────────────────────────
    cutoff_7  = target_dt - timedelta(days=7)
    cutoff_14 = target_dt - timedelta(days=14)

    last_7  = [(g, d) for g, d in prior if d >= cutoff_7]
    last_14 = [(g, d) for g, d in prior if d >= cutoff_14]

    games_in_last_7d  = len(last_7)
    games_in_last_14d = len(last_14)

    # Miles traveled: sum of inter-arena legs
    def _sum_miles(window: List[Tuple[dict, datetime]]) -> float:
        total = 0.0
        prev_venue: Optional[str] = None
        for g, _ in sorted(window, key=lambda x: x[1]):
            matchup = g.get("matchup", "")
            is_home  = g.get("home", "vs." in matchup)
            opp      = g.get("opponent", "")
            venue    = abbrev if is_home else opp
            if prev_venue and prev_venue != venue:
                total += _miles_between(prev_venue, venue)
            prev_venue = venue
        return round(total, 1)

    # Include the leg arriving at this game
    def _sum_miles_with_target(window: List[Tuple[dict, datetime]], target_venue: str) -> float:
        combined = window[:]
        # Add a synthetic "last step to target"
        miles = _sum_miles(window)
        if window:
            last_game, _ = sorted(window, key=lambda x: x[1])[-1]
            last_home = last_game.get("home", True)
            last_opp  = last_game.get("opponent", "")
            last_venue = abbrev if last_home else last_opp
            miles += _miles_between(last_venue, target_venue)
        return round(miles, 1)

    # Determine target game venue
    if target_idx is not None:
        tg, _ = games_dated[target_idx]
        target_is_home = tg.get("home", True)
        target_opp     = tg.get("opponent", "")
    else:
        target_is_home = True
        target_opp     = ""
    target_venue = abbrev if target_is_home else target_opp

    miles_7d  = _sum_miles_with_target(last_7, target_venue)
    miles_14d = _sum_miles_with_target(last_14, target_venue)

    # Time zones crossed last 7d
    tz_crossings = 0
    prev_tz: Optional[int] = None
    for g, _ in sorted(last_7, key=lambda x: x[1]):
        is_home = g.get("home", True)
        opp_tz  = g.get("opponent", "")
        venue   = abbrev if is_home else opp_tz
        tz      = _tz_offset(venue)
        if prev_tz is not None:
            tz_crossings += abs(tz - prev_tz)
        prev_tz = tz
    time_zones_crossed_last_7d = tz_crossings

    # Consecutive road / home streaks (going backwards from target)
    consec_road = 0
    consec_home = 0
    for g, _ in reversed(prior):
        is_home = g.get("home", True)
        if not is_home:
            if consec_home > 0:
                break
            consec_road += 1
        else:
            if consec_road > 0:
                break
            consec_home += 1

    # Days since / until next game
    days_since = 99
    if prior:
        last_dt = prior[-1][1]
        days_since = (target_dt - last_dt).days

    days_until = 99
    if future_games:
        next_dt = future_games[0][1]
        days_until = (next_dt - target_dt).days

    # 4-in-6 and 5-in-7 flags (include target game)
    def _count_in_window(days: int) -> int:
        cutoff = target_dt - timedelta(days=days)
        count  = sum(1 for _, d in prior if d >= cutoff)
        return count + 1  # +1 for target game

    is_4in6 = int(_count_in_window(6) >= 4)
    is_5in7 = int(_count_in_window(7) >= 5)

    # Cross-country flag: flew >1500 miles in last 24h
    cross_country_flag = 0
    cutoff_24h = target_dt - timedelta(hours=24)
    for g, d in prior:
        if d >= cutoff_24h:
            is_home_g = g.get("home", True)
            opp_g     = g.get("opponent", "")
            prev_venue_g = abbrev if is_home_g else opp_g
            leg = _miles_between(prev_venue_g, target_venue)
            if leg > 1500:
                cross_country_flag = 1
                break

    return {
        "team_id":                    team_id,
        "game_date":                  game_date,
        "games_in_last_7d":           games_in_last_7d,
        "games_in_last_14d":          games_in_last_14d,
        "miles_traveled_last_7d":     miles_7d,
        "miles_traveled_last_14d":    miles_14d,
        "time_zones_crossed_last_7d": time_zones_crossed_last_7d,
        "consecutive_road_games":     consec_road,
        "consecutive_home_games":     consec_home,
        "days_since_last_game":       days_since,
        "days_until_next_game":       days_until,
        "is_4in6":                    is_4in6,
        "is_5in7":                    is_5in7,
        "cross_country_flag":         cross_country_flag,
    }


def _default_features(team_id: int, game_date: str) -> dict:
    return {
        "team_id":                    team_id,
        "game_date":                  game_date,
        "games_in_last_7d":           0,
        "games_in_last_14d":          0,
        "miles_traveled_last_7d":     0.0,
        "miles_traveled_last_14d":    0.0,
        "time_zones_crossed_last_7d": 0,
        "consecutive_road_games":     0,
        "consecutive_home_games":     0,
        "days_since_last_game":       99,
        "days_until_next_game":       99,
        "is_4in6":                    0,
        "is_5in7":                    0,
        "cross_country_flag":         0,
    }
