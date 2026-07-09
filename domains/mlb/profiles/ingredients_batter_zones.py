"""domains.mlb.profiles.ingredients_batter_zones -- ATTACK-ZONE grid: heart/
shadow/chase/waste region x metric builders (17 batter attributes), the
batter-side half of the region grid started in ingredients_pitcher_zones.py.
Zone geometry (classify_attack_zone), _geom_prep, _region_swing_table, and
_region_bip_table are all REUSED verbatim from that module -- zero
reimplementation, same cross-import shape as ingredients_batter_grid.py
reusing PITCH_CLASSES/classify_pitch_class from ingredients_pitcher_grid.py.

FLOORS (declared per family, task brief: >=50 pitches seen in region for
batters):
  region_swing_rate_*    floor=50  (n pitches seen in region)
  region_whiff_vs_*      floor=50  (n_swings in region, matches whiff_vs_cls)
  region_xwoba_contact_* floor=20  (n_bip in region, matches xwoba_contact_vs_cls)
  shadow_take_rate       floor=50  (n shadow pitches seen)
  chase_rate_by_class_*  floor=50  (n chase-region pitches of that class,
                                    matches chase_vs_cls's floor=50)
  heart_damage_xwoba     floor=20  (n_bip in heart -- same family as
                                    region_xwoba_contact_heart; a distinct,
                                    separately-named "damage exposure" claim
                                    per the brief, not a re-derivation)
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from domains.mlb.profiles.ingredients_batter import _SWING_DESCRIPTIONS
from domains.mlb.profiles.ingredients_pitcher_grid import PITCH_CLASSES, classify_pitch_class
from domains.mlb.profiles.ingredients_pitcher_zones import (
    ATTACK_ZONES, _geom_prep, _region_bip_table, _region_swing_table,
)


def _region_swing_rate_table(pitches: pd.DataFrame) -> pd.DataFrame:
    """Swing rate among ALL region pitches (not whiff-among-swings) --
    batter-only table, by (entity, region)."""
    p = _geom_prep(pitches, "batter")
    p["is_swing"] = p["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    return p.groupby(["entity_id", "attack_zone"])["is_swing"].agg(swing_rate="mean", n="size").reset_index()


def _region_class_swing_table(pitches: pd.DataFrame) -> pd.DataFrame:
    """Swing rate by (entity, region, pitch_class) -- feeds chase_rate_by_class_*."""
    p = _geom_prep(pitches, "batter")
    p["pitch_class"] = classify_pitch_class(p["pitch_type"])
    p = p.dropna(subset=["pitch_class"])
    p["is_swing"] = p["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    return p.groupby(["entity_id", "attack_zone", "pitch_class"])["is_swing"].agg(
        swing_rate="mean", n="size").reset_index()


def _make_swing_rate_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_swing_rate_table(pitches)
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["swing_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"swing_rate": round(float(r.swing_rate), 4),
                                                    "n_region_pitches": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_whiff_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_swing_table(pitches, "batter")
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["whiff_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"whiff_rate": round(float(r.whiff_rate), 4),
                                                    "n_swings": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_xwoba_contact_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_bip_table(pitches, "batter")
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["xwoba"]
        sub["ingredients"] = sub.apply(lambda r: {"xwoba_on_contact": round(float(r.xwoba), 4),
                                                    "n_bip": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_chase_by_class_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_class_swing_table(pitches)
        sub = g[(g["attack_zone"] == "chase") & (g["pitch_class"] == cls)].copy()
        sub["raw_value"] = sub["swing_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"chase_rate": round(float(r.swing_rate), 4),
                                                    "n_chase_pitches": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


REGION_SWING_RATE_BUILDERS = {f"region_swing_rate_{z}": _make_swing_rate_builder(z) for z in ATTACK_ZONES}
# NOTE: "region_whiff_vs_*" (not "region_whiff_rate_*") -- the pitcher-side
# module already claims that name for its own whiff attribute; same "vs"
# (batter) / "rate"-under-"by_class" (pitcher) split ingredients_batter_grid.py
# already uses (whiff_vs_cls vs whiff_by_class_cls) to keep the flat
# registry namespace collision-free.
REGION_WHIFF_BUILDERS = {f"region_whiff_vs_{z}": _make_whiff_builder(z) for z in ATTACK_ZONES}
REGION_XWOBA_CONTACT_BUILDERS = {f"region_xwoba_contact_{z}": _make_xwoba_contact_builder(z) for z in ATTACK_ZONES}
CHASE_BY_CLASS_BUILDERS = {f"chase_rate_by_class_{c}": _make_chase_by_class_builder(c) for c in PITCH_CLASSES}


def build_shadow_take_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    """1 - swing_rate on SHADOW-region pitches -- the discipline jewel: how
    often a batter lays off borderline pitches, framed as a take rate rather
    than the swing-rate framing already covered by region_swing_rate_shadow."""
    g = _region_swing_rate_table(pitches)
    sub = g[g["attack_zone"] == "shadow"].copy()
    sub["raw_value"] = 1.0 - sub["swing_rate"]
    sub["ingredients"] = sub.apply(lambda r: {"take_rate": round(float(1.0 - r.swing_rate), 4),
                                               "n_shadow_pitches": int(r.n)}, axis=1, result_type="reduce")
    return sub[["entity_id", "raw_value", "n", "ingredients"]]


def build_heart_damage_xwoba(pitches: pd.DataFrame) -> pd.DataFrame:
    """xwOBA on contact restricted to the HEART region -- same underlying
    table as region_xwoba_contact_heart, exposed as its own named
    damage-exposure attribute per the brief."""
    g = _region_bip_table(pitches, "batter")
    sub = g[g["attack_zone"] == "heart"].copy()
    sub["raw_value"] = sub["xwoba"]
    sub["ingredients"] = sub.apply(lambda r: {"xwoba_on_heart_contact": round(float(r.xwoba), 4),
                                               "n_bip": int(r.n)}, axis=1, result_type="reduce")
    return sub[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    **REGION_SWING_RATE_BUILDERS,
    **REGION_WHIFF_BUILDERS,
    **REGION_XWOBA_CONTACT_BUILDERS,
    "shadow_take_rate": build_shadow_take_rate,
    **CHASE_BY_CLASS_BUILDERS,
    "heart_damage_xwoba": build_heart_damage_xwoba,
}
