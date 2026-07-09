"""domains.basketball_wnba.profiles.ingredients_player -- one builder function
per PLAYER attribute in attribute_registry.ATTRIBUTES. Each takes the raw
source frame build_profiles.py loaded for that attribute and returns a tidy
frame: entity_id, entity_name, raw_value, n (the registry-floor denominator),
ingredients (dict, json.dumps'd by build_profiles.py).

on_court_impact/gravity read on_off_wnba_2026.parquet directly (NOT the
already-floor-filtered gravity_proxy_wnba_2026.parquet) so the registry's own
floor re-application stays honest -- same precedent as
scripts/platformkit/intel_validation/wnba_lineup_claims.py's gravity claim.

scoring_per36/reb_per36/ast_per36/efg/usage_proxy_per36/recent_form reuse
domains.basketball_wnba.claims_player_form's _window_slice/_compute_table --
zero reimplementation of the per-36 rate math (task-directed reuse).
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_wnba.claims_player_form import _compute_table, _window_slice

MIN_ON_FLOOR = 300.0  # on/off-derived pre-filter, task-declared


def build_on_court_impact(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["entity_id"] = out["player_id"].astype(str)
    out["entity_name"] = out["player_name"]
    out["raw_value"] = out["net_rating_on_per48"]
    out["n"] = out["min_on"]
    out["ingredients"] = out.apply(lambda r: {
        "net_rating_on_per48": round(float(r.net_rating_on_per48), 4),
        "net_rating_off_per48": round(float(r.net_rating_off_per48), 4),
        "min_on": round(float(r.min_on), 2), "min_off": round(float(r.min_off), 2),
        "team_id": int(r.team_id),
    }, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


def build_gravity(df: pd.DataFrame) -> pd.DataFrame:
    pre = df[df["min_on"] >= MIN_ON_FLOOR].copy()
    pre["entity_id"] = pre["player_id"].astype(str)
    pre["entity_name"] = pre["player_name"]
    pre["raw_value"] = pre["teammate_efg_on"] - pre["teammate_efg_off"]
    pre["n"] = pre[["teammate_fga_on", "teammate_fga_off"]].min(axis=1)
    pre["ingredients"] = pre.apply(lambda r: {
        "teammate_efg_on": round(float(r.teammate_efg_on), 4),
        "teammate_efg_off": round(float(r.teammate_efg_off), 4),
        "teammate_fga_on": int(r.teammate_fga_on), "teammate_fga_off": int(r.teammate_fga_off),
        "min_on": round(float(r.min_on), 2), "team_id": int(r.team_id),
    }, axis=1)
    return pre[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


def _box_metric_builder(metric: str):
    """Factory: one builder per plain box-derived rate metric, full-season
    window, via claims_player_form's own recompute table (no reimplementation)."""
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        sliced = _window_slice(df, "full")
        table = _compute_table(sliced, metric)
        names = df.drop_duplicates("player_id", keep="last").set_index("player_id")["player_name"]
        table["entity_id"] = table["player_id"].astype(str)
        table["entity_name"] = table["player_id"].map(lambda pid: names.get(pid, str(pid)))
        table["raw_value"] = table["value"]
        table["n"] = table["games"]
        table["ingredients"] = table.apply(lambda r: {
            metric: round(float(r.value), 4), "games": int(r.games), "window": "full"}, axis=1)
        return table[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


build_scoring_per36 = _box_metric_builder("pts_per36")
build_reb_per36 = _box_metric_builder("reb_per36")
build_ast_per36 = _box_metric_builder("ast_per36")
build_efg = _box_metric_builder("efg_pct")
build_usage_proxy_per36 = _box_metric_builder("usage_proxy_per36")


def build_recent_form(df: pd.DataFrame) -> pd.DataFrame:
    full = _compute_table(_window_slice(df, "full"), "pts_per36").set_index("player_id")
    last10 = _compute_table(_window_slice(df, "last_10"), "pts_per36").set_index("player_id")
    names = df.drop_duplicates("player_id", keep="last").set_index("player_id")["player_name"]
    common = last10.index.intersection(full.index)
    out = pd.DataFrame({
        "player_id": common,
        "raw_value": (last10.loc[common, "value"] - full.loc[common, "value"]).values,
        "n": last10.loc[common, "games"].values,
        "full_games": full.loc[common, "games"].values,
        "full_value": full.loc[common, "value"].values,
        "last10_value": last10.loc[common, "value"].values,
    })
    out["entity_id"] = out["player_id"].astype(str)
    out["entity_name"] = out["player_id"].map(lambda pid: names.get(pid, str(pid)))
    out["ingredients"] = out.apply(lambda r: {
        "last10_pts_per36": round(float(r.last10_value), 4),
        "full_pts_per36": round(float(r.full_value), 4),
        "last10_games": int(r.n), "full_games": int(r.full_games),
    }, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "on_court_impact": build_on_court_impact,
    "gravity": build_gravity,
    "scoring_per36": build_scoring_per36,
    "reb_per36": build_reb_per36,
    "ast_per36": build_ast_per36,
    "efg": build_efg,
    "usage_proxy_per36": build_usage_proxy_per36,
    "recent_form": build_recent_form,
}
