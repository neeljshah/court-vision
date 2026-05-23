"""
back_to_back_impact.py — Per-stat, per-age B2B multipliers for prop prediction.

The existing back_to_back_model.py computes a global B2B ratio across all
players. This module adds age-bucketed granularity: older players suffer larger
B2B penalties, especially on rebounds and FG% (fatigue-driven).

JSON artifact written to data/models/b2b_curve.json:
    {
      "pts": {
        "<25":   {"b2b_avg": 13.1, "reg_avg": 13.5, "ratio": 0.970, "n_b2b": 1234, "n_reg": 9800},
        "25-29": {...},
        ...
      },
      ...
    }

Public API
----------
    is_back_to_back(player_id, game_date)              -> bool
    get_b2b_multiplier(player_id, stat, age)           -> float
    fit_b2b_curve(seasons)                             -> dict
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_B2B_PATH  = os.path.join(_MODEL_DIR, "b2b_curve.json")

log = logging.getLogger(__name__)

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min", "fg_pct")

# Age buckets
_AGE_BUCKETS: List[Tuple[str, int, int]] = [
    ("<25",   0,  25),
    ("25-29", 25, 30),
    ("30-32", 30, 33),
    ("33+",   33, 99),
]
_AGE_LABELS = [b[0] for b in _AGE_BUCKETS]

# Research-backed fallback multipliers (applied when n < 30)
_FALLBACK_RATIO: Dict[str, Dict[str, float]] = {
    "pts":    {"<25": 0.975, "25-29": 0.970, "30-32": 0.962, "33+": 0.950},
    "reb":    {"<25": 0.980, "25-29": 0.975, "30-32": 0.968, "33+": 0.955},
    "ast":    {"<25": 0.978, "25-29": 0.972, "30-32": 0.965, "33+": 0.952},
    "fg3m":   {"<25": 0.972, "25-29": 0.968, "30-32": 0.960, "33+": 0.945},
    "stl":    {"<25": 0.970, "25-29": 0.965, "30-32": 0.958, "33+": 0.942},
    "blk":    {"<25": 0.975, "25-29": 0.970, "30-32": 0.963, "33+": 0.948},
    "tov":    {"<25": 1.010, "25-29": 1.015, "30-32": 1.022, "33+": 1.030},
    "min":    {"<25": 0.985, "25-29": 0.980, "30-32": 0.975, "33+": 0.965},
    "fg_pct": {"<25": 0.976, "25-29": 0.971, "30-32": 0.963, "33+": 0.950},
}


def _age_bucket(age: int) -> str:
    for label, lo, hi in _AGE_BUCKETS:
        if lo <= age < hi:
            return label
    return "33+"


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


# ── Fit ────────────────────────────────────────────────────────────────────────

def fit_b2b_curve(seasons: Optional[List[str]] = None) -> Dict:
    """
    Walk gamelog files and compute per-(stat, age_bucket) B2B vs non-B2B ratios.

    Methodology:
      - For each player-game pair where gap from previous game == 1 day → B2B
      - Compute player season_avg for that stat (from all games)
      - Ratio = actual_b2b / player_season_avg
      - Group by age bucket (from gamelog 'age' field if present, else 27)

    Returns and persists the B2B curve dict.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    # stat → age_label → {"b2b": [values], "reg": [values]}
    buckets: Dict[str, Dict[str, Dict[str, List[float]]]] = {
        s: {a: {"b2b": [], "reg": []} for a in _AGE_LABELS} for s in _STATS
    }

    pattern = os.path.join(_NBA_CACHE, "gamelog_full_*.json")
    files = glob.glob(pattern)
    log.info("fit_b2b_curve: scanning %d gamelog files", len(files))

    for fpath in files:
        try:
            data = json.load(open(fpath))
        except Exception:
            continue

        if isinstance(data, dict):
            player_logs: Dict[str, List[dict]] = {}
            for k, v in data.items():
                if isinstance(v, list):
                    player_logs[k] = v
                elif isinstance(v, dict):
                    player_logs[k] = [v]
        elif isinstance(data, list):
            pid = os.path.basename(fpath).replace("gamelog_full_", "").split("_")[0]
            player_logs = {pid: data}
        else:
            continue

        for pid_str, logs in player_logs.items():
            if len(logs) < 5:
                continue

            # Parse and sort by ISO date (handle NBA API "Apr 06, 2023" format)
            parsed: List[tuple] = []
            for g in logs:
                d = _parse_date(g.get("game_date", ""))
                if d:
                    parsed.append((d, g))
            if len(parsed) < 5:
                continue
            parsed.sort(key=lambda x: x[0])

            for i in range(1, len(parsed)):
                curr_d, row = parsed[i]
                prev_d, _   = parsed[i - 1]
                mins = _parse_min(row.get("min", 0))
                if mins < 5:
                    continue

                gap = (curr_d - prev_d).days
                is_b2b = (gap == 1)

                try:
                    age = int(float(row.get("age", 27) or 27))
                except (TypeError, ValueError):
                    age = 27
                age_label = _age_bucket(age)

                slot = "b2b" if is_b2b else "reg"
                for stat in _STATS:
                    try:
                        val = float(row.get(stat, 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    if val < 0:
                        continue
                    buckets[stat][age_label][slot].append(val)

    # Aggregate — ratio = b2b_avg / reg_avg per (stat, age)
    curve: Dict[str, Dict[str, Dict]] = {}
    for stat in _STATS:
        curve[stat] = {}
        for age_label in _AGE_LABELS:
            b2b_vals = buckets[stat][age_label]["b2b"]
            reg_vals  = buckets[stat][age_label]["reg"]
            n_b2b = len(b2b_vals)
            n_reg  = len(reg_vals)

            if n_b2b >= 30 and n_reg >= 30:
                b2b_avg = float(np.mean(b2b_vals))
                reg_avg  = float(np.mean(reg_vals))
                denom = max(reg_avg, 0.01)
                ratio = b2b_avg / denom
                # Clip to [0.88, 1.05] — anything outside is noise
                ratio = float(np.clip(ratio, 0.88, 1.05))
            else:
                b2b_avg = 0.0
                reg_avg  = 0.0
                ratio = _FALLBACK_RATIO.get(stat, {}).get(age_label, 0.97)
                log.debug("B2B fallback for %s/%s (n=%d/%d)", stat, age_label, n_b2b, n_reg)

            curve[stat][age_label] = {
                "b2b_avg": round(b2b_avg, 3),
                "reg_avg":  round(reg_avg, 3),
                "ratio":    round(ratio, 4),
                "n_b2b":   n_b2b,
                "n_reg":   n_reg,
            }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_B2B_PATH, "w") as f:
        json.dump(curve, f, indent=2)
    log.info("Wrote B2B curve to %s", _B2B_PATH)
    return curve


# ── Runtime API ────────────────────────────────────────────────────────────────

_b2b_cache: Optional[Dict] = None


def _load_b2b() -> Dict:
    global _b2b_cache
    if _b2b_cache is not None:
        return _b2b_cache
    if os.path.exists(_B2B_PATH):
        try:
            with open(_B2B_PATH) as f:
                _b2b_cache = json.load(f)
                return _b2b_cache
        except Exception:
            pass
    try:
        _b2b_cache = fit_b2b_curve()
    except Exception:
        _b2b_cache = {}
    return _b2b_cache


def is_back_to_back(player_id: int, game_date: str) -> bool:
    """
    Return True if the player played a game yesterday (gap == 1 day).

    Reads from gamelog_full_{player_id}_*.json files.

    Args:
        player_id: NBA player ID
        game_date: ISO date string 'YYYY-MM-DD' of upcoming game

    Returns:
        bool — True if B2B situation.
    """
    target = _parse_date(game_date)
    if target is None:
        return False

    from datetime import timedelta
    yesterday = target - timedelta(days=1)

    pattern1 = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_*.json")
    files = glob.glob(pattern1)
    if not files:
        files = glob.glob(os.path.join(_NBA_CACHE, "gamelog_full_*.json"))

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
            if d == yesterday and _parse_min(row.get("min", 0)) >= 5:
                return True

    return False


def get_b2b_multiplier(player_id: int, stat: str, age: int) -> float:
    """
    Return performance multiplier for a B2B game.

    Args:
        player_id: NBA player ID (used to check if B2B actually occurred)
        stat:      Stat name (pts/reb/ast/fg3m/stl/blk/tov/min/fg_pct)
        age:       Player age in years

    Returns:
        float multiplier in [0.88, 1.05]. 1.0 = no change.
        Note: caller is responsible for checking is_back_to_back first.
    """
    curve = _load_b2b()
    age_label = _age_bucket(age)
    entry = curve.get(stat, {}).get(age_label, {})
    if entry:
        return float(entry.get("ratio", _FALLBACK_RATIO.get(stat, {}).get(age_label, 0.97)))
    return _FALLBACK_RATIO.get(stat, {}).get(age_label, 0.97)
