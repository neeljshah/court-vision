"""
injury_impact.py — Team injury impact measured in estimated win-shares lost.

Strategy
--------
For each game, identify which players were inactive (did not play) for each team.
Weight each inactive player's absence by their prior-season per-game win-shares
(WS_pg) — or by a points+minutes proxy when WS data is unavailable.

Win-share proxy when full WS data is missing:
    ws_proxy = min(pts_pg * 0.05 + min_pg * 0.003, 0.3)

This caps a single player at 0.3 WS/game (roughly a max-contract star), which
prevents outlier values from dominating the feature.

Data sources (all local cache — no live API calls needed):
  - data/nba/season_games_{season}.json — game_id list
  - data/nba/player_avgs_{season}.json  — pts, min per game keyed by player name
  - data/nba/boxscore_{game_id}.json    — who actually played (starters + bench)

Caching
-------
Results are cached at data/cache/injury_impact_{team}_{game_id}.json
to avoid re-computing on subsequent calls.

Public API
----------
    get_injury_impact(team_id_or_abbr, game_id, season) -> float
    build_injury_lookup(seasons)                        -> dict
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE   = os.path.join(_PROJECT_DIR, "data", "nba")
_INJ_CACHE   = os.path.join(_PROJECT_DIR, "data", "cache", "injury_impact")

# Per-game WS cap: no single player contributes more than this to the feature
_MAX_WS_PER_PLAYER = 0.30
# Teams always rest 1-2 players — don't flag routine DNPs as "injury"
# We only count players who were rostered last season but have 0 min this game
_MIN_PREV_SEASON_GP = 10  # player must have played 10+ games last season to count


def _ws_proxy(pts_pg: float, min_pg: float) -> float:
    """Approximate per-game win shares from basic rate stats."""
    raw = pts_pg * 0.05 + min_pg * 0.003
    return round(min(raw, _MAX_WS_PER_PLAYER), 4)


def _load_player_avgs(season: str) -> dict:
    """Load player_avgs_{season}.json keyed by player_name (lowercase)."""
    path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    if not os.path.exists(path):
        return {}
    try:
        raw = json.load(open(path))
        # Keys may be title-case names — normalise to lowercase
        return {k.lower(): v for k, v in raw.items()}
    except Exception:
        return {}


def _prev_season(season: str) -> str:
    """Return the season string for the year before the given season."""
    try:
        start = int(season.split("-")[0])
        prev_start = start - 1
        prev_end   = prev_start + 1
        return f"{prev_start}-{str(prev_end)[-2:]}"
    except Exception:
        return season


def _load_boxscore_players(game_id: str) -> Optional[List[dict]]:
    """Load player list from data/nba/boxscore_{game_id}.json. None on miss."""
    path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if not os.path.exists(path):
        return None
    try:
        bs = json.load(open(path))
        return bs.get("players", [])
    except Exception:
        return None


def _load_cache(team_abbr: str, game_id: str) -> Optional[float]:
    os.makedirs(_INJ_CACHE, exist_ok=True)
    path = os.path.join(_INJ_CACHE, f"{team_abbr}_{game_id}.json")
    if os.path.exists(path):
        try:
            return float(json.load(open(path))["ws_lost"])
        except Exception:
            pass
    return None


def _save_cache(team_abbr: str, game_id: str, ws_lost: float) -> None:
    os.makedirs(_INJ_CACHE, exist_ok=True)
    path = os.path.join(_INJ_CACHE, f"{team_abbr}_{game_id}.json")
    try:
        with open(path, "w") as f:
            json.dump({"ws_lost": ws_lost}, f)
    except Exception:
        pass


def _compute_team_ws_lost(
    team_abbr: str,
    game_id: str,
    season: str,
    prev_avgs: dict,
    all_avgs: dict,
) -> float:
    """
    Compute total win-shares lost for a team in a given game.

    Strategy:
      1. Load the boxscore to get which players actually played (min > 0).
      2. Build a set of player names who played for this team.
      3. For each player in prev_season avgs (this team, min >= threshold):
         if they are NOT in the active players set → count their WS proxy as lost.

    Returns:
        float — sum of WS proxies for inactive players (0.0 on any failure).
    """
    cached = _load_cache(team_abbr, game_id)
    if cached is not None:
        return cached

    players = _load_boxscore_players(game_id)
    if players is None:
        # No boxscore cached — can't determine inactives; return 0.0 and don't cache
        return 0.0

    # Names of players who actually played for this team (min > 0)
    active_names = {
        p.get("player_name", "").lower()
        for p in players
        if str(p.get("team_abbreviation", "")).upper() == team_abbr.upper()
        and float(p.get("min", 0) or 0) > 0
    }

    # Also check current season for lineup context (handles mid-season trades)
    # Use prev_season avgs as the "expected" roster
    ws_lost = 0.0
    for name, stats in prev_avgs.items():
        team = str(stats.get("team", "")).upper()
        if team != team_abbr.upper():
            continue
        gp = int(stats.get("gp", 0) or 0)
        if gp < _MIN_PREV_SEASON_GP:
            continue
        # If player wasn't in boxscore for this game, they were inactive
        if name not in active_names:
            pts = float(stats.get("pts", 0) or 0)
            mins = float(stats.get("min", 0) or 0)
            ws = _ws_proxy(pts, mins)
            ws_lost += ws

    ws_lost = round(ws_lost, 4)
    _save_cache(team_abbr, game_id, ws_lost)
    return ws_lost


def get_injury_impact(
    team_abbr: str,
    game_id: str,
    season: str,
) -> float:
    """
    Return estimated win-shares lost due to injuries for a team in a game.

    Uses prior-season player averages to identify expected contributors who
    were absent from the boxscore.

    Args:
        team_abbr:  Team abbreviation e.g. "GSW".
        game_id:    NBA game ID string e.g. "0022400061".
        season:     Season string e.g. "2024-25".

    Returns:
        Float WS lost (0.0 on data miss — never raises).
    """
    try:
        prev_ssn   = _prev_season(season)
        prev_avgs  = _load_player_avgs(prev_ssn)
        # Also try current season avgs (updated mid-season)
        curr_avgs  = _load_player_avgs(season)
        # Merge: prefer current season to handle trades/rookies, prev for WS weight
        combined   = {**curr_avgs, **prev_avgs}  # prev takes precedence for WS weight
        return _compute_team_ws_lost(team_abbr, game_id, season, combined, curr_avgs)
    except Exception as exc:
        log.warning("injury_impact: %s %s: %s", team_abbr, game_id, exc)
        return 0.0


def build_injury_lookup(seasons: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Pre-compute injury impact for all games in the given seasons.

    Returns:
        Dict: game_id → {"home_inj_ws": float, "away_inj_ws": float, "inj_ws_diff": float}
        Entries are missing if boxscore data unavailable.
    """
    lookup: Dict[str, Dict[str, float]] = {}

    for season in seasons:
        rows = _load_season_rows(season)
        prev_ssn  = _prev_season(season)
        prev_avgs = _load_player_avgs(prev_ssn)
        curr_avgs = _load_player_avgs(season)
        combined  = {**curr_avgs, **prev_avgs}

        for g in rows:
            gid  = str(g.get("game_id", ""))
            home = str(g.get("home_team", ""))
            away = str(g.get("away_team", ""))
            if not gid or not home or not away:
                continue
            try:
                h_ws = _compute_team_ws_lost(home, gid, season, combined, curr_avgs)
                a_ws = _compute_team_ws_lost(away, gid, season, combined, curr_avgs)
                lookup[gid] = {
                    "home_inj_ws":  h_ws,
                    "away_inj_ws":  a_ws,
                    "inj_ws_diff":  round(h_ws - a_ws, 4),
                }
            except Exception as exc:
                log.debug("injury_lookup: %s: %s", gid, exc)

    return lookup


def _load_season_rows(season: str) -> List[dict]:
    """Load season_games rows from cache."""
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        return []
    try:
        payload = json.load(open(path))
        if isinstance(payload, dict):
            return payload.get("rows", [])
        return payload
    except Exception:
        return []
