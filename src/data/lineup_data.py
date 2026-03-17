"""
lineup_data.py — NBA 5-man lineup data and on/off splits.

Fetches and caches per-game lineup data from the NBA Stats API:
  - 5-man unit net rating and minutes
  - On/off splits for individual players
  - Lineup pace, eFG%, turnover rate

All data cached under data/nba/lineups/ as JSON.

Public API
----------
    get_game_lineups(game_id)               -> List[dict]
    get_lineup_splits(team_id, season)      -> List[dict]
    get_player_on_off(player_id, season)    -> dict
    get_top_lineups(team_abbrev, season, n) -> List[dict]
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "lineups")
os.makedirs(_CACHE_DIR, exist_ok=True)

_API_DELAY = 0.6  # seconds between NBA API calls


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    safe = key.replace("/", "_").replace(" ", "_")
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _load_cache(key: str) -> Optional[list | dict]:
    path = _cache_path(key)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: list | dict) -> None:
    with open(_cache_path(key), "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Team ID lookup
# ─────────────────────────────────────────────────────────────────────────────

def _team_id(abbrev: str) -> Optional[int]:
    """Look up NBA team ID from abbreviation."""
    try:
        from nba_api.stats.static import teams as nba_teams_static
        matches = [t for t in nba_teams_static.get_teams() if t["abbreviation"] == abbrev]
        return matches[0]["id"] if matches else None
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Lineup splits (season-level)
# ─────────────────────────────────────────────────────────────────────────────

def get_lineup_splits(
    team_abbrev: str,
    season: str = "2024-25",
    min_minutes: float = 5.0,
) -> list[dict]:
    """
    Fetch all 5-man lineup stats for a team over a full season.

    Args:
        team_abbrev: Team abbreviation (e.g. "GSW")
        season: NBA season string (e.g. "2024-25")
        min_minutes: Only return lineups with >= this many minutes played

    Returns:
        List of dicts sorted by net_rating descending:
        {
            "lineup": List[str],     # 5 player names
            "minutes": float,
            "net_rating": float,     # points per 100 possessions differential
            "off_rating": float,
            "def_rating": float,
            "pace": float,
            "efg_pct": float,
            "tov_pct": float,
            "oreb_pct": float,
            "ft_rate": float,
            "plus_minus": float,
        }
    """
    cache_key = f"lineup_splits_{team_abbrev}_{season}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    team_id_val = _team_id(team_abbrev)
    if team_id_val is None:
        print(f"[lineup_data] Unknown team: {team_abbrev}")
        return []

    try:
        from nba_api.stats.endpoints import leaguedashlineups
    except ImportError:
        print("[lineup_data] nba_api not installed")
        return []

    time.sleep(_API_DELAY)
    try:
        resp = leaguedashlineups.LeagueDashLineups(
            season=season,
            team_id_nullable=team_id_val,
            measure_type_detailed_defense="Advanced",
            per_mode_simple="Per100Possessions",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[lineup_data] API error for lineup splits: {e}")
        return []

    result = []
    for _, row in df.iterrows():
        mins = float(row.get("MIN", 0))
        if mins < min_minutes:
            continue
        lineup_str = row.get("GROUP_NAME", "")
        players = [p.strip() for p in lineup_str.split(" - ")]
        entry = {
            "lineup": players,
            "minutes": round(mins, 1),
            "net_rating": float(row.get("NET_RATING", 0) or 0),
            "off_rating": float(row.get("OFF_RATING", 0) or 0),
            "def_rating": float(row.get("DEF_RATING", 0) or 0),
            "pace": float(row.get("PACE", 0) or 0),
            "efg_pct": float(row.get("EFG_PCT", 0) or 0),
            "tov_pct": float(row.get("TM_TOV_PCT", 0) or 0),
            "oreb_pct": float(row.get("OREB_PCT", 0) or 0),
            "ft_rate": float(row.get("FTA_RATE", 0) or 0),
            "plus_minus": float(row.get("PLUS_MINUS", 0) or 0),
        }
        result.append(entry)

    result.sort(key=lambda x: x["net_rating"], reverse=True)
    _save_cache(cache_key, result)
    return result


def get_top_lineups(
    team_abbrev: str,
    season: str = "2024-25",
    n: int = 5,
    min_minutes: float = 30.0,
) -> list[dict]:
    """
    Return the top N lineups by net rating with >= min_minutes played.

    Args:
        team_abbrev: Team abbreviation
        season: NBA season string
        n: Number of lineups to return
        min_minutes: Minimum minutes threshold

    Returns:
        Top N lineup dicts (see get_lineup_splits for schema).
    """
    all_lineups = get_lineup_splits(team_abbrev, season, min_minutes=min_minutes)
    return all_lineups[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Player on/off splits
# ─────────────────────────────────────────────────────────────────────────────

def get_player_on_off(player_id: int, season: str = "2024-25") -> dict:
    """
    Fetch on/off net rating splits for a specific player.

    Args:
        player_id: NBA player ID
        season: NBA season string

    Returns:
        {
            "on_net_rating": float,
            "off_net_rating": float,
            "on_off_diff": float,       # on minus off (higher = more impactful)
            "on_minutes": float,
            "off_minutes": float,
        }
    """
    cache_key = f"on_off_{player_id}_{season}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    try:
        from nba_api.stats.endpoints import playerdashboardbygeneralsplits
    except ImportError:
        print("[lineup_data] nba_api not installed")
        return {}

    time.sleep(_API_DELAY)
    try:
        resp = playerdashboardbygeneralsplits.PlayerDashboardByGeneralSplits(
            player_id=player_id,
            season=season,
            measure_type_detailed="Advanced",
            per_mode_simple="Per100Possessions",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[lineup_data] API error for player on/off {player_id}: {e}")
        return {}

    if df.empty:
        return {}

    row = df.iloc[0]
    result = {
        "on_net_rating": float(row.get("NET_RATING", 0) or 0),
        "off_net_rating": 0.0,  # requires separate call — placeholder
        "on_off_diff": 0.0,
        "on_minutes": float(row.get("MIN", 0) or 0),
        "off_minutes": 0.0,
    }
    _save_cache(cache_key, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Game-level lineup summary
# ─────────────────────────────────────────────────────────────────────────────

def get_game_lineups(game_id: str) -> list[dict]:
    """
    Fetch 5-man lineup breakdowns for a specific game.

    Args:
        game_id: NBA game ID string (e.g. "0022300001")

    Returns:
        List of lineup stint dicts for both teams:
        {
            "team_id": int,
            "lineup": List[str],
            "period": int,
            "time_in": str,
            "time_out": str,
            "minutes": float,
            "plus_minus": int,
        }
    """
    cache_key = f"game_lineups_{game_id}"
    cached = _load_cache(cache_key)
    if cached:
        return cached

    try:
        from nba_api.stats.endpoints import gamerotation
    except ImportError:
        print("[lineup_data] nba_api not installed")
        return []

    time.sleep(_API_DELAY)
    try:
        resp = gamerotation.GameRotation(game_id=game_id)
        frames = resp.get_data_frames()
    except Exception as e:
        print(f"[lineup_data] API error for game lineups {game_id}: {e}")
        return []

    result = []
    for df in frames:
        if df.empty:
            continue
        for _, row in df.iterrows():
            result.append({
                "team_id": int(row.get("TEAM_ID", 0)),
                "player_id": int(row.get("PERSON_ID", 0)),
                "player_name": str(row.get("PLAYER_FIRST", "") + " " + row.get("PLAYER_LAST", "")).strip(),
                "period": int(row.get("IN_TIME_REAL", 0)) // 600,  # approximate
                "in_time": float(row.get("IN_TIME_REAL", 0)),
                "out_time": float(row.get("OUT_TIME_REAL", 0)),
                "pts_diff": int(row.get("PT_DIFF", 0)),
            })

    _save_cache(cache_key, result)
    return result


def lineup_net_rating_lookup(
    team_abbrev: str,
    player_names: list[str],
    season: str = "2024-25",
) -> Optional[float]:
    """
    Look up net rating for a specific 5-man lineup from season data.

    Args:
        team_abbrev: Team abbreviation
        player_names: List of 5 player last names (partial match OK)
        season: NBA season

    Returns:
        Net rating float if lineup found (>= 30 min played), else None.
    """
    splits = get_lineup_splits(team_abbrev, season, min_minutes=30.0)
    target_set = set(n.lower() for n in player_names)
    for lu in splits:
        lu_set = set(n.split()[-1].lower() for n in lu["lineup"])
        if lu_set == target_set:
            return lu["net_rating"]
    return None
