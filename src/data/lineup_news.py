"""
lineup_news.py — Projected starter / roster availability for upcoming games.

Combines NBA Stats API roster + most-recent boxscore starters to estimate
who will be in the starting five for an upcoming game.

Cache location: data/cache/lineups/{team}_{date}.json
Cache TTL:      2 hours (lineups are relatively stable day-of)

Public API
----------
    get_projected_starters(team_id, game_date)        -> List[int]
    get_projected_starters_by_abbrev(abbrev, date)    -> List[int]
    get_lineup_freshness_minutes(team, game_date)     -> int
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

log = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR  = os.path.join(PROJECT_DIR, "data", "cache", "lineups")
_CACHE_TTL  = 7200  # 2 hours
_API_DELAY  = 0.8   # seconds between NBA API calls

# Map abbreviation → team_id for convenience
_ABBREV_TO_ID: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}

_ID_TO_ABBREV: dict[int, str] = {v: k for k, v in _ABBREV_TO_ID.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────────────────────────────────────

def _cache_path(team: str, game_date: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{team.upper()}_{game_date}.json")


def _cache_is_fresh(team: str, game_date: str) -> bool:
    path = _cache_path(team, game_date)
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < _CACHE_TTL


def _load_cache(team: str, game_date: str) -> Optional[dict]:
    path = _cache_path(team, game_date)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("[lineup_news] cache load failed: %s", exc)
        return None


def _save_cache(team: str, game_date: str, data: dict) -> None:
    try:
        with open(_cache_path(team, game_date), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        log.warning("[lineup_news] cache save failed: %s", exc)


def get_lineup_freshness_minutes(team: str, game_date: str) -> int:
    """Return age of lineup cache in minutes, or 999 if no cache exists."""
    path = _cache_path(team, game_date)
    if not os.path.exists(path):
        return 999
    age_secs = time.time() - os.path.getmtime(path)
    return int(age_secs / 60)


# ──────────────────────────────────────────────────────────────────────────────
# NBA Stats API helpers
# ──────────────────────────────────────────────────────────────────────────────

def _roster_player_ids(team_id: int) -> List[int]:
    """Return all active player IDs on a team from commonteamroster endpoint."""
    try:
        from nba_api.stats.endpoints import commonteamroster
        time.sleep(_API_DELAY)
        resp = commonteamroster.CommonTeamRoster(team_id=team_id)
        df   = resp.get_data_frames()[0]
        if df.empty:
            return []
        return [int(pid) for pid in df["PLAYER_ID"].dropna().tolist()]
    except Exception as exc:
        log.warning("[lineup_news] roster API failed for team %s: %s", team_id, exc)
        return []


def _last_game_starters(team_id: int) -> List[int]:
    """
    Fetch the starting 5 for this team from their most recent boxscore.

    Uses leaguegamelog → most recent game → boxscoresummary starters.
    """
    try:
        from nba_api.stats.endpoints import leaguegamelog, boxscoresummaryv2
        time.sleep(_API_DELAY)

        log_resp = leaguegamelog.LeagueGameLog(
            player_or_team="T",
            season="2024-25",
            season_type_all_star="Regular Season",
        )
        df = log_resp.get_data_frames()[0]
        team_games = df[df["TEAM_ID"] == team_id].sort_values("GAME_DATE", ascending=False)
        if team_games.empty:
            return []

        last_game_id = str(team_games.iloc[0]["GAME_ID"])
        time.sleep(_API_DELAY)

        box_resp  = boxscoresummaryv2.BoxScoreSummaryV2(game_id=last_game_id)
        frames    = box_resp.get_data_frames()

        # Frame index 5 is "InactivePlayers", frame 0 is "GameSummary"
        # Starting lineups come from frame 4 "LineScore" or we use boxscoretraditionalv2
        # Use frame 4 if available; fall back to first 5 players on team in boxscore
        if len(frames) > 4:
            # Try playertrack-style — look for start position in data
            pass

        # Simpler fallback: use boxscoretraditionalv2 to get players + start positions
        from nba_api.stats.endpoints import boxscoretraditionalv2
        time.sleep(_API_DELAY)
        trad_resp = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=last_game_id)
        player_df = trad_resp.get_data_frames()[0]
        team_df   = player_df[player_df["TEAM_ID"] == team_id]
        starters  = team_df[team_df["START_POSITION"].str.strip() != ""]
        return [int(pid) for pid in starters["PLAYER_ID"].dropna().tolist()][:5]

    except Exception as exc:
        log.warning("[lineup_news] last-game starters failed for team %s: %s", team_id, exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get_projected_starters(
    team_id: int,
    game_date: str,
    force: bool = False,
) -> List[int]:
    """
    Estimate the starting 5 player IDs for a team on a given game date.

    Strategy:
    1. Return cached result if fresh (within 2 hours).
    2. Hit commonteamroster to validate roster membership.
    3. Use last boxscore's START_POSITION=non-empty as projected starters.
    4. If boxscore unavailable, return first 5 roster IDs as placeholder.

    Args:
        team_id:   NBA team ID integer.
        game_date: ISO date string (YYYY-MM-DD).
        force:     Bypass cache.

    Returns:
        List of up to 5 player_id integers.  Empty list if unavailable.
    """
    abbrev = _ID_TO_ABBREV.get(team_id, str(team_id))

    if not force and _cache_is_fresh(abbrev, game_date):
        cached = _load_cache(abbrev, game_date)
        if cached:
            return cached.get("starters", [])

    starters = _last_game_starters(team_id)

    if not starters:
        # Fallback: first 5 active roster players
        roster = _roster_player_ids(team_id)
        starters = roster[:5]

    result = {
        "team_id":    team_id,
        "team":       abbrev,
        "game_date":  game_date,
        "starters":   starters,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "method":     "boxscore_starters" if starters else "roster_fallback",
    }
    _save_cache(abbrev, game_date, result)
    log.info("[lineup_news] %s starters for %s: %s", abbrev, game_date, starters)
    return starters


def get_projected_starters_by_abbrev(
    team_abbrev: str,
    game_date: str,
    force: bool = False,
) -> List[int]:
    """
    Convenience wrapper — resolve team abbreviation to ID then call
    get_projected_starters.

    Args:
        team_abbrev: Three-letter abbreviation (e.g. "GSW").
        game_date:   ISO date string.
        force:       Bypass cache.

    Returns:
        List of up to 5 player_id integers.
    """
    team_id = _ABBREV_TO_ID.get(team_abbrev.upper())
    if team_id is None:
        log.warning("[lineup_news] Unknown team abbreviation: %s", team_abbrev)
        return []
    return get_projected_starters(team_id, game_date, force=force)
