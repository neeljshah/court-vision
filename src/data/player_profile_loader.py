"""
player_profile_loader.py — Module-cached loader for player_profile_features.parquet.

Public API
----------
    load_player_profiles() -> pd.DataFrame
    get_player_profile(player_id, as_of_date=None) -> dict | None
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, date
from typing import Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PARQUET_PATH = os.path.join(PROJECT_DIR, "data", "cache", "player_profile_features.parquet")

log = logging.getLogger(__name__)

# Module-level caches
_DF_CACHE: Optional[pd.DataFrame] = None
_DICT_CACHE: Optional[dict[int, dict]] = None


def load_player_profiles() -> pd.DataFrame:
    """Return the full profiles DataFrame, loading once and caching in memory."""
    global _DF_CACHE
    if _DF_CACHE is not None:
        return _DF_CACHE
    try:
        _DF_CACHE = pd.read_parquet(_PARQUET_PATH)
        log.debug("player_profile_loader: loaded %d rows from %s", len(_DF_CACHE), _PARQUET_PATH)
    except Exception as exc:
        log.warning("player_profile_loader: could not load parquet: %s", exc)
        _DF_CACHE = pd.DataFrame()
    return _DF_CACHE


def _profiles_dict() -> dict[int, dict]:
    """Return dict-of-dicts indexed by player_id for O(1) lookup."""
    global _DICT_CACHE
    if _DICT_CACHE is not None:
        return _DICT_CACHE
    df = load_player_profiles()
    if df.empty:
        _DICT_CACHE = {}
        return _DICT_CACHE
    _DICT_CACHE = {int(row["player_id"]): row.to_dict() for _, row in df.iterrows()}
    return _DICT_CACHE


def _parse_date(d: str | date | datetime | None) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _recompute_as_of(profile: dict, as_of: date) -> dict:
    """
    Recompute age_precise_days, years_in_league, rookie_flag relative to as_of.
    Returns a shallow copy with updated values; originals untouched.
    """
    out = dict(profile)

    birthdate = _parse_date(profile.get("birthdate"))
    if birthdate is not None:
        delta = as_of - birthdate
        out["age_precise_days_as_of"] = max(delta.days, 0)
    else:
        out["age_precise_days_as_of"] = None

    from_year = profile.get("from_year")
    if from_year is not None:
        try:
            # from_year is the first season year (e.g. 2005 means 2005-06 season)
            first_season_start = date(int(from_year), 10, 1)
            years_in = (as_of - first_season_start).days / 365.25
            out["years_in_league_as_of"] = max(int(years_in), 0)
            out["rookie_flag_as_of"] = int(int(years_in) < 1)
        except Exception:
            pass

    out["profile_as_of"] = as_of.isoformat()
    return out


def get_player_profile(
    player_id: int,
    as_of_date: Optional[str | date | datetime] = None,
) -> Optional[dict]:
    """
    Return profile dict for player_id, or None if not found.

    When as_of_date is given, recompute age_precise_days_as_of,
    years_in_league_as_of, and rookie_flag_as_of relative to that date.
    """
    profiles = _profiles_dict()
    profile = profiles.get(int(player_id))
    if profile is None:
        return None

    if as_of_date is None:
        return dict(profile)

    as_of = _parse_date(as_of_date)
    if as_of is None:
        return dict(profile)

    return _recompute_as_of(profile, as_of)
