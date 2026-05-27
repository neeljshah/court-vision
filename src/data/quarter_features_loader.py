"""src/data/quarter_features_loader.py — module-cached loader for quarter_features.parquet.

Parquet schema (11 307 rows, per game_id × player_id):
    game_id, game_date, season, player_id, player_name, team_id,
    q1_usg, q3_starter_minutes, halftime_pace_shift,
    trailing_team_q4_usg_concentration, q1_minutes, q4_minutes,
    q1_pts, q2_pts, q3_pts, q4_pts, fourth_quarter_share_pts,
    second_half_share_min
"""
from __future__ import annotations

import os
from typing import Dict, Optional

import pandas as pd

_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PARQUET_PATH = os.path.join(_PROJECT, "data", "cache", "quarter_features.parquet")

_DF_CACHE: Optional[pd.DataFrame] = None


def load_quarter_features() -> pd.DataFrame:
    """Return the full quarter_features DataFrame (module-cached after first call)."""
    global _DF_CACHE
    if _DF_CACHE is not None:
        return _DF_CACHE
    if not os.path.exists(_PARQUET_PATH):
        _DF_CACHE = pd.DataFrame()
        return _DF_CACHE
    df = pd.read_parquet(_PARQUET_PATH)
    df["game_id"] = df["game_id"].astype(str)
    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce")
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    _DF_CACHE = df
    return _DF_CACHE


def get_quarter_row(game_id: str, player_id: int) -> Optional[Dict]:
    """Return a single row dict for (game_id, player_id), or None if not found."""
    df = load_quarter_features()
    if df.empty:
        return None
    mask = (df["game_id"] == str(game_id)) & (df["player_id"] == int(player_id))
    hits = df[mask]
    if hits.empty:
        return None
    return hits.iloc[0].to_dict()


def get_team_quarter_summary(game_id: str, team_id: int) -> Dict:
    """Return team-level quarter aggregates for a game (useful for inplay models).

    Aggregates across all players on the team for the given game:
        q1_pts_total, q2_pts_total, q3_pts_total, q4_pts_total,
        first_half_pts, second_half_pts,
        avg_q1_usg, avg_halftime_pace_shift,
        avg_trailing_team_q4_usg_concentration (hhi proxy),
        n_players
    Returns an empty dict when no matching rows are found.
    """
    df = load_quarter_features()
    if df.empty:
        return {}
    mask = (df["game_id"] == str(game_id)) & (df["team_id"] == int(team_id))
    team_df = df[mask]
    if team_df.empty:
        return {}

    q1_total = float(team_df["q1_pts"].sum())
    q2_total = float(team_df["q2_pts"].sum())
    q3_total = float(team_df["q3_pts"].sum())
    q4_total = float(team_df["q4_pts"].sum())

    return {
        "game_id": str(game_id),
        "team_id": int(team_id),
        "n_players": int(len(team_df)),
        "q1_pts_total": q1_total,
        "q2_pts_total": q2_total,
        "q3_pts_total": q3_total,
        "q4_pts_total": q4_total,
        "first_half_pts": q1_total + q2_total,
        "second_half_pts": q3_total + q4_total,
        "avg_q1_usg": float(team_df["q1_usg"].mean()),
        "avg_halftime_pace_shift": float(team_df["halftime_pace_shift"].mean()),
        # HHI proxy: max across players (concentration of scoring pressure on one star)
        "avg_trailing_team_q4_usg_hhi": float(
            team_df["trailing_team_q4_usg_concentration"].mean()
        ),
    }


def reset_cache() -> None:
    """Drop the cached DataFrame (test helper)."""
    global _DF_CACHE
    _DF_CACHE = None


__all__ = [
    "load_quarter_features",
    "get_quarter_row",
    "get_team_quarter_summary",
    "reset_cache",
]
