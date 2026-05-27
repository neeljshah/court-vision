"""
defender_matchup_loader.py — Module-level cached loader for defender matchup parquet.

Public API
----------
    load_defender_matchup_features() -> pd.DataFrame
    get_defender_matchup_row(game_id, off_player_id) -> dict | None
"""

from __future__ import annotations

import os
import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PARQUET_PATH = os.path.join(_PROJECT_DIR, "data", "cache", "defender_matchup_features.parquet")

# Module-level cache: loaded once on first call.
_DF: Optional[pd.DataFrame] = None

# Columns to expose (excludes primary_def_def_rating which is 100% NaN).
_KEEP_COLS = [
    "game_id",
    "off_player_id",
    "matchup_fg_pct_l10",
    "matchup_partial_poss_share",
    "switches_per_poss",
    "primary_def_height_in",
    "height_advantage_in",
    "help_blocks_per_game",
    "matchup_3p_pct_l10",
]


def load_defender_matchup_features() -> pd.DataFrame:
    """Return the defender matchup parquet as a DataFrame (cached after first load).

    Returns an empty DataFrame with correct columns if the parquet is missing.
    """
    global _DF
    if _DF is not None:
        return _DF

    if not os.path.exists(_PARQUET_PATH):
        log.warning("defender_matchup_features.parquet not found at %s", _PARQUET_PATH)
        _DF = pd.DataFrame(columns=_KEEP_COLS)
        return _DF

    try:
        raw = pd.read_parquet(_PARQUET_PATH)
        # Keep only known columns that are present.
        cols = [c for c in _KEEP_COLS if c in raw.columns]
        _DF = raw[cols].copy()
        # Normalise game_id to str for consistent key matching.
        _DF["game_id"] = _DF["game_id"].astype(str)
        _DF["off_player_id"] = _DF["off_player_id"].astype(str)
        log.debug("Loaded defender_matchup_features: %d rows", len(_DF))
    except Exception as exc:
        log.warning("Failed to load defender_matchup_features: %s", exc)
        _DF = pd.DataFrame(columns=_KEEP_COLS)

    return _DF


def get_defender_matchup_row(game_id: str, off_player_id: int) -> Optional[dict]:
    """Return the defender matchup feature row for (game_id, off_player_id), or None.

    Args:
        game_id:       NBA game ID string.
        off_player_id: Offensive player's NBA ID integer.

    Returns:
        Dict of feature columns (excluding primary_def_def_rating) or None if not found.
    """
    df = load_defender_matchup_features()
    if df.empty:
        return None

    mask = (df["game_id"] == str(game_id)) & (df["off_player_id"] == str(off_player_id))
    matches = df[mask]
    if matches.empty:
        return None

    row = matches.iloc[0]
    return row.to_dict()
