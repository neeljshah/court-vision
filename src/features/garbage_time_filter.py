"""
garbage_time_filter.py — Garbage-time-aware rolling stats for player props.

Public API
----------
    is_garbage_time(margin, period, game_clock_sec) -> bool
    estimate_garbage_minutes_per_game(game_id)      -> Dict[int, float]
    get_clean_rolling_avg(player_id, stat, season, through_date, n_games) -> float
    get_raw_rolling_avg(player_id, stat, season, through_date, n_games)   -> float
    get_garbage_minutes(game_id, season)            -> Dict[int, float]
    load_season_cache / save_season_cache           -> cache I/O
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")
_GT_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "garbage_time")

log = logging.getLogger(__name__)

# Hoop-R thresholds: Q4 |margin| > 25, Q3 |margin| > 30
_GT_Q4_MARGIN = 25
_GT_Q3_MARGIN = 30
_Q4_TOTAL_SEC = 720   # seconds; clock counts up 0→720


def is_garbage_time(margin: int, period: int, game_clock_sec: int) -> bool:
    """Return True if game state qualifies as garbage time (margin always positive)."""
    if period == 3 and margin >= _GT_Q3_MARGIN:
        return True
    if period == 4 and margin >= _GT_Q4_MARGIN:
        return True
    return False


def _load_pbp_period(game_id: str, period: int) -> List[dict]:
    path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{period}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _parse_margin(raw: str) -> Optional[int]:
    if not raw:
        return None
    try:
        return abs(int(raw))
    except (ValueError, TypeError):
        return None


def _garbage_seconds_from_pbp(game_id: str) -> float:
    """Scan Q3+Q4 PBP; return garbage seconds remaining in Q4 (0–720)."""
    # Q3: if blowout hit in Q3, entire Q4 is garbage
    for ev in _load_pbp_period(game_id, 3):
        m = _parse_margin(ev.get("score_margin", ""))
        if m is not None and m >= _GT_Q3_MARGIN:
            return float(_Q4_TOTAL_SEC)
    # Q4: find first event where margin crossed threshold
    for ev in _load_pbp_period(game_id, 4):
        m = _parse_margin(ev.get("score_margin", ""))
        if m is not None and m >= _GT_Q4_MARGIN:
            clock = int(ev.get("game_clock_sec", 0))
            return max(0.0, _Q4_TOTAL_SEC - clock)
    return 0.0


def _heuristic_garbage_seconds(final_margin: float) -> float:
    """Fallback when no PBP available — margin-based estimate of garbage Q4 seconds."""
    if final_margin >= 30:
        return 360.0
    if final_margin >= 25:
        return 240.0
    if final_margin >= 20:
        return 120.0
    return 0.0


def estimate_garbage_minutes_per_game(game_id: str) -> Dict[int, float]:
    """Return {player_id: garbage_minutes_played} for one game.

    Uses PBP when cached; falls back to final-margin heuristic.
    Only bench players (non-starter or <18 min) receive garbage credit,
    allocated proportional to their share of total bench minutes.
    """
    bs_path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if not os.path.exists(bs_path):
        return {}
    try:
        with open(bs_path) as f:
            bs = json.load(f)
    except Exception:
        return {}

    final_margin = abs(
        float(bs.get("home_score", 0) or 0) - float(bs.get("away_score", 0) or 0)
    )
    q4_pbp = _load_pbp_period(game_id, 4)
    garbage_sec = _garbage_seconds_from_pbp(game_id) if q4_pbp else _heuristic_garbage_seconds(final_margin)
    if garbage_sec <= 0:
        return {}

    garbage_min = garbage_sec / 60.0
    players = bs.get("players", [])
    bench = [p for p in players if not p.get("starter", True) or float(p.get("min", 0) or 0) < 18]
    bench_min = sum(float(p.get("min", 0) or 0) for p in bench)
    if bench_min <= 0:
        return {}

    result: Dict[int, float] = {}
    for p in bench:
        pm = float(p.get("min", 0) or 0)
        if pm <= 0:
            continue
        result[int(p["player_id"])] = round(min(pm, garbage_min * (pm / bench_min)), 2)
    return result


def _season_cache_path(season: str) -> str:
    os.makedirs(_GT_CACHE_DIR, exist_ok=True)
    return os.path.join(_GT_CACHE_DIR, f"{season}.json")


def load_season_cache(season: str) -> Dict[str, Dict[int, float]]:
    """Load {game_id: {player_id(int): garbage_min}} from disk."""
    path = _season_cache_path(season)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            raw = json.load(f)
        return {gid: {int(pid): float(m) for pid, m in pm.items()} for gid, pm in raw.items()}
    except Exception:
        return {}


def save_season_cache(season: str, data: Dict[str, Dict[int, float]]) -> None:
    """Persist {game_id: {player_id: garbage_min}} to disk (string keys for JSON)."""
    path = _season_cache_path(season)
    serialized = {gid: {str(pid): m for pid, m in pm.items()} for gid, pm in data.items()}
    with open(path, "w") as f:
        json.dump(serialized, f, indent=2)


def get_garbage_minutes(game_id: str, season: str) -> Dict[int, float]:
    """Cached lookup; computes and writes back on cache miss."""
    cache = load_season_cache(season)
    if game_id in cache:
        return cache[game_id]
    result = estimate_garbage_minutes_per_game(game_id)
    cache[game_id] = result
    save_season_cache(season, cache)
    return result


_STAT_KEYS = {"pts", "reb", "ast", "stl", "blk", "tov", "min"}


def _parse_game_date(raw: str) -> Optional[datetime]:
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _load_recent_games(player_id: int, season: str, through_date: str, n_games: int):
    """Return up to n_games game dicts strictly before through_date, newest-first."""
    gl_path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    if not os.path.exists(gl_path):
        return []
    with open(gl_path) as f:
        games: List[dict] = json.load(f)
    cutoff = _parse_game_date(through_date)
    if cutoff is None:
        return []
    eligible = [(d, g) for g in games if (d := _parse_game_date(g.get("game_date", ""))) and d < cutoff]
    eligible.sort(key=lambda x: x[0], reverse=True)
    return [g for _, g in eligible[:n_games]]


def get_clean_rolling_avg(
    player_id: int, stat: str, season: str, through_date: str, n_games: int = 10,
) -> float:
    """Rolling avg with garbage-time stat contribution removed.

    Proportional scaling: clean_val = raw_val * (clean_min / total_min).
    """
    if stat not in _STAT_KEYS:
        raise ValueError(f"Unknown stat '{stat}'. Choose from {_STAT_KEYS}")
    recent = _load_recent_games(player_id, season, through_date, n_games)
    if not recent:
        return 0.0
    cache = load_season_cache(season)
    vals: List[float] = []
    for g in recent:
        raw_val   = float(g.get(stat, 0) or 0)
        total_min = float(g.get("min", 0) or 0)
        if total_min <= 0:
            vals.append(0.0)
            continue
        gt_min = float(cache.get(str(g.get("game_id", "")), {}).get(player_id, 0))
        if gt_min <= 0 or stat == "min":
            vals.append(raw_val)
            continue
        clean_min = max(0.0, total_min - gt_min)
        vals.append(0.0 if clean_min <= 0 else round(raw_val * (clean_min / total_min), 3))
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def get_raw_rolling_avg(
    player_id: int, stat: str, season: str, through_date: str, n_games: int = 10,
) -> float:
    """Rolling average without garbage-time adjustment (baseline)."""
    recent = _load_recent_games(player_id, season, through_date, n_games)
    if not recent:
        return 0.0
    vals = [float(g.get(stat, 0) or 0) for g in recent]
    return round(sum(vals) / len(vals), 3)
