"""domains.basketball_wnba.profiles.ingredients_lineup -- one builder function
per LINEUP attribute in attribute_registry.ATTRIBUTES.

spacing reads lineup_spacing_wnba_2026.parquet directly (already one row per
lineup). matchup_net melts lineup_matchups_wnba_2026.parquet's two-sided
(team_id_a/b, lineup_key_a/b, pts_a/b) rows into one row per (team_id,
lineup_key) side before summing -- the raw parquet has no single-sided
per-lineup net column. minutes_together sums stints_wnba_2026.parquet's
elapsed_s per (team_id, lineup_key).

entity_id = "{team_id}:{lineup_key}" (composite string; a bare lineup_key is
not schema-guaranteed globally unique across teams, even if true in practice
for this corpus -- see wnba_lineup_claims.py's verified-zero-collision note).
"""
from __future__ import annotations

import pandas as pd


def _entity_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["entity_id"] = df["team_id"].astype(str) + ":" + df["lineup_key"].astype(str)
    df["entity_name"] = df["lineup_key"].astype(str)
    return df


def build_spacing(df: pd.DataFrame) -> pd.DataFrame:
    out = _entity_cols(df)
    out["raw_value"] = out["spacing_mean_dist"]
    out["n"] = out["n_shots"]
    out["ingredients"] = out.apply(lambda r: {
        "spacing_mean_dist": round(float(r.spacing_mean_dist), 4),
        "n_shots": int(r.n_shots), "team_id": int(r.team_id),
    }, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


def build_matchup_net(df: pd.DataFrame) -> pd.DataFrame:
    side_a = df.rename(columns={
        "team_id_a": "team_id", "lineup_key_a": "lineup_key", "pts_a": "pts_for", "pts_b": "pts_against",
    })[["team_id", "lineup_key", "pts_for", "pts_against", "overlap_s"]]
    side_b = df.rename(columns={
        "team_id_b": "team_id", "lineup_key_b": "lineup_key", "pts_b": "pts_for", "pts_a": "pts_against",
    })[["team_id", "lineup_key", "pts_for", "pts_against", "overlap_s"]]
    melted = pd.concat([side_a, side_b], ignore_index=True)
    g = melted.groupby(["team_id", "lineup_key"]).agg(
        pts_for=("pts_for", "sum"), pts_against=("pts_against", "sum"), overlap_s=("overlap_s", "sum"),
    ).reset_index()
    g = g[g["overlap_s"] > 0].copy()
    g["net_per48"] = (g["pts_for"] - g["pts_against"]) / (g["overlap_s"] / 60.0) * 48.0
    out = _entity_cols(g)
    out["raw_value"] = out["net_per48"]
    out["n"] = out["overlap_s"]
    out["ingredients"] = out.apply(lambda r: {
        "pts_for": round(float(r.pts_for), 2), "pts_against": round(float(r.pts_against), 2),
        "overlap_s": round(float(r.overlap_s), 1), "team_id": int(r.team_id),
    }, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


def build_minutes_together(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["team_id", "lineup_key"]).agg(
        elapsed_s=("elapsed_s", "sum"), n_games=("game_id", "nunique"),
    ).reset_index()
    g = g[g["elapsed_s"] > 0].copy()
    out = _entity_cols(g)
    out["raw_value"] = out["elapsed_s"] / 60.0
    out["n"] = out["elapsed_s"]
    out["ingredients"] = out.apply(lambda r: {
        "minutes_together": round(float(r.elapsed_s) / 60.0, 2),
        "n_games": int(r.n_games), "team_id": int(r.team_id),
    }, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "spacing": build_spacing,
    "matchup_net": build_matchup_net,
    "minutes_together": build_minutes_together,
}
