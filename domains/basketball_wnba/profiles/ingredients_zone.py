"""domains.basketball_wnba.profiles.ingredients_zone -- per-player OFFENSIVE
zone-shooting attributes (attempt_share + efg for each of the 5
composition.zone_geometry zones) plus assisted_share, all off
source_shots.load_all_shots's one-row-per-attempt frame.

3pt zones (corner3/above_break_3) use eFG=1.5*fgm/fga (a make is worth 1.5x
a 2pt make); rim/paint/mid use plain fgm/fga -- same convention as NBA's
zone_onoff.compute_zone_onoff three_efg_allowed column.

n floor is the zone's own fga count (or fgm count for assisted_share) --
>=20 attempts, per the task's declared floor for this 168-game corpus.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_wnba.claims_player_form import load_boxscores

_THREE_ZONES = {"corner3", "above_break_3"}


def _names() -> pd.Series:
    box = load_boxscores()
    return box.drop_duplicates("player_id", keep="last").set_index("player_id")["player_name"]


def _entity_cols(df: pd.DataFrame, id_col: str = "person_id") -> pd.DataFrame:
    names = _names()
    out = df.copy()
    out["entity_id"] = out[id_col].astype(str)
    out["entity_name"] = out[id_col].astype(str).map(lambda s: names.get(s, s))
    return out


def _zone_share_builder(zone: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _builder(shots: pd.DataFrame) -> pd.DataFrame:
        total = shots.groupby("person_id").agg(total_fga=("fga", "sum")).reset_index()
        zsub = shots[shots["zone"] == zone]
        zg = zsub.groupby("person_id").agg(zone_fga=("fga", "sum"), zone_fgm=("fgm", "sum")).reset_index()
        merged = zg.merge(total, on="person_id", how="left")
        merged["raw_value"] = merged["zone_fga"] / merged["total_fga"]
        merged["n"] = merged["zone_fga"]
        out = _entity_cols(merged)
        out["ingredients"] = out.apply(lambda r: {
            "zone_fga": int(r.zone_fga), "zone_fgm": int(r.zone_fgm), "total_fga": int(r.total_fga),
        }, axis=1)
        return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


def _zone_efg_builder(zone: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    mult = 1.5 if zone in _THREE_ZONES else 1.0

    def _builder(shots: pd.DataFrame) -> pd.DataFrame:
        zsub = shots[shots["zone"] == zone]
        zg = zsub.groupby("person_id").agg(zone_fga=("fga", "sum"), zone_fgm=("fgm", "sum")).reset_index()
        zg = zg[zg["zone_fga"] > 0].copy()
        zg["raw_value"] = mult * zg["zone_fgm"] / zg["zone_fga"]
        zg["n"] = zg["zone_fga"]
        out = _entity_cols(zg)
        out["ingredients"] = out.apply(lambda r: {"zone_fga": int(r.zone_fga), "zone_fgm": int(r.zone_fgm)}, axis=1)
        return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


def build_assisted_share(shots: pd.DataFrame) -> pd.DataFrame:
    made = shots[shots["fgm"] == 1]
    g = made.groupby("person_id").agg(fgm=("fgm", "sum"), assisted=("is_assisted", "sum")).reset_index()
    g["raw_value"] = g["assisted"] / g["fgm"]
    g["n"] = g["fgm"]
    out = _entity_cols(g)
    out["ingredients"] = out.apply(lambda r: {"assisted_fgm": int(r.assisted), "fgm": int(r.fgm)}, axis=1)
    return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]


BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {"assisted_share": build_assisted_share}
for _zone in ZONES:
    BUILDERS[f"zone_{_zone}_share"] = _zone_share_builder(_zone)
    BUILDERS[f"zone_{_zone}_efg"] = _zone_efg_builder(_zone)
