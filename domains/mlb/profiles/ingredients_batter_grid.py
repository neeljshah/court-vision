"""domains.mlb.profiles.ingredients_batter_grid -- pitch-class x count-state
grid builders (20 attributes) extending ingredients_batter.py's flat
7-attribute set. Same tidy shape (entity_id, raw_value, n, ingredients).
All DESCRIPTIVE (finer-grained splits, no new prereg replication run).

Pitch-class machinery (classify_pitch_class, PITCH_CLASSES) reused from
ingredients_pitcher_grid.py -- one classification, both entities, zero
reimplementation. Same NaN-safety discipline as that module: grid tables
group on real observed rows only, never nansum over a reindexed empty slice.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from domains.mlb.prereg_shift_unblocked import spray_angle_deg
from domains.mlb.profiles.ingredients_batter import _SWING_DESCRIPTIONS, _two_cell
from domains.mlb.profiles.ingredients_pitcher_grid import (
    PITCH_CLASSES, _MISS_DESCRIPTIONS, classify_pitch_class,
)

_PULL_THRESHOLD_DEG = 15.0  # matches prereg_shift_unblocked's own pull threshold


def _prep(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches[pitches["pitch_type"].notna() & (pitches["pitch_type"] != "None")].copy()
    p["entity_id"] = p["batter"]
    p["pitch_class"] = classify_pitch_class(p["pitch_type"])
    return p.dropna(subset=["pitch_class"])


def _whiff_class_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    sw = p[p["description"].isin(_SWING_DESCRIPTIONS)].copy()
    sw["is_miss"] = sw["description"].isin(_MISS_DESCRIPTIONS).astype(int)
    return sw.groupby(["entity_id", "pitch_class"])["is_miss"].agg(whiff_rate="mean", n="size").reset_index()


def _make_whiff_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _whiff_class_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["whiff_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"whiff_rate": round(float(r.whiff_rate), 4),
                                                    "n_swings": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _xwoba_contact_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    bip = p[(p["type"] == "X") & p["estimated_woba_using_speedangle"].notna()].copy()
    return bip.groupby(["entity_id", "pitch_class"])["estimated_woba_using_speedangle"].agg(
        xwoba="mean", n="size").reset_index()


def _make_xwoba_contact_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _xwoba_contact_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["xwoba"]
        sub["ingredients"] = sub.apply(lambda r: {"xwoba_on_contact": round(float(r.xwoba), 4),
                                                    "n_bip": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _chase_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    oz = p[p["zone"].notna() & (p["zone"] >= 11)].copy()
    oz["is_swing"] = oz["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    return oz.groupby(["entity_id", "pitch_class"])["is_swing"].agg(chase_rate="mean", n="size").reset_index()


def _make_chase_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _chase_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["chase_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"chase_rate": round(float(r.chase_rate), 4),
                                                    "n_out_of_zone": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


WHIFF_BUILDERS = {f"whiff_vs_{c}": _make_whiff_builder(c) for c in PITCH_CLASSES}
XWOBA_CONTACT_BUILDERS = {f"xwoba_contact_vs_{c}": _make_xwoba_contact_builder(c) for c in PITCH_CLASSES}
CHASE_BUILDERS = {f"chase_vs_{c}": _make_chase_builder(c) for c in PITCH_CLASSES}


def _make_xwoba_count_builder(state: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        term = pitches[pitches["events"].notna()].dropna(subset=["estimated_woba_using_speedangle"]).copy()
        if state == "ahead":
            term = term[term["balls"] > term["strikes"]]
        elif state == "behind":
            term = term[term["strikes"] > term["balls"]]
        else:  # two_strike
            term = term[term["strikes"] == 2]
        term["entity_id"] = term["batter"]
        g = term.groupby("entity_id")["estimated_woba_using_speedangle"].agg(xwoba="mean", n="size").reset_index()
        g["raw_value"] = g["xwoba"]
        g["ingredients"] = g.apply(lambda r: {"xwoba": round(float(r.xwoba), 4), "n_pa": int(r.n)},
                                    axis=1, result_type="reduce")
        return g[["entity_id", "raw_value", "n", "ingredients"]]
    return build


XWOBA_COUNT_BUILDERS = {f"xwoba_{s}": _make_xwoba_count_builder(s) for s in ("ahead", "behind", "two_strike")}


def build_first_pitch_swing_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    fp = pitches[(pitches["balls"] == 0) & (pitches["strikes"] == 0)].copy()
    fp["entity_id"] = fp["batter"]
    fp["is_swing"] = fp["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    g = fp.groupby("entity_id")["is_swing"].agg(swing_rate="mean", n="size").reset_index()
    g["raw_value"] = g["swing_rate"]
    g["ingredients"] = g.apply(lambda r: {"swing_rate": round(float(r.swing_rate), 4),
                                           "n_first_pitches": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def _bb_type_table(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords[(hitcoords["type"] == "X") & hitcoords["bb_type"].notna()
                    & (hitcoords["bb_type"] != "None")].copy()
    bip["entity_id"] = bip["batter"]
    counts = bip.groupby(["entity_id", "bb_type"]).size().unstack("bb_type", fill_value=0)
    counts = counts.reindex(columns=["ground_ball", "line_drive", "fly_ball", "popup"], fill_value=0)
    counts["total"] = counts.sum(axis=1)
    return counts.reset_index()


def _make_bb_share_builder(bb_type: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(hitcoords: pd.DataFrame) -> pd.DataFrame:
        t = _bb_type_table(hitcoords)
        t = t[t["total"] > 0].copy()
        t["raw_value"] = t[bb_type] / t["total"]
        t["n"] = t["total"].astype(int)
        t["ingredients"] = t.apply(lambda r: {f"{bb_type}_share": round(float(r["raw_value"]), 4),
                                               "n_bip": int(r["total"])}, axis=1, result_type="reduce")
        return t[["entity_id", "raw_value", "n", "ingredients"]]
    return build


BB_SHARE_BUILDERS = {
    "gb_share_batter": _make_bb_share_builder("ground_ball"),
    "ld_share_batter": _make_bb_share_builder("line_drive"),
    "fb_share_batter": _make_bb_share_builder("fly_ball"),
}


def build_hard_contact_share(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords.dropna(subset=["launch_speed_angle"]).copy()
    bip["entity_id"] = bip["batter"]
    bip["is_hard"] = bip["launch_speed_angle"].isin([5, 6]).astype(int)
    g = bip.groupby("entity_id")["is_hard"].agg(hard_share="mean", n="size").reset_index()
    g["raw_value"] = g["hard_share"]
    g["ingredients"] = g.apply(lambda r: {"hard_contact_share": round(float(r.hard_share), 4),
                                           "n_batted_balls": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def _spray_bucket(hc_x: pd.Series, hc_y: pd.Series, stand: pd.Series) -> pd.Series:
    deg = spray_angle_deg(hc_x, hc_y)
    is_rhb = (stand == "R").to_numpy()
    pull = np.where(is_rhb, deg < -_PULL_THRESHOLD_DEG, deg > _PULL_THRESHOLD_DEG)
    oppo = np.where(is_rhb, deg > _PULL_THRESHOLD_DEG, deg < -_PULL_THRESHOLD_DEG)
    return pd.Series(np.select([pull, oppo], ["pull", "oppo"], default="center"), index=deg.index)


def build_spray_entropy(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords.dropna(subset=["hc_x", "hc_y", "stand"]).copy()
    bip["entity_id"] = bip["batter"]
    bip["bucket"] = _spray_bucket(bip["hc_x"], bip["hc_y"], bip["stand"])
    counts = bip.groupby(["entity_id", "bucket"]).size().reset_index(name="n_bucket")
    counts["p"] = counts["n_bucket"] / counts.groupby("entity_id")["n_bucket"].transform("sum")
    counts["contrib"] = -(counts["p"] * np.log(counts["p"]))
    ent = counts.groupby("entity_id")["contrib"].sum().reset_index(name="entropy")
    total = bip.groupby("entity_id").size().reset_index(name="n")
    out = ent.merge(total, on="entity_id")
    out["raw_value"] = out["entropy"]
    out["ingredients"] = out.apply(lambda r: {"entropy": round(float(r.entropy), 4),
                                               "n_batted_balls": int(r.n)}, axis=1, result_type="reduce")
    return out[["entity_id", "raw_value", "n", "ingredients"]]


def build_risp_xwoba_delta(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].dropna(subset=["estimated_woba_using_speedangle"]).copy()
    term["entity_id"] = term["batter"]
    term["risp_cell"] = (term["on_2b"].notna() | term["on_3b"].notna()).map({True: "risp", False: "no_risp"})
    wide = _two_cell(term, "risp_cell", "estimated_woba_using_speedangle", "risp", "no_risp",
                      "xwoba_risp", "n_risp", "xwoba_no_risp", "n_no_risp")
    wide["raw_value"] = wide["xwoba_risp"] - wide["xwoba_no_risp"]
    wide["n"] = wide[["n_risp", "n_no_risp"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "xwoba_risp": round(float(r.xwoba_risp), 4), "n_risp": int(r.n_risp),
        "xwoba_no_risp": round(float(r.xwoba_no_risp), 4), "n_no_risp": int(r.n_no_risp),
    }, axis=1, result_type="reduce")
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_inning_late_xwoba_delta(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].dropna(subset=["estimated_woba_using_speedangle"]).copy()
    term["entity_id"] = term["batter"]
    term["inning_cell"] = (term["inning"] >= 7).map({True: "late", False: "early"})
    wide = _two_cell(term, "inning_cell", "estimated_woba_using_speedangle", "late", "early",
                      "xwoba_late", "n_late", "xwoba_early", "n_early")
    wide["raw_value"] = wide["xwoba_late"] - wide["xwoba_early"]
    wide["n"] = wide[["n_late", "n_early"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "xwoba_late": round(float(r.xwoba_late), 4), "n_late": int(r.n_late),
        "xwoba_early": round(float(r.xwoba_early), 4), "n_early": int(r.n_early),
    }, axis=1, result_type="reduce")
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    **WHIFF_BUILDERS, **XWOBA_CONTACT_BUILDERS, **CHASE_BUILDERS,
    **XWOBA_COUNT_BUILDERS,
    "first_pitch_swing_rate": build_first_pitch_swing_rate,
    **BB_SHARE_BUILDERS,
    "hard_contact_share": build_hard_contact_share,
    "spray_entropy": build_spray_entropy,
    "risp_xwoba_delta": build_risp_xwoba_delta,
    "inning_late_xwoba_delta": build_inning_late_xwoba_delta,
}
