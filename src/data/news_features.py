"""
news_features.py — Feature vector builder consumed at prediction time.

Combines injury news + projected lineup data for a matchup into a flat
feature dict usable by downstream models (win probability, player props, etc).

Public API
----------
    build_news_features(home_team, away_team, game_date) -> dict
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
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")

# MPG threshold for "star" classification when no explicit star list exists
_STAR_MPG_CUTOFF = 30.0

# Statuses that count as a player being unavailable/risky
_OUT_STATUSES       = {"OUT", "DOUBTFUL"}
_QUESTIONABLE_STATUS = "QUESTIONABLE"


# ──────────────────────────────────────────────────────────────────────────────
# All-star / star player detection
# ──────────────────────────────────────────────────────────────────────────────

_star_ids: Optional[set] = None


def _load_star_ids() -> set:
    """
    Build a set of player_id ints considered "stars".

    Priority:
    1. data/nba/allstar_players.json (manually curated or from nba_api)
    2. Players with avg_minutes >= _STAR_MPG_CUTOFF from player_avgs cache
    """
    # Try explicit allstar list first
    allstar_path = os.path.join(_NBA_CACHE, "allstar_players.json")
    if os.path.exists(allstar_path):
        try:
            with open(allstar_path, encoding="utf-8") as f:
                data = json.load(f)
            ids = set()
            for entry in data:
                if isinstance(entry, (int, float)):
                    ids.add(int(entry))
                elif isinstance(entry, dict) and "player_id" in entry:
                    ids.add(int(entry["player_id"]))
            if ids:
                log.debug("[news_features] Loaded %d all-stars from %s", len(ids), allstar_path)
                return ids
        except Exception as exc:
            log.debug("[news_features] allstar file parse error: %s", exc)

    # Fallback: high-MPG players from avgs cache
    for season in ("2024-25", "2025-26", "2023-24"):
        path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                avgs = json.load(f)
            ids = set()
            for name, info in avgs.items():
                if not isinstance(info, dict):
                    continue
                mpg = float(info.get("avg_minutes", info.get("min", 0)) or 0)
                if mpg >= _STAR_MPG_CUTOFF and "player_id" in info:
                    ids.add(int(info["player_id"]))
            if ids:
                log.debug("[news_features] Built star set from %s: %d players >= %.0f mpg",
                          path, len(ids), _STAR_MPG_CUTOFF)
                return ids
        except Exception as exc:
            log.debug("[news_features] avgs parse error: %s", exc)

    # Last resort: well-known star IDs (2024-25 season top players)
    _fallback_stars = {
        2544,   # LeBron James
        203999, # Nikola Jokic
        1629029, # Luka Doncic
        203954, # Joel Embiid
        1628369, # Jayson Tatum
        201935, # James Harden
        1629627, # Zion Williamson
        1628378, # De'Aaron Fox
        1628384, # Donovan Mitchell
        1627783, # Pascal Siakam
        203507, # Giannis Antetokounmpo
        1629028, # Shai Gilgeous-Alexander
        1629630, # Ja Morant
        202681, # Kyrie Irving
    }
    log.debug("[news_features] Using hardcoded fallback star IDs (%d)", len(_fallback_stars))
    return _fallback_stars


def _get_star_ids() -> set:
    global _star_ids
    if _star_ids is None:
        _star_ids = _load_star_ids()
    return _star_ids


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _count_by_status(records: List[dict], team: str, statuses: set) -> int:
    team_upper = team.upper()
    return sum(
        1 for r in records
        if r.get("team", "").upper() == team_upper
        and r.get("status", "").upper() in statuses
    )


def _star_out_flag(records: List[dict], team: str, star_ids: set) -> int:
    """Return 1 if any star player on team is OUT or DOUBTFUL."""
    team_upper = team.upper()
    for rec in records:
        if rec.get("team", "").upper() != team_upper:
            continue
        if rec.get("status", "").upper() not in _OUT_STATUSES:
            continue
        pid = rec.get("player_id")
        if pid is not None and int(pid) in star_ids:
            return 1
    return 0


def _starter_change_flag(
    team: str,
    game_date: str,
    prev_date: Optional[str] = None,
) -> int:
    """
    Return 1 if projected starting lineup differs from the previous game.

    Compares current projected starters vs last boxscore starters.
    Returns 0 if data unavailable (safe default — no artificial edge).
    """
    try:
        from src.data.lineup_news import get_projected_starters_by_abbrev, _cache_path
        current = set(get_projected_starters_by_abbrev(team, game_date))
        if not current:
            return 0

        # Check cache for any prior date — use the most recently cached lineup
        import glob
        cache_dir = os.path.join(PROJECT_DIR, "data", "cache", "lineups")
        pattern   = os.path.join(cache_dir, f"{team.upper()}_*.json")
        files     = sorted(glob.glob(pattern))
        # Exclude today's cache
        prev_files = [f for f in files if game_date not in f]
        if not prev_files:
            return 0

        with open(prev_files[-1], encoding="utf-8") as f:
            prev_data = json.load(f)
        prev_starters = set(prev_data.get("starters", []))
        if not prev_starters:
            return 0

        return 1 if current != prev_starters else 0
    except Exception as exc:
        log.debug("[news_features] starter_change_flag error for %s: %s", team, exc)
        return 0


def _news_freshness_minutes(game_date: str) -> int:
    """Return age of the news cache for this game date in minutes."""
    try:
        from src.data.news_ingest import _cache_path as news_cache_path
        import os as _os
        path = news_cache_path(game_date)
        if not _os.path.exists(path):
            return 999
        age_secs = time.time() - _os.path.getmtime(path)
        return int(age_secs / 60)
    except Exception:
        return 999


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def build_news_features(
    home_team: str,
    away_team: str,
    game_date: Optional[str] = None,
) -> dict:
    """
    Build a flat feature dict capturing injury/lineup news for a matchup.

    Args:
        home_team: Home team abbreviation (e.g. "GSW").
        away_team: Away team abbreviation (e.g. "LAL").
        game_date: ISO date string (YYYY-MM-DD).  Defaults to today.

    Returns:
        {
            "home_inactives_count":    int,   # players OUT or DOUBTFUL
            "away_inactives_count":    int,
            "home_questionable_count": int,
            "away_questionable_count": int,
            "home_starter_change_flag": int,  # 1 if projected starter != last game
            "away_starter_change_flag": int,
            "home_star_out_flag":      int,   # any all-star OUT/DOUBTFUL
            "away_star_out_flag":      int,
            "news_freshness_minutes":  int,   # minutes since last cache refresh
        }
    """
    if game_date is None:
        game_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Import here to avoid circular imports at module load time
    from src.data.news_ingest import get_injury_records

    records    = get_injury_records(game_date)
    star_ids   = _get_star_ids()

    features = {
        "home_inactives_count":     _count_by_status(records, home_team, _OUT_STATUSES),
        "away_inactives_count":     _count_by_status(records, away_team, _OUT_STATUSES),
        "home_questionable_count":  _count_by_status(records, home_team, {_QUESTIONABLE_STATUS}),
        "away_questionable_count":  _count_by_status(records, away_team, {_QUESTIONABLE_STATUS}),
        "home_starter_change_flag": _starter_change_flag(home_team, game_date),
        "away_starter_change_flag": _starter_change_flag(away_team, game_date),
        "home_star_out_flag":       _star_out_flag(records, home_team, star_ids),
        "away_star_out_flag":       _star_out_flag(records, away_team, star_ids),
        "news_freshness_minutes":   _news_freshness_minutes(game_date),
    }
    log.info(
        "[news_features] %s vs %s on %s: home_inactive=%d away_inactive=%d",
        home_team, away_team, game_date,
        features["home_inactives_count"],
        features["away_inactives_count"],
    )
    return features
