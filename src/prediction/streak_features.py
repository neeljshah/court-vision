"""src/prediction/streak_features.py -- R10_M16 hot-hand / streak features.

Shared between TRAINING (scripts/train_residual_heads_endq3_streak.py) and
INFERENCE (src/prediction/residual_heads.apply_residual_correction).

Per-stat ship gate (probe scripts/probe_R10_M16_streak.py):
  FG3M, STL, BLK, TOV  -> SHIP (4/4 WF folds positive)
  PTS, REB, AST        -> REJECT (do NOT add streak inputs for these)

Public API
----------
SHIP_STREAK_STATS               -- frozenset of stats that ship streak features.
STREAK_FEATURE_NAMES_PER_STAT   -- {stat -> [feature_name, ...]}
load_player_histories(cache)    -- {pid -> [(date, {stat: val}), ...]}, cached.
compute_streak_features_for_stat(history, target_date, stat) -> dict
streak_vector_for_stat(history, target_date, stat) -> list[float]
coerce_target_date(value)       -- snap['game_date'] -> datetime (or None)
"""
from __future__ import annotations

import json
import os
from datetime import date as _date
from datetime import datetime
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE_DEFAULT = os.path.join(PROJECT_DIR, "data", "nba")

# Stats for which the probe shipped streak features (4/4 WF folds positive).
SHIP_STREAK_STATS: FrozenSet[str] = frozenset({"fg3m", "stl", "blk", "tov"})

# Each shipping stat receives 4 streak features:
#   hot_streak_<stat>, cold_streak_<stat>, consec_above_<stat>, n_prior_<stat>.
_FEAT_PREFIXES: Tuple[str, ...] = ("hot_streak", "cold_streak", "consec_above", "n_prior")
STREAK_FEATURE_NAMES_PER_STAT: Dict[str, List[str]] = {
    stat: [f"{prefix}_{stat}" for prefix in _FEAT_PREFIXES]
    for stat in SHIP_STREAK_STATS
}

_EPS = 1e-6
_L3 = 3
_L20 = 20

# Module-level cached histories (loaded once per process).
_HIST_CACHE: Optional[Dict[int, List[Tuple[datetime, Dict[str, float]]]]] = None


def _parse_date(raw) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except (TypeError, ValueError):
        pass
    # ISO yyyy-mm-dd fallback for live snap.get('game_date') values.
    try:
        return datetime.strptime(str(raw).strip()[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def load_player_histories(
    nba_cache: str = _NBA_CACHE_DEFAULT,
    use_cache: bool = True,
) -> Dict[int, List[Tuple[datetime, Dict[str, float]]]]:
    """Load all gamelog_<pid>_<season>.json files.

    Returns {pid -> [(date, {pts, reb, ast, fg3m, stl, blk, tov, min}), ...]}
    sorted oldest -> newest, deduplicated by date.

    The module caches the result on first call; pass use_cache=False to
    force a reload (only useful for tests).
    """
    global _HIST_CACHE
    if use_cache and _HIST_CACHE is not None:
        return _HIST_CACHE

    histories: Dict[int, List[Tuple[datetime, Dict[str, float]]]] = {}
    if not os.path.isdir(nba_cache):
        if use_cache:
            _HIST_CACHE = histories
        return histories

    for fname in os.listdir(nba_cache):
        if not fname.startswith("gamelog_") or not fname.endswith(".json"):
            continue
        parts = fname[len("gamelog_"):-len(".json")].rsplit("_", 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        fpath = os.path.join(nba_cache, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                games = json.load(fh)
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            d = _parse_date(g.get("GAME_DATE") or "")
            if d is None:
                continue
            try:
                row = {
                    "pts":  float(g.get("PTS")  or 0),
                    "reb":  float(g.get("REB")  or 0),
                    "ast":  float(g.get("AST")  or 0),
                    "fg3m": float(g.get("FG3M") or 0),
                    "stl":  float(g.get("STL")  or 0),
                    "blk":  float(g.get("BLK")  or 0),
                    "tov":  float(g.get("TOV")  or 0),
                    "min":  float(g.get("MIN")  or 0),
                }
            except (TypeError, ValueError):
                continue
            if row["min"] < 1.0:
                continue  # DNP
            histories.setdefault(pid, []).append((d, row))

    # Sort + dedup by date per player.
    for pid in list(histories.keys()):
        seen: Dict[datetime, Dict[str, float]] = {}
        for d, row in histories[pid]:
            seen[d] = row  # later entry wins on same-date collisions
        histories[pid] = sorted(seen.items())

    if use_cache:
        _HIST_CACHE = histories
    return histories


def reset_cache() -> None:
    """Forget the cached gamelog histories. Test-only."""
    global _HIST_CACHE
    _HIST_CACHE = None


def set_cache(histories: Dict[int, List[Tuple[datetime, Dict[str, float]]]]) -> None:
    """Inject an explicit history map. Test-only."""
    global _HIST_CACHE
    _HIST_CACHE = histories


def compute_streak_features_for_stat(
    history: Sequence[Tuple[datetime, Dict[str, float]]],
    target_date: datetime,
    stat: str,
) -> Dict[str, float]:
    """Compute the 4 streak features for `stat` from games strictly before `target_date`.

    Mirrors probe_R10_M16_streak.compute_streak_features (same z-score trend,
    same L3/L20 windows, same consec-above-mean definition).
    """
    stat_lc = stat.lower()
    if stat_lc not in SHIP_STREAK_STATS:
        return {}

    # Strict shift(1) -- games dated strictly before target_date.
    prior = [(d, row) for d, row in history if d < target_date]
    vals = [row[stat_lc] for _, row in prior]

    l3 = vals[-_L3:] if len(vals) >= _L3 else vals
    l20 = vals[-_L20:] if len(vals) >= _L20 else vals

    mean_l3 = sum(l3) / len(l3) if l3 else 0.0
    if l20:
        mean_l20 = sum(l20) / len(l20)
        # Population std (matches numpy default in the probe).
        if len(l20) > 1:
            mu = mean_l20
            var = sum((v - mu) ** 2 for v in l20) / len(l20)
            std_l20 = var ** 0.5
        else:
            std_l20 = 0.0
    else:
        mean_l20 = 0.0
        std_l20 = 0.0

    z = (mean_l3 - mean_l20) / (std_l20 + _EPS)

    consec = 0
    for _, row in reversed(prior):
        if row[stat_lc] > mean_l20:
            consec += 1
        else:
            break

    return {
        f"hot_streak_{stat_lc}":   float(z),
        f"cold_streak_{stat_lc}":  float(-z),
        f"consec_above_{stat_lc}": float(consec),
        f"n_prior_{stat_lc}":      float(len(prior)),
    }


def streak_vector_for_stat(
    history: Sequence[Tuple[datetime, Dict[str, float]]],
    target_date: datetime,
    stat: str,
) -> List[float]:
    """Same as compute_streak_features_for_stat but returns an ordered list."""
    if stat.lower() not in SHIP_STREAK_STATS:
        return []
    feats = compute_streak_features_for_stat(history, target_date, stat)
    return [feats[name] for name in STREAK_FEATURE_NAMES_PER_STAT[stat.lower()]]


def coerce_target_date(value) -> Optional[datetime]:
    """Convert snap['game_date'] (str / datetime / date / None) to datetime.

    Accepts ISO 'YYYY-MM-DD' and 'Mon DD, YYYY'. Returns None on failure.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, _date):
        return datetime(value.year, value.month, value.day)
    return _parse_date(value)
