"""domains.soccer.profiles.snapshots_expanded -- assembles the 07-08
expansion's snapshot frames from the same possessions/poss_snap/form_snap
build_profiles.build_snapshots() already computes for the original 7
attributes (nothing re-scanned that isn't new). Split out of build_profiles.py
for the <=300 LOC/file rail.
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.profiles.source_builders import (
    build_conceded_snapshot,
    build_possession_periods,
    build_season_side_snapshot,
    build_shot_counts,
)


def build_expanded_snapshots(
    match_teams: pd.DataFrame, possessions: pd.DataFrame, poss_snap: pd.DataFrame, form_snap: pd.DataFrame,
) -> dict[str, object]:
    conceded_snap = build_conceded_snapshot(possessions, match_teams)
    period_map = build_possession_periods()
    poss_snap_period = poss_snap.copy()
    poss_snap_period["possession"] = possessions["possession"].values
    poss_snap_period = poss_snap_period.merge(period_map, on=["match_id", "possession"], how="left")
    # pre-masked once here (not in the claim formula) -- same convention as
    # build_possession_snapshot's counter_xg/regular_xg/set_piece_xg masking.
    poss_snap_period["first_half_xg"] = poss_snap_period["xg"].where(poss_snap_period["period"] == 1, 0.0)
    poss_snap_period["second_half_xg"] = poss_snap_period["xg"].where(poss_snap_period["period"] >= 2, 0.0)
    shot_counts = build_shot_counts()
    season_side_snap = build_season_side_snapshot()

    return {
        "defensive_counter_threat": conceded_snap, "defensive_set_piece_threat": conceded_snap,
        "first_half_xg_share": poss_snap_period, "second_half_xg_share": poss_snap_period,
        "possessions_per_match": poss_snap, "shots_per_possession": (poss_snap, shot_counts),
        "formation_primary_xg": (poss_snap, form_snap), "formation_secondary_xg": (poss_snap, form_snap),
        "home_goal_rate": season_side_snap, "away_goal_rate": season_side_snap,
        "away_strength": season_side_snap, "clean_sheet_rate": season_side_snap,
        "comeback_rate": season_side_snap, "shot_conversion_rate": season_side_snap,
        "shot_accuracy": season_side_snap, "discipline_rate": season_side_snap,
        "foul_rate": season_side_snap, "corner_rate": season_side_snap,
    }


EXPANDED_SOURCES_SB = [
    "defensive_counter_threat", "defensive_set_piece_threat", "first_half_xg_share", "second_half_xg_share",
    "possessions_per_match", "shots_per_possession", "formation_primary_xg", "formation_secondary_xg",
]
EXPANDED_SOURCES_SEASON = [
    "home_goal_rate", "away_goal_rate", "away_strength", "clean_sheet_rate", "comeback_rate",
    "shot_conversion_rate", "shot_accuracy", "discipline_rate", "foul_rate", "corner_rate",
]
