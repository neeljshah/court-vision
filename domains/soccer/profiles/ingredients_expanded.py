"""domains.soccer.profiles.ingredients_expanded -- the 07-08 expansion's 18
new team attribute compute functions (7 -> 25 total), same entity_id/
entity_name/window/raw_value/n/ingredients row shape as build_profiles.py's
original 7 (row_shape.py, imported not duplicated). Two new corpus sources:
- statsbomb possession corpus (8 attrs): source_builders.build_conceded_snapshot/
  build_possession_periods/build_shot_counts, ALL additive -- none touch the
  preregistered prereg_possession_chains.build_possessions.
- footballdata season corpus (10 attrs): source_builders.build_season_side_snapshot,
  one melted team-perspective row per (team, match, side).

BLOCKED (see attribute_registry.BLOCKED_ATTRIBUTES): lead/trail score-state
splits (own-goal attribution direction + extra-time period continuity are the
same class of silent-wrong-side bug that already got press_resistance
blocked -- not attempted) and late_goal_share (no goal-minute column exists
anywhere in the footballdata corpus).
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.profiles.row_shape import _entity_names, _rows

_SB_WINDOW = "statsbomb_2015_2021"
MIN_FORMATION_MATCHES = 10  # task-declared floor for a formation to count as a team's "top" formation


# ------------------------------------------------------------- statsbomb (8)

def _defensive_counter_threat(conceded_snap: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    agg = conceded_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"), total_n=("xg", "count"), counter_xg_sum=("counter_xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(names)
    agg["raw_value"] = agg["counter_xg_sum"] / agg["total_n"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["counter_xg_sum", "total_n"], _SB_WINDOW)


def _defensive_set_piece_threat(conceded_snap: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    agg = conceded_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"),
        set_piece_xg_sum=("set_piece_xg", "sum"), total_xg_sum=("xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(names)
    agg["raw_value"] = agg["set_piece_xg_sum"] / agg["total_xg_sum"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["set_piece_xg_sum", "total_xg_sum"], _SB_WINDOW)


def _half_xg_share(poss_snap: pd.DataFrame, half_col: str) -> pd.DataFrame:
    """poss_snap must already carry the pre-masked half_col (first_half_xg/
    second_half_xg, masked ONCE in build_profiles.build_snapshots -- same
    convention as build_possession_snapshot's counter_xg/regular_xg masking,
    so the claims validator's bare-column grammar can sum it directly)."""
    agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"), half_xg_sum=(half_col, "sum"), total_xg_sum=("xg", "sum"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["half_xg_sum"] / agg["total_xg_sum"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["half_xg_sum", "total_xg_sum"], _SB_WINDOW)


def _first_half_xg_share(poss_snap: pd.DataFrame) -> pd.DataFrame:
    return _half_xg_share(poss_snap, "first_half_xg")


def _second_half_xg_share(poss_snap: pd.DataFrame) -> pd.DataFrame:
    return _half_xg_share(poss_snap, "second_half_xg")


def _possessions_per_match(poss_snap: pd.DataFrame) -> pd.DataFrame:
    agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"), total_n=("xg", "count"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["total_n"] / agg["team_matches"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["total_n", "team_matches"], _SB_WINDOW)


def _shots_per_possession(poss_snap: pd.DataFrame, shot_counts: pd.DataFrame) -> pd.DataFrame:
    poss_agg = poss_snap.groupby("entity_id").agg(
        team_matches=("match_id", "nunique"), total_poss=("xg", "count"),
    ).reset_index()
    shots_agg = shot_counts.rename(columns={"team_id": "entity_id"}).copy()
    shots_agg["entity_id"] = shots_agg["entity_id"].astype(str)
    shots_agg = shots_agg.groupby("entity_id").agg(total_shots=("n_shots", "sum")).reset_index()
    agg = poss_agg.merge(shots_agg, on="entity_id", how="left").fillna({"total_shots": 0.0})
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["total_shots"] / agg["total_poss"]
    agg["n"] = agg["team_matches"]
    return _rows(agg, ["total_shots", "total_poss"], _SB_WINDOW)


def _formation_xg_rank(poss_snap: pd.DataFrame, form_snap: pd.DataFrame, rank: int) -> pd.DataFrame:
    """xG-per-possession restricted to the matches where a team used its
    #`rank` most-common formation (1=primary, 2=second), floored on that
    formation itself having >=MIN_FORMATION_MATCHES matches."""
    if form_snap.empty:
        return form_snap
    counts = form_snap.groupby(["entity_id", "formation"])["match_id"].nunique().reset_index(name="formation_n")
    counts["formation_rank"] = counts.groupby("entity_id")["formation_n"].rank(method="first", ascending=False)
    sel = counts[(counts["formation_rank"] == rank) & (counts["formation_n"] >= MIN_FORMATION_MATCHES)]
    if sel.empty:
        return pd.DataFrame()
    match_map = form_snap.merge(sel[["entity_id", "formation"]], on=["entity_id", "formation"], how="inner")
    match_map = match_map[["entity_id", "match_id", "formation"]].drop_duplicates()
    joined = poss_snap.merge(match_map, on=["entity_id", "match_id"], how="inner")
    agg = joined.groupby(["entity_id", "formation"]).agg(
        xg_sum=("xg", "sum"), poss_n=("xg", "count"), match_n=("match_id", "nunique"),
    ).reset_index()
    agg["entity_name"] = agg["entity_id"].map(_entity_names(poss_snap))
    agg["raw_value"] = agg["xg_sum"] / agg["poss_n"]
    agg["n"] = agg["match_n"]
    return _rows(agg, ["formation", "xg_sum", "poss_n", "match_n"], _SB_WINDOW)


def _formation_primary_xg(poss_snap: pd.DataFrame, form_snap: pd.DataFrame) -> pd.DataFrame:
    return _formation_xg_rank(poss_snap, form_snap, rank=1)


def _formation_secondary_xg(poss_snap: pd.DataFrame, form_snap: pd.DataFrame) -> pd.DataFrame:
    return _formation_xg_rank(poss_snap, form_snap, rank=2)


# ------------------------------------------------------------ footballdata (10)

def _season_rate(snap: pd.DataFrame, value_col: str, agg: str, side_filter: str | None = None) -> pd.DataFrame:
    df = snap if side_filter is None else snap[snap["is_home"] == (side_filter == "home")]
    g = df.groupby(["entity_id", "season"]).agg(
        match_n=("match_id", "count"), value=(value_col, agg),
    ).reset_index()
    g["entity_name"] = g["entity_id"]
    g["raw_value"] = g["value"]
    g["n"] = g["match_n"]
    g["window"] = "footballdata_" + g["season"].astype(str)
    return _rows(g, ["value", "match_n"], None)


def _season_ratio(snap: pd.DataFrame, num_col: str, den_col: str) -> pd.DataFrame:
    g = snap.groupby(["entity_id", "season"]).agg(
        match_n=("match_id", "count"), num_sum=(num_col, "sum"), den_sum=(den_col, "sum"),
    ).reset_index()
    g["entity_name"] = g["entity_id"]
    g["raw_value"] = g["num_sum"] / g["den_sum"]
    g["n"] = g["match_n"]
    g["window"] = "footballdata_" + g["season"].astype(str)
    return _rows(g, ["num_sum", "den_sum", "match_n"], None)


def _home_goal_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "goals_for", "mean", side_filter="home")


def _away_goal_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "goals_for", "mean", side_filter="away")


def _away_strength(snap: pd.DataFrame) -> pd.DataFrame:
    away = snap[~snap["is_home"]].copy()
    away["pts"] = 0.0
    away.loc[away["goals_for"] > away["goals_against"], "pts"] = 3.0
    away.loc[away["goals_for"] == away["goals_against"], "pts"] = 1.0
    g = away.groupby(["entity_id", "season"]).agg(match_n=("match_id", "count"), pts_sum=("pts", "sum")).reset_index()
    g["entity_name"] = g["entity_id"]
    g["raw_value"] = g["pts_sum"] / g["match_n"] / 3.0
    g["n"] = g["match_n"]
    g["window"] = "footballdata_" + g["season"].astype(str)
    return _rows(g, ["pts_sum", "match_n"], None)


def _clean_sheet_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "clean_sheet", "mean")


def _comeback_rate(snap: pd.DataFrame) -> pd.DataFrame:
    trailed = snap[snap["trailed_ht"] == 1.0]
    return _season_rate(trailed, "won_or_drew", "mean")


def _shot_conversion_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_ratio(snap, "goals_for", "shots_for")


def _shot_accuracy(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_ratio(snap, "sot_for", "shots_for")


def _discipline_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "cards_for", "mean")


def _foul_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "fouls_for", "mean")


def _corner_rate(snap: pd.DataFrame) -> pd.DataFrame:
    return _season_rate(snap, "corners_for", "mean")
