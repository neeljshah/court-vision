"""domains.mlb.profiles.ingredients_pitcher_zones -- ATTACK-ZONE grid: heart/
shadow/chase/waste region x metric builders (30 pitcher attributes), the next
honest multiplier past ingredients_pitcher_grid.py's pitch-class x count-state
grid (63 -> 110 total attributes, see attribute_registry.py).

ATTACK ZONES (declared BEFORE running, Statcast-standard-adjacent -- NOT a
literal replica of Statcast's proprietary Heart/Shadow/Chase/Waste cutoffs
(not published to this precision), same conceptual structure: a shrunk inner
"heart" box, a symmetric edge band, a near-miss "chase" band, and a far
"waste" band). REUSES prereg_shift_framing.classify_borderline's own signed-
distance geometry verbatim (zero reimplementation):

    edge_dist = max(|plate_x| - PLATE_HALF_WIDTH_FT, plate_z - sz_top, sz_bot - plate_z)

  edge_dist <= -SHADOW_FT              -> HEART   (>=3in inside the true zone
                                                     edge on every axis)
  -SHADOW_FT < edge_dist <= SHADOW_FT  -> SHADOW  (the zone-edge band, both
                                                     sides of the rubber line
                                                     -- IDENTICAL to classify_
                                                     borderline's own "is
                                                     borderline" test; SHELL_FT
                                                     =0.25ft reused as-is)
  SHADOW_FT < edge_dist <= CHASE_FT    -> CHASE   (clearly out but a batter
                                                     could still reasonably
                                                     offer at it)
  edge_dist > CHASE_FT                 -> WASTE   (far out; CHASE_FT=1.00ft
                                                     beyond the shadow band,
                                                     declared before running)

FLOORS (declared per family, matching this module's own precedent -- see
ingredients_pitcher_grid.py's whiff_by_class=100 / called_strike_by_class=100
/ xwoba_against_by_class=30 / mix cell=100):
  region_pitch_share_*        floor=100  (n_total_pitches, all regions)
  region_whiff_rate_*         floor=100  (n_swings in region)
  region_called_strike_rate_* floor=100  (n_taken in region)
  region_xwoba_against_*      floor=30   (n_bip in region)
  region_mix_*_*              floor=100  (n pitches in region, share-of-region-by-class)
  chase_induce_rate_ahead     floor=50   (n chase-region pitches while pitcher
                                          ahead -- rarer conjunction, matches
                                          command_edge_share_behind's floor=50)
  heart_share_behind          floor=50   (n pitches while pitcher behind --
                                          same shape as command_edge_share_behind)

LANDMINE guard (same discipline as ingredients_pitcher_grid.py): every table
below groups on real observed rows via .size()/unstack(fill_value=0) on
combos that actually occurred; a region a pitcher never threw into is simply
ABSENT, never a fabricated 0.0.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from domains.mlb.prereg_shift_framing import PLATE_HALF_WIDTH_FT, SHELL_FT
from domains.mlb.profiles.ingredients_batter import _SWING_DESCRIPTIONS
from domains.mlb.profiles.ingredients_pitcher_grid import (
    PITCH_CLASSES, _MISS_DESCRIPTIONS, _TAKEN_DESCRIPTIONS, classify_pitch_class,
)

ATTACK_ZONES = ("heart", "shadow", "chase", "waste")
SHADOW_FT = SHELL_FT  # reuse framing's declared edge-shell half-width (0.25 ft) verbatim
CHASE_FT = 1.00  # declared before running: 1.0 ft beyond the shadow band -> CHASE; beyond -> WASTE


def classify_attack_zone(df: pd.DataFrame) -> pd.Series:
    """See module docstring ATTACK ZONES. Requires plate_x/plate_z/sz_top/
    sz_bot all non-null (caller filters first, same contract as
    classify_borderline)."""
    dx = df["plate_x"].abs() - PLATE_HALF_WIDTH_FT
    dz_top = df["plate_z"] - df["sz_top"]
    dz_bot = df["sz_bot"] - df["plate_z"]
    edge_dist = np.maximum.reduce([dx.to_numpy(), dz_top.to_numpy(), dz_bot.to_numpy()])
    zone = np.select([edge_dist <= -SHADOW_FT, edge_dist <= SHADOW_FT, edge_dist <= CHASE_FT],
                      ["heart", "shadow", "chase"], default="waste")
    return pd.Series(zone, index=df.index)


def _geom_prep(pitches: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    p = pitches.dropna(subset=["plate_x", "plate_z", "sz_top", "sz_bot"]).copy()
    p["entity_id"] = p[entity_col]
    p["attack_zone"] = classify_attack_zone(p)
    return p


def _region_swing_table(pitches: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Whiff rate among SWINGS, by (entity, region) -- shared by pitcher
    region_whiff_rate_* and batter region_whiff_rate_* (identical shape,
    different entity_col)."""
    p = _geom_prep(pitches, entity_col)
    sw = p[p["description"].isin(_SWING_DESCRIPTIONS)].copy()
    sw["is_miss"] = sw["description"].isin(_MISS_DESCRIPTIONS).astype(int)
    return sw.groupby(["entity_id", "attack_zone"])["is_miss"].agg(whiff_rate="mean", n="size").reset_index()


def _region_bip_table(pitches: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """xwOBA on contact (balls in play), by (entity, region) -- shared by
    pitcher region_xwoba_against_* and batter region_xwoba_contact_*."""
    p = _geom_prep(pitches, entity_col)
    bip = p[(p["type"] == "X") & p["estimated_woba_using_speedangle"].notna()].copy()
    return bip.groupby(["entity_id", "attack_zone"])["estimated_woba_using_speedangle"].agg(
        xwoba="mean", n="size").reset_index()


# --------------------------------------------------------------- pitcher-only tables
def _region_pitch_share_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _geom_prep(pitches, "pitcher")
    counts = p.groupby(["entity_id", "attack_zone"]).size().unstack("attack_zone", fill_value=0)
    counts = counts.reindex(columns=list(ATTACK_ZONES), fill_value=0)
    counts["total"] = counts[list(ATTACK_ZONES)].sum(axis=1)
    for z in ATTACK_ZONES:
        counts[f"share_{z}"] = counts[z] / counts["total"]
    return counts.reset_index()


def _region_taken_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _geom_prep(pitches, "pitcher")
    tk = p[p["description"].isin(_TAKEN_DESCRIPTIONS)].copy()
    tk["is_strike"] = (tk["description"] == "called_strike").astype(int)
    return tk.groupby(["entity_id", "attack_zone"])["is_strike"].agg(
        called_strike_rate="mean", n="size").reset_index()


def _region_class_share_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _geom_prep(pitches, "pitcher")
    p["pitch_class"] = classify_pitch_class(p["pitch_type"])
    p = p.dropna(subset=["pitch_class"])
    counts = p.groupby(["entity_id", "attack_zone", "pitch_class"]).size().unstack("pitch_class", fill_value=0)
    counts = counts.reindex(columns=list(PITCH_CLASSES), fill_value=0)
    counts["total"] = counts[list(PITCH_CLASSES)].sum(axis=1)
    for cls in PITCH_CLASSES:
        counts[f"share_{cls}"] = counts[cls] / counts["total"]
    return counts.reset_index()


def _make_pitch_share_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        t = _region_pitch_share_table(pitches)
        t = t[t["total"] > 0].copy()
        t["raw_value"] = t[f"share_{region}"]
        t["n"] = t["total"].astype(int)
        t["ingredients"] = t.apply(lambda r: {f"share_{region}": round(float(r[f"share_{region}"]), 4),
                                               "n_total_pitches": int(r["total"])}, axis=1, result_type="reduce")
        return t[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_whiff_builder(region: str, entity_col: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_swing_table(pitches, entity_col)
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["whiff_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"whiff_rate": round(float(r.whiff_rate), 4),
                                                    "n_swings": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_called_strike_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_taken_table(pitches)
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["called_strike_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"called_strike_rate": round(float(r.called_strike_rate), 4),
                                                    "n_taken": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_xwoba_against_builder(region: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _region_bip_table(pitches, "pitcher")
        sub = g[g["attack_zone"] == region].copy()
        sub["raw_value"] = sub["xwoba"]
        sub["ingredients"] = sub.apply(lambda r: {"xwoba_against": round(float(r.xwoba), 4),
                                                    "n_bip": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_class_share_builder(region: str, cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        t = _region_class_share_table(pitches)
        sub = t[(t["attack_zone"] == region) & (t["total"] > 0)].copy()
        sub["raw_value"] = sub[f"share_{cls}"]
        sub["n"] = sub["total"].astype(int)
        sub["ingredients"] = sub.apply(lambda r: {f"share_{cls}": round(float(r[f"share_{cls}"]), 4),
                                                    "n_region_pitches": int(r["total"])}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


REGION_PITCH_SHARE_BUILDERS = {f"region_pitch_share_{z}": _make_pitch_share_builder(z) for z in ATTACK_ZONES}
REGION_WHIFF_BUILDERS = {f"region_whiff_rate_{z}": _make_whiff_builder(z, "pitcher") for z in ATTACK_ZONES}
REGION_CALLED_STRIKE_BUILDERS = {f"region_called_strike_rate_{z}": _make_called_strike_builder(z)
                                  for z in ATTACK_ZONES}
REGION_XWOBA_AGAINST_BUILDERS = {f"region_xwoba_against_{z}": _make_xwoba_against_builder(z) for z in ATTACK_ZONES}
REGION_CLASS_SHARE_BUILDERS = {f"region_mix_{z}_{c}": _make_class_share_builder(z, c)
                                for z in ATTACK_ZONES for c in PITCH_CLASSES}


def build_chase_induce_rate_ahead(pitches: pd.DataFrame) -> pd.DataFrame:
    """CHASE-region swing rate restricted to counts where the pitcher is
    ahead (strikes > balls) -- operationalizes the brief's "2-strike
    chase-induce rate (chase region swing rate when ahead)" using this
    module's existing ahead/behind count-leverage convention (see
    ingredients_pitcher_grid._count_state) rather than a literal
    strikes==2 filter -- deviation noted here, not silently substituted."""
    p = _geom_prep(pitches, "pitcher")
    p = p[(p["attack_zone"] == "chase") & (p["strikes"] > p["balls"])].copy()
    p["is_swing"] = p["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    g = p.groupby("entity_id")["is_swing"].agg(chase_induce_rate="mean", n="size").reset_index()
    g["raw_value"] = g["chase_induce_rate"]
    g["ingredients"] = g.apply(lambda r: {"chase_induce_rate": round(float(r.chase_induce_rate), 4),
                                           "n_chase_ahead": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_heart_share_behind(pitches: pd.DataFrame) -> pd.DataFrame:
    """HEART-region pitch share restricted to counts where the pitcher is
    behind (balls > strikes) -- damage-exposure proxy: how often a pitcher
    is forced into the heart of the zone when the count favors the batter.
    Same shape as ingredients_pitcher_grid.build_command_edge_share_behind."""
    p = _geom_prep(pitches, "pitcher")
    p = p[p["balls"] > p["strikes"]].copy()
    p["is_heart"] = (p["attack_zone"] == "heart").astype(int)
    g = p.groupby("entity_id")["is_heart"].agg(heart_share="mean", n="size").reset_index()
    g["raw_value"] = g["heart_share"]
    g["ingredients"] = g.apply(lambda r: {"heart_share": round(float(r.heart_share), 4),
                                           "n_pitches_behind": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    **REGION_PITCH_SHARE_BUILDERS,
    **REGION_WHIFF_BUILDERS,
    **REGION_CALLED_STRIKE_BUILDERS,
    **REGION_XWOBA_AGAINST_BUILDERS,
    **REGION_CLASS_SHARE_BUILDERS,
    "chase_induce_rate_ahead": build_chase_induce_rate_ahead,
    "heart_share_behind": build_heart_share_behind,
}
