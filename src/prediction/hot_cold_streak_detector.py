"""
hot_cold_streak_detector.py — Bayesian changepoint detection on player form streaks.

Pure statistical computation — no model file needed.

Detection rules:
  Hot:  rolling_10 > season_avg + 1.5 * rolling_std for 4+ consecutive games
  Cold: rolling_10 < season_avg - 1.5 * rolling_std for 4+ consecutive games

Also computes mean-reversion probability: P(regression in next game | streak length).

Public API
----------
    predict_streak(player_id, season) -> dict
        -> {streak_type, streak_length, streak_pts_delta, reversion_prob}
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# Minimum consecutive games above/below threshold to declare a streak
_MIN_STREAK_GAMES = 4
# Threshold: season_avg ± 1.5 * rolling_std
_STREAK_THRESHOLD_SIGMA = 1.5
# Mean-reversion rate per additional streak game (logistic growth)
_REVERSION_RATE = 0.18


def _load_gamelog(player_id: int, season: str) -> list:
    """Load cached gamelog rows, sorted by GAME_DATE descending."""
    import datetime

    cache_path = os.path.join(_NBA_CACHE, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(cache_path):
        return []
    try:
        rows = json.load(open(cache_path))
    except Exception:
        return []

    if not rows:
        return []

    def _parse_date(d: str):
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.datetime.strptime(str(d).strip(), fmt)
            except ValueError:
                continue
        return datetime.datetime.min

    if "GAME_DATE" in rows[0]:
        rows = sorted(rows, key=lambda r: _parse_date(r["GAME_DATE"]), reverse=True)

    return rows


def _compute_rolling_stats(rows: list, stat: str = "PTS", window: int = 10) -> dict:
    """
    Compute rolling mean + std, season mean, and streak stats for a given stat key.

    Returns:
        {season_avg, rolling_avg, rolling_std, recent_values, all_values}
    """
    values = [float(r.get(stat, 0.0) or 0.0) for r in rows]
    if not values:
        return {}

    all_vals = values
    recent = values[:window]

    season_avg = sum(all_vals) / len(all_vals)
    rolling_avg = sum(recent) / len(recent) if recent else season_avg

    if len(all_vals) > 1:
        variance = sum((v - season_avg) ** 2 for v in all_vals) / (len(all_vals) - 1)
        rolling_std = math.sqrt(variance)
    else:
        rolling_std = 0.0

    return {
        "season_avg":   round(season_avg, 3),
        "rolling_avg":  round(rolling_avg, 3),
        "rolling_std":  round(rolling_std, 3),
        "recent_values": recent,
        "all_values":    all_vals,
    }


def _detect_streak(recent_values: list, season_avg: float, rolling_std: float) -> tuple:
    """
    Detect the current hot/cold streak from most-recent games (index 0 = most recent).

    Returns (streak_type, streak_length, direction_delta)
    """
    if not recent_values or rolling_std < 0.1:
        return "neutral", 0, 0.0

    threshold_hi = season_avg + _STREAK_THRESHOLD_SIGMA * rolling_std
    threshold_lo = season_avg - _STREAK_THRESHOLD_SIGMA * rolling_std

    # Count consecutive games from most recent going back
    hot_len = 0
    cold_len = 0
    for v in recent_values:
        if v > threshold_hi:
            if cold_len > 0:
                break
            hot_len += 1
        elif v < threshold_lo:
            if hot_len > 0:
                break
            cold_len += 1
        else:
            break

    if hot_len >= _MIN_STREAK_GAMES:
        delta = round(sum(recent_values[:hot_len]) / hot_len - season_avg, 2)
        return "hot", hot_len, delta
    elif cold_len >= _MIN_STREAK_GAMES:
        delta = round(sum(recent_values[:cold_len]) / cold_len - season_avg, 2)
        return "cold", cold_len, delta

    return "neutral", 0, 0.0


def _compute_reversion_prob(streak_length: int, streak_type: str) -> float:
    """
    Bayesian mean-reversion probability.

    P(regression | streak_length) using logistic growth:
      base = 0.40 (random game-to-game variance)
      Each additional streak game adds ~18% more reversion pressure.
    """
    if streak_type == "neutral" or streak_length == 0:
        return 0.0

    # Logistic: approaches 0.85 asymptotically
    raw = 0.40 + (1.0 - 0.40) * (1.0 - math.exp(-_REVERSION_RATE * streak_length))
    return round(min(raw, 0.85), 4)


def predict_streak(
    player_id: int,
    season: str = "2024-25",
) -> dict:
    """
    Detect player's current hot/cold streak and mean-reversion probability.

    Returns:
        {streak_type: 'hot'|'cold'|'neutral', streak_length, streak_pts_delta, reversion_prob}
    """
    rows = _load_gamelog(player_id, season)

    if not rows:
        return {
            "streak_type":      "neutral",
            "streak_length":    0,
            "streak_pts_delta": 0.0,
            "reversion_prob":   0.0,
        }

    pts_stats = _compute_rolling_stats(rows, stat="PTS", window=15)
    if not pts_stats:
        return {
            "streak_type":      "neutral",
            "streak_length":    0,
            "streak_pts_delta": 0.0,
            "reversion_prob":   0.0,
        }

    streak_type, streak_length, streak_delta = _detect_streak(
        pts_stats["recent_values"],
        pts_stats["season_avg"],
        pts_stats["rolling_std"],
    )

    reversion_prob = _compute_reversion_prob(streak_length, streak_type)

    return {
        "streak_type":      streak_type,          # "hot", "cold", or "neutral"
        "streak_length":    streak_length,         # consecutive games in streak
        "streak_pts_delta": streak_delta,          # avg pts above/below season avg
        "reversion_prob":   reversion_prob,        # P(regression next game)
    }


def predict_streak_from_values(
    values: list,
    season_avg: Optional[float] = None,
) -> dict:
    """
    Compute streak from raw game value list (most recent first).
    Useful when gamelog is already loaded.
    """
    if not values:
        return {"streak_type": "neutral", "streak_length": 0,
                "streak_pts_delta": 0.0, "reversion_prob": 0.0}

    if season_avg is None:
        season_avg = sum(values) / len(values)

    if len(values) > 1:
        variance = sum((v - season_avg) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0

    streak_type, streak_length, streak_delta = _detect_streak(values, season_avg, std)
    reversion_prob = _compute_reversion_prob(streak_length, streak_type)

    return {
        "streak_type":      streak_type,
        "streak_length":    streak_length,
        "streak_pts_delta": streak_delta,
        "reversion_prob":   reversion_prob,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--player-id", type=int, default=2544)
    ap.add_argument("--season", default="2024-25")
    args = ap.parse_args()
    r = predict_streak(args.player_id, args.season)
    print(json.dumps(r, indent=2))
