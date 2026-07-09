"""domains.basketball_nba.knowledge._data -- shared loaders for the mechanism
validation scripts in this package. Builds the one team-game frame every
schedule/rest mechanism needs (pts, opp_pts, margin, rest days) ONCE so
validate_*.py scripts don't each re-derive it slightly differently.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
BOX_PATH = REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
PBP_FEATURES_PATH = REPO / "data" / "cache" / "pbp_possession_features.parquet"
FOUR_FACTOR_PATH = REPO / "data" / "cache" / "team_system" / "four_factor_env.parquet"
LEDGER_PATH = Path(__file__).resolve().parent / "validation_ledger.jsonl"


def load_player_boxscores() -> pd.DataFrame:
    df = pd.read_parquet(BOX_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def team_game_frame(pbox: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team): team pts (summed from the player rows),
    opp pts (the other team's sum for the SAME game_id), margin, win, date,
    season, is_home -- and `rest_days` (calendar gap since that team's own
    previous game, NaN for a team's first game on record, which is season-
    opener-safe: no prior game exists to compute a rest gap from)."""
    team_pts = pbox.groupby(["game_id", "team", "date", "season"], as_index=False).agg(
        pts=("pts", "sum"), is_home=("is_home", "first"))
    merged = team_pts.merge(
        team_pts[["game_id", "team", "pts"]].rename(columns={"team": "opp", "pts": "opp_pts"}),
        on="game_id")
    merged = merged[merged["team"] != merged["opp"]].reset_index(drop=True)
    merged["margin"] = merged["pts"] - merged["opp_pts"]
    merged["win"] = (merged["margin"] > 0).astype(int)
    merged = merged.sort_values(["team", "date"]).reset_index(drop=True)
    merged["rest_days"] = merged.groupby("team")["date"].diff().dt.days - 1
    return merged


__all__ = ["REPO", "BOX_PATH", "PBP_FEATURES_PATH", "FOUR_FACTOR_PATH", "LEDGER_PATH",
           "load_player_boxscores", "team_game_frame"]
