"""domains.basketball_wnba.profiles.ingredients_defzone -- on-court DEFENSIVE
zone-shooting-allowed deltas (on - off), off zone_onoff_wnba_2026.parquet
(domains.basketball_wnba.lineups.zone_onoff_wnba, itself a thin adapter over
NBA's zone_onoff.py -- see that module's docstring for the defense-keying
proof). Mirrors gravity's on/off-delta shape and compound floor pattern
(pre-filter min(min_on,min_off)>=300 INSIDE the builder, same on/off-derived
floor as on_court_impact/gravity).

raw_value = off - on (NOT on - off): a positive delta means the player
allows LESS of that shot type/efficiency while on the floor than off it --
"higher = tighter individual defense", matching this registry's only
percentile direction (build_profiles._percentile_and_rating always ranks
higher raw_value as better; there is no per-attribute direction flag here).
Purely descriptive, no causal claim.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

MIN_MINUTES_FLOOR = 300.0  # min(min_on, min_off), same on/off-derived floor as gravity/on_court_impact


def _delta_builder(on_col: str, off_col: str, ingredient_name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        pre = df[(df["min_on"] >= MIN_MINUTES_FLOOR) & (df["min_off"] >= MIN_MINUTES_FLOOR)].copy()
        pre = pre.dropna(subset=[on_col, off_col])
        pre["entity_id"] = pre["player_id"].astype(str)
        pre["entity_name"] = pre["player_name"]
        pre["raw_value"] = pre[off_col] - pre[on_col]
        pre["n"] = pre[["min_on", "min_off"]].min(axis=1)
        pre["ingredients"] = pre.apply(lambda r: {
            ingredient_name + "_on": round(float(r[on_col]), 4), ingredient_name + "_off": round(float(r[off_col]), 4),
            "min_on": round(float(r.min_on), 2), "min_off": round(float(r.min_off), 2), "team_id": int(r.team_id),
        }, axis=1)
        return pre[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "def_rim_share_allowed_delta": _delta_builder("rim_share_allowed_on", "rim_share_allowed_off", "rim_share_allowed"),
    "def_rim_efg_allowed_delta": _delta_builder("rim_efg_allowed_on", "rim_efg_allowed_off", "rim_efg_allowed"),
    "def_three_share_allowed_delta": _delta_builder("three_share_allowed_on", "three_share_allowed_off", "three_share_allowed"),
    "def_three_efg_allowed_delta": _delta_builder("three_efg_allowed_on", "three_efg_allowed_off", "three_efg_allowed"),
}
