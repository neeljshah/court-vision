"""domains.mlb.knowledge._data -- shared pitch-level loader for the mechanism
validation scripts in this package. One place to point at the savant_full__*
parquets so every validate_*.py script reads the same corpus the same way.

ponytail: single-season default keeps validation runtime seconds not minutes;
pass season= to check another year or replicate a finding cross-season.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
STATCAST_DIR = REPO / "data" / "cache" / "statcast"
LEDGER_PATH = Path(__file__).resolve().parent / "validation_ledger.jsonl"

DEFAULT_SEASON = 2025


def load_season(season: int = DEFAULT_SEASON) -> pd.DataFrame:
    """One season of pitch-level Statcast rows (savant_full__<year>.parquet)."""
    path = STATCAST_DIR / ("savant_full__%d.parquet" % season)
    return pd.read_parquet(path)


def pa_final_pitch(df: pd.DataFrame) -> pd.DataFrame:
    """One row per plate appearance -- the LAST pitch of each (game_pk,
    at_bat_number), which is where Statcast populates `events` and the
    outcome-level fields (estimated_woba_using_speedangle, description of the
    ball-in-play/strikeout/walk). Sorted by pitch_number so 'last' is correct."""
    d = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    return d.groupby(["game_pk", "at_bat_number"], sort=False).tail(1)


__all__ = ["REPO", "STATCAST_DIR", "LEDGER_PATH", "DEFAULT_SEASON", "load_season", "pa_final_pitch"]
