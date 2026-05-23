"""
clean_stats.py — Convenience wrapper for garbage-time-adjusted player features.

Wraps garbage_time_filter to produce a single dict of all 7 stat rolling
averages (points, rebounds, assists, steals, blocks, turnovers, minutes) plus
per-36 rates and variance, ready for consumption by the prop retrain pipeline.

Public API
----------
    get_clean_features(player_id, season, through_date, n_games) -> dict
    get_raw_features(player_id, season, through_date, n_games)   -> dict
"""

from __future__ import annotations

import math
import os
import sys
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.features.garbage_time_filter import (
    _parse_game_date,
    get_clean_rolling_avg,
    get_raw_rolling_avg,
    load_season_cache,
)

import json
import logging

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
log = logging.getLogger(__name__)

_STATS = ["pts", "reb", "ast", "stl", "blk", "tov", "min"]


def _compute_variance(
    player_id: int,
    stat: str,
    season: str,
    through_date: str,
    n_games: int,
    clean: bool,
) -> float:
    """Variance of per-game values (garbage-adjusted if clean=True)."""
    gl_path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    if not os.path.exists(gl_path):
        return 0.0

    with open(gl_path) as f:
        games = json.load(f)

    cutoff = _parse_game_date(through_date)
    if cutoff is None:
        return 0.0

    eligible = []
    for g in games:
        gd = _parse_game_date(g.get("game_date", ""))
        if gd and gd < cutoff:
            eligible.append((gd, g))
    eligible.sort(key=lambda x: x[0], reverse=True)
    recent = [g for _, g in eligible[:n_games]]

    if len(recent) < 2:
        return 0.0

    if not clean:
        vals = [float(g.get(stat, 0) or 0) for g in recent]
    else:
        cache = load_season_cache(season)
        vals = []
        for g in recent:
            gid = str(g.get("game_id", ""))
            raw_val = float(g.get(stat, 0) or 0)
            total_min = float(g.get("min", 0) or 0)

            if total_min <= 0 or stat == "min":
                vals.append(raw_val)
                continue

            gt_map = cache.get(gid, {})
            gt_min = float(gt_map.get(player_id, 0))

            if gt_min <= 0:
                vals.append(raw_val)
                continue

            clean_min = max(0.0, total_min - gt_min)
            scale = clean_min / total_min if total_min > 0 else 1.0
            vals.append(raw_val * scale)

    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return round(variance, 4)


def _per36(stat_avg: float, min_avg: float) -> float:
    """Scale stat to per-36-minute rate."""
    if min_avg <= 0:
        return 0.0
    return round(stat_avg * 36.0 / min_avg, 3)


def get_clean_features(
    player_id: int,
    season: str,
    through_date: str,
    n_games: int = 10,
) -> dict:
    """
    Produce garbage-time-adjusted rolling features for a player.

    Returns a flat dict with keys:
      clean_{stat}_avg          — rolling average (garbage-adjusted)
      clean_{stat}_per36        — per-36 rate (garbage-adjusted)
      clean_{stat}_var          — variance over n_games (garbage-adjusted)
      clean_min_avg             — average clean minutes
      garbage_time_adjusted: True

    All 7 stats: pts, reb, ast, stl, blk, tov, min.
    """
    avgs = {
        stat: get_clean_rolling_avg(player_id, stat, season, through_date, n_games)
        for stat in _STATS
    }
    min_avg = avgs.get("min", 0.0)

    features: dict = {"garbage_time_adjusted": True, "n_games": n_games}
    for stat in _STATS:
        avg = avgs[stat]
        features[f"clean_{stat}_avg"] = avg
        if stat != "min":
            features[f"clean_{stat}_per36"] = _per36(avg, min_avg)
        features[f"clean_{stat}_var"] = _compute_variance(
            player_id, stat, season, through_date, n_games, clean=True
        )

    features["clean_min_avg"] = min_avg
    return features


def get_raw_features(
    player_id: int,
    season: str,
    through_date: str,
    n_games: int = 10,
) -> dict:
    """
    Same shape as get_clean_features but without garbage-time adjustment.
    Useful for diff-comparison in A/B testing.
    """
    avgs = {
        stat: get_raw_rolling_avg(player_id, stat, season, through_date, n_games)
        for stat in _STATS
    }
    min_avg = avgs.get("min", 0.0)

    features: dict = {"garbage_time_adjusted": False, "n_games": n_games}
    for stat in _STATS:
        avg = avgs[stat]
        features[f"raw_{stat}_avg"] = avg
        if stat != "min":
            features[f"raw_{stat}_per36"] = _per36(avg, min_avg)
        features[f"raw_{stat}_var"] = _compute_variance(
            player_id, stat, season, through_date, n_games, clean=False
        )

    features["raw_min_avg"] = min_avg
    return features


def compare_clean_vs_raw(
    player_id: int,
    season: str,
    through_date: str,
    n_games: int = 10,
) -> dict:
    """
    Return side-by-side clean vs raw averages for all stats.
    Useful for QA and reporting.

    Returns:
        {stat: {"raw": float, "clean": float, "delta": float}, ...}
    """
    result = {}
    for stat in _STATS:
        raw = get_raw_rolling_avg(player_id, stat, season, through_date, n_games)
        clean = get_clean_rolling_avg(player_id, stat, season, through_date, n_games)
        result[stat] = {
            "raw":   raw,
            "clean": clean,
            "delta": round(clean - raw, 3),
        }
    return result
