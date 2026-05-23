"""
injury_rampup.py — Return-from-injury rampup multipliers for prop prediction.

Players returning from a 7+ day absence systematically underperform season
averages in their first 1-5 games back. This module fits per-(days_out_bucket,
games_since_return) empirical ratios from historical gamelogs and exposes a
clean multiplier API.

JSON artifact written to data/models/injury_rampup.json:
    {
      "pts": {"7-13_1": {"ratio": 0.88, "n": 342}, ...},
      ...
    }

Public API
----------
    days_since_last_game(player_id, game_date)         -> int
    get_rampup_multiplier(player_id, stat, game_date)  -> float  (0.80–1.00)
    fit_rampup_curve(seasons)                          -> dict
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_RAMPUP_PATH  = os.path.join(_MODEL_DIR, "injury_rampup.json")

log = logging.getLogger(__name__)

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min")

# Days-out buckets (days_since_last_game)
_DAYS_BUCKETS = [
    ("7-13",  7,  14),
    ("14-29", 14, 30),
    ("30+",   30, 9999),
]

# Games-since-return buckets (1-indexed game number after return)
_GAME_BUCKETS = [1, 2, 3, (4, 5), (6, 999)]

_GAME_BUCKET_LABELS = ["1", "2", "3", "4-5", "6+"]


def _bucket_label(game_n: int) -> Optional[str]:
    """Return games-since-return bucket label, or None if not applicable."""
    if game_n == 1: return "1"
    if game_n == 2: return "2"
    if game_n == 3: return "3"
    if 4 <= game_n <= 5: return "4-5"
    if game_n >= 6: return "6+"
    return None


def _days_bucket_label(days: int) -> Optional[str]:
    """Return days-out bucket label for a given gap, or None if < 7."""
    for label, lo, hi in _DAYS_BUCKETS:
        if lo <= days < hi:
            return label
    return None


def _parse_min(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    if s in ("", "None", "null", "0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    # ISO format: "2023-04-06" or "2023-04-06T..."
    if len(s) >= 10 and s[4] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    # NBA API format: "Apr 06, 2023"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Season-average computation helper ─────────────────────────────────────────

def _player_season_avg(logs: List[dict], stat: str) -> float:
    """Compute a player's season average for stat from their game logs."""
    vals = []
    for g in logs:
        mins = _parse_min(g.get("min", 0))
        if mins < 5:
            continue
        try:
            v = float(g.get(stat, 0) or 0)
            if v >= 0:
                vals.append(v)
        except (TypeError, ValueError):
            continue
    return float(np.mean(vals)) if len(vals) >= 5 else 0.0


# ── Fit ────────────────────────────────────────────────────────────────────────

def fit_rampup_curve(seasons: Optional[List[str]] = None) -> Dict:
    """
    Walk all gamelog files and compute rampup ratios.

    For each (player, game) where days_since_last_game >= 7:
      - Bucket by (days_out_bucket, games_since_return)
      - Compute ratio = actual / player_season_avg

    Returns and persists the rampup curve dict.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    # buckets: stat → "days_label_game_label" → [ratio values]
    raw: Dict[str, Dict[str, List[float]]] = {s: {} for s in _STATS}

    pattern = os.path.join(_NBA_CACHE, "gamelog_full_*.json")
    files = glob.glob(pattern)
    log.info("fit_rampup_curve: scanning %d gamelog files", len(files))

    for fpath in files:
        try:
            data = json.load(open(fpath))
        except Exception:
            continue

        # Normalize to per-player lists
        if isinstance(data, dict):
            player_logs: Dict[str, List[dict]] = {}
            for k, v in data.items():
                if isinstance(v, list):
                    player_logs[k] = v
                elif isinstance(v, dict):
                    player_logs[k] = [v]
        elif isinstance(data, list):
            # Single-player file — guess player_id from filename
            pid = os.path.basename(fpath).replace("gamelog_full_", "").split("_")[0]
            player_logs = {pid: data}
        else:
            continue

        for pid_str, logs in player_logs.items():
            if len(logs) < 10:
                continue

            # Parse and sort by ISO date (handle NBA API "Apr 06, 2023" format)
            parsed: List[tuple] = []  # (date_obj, row)
            for g in logs:
                d = _parse_date(g.get("game_date", ""))
                if d:
                    parsed.append((d, g))
            if len(parsed) < 10:
                continue
            parsed.sort(key=lambda x: x[0])
            logs_sorted = [row for _, row in parsed]
            dates_sorted = [d for d, _ in parsed]

            # First pass: identify which games are in rampup windows
            # (so we can compute a "baseline" season avg excluding them)
            rampup_indices: set = set()
            last_idx = 0
            for i in range(1, len(dates_sorted)):
                gap = (dates_sorted[i] - dates_sorted[i-1]).days
                mins = _parse_min(logs_sorted[i].get("min", 0))
                if gap >= 7 and mins >= 5:
                    # Games 1..5 after the gap are in the rampup window
                    for j in range(i, min(i + 6, len(dates_sorted))):
                        # Only include while still in "return sequence" (gap<=3)
                        if j == i or (dates_sorted[j] - dates_sorted[j-1]).days <= 3:
                            rampup_indices.add(j)
                        else:
                            break

            # Season avg from non-rampup games only
            baseline_vals: Dict[str, List[float]] = {s: [] for s in _STATS}
            for i, row in enumerate(logs_sorted):
                if i in rampup_indices:
                    continue
                mins = _parse_min(row.get("min", 0))
                if mins < 5:
                    continue
                for stat in _STATS:
                    try:
                        v = float(row.get(stat, 0) or 0)
                        if v >= 0:
                            baseline_vals[stat].append(v)
                    except (TypeError, ValueError):
                        continue
            season_avgs = {
                s: float(np.mean(baseline_vals[s])) if len(baseline_vals[s]) >= 5 else 0.0
                for s in _STATS
            }

            # Second pass: collect rampup ratios
            return_seq: int = 0
            current_gap: int = 0

            for i in range(1, len(dates_sorted)):
                row = logs_sorted[i]
                mins = _parse_min(row.get("min", 0))
                gap = (dates_sorted[i] - dates_sorted[i-1]).days

                if gap >= 7:
                    return_seq = 1
                    current_gap = gap
                elif return_seq > 0 and gap <= 3:
                    return_seq += 1
                else:
                    return_seq = 0

                if return_seq > 0 and mins >= 5:
                    days_label = _days_bucket_label(current_gap)
                    game_label = _bucket_label(return_seq)
                    if days_label and game_label:
                        bucket_key = f"{days_label}_{game_label}"
                        for stat in _STATS:
                            s_avg = season_avgs[stat]
                            if s_avg <= 0:
                                continue
                            try:
                                actual = float(row.get(stat, 0) or 0)
                            except (TypeError, ValueError):
                                continue
                            ratio = actual / s_avg
                            if 0.1 <= ratio <= 3.0:
                                raw[stat].setdefault(bucket_key, []).append(ratio)

    # Aggregate
    curve: Dict[str, Dict[str, Dict]] = {}
    for stat in _STATS:
        curve[stat] = {}
        for bucket_key, vals in raw[stat].items():
            n = len(vals)
            ratio = float(np.mean(vals)) if n >= 5 else 1.0
            # Clip to reasonable range — never below 0.70, never above 1.00
            ratio = float(np.clip(ratio, 0.70, 1.00))
            curve[stat][bucket_key] = {"ratio": round(ratio, 4), "n": n}

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_RAMPUP_PATH, "w") as f:
        json.dump(curve, f, indent=2)
    log.info("Wrote injury rampup curve to %s", _RAMPUP_PATH)
    return curve


# ── Runtime API ────────────────────────────────────────────────────────────────

_rampup_cache: Optional[Dict] = None


def _load_rampup() -> Dict:
    global _rampup_cache
    if _rampup_cache is not None:
        return _rampup_cache
    if os.path.exists(_RAMPUP_PATH):
        try:
            with open(_RAMPUP_PATH) as f:
                _rampup_cache = json.load(f)
                return _rampup_cache
        except Exception:
            pass
    try:
        _rampup_cache = fit_rampup_curve()
    except Exception:
        _rampup_cache = {}
    return _rampup_cache


def days_since_last_game(player_id: int, game_date: str) -> int:
    """
    Return how many calendar days elapsed since player_id's previous game.

    Reads from gamelog_full_{player_id}_*.json files. Returns 0 if no prior
    game is found (treat as normal rest).

    Args:
        player_id: NBA player ID
        game_date: ISO date string 'YYYY-MM-DD' of the upcoming game

    Returns:
        Integer days gap. 0 = no prior game found.
    """
    target = _parse_date(game_date)
    if target is None:
        return 0

    pattern = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_*.json")
    files = glob.glob(pattern)
    if not files:
        # Try player-keyed aggregate file
        pattern2 = os.path.join(_NBA_CACHE, "gamelog_full_*.json")
        files = glob.glob(pattern2)

    best_date: Optional[date] = None
    for fpath in files:
        try:
            data = json.load(open(fpath))
        except Exception:
            continue

        rows: List[dict] = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            pid_str = str(player_id)
            if pid_str in data:
                v = data[pid_str]
                rows = v if isinstance(v, list) else [v]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        for r in v:
                            if str(r.get("player_id", "")) == pid_str:
                                rows.append(r)

        for row in rows:
            d = _parse_date(row.get("game_date", ""))
            if d and d < target:
                mins = _parse_min(row.get("min", 0))
                if mins >= 5 and (best_date is None or d > best_date):
                    best_date = d

    if best_date is None:
        return 0
    return (target - best_date).days


def get_rampup_multiplier(player_id: int, stat: str, game_date: str) -> float:
    """
    Return a performance multiplier in [0.70, 1.00] for a returning player.

    Uses days_since_last_game to determine the rampup bucket, then looks up
    the empirical ratio. Returns 1.0 if no data or gap < 7 days.

    Args:
        player_id:  NBA player ID
        stat:       Stat name (pts/reb/ast/fg3m/stl/blk/tov/min)
        game_date:  ISO date string 'YYYY-MM-DD' of the game

    Returns:
        Multiplier float in [0.70, 1.00]. 1.0 = no rampup penalty.
    """
    gap = days_since_last_game(player_id, game_date)
    if gap < 7:
        return 1.0

    days_label = _days_bucket_label(gap)
    if days_label is None:
        return 1.0

    # We don't know which game-since-return this is at prediction time,
    # so default to game 1 (most conservative — highest penalty)
    bucket_key = f"{days_label}_1"
    curve = _load_rampup()
    entry = curve.get(stat, {}).get(bucket_key, {})
    return float(entry.get("ratio", 1.0))
