"""
position_priors.py — Per-position Bayesian priors for prop prediction.

Replaces the global _STAT_DEFAULTS flat prior in player_props.py with
position-aware priors (G/F/C/GF/FC). This directly improves BLK/STL which
suffer low R² because a global prior conflates guards (~0.5 BLK) with
centers (~1.5 BLK).

JSON artifact written to data/models/position_priors.json:
    {"pts": {"G": {"mean": 14.2, "std": 8.1, "K": 15, "n": 12450}, ...}, ...}

Public API
----------
    get_position(player_id)                              -> str
    get_position_prior(stat, position, season)           -> (mean, K)
    get_position_priors(player_ids, stat, season)        -> pd.Series
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE   = os.path.join(PROJECT_DIR, "data", "nba")
_CACHE_DIR   = os.path.join(PROJECT_DIR, "data", "cache")
_MODEL_DIR   = os.path.join(PROJECT_DIR, "data", "models")
_PRIORS_PATH = os.path.join(_MODEL_DIR, "position_priors.json")
_POS_CACHE   = os.path.join(_CACHE_DIR, "positions.json")

log = logging.getLogger(__name__)

# Stats tracked — full set props model uses
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min")

# Shrinkage K — high-volume stats need less shrinkage than tail stats
_SHRINK_K: Dict[str, int] = {
    "pts":  15, "reb":  15, "ast":  15, "min":  15,
    "fg3m": 30, "stl":  30, "blk":  30, "tov":  30,
}

# Position normalization: NBA API positions → our 5 buckets
_POS_MAP: Dict[str, str] = {
    "G": "G", "PG": "G", "SG": "G",
    "F": "F", "SF": "F", "PF": "F",
    "C": "C",
    "G-F": "GF", "F-G": "GF",
    "F-C": "FC", "C-F": "FC",
}
_ALL_POSITIONS = ("G", "F", "C", "GF", "FC")

# Sensible league-wide fallback priors (used when data is absent)
_FALLBACK: Dict[str, Dict[str, float]] = {
    "pts":  {"G": 13.5, "F": 13.0, "C": 11.0, "GF": 12.0, "FC": 11.5},
    "reb":  {"G":  3.5, "F":  5.5, "C":  7.5, "GF":  4.5, "FC":  6.5},
    "ast":  {"G":  4.0, "F":  2.5, "C":  2.0, "GF":  3.0, "FC":  2.2},
    "fg3m": {"G":  1.5, "F":  1.0, "C":  0.2, "GF":  1.1, "FC":  0.4},
    "stl":  {"G":  1.0, "F":  0.8, "C":  0.5, "GF":  0.9, "FC":  0.6},
    "blk":  {"G":  0.3, "F":  0.6, "C":  1.4, "GF":  0.4, "FC":  1.0},
    "tov":  {"G":  2.0, "F":  1.6, "C":  1.5, "GF":  1.8, "FC":  1.5},
    "min":  {"G": 24.0, "F": 23.0, "C": 22.0, "GF": 23.5, "FC": 22.5},
}

# Module-level cache
_priors_cache: Optional[Dict] = None
_position_cache: Optional[Dict[str, str]] = None  # player_id (str) → position


# ── Position lookup ────────────────────────────────────────────────────────────

def _load_position_cache() -> Dict[str, str]:
    global _position_cache
    if _position_cache is not None:
        return _position_cache
    if os.path.exists(_POS_CACHE):
        try:
            with open(_POS_CACHE) as f:
                _position_cache = json.load(f)
                return _position_cache
        except Exception:
            pass
    _position_cache = {}
    return _position_cache


def _save_position_cache(cache: Dict[str, str]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with open(_POS_CACHE, "w") as f:
        json.dump(cache, f)


def _normalize_position(raw: str) -> str:
    """Map raw NBA API position string to our 5-bucket system."""
    if not raw:
        return "F"
    r = raw.strip()
    return _POS_MAP.get(r, _POS_MAP.get(r.upper(), "F"))


def get_position(player_id: int) -> str:
    """
    Return position bucket for player_id: 'G' | 'F' | 'C' | 'GF' | 'FC'.

    Lookup order:
      1. In-memory + disk cache (data/cache/positions.json)
      2. NBA Stats API commonplayerinfo
      3. Default 'F'
    """
    cache = _load_position_cache()
    key = str(player_id)
    if key in cache:
        return cache[key]

    # Try NBA API
    if os.environ.get("NBA_OFFLINE", "0") != "1":
        try:
            from nba_api.stats.endpoints import commonplayerinfo
            time.sleep(0.5)
            info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
            df = info.get_data_frames()[0]
            if len(df) > 0:
                raw = str(df.iloc[0].get("POSITION", "F") or "F")
                pos = _normalize_position(raw)
                cache[key] = pos
                _save_position_cache(cache)
                return pos
        except Exception as e:
            log.debug("Position API failed for %s: %s", player_id, e)

    cache[key] = "F"
    _save_position_cache(cache)
    return "F"


# ── Prior computation ──────────────────────────────────────────────────────────

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


def _parse_date(s: str) -> Optional[str]:
    """Normalize any date string to 'YYYY-MM-DD', or return None."""
    if not s:
        return None
    s = str(s).strip()
    # Already ISO format
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    # NBA API format: "Apr 06, 2023"
    from datetime import datetime
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def build_position_priors(seasons: Optional[List[str]] = None) -> Dict:
    """
    Walk gamelog_full_*_{season}.json files and compute per-(position, stat)
    mean, std, K, n. Persist result to data/models/position_priors.json.

    Returns the priors dict.
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    pos_cache = _load_position_cache()

    # buckets: stat → position → list of per-game values
    buckets: Dict[str, Dict[str, List[float]]] = {
        s: {p: [] for p in _ALL_POSITIONS} for s in _STATS
    }

    pattern = os.path.join(_NBA_CACHE, "gamelog_full_*.json")
    files = glob.glob(pattern)
    log.info("Found %d gamelog files", len(files))

    for fpath in files:
        try:
            data = json.load(open(fpath))
        except Exception as e:
            log.warning("Failed to load %s: %s", fpath, e)
            continue

        # File may be a list of game-log rows OR a dict keyed by player_id
        if isinstance(data, dict):
            rows_iter = []
            for pid_str, logs in data.items():
                if isinstance(logs, list):
                    for row in logs:
                        if isinstance(row, dict):
                            row.setdefault("player_id", pid_str)
                            rows_iter.append(row)
                elif isinstance(logs, dict):
                    logs["player_id"] = pid_str
                    rows_iter.append(logs)
        elif isinstance(data, list):
            rows_iter = data
        else:
            continue

        for row in rows_iter:
            minutes = _parse_min(row.get("min", 0))
            if minutes < 5:
                continue  # skip DNP / garbage time entries

            pid_raw = row.get("player_id", 0)
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                pid = 0

            # Position: prefer cached, then row field, then default
            pid_key = str(pid)
            pos = pos_cache.get(pid_key)
            if pos is None:
                raw_pos = str(row.get("position", row.get("pos", "F")) or "F")
                pos = _normalize_position(raw_pos)
                pos_cache[pid_key] = pos

            for stat in _STATS:
                try:
                    val = float(row.get(stat, 0) or 0)
                except (TypeError, ValueError):
                    continue
                if val < 0:
                    continue
                buckets[stat][pos].append(val)

    # Persist updated position cache
    _save_position_cache(pos_cache)

    # Build priors dict
    priors: Dict[str, Dict[str, Dict]] = {}
    for stat in _STATS:
        priors[stat] = {}
        K = _SHRINK_K.get(stat, 20)
        for pos in _ALL_POSITIONS:
            vals = buckets[stat][pos]
            n = len(vals)
            if n >= 30:
                mean = float(np.mean(vals))
                std  = float(np.std(vals, ddof=1))
            else:
                mean = _FALLBACK.get(stat, {}).get(pos, 0.0)
                std  = mean * 0.6 if mean > 0 else 1.0
                log.debug("Using fallback for %s / %s (n=%d)", stat, pos, n)
            priors[stat][pos] = {
                "mean": round(mean, 3),
                "std":  round(std, 3),
                "K":    K,
                "n":    n,
            }

    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_PRIORS_PATH, "w") as f:
        json.dump(priors, f, indent=2)
    log.info("Wrote position priors to %s", _PRIORS_PATH)

    global _priors_cache
    _priors_cache = priors
    return priors


# ── Public API ─────────────────────────────────────────────────────────────────

def _load_priors() -> Dict:
    global _priors_cache
    if _priors_cache is not None:
        return _priors_cache
    if os.path.exists(_PRIORS_PATH):
        try:
            with open(_PRIORS_PATH) as f:
                _priors_cache = json.load(f)
                return _priors_cache
        except Exception:
            pass
    # Build from data if available, else return fallback structure
    try:
        return build_position_priors()
    except Exception:
        pass
    # Last resort: construct fallbacks
    _priors_cache = {
        s: {p: {"mean": _FALLBACK.get(s, {}).get(p, 1.0),
                "std":  _FALLBACK.get(s, {}).get(p, 1.0) * 0.6,
                "K":    _SHRINK_K.get(s, 20), "n": 0}
            for p in _ALL_POSITIONS}
        for s in _STATS
    }
    return _priors_cache


def get_position_prior(stat: str, position: str, season: str = "2024-25") -> Tuple[float, float]:
    """
    Return (mean, shrinkage_K) for a given stat and position bucket.

    Args:
        stat:     One of pts/reb/ast/fg3m/stl/blk/tov/min
        position: 'G' | 'F' | 'C' | 'GF' | 'FC'
        season:   Season string (currently unused — priors pooled across seasons)

    Returns:
        (mean, K) tuple — mean is the position-specific league average,
        K is the effective sample size for Bayesian shrinkage.
    """
    priors = _load_priors()
    pos = position if position in _ALL_POSITIONS else "F"
    entry = priors.get(stat, {}).get(pos, {})
    mean = float(entry.get("mean", _FALLBACK.get(stat, {}).get(pos, 1.0)))
    K    = int(entry.get("K",    _SHRINK_K.get(stat, 20)))
    return mean, K


def get_position_priors(
    player_ids: List[int],
    stat: str,
    season: str = "2024-25",
) -> pd.Series:
    """
    Return a Series of position-prior means indexed by player_id.

    Args:
        player_ids: List of NBA player IDs
        stat:       Stat column name
        season:     Season string

    Returns:
        pd.Series[int → float], index=player_id, values=position-prior mean
    """
    result = {}
    for pid in player_ids:
        pos = get_position(pid)
        mean, _ = get_position_prior(stat, pos, season)
        result[pid] = mean
    return pd.Series(result, dtype=float)
