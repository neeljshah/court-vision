"""domains.mlb.profiles.ingredients_pitcher -- one builder function per
PITCHER attribute in attribute_registry.ATTRIBUTES. Same tidy shape as
ingredients_batter.py (entity_id, raw_value, n, ingredients).

Zero reimplementation: FASTBALL_TYPES / is_breaking reused from
domains.mlb.prereg.mlb_hypotheses (the exact ingredient the REPLICATED
count-leverage x pitch-mix mechanism was tested on). add_tto reused from
the same module for TTO_durability's PA-terminal bucketing.
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.prereg.mlb_hypotheses import _NEG_EVENTS, _POS_EVENTS, FASTBALL_TYPES, add_tto

from domains.mlb.profiles.ingredients_batter import _two_cell

_MISS_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked"}
_SWING_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play"}


def build_mix_by_leverage(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches[pitches["pitch_type"].notna() & (pitches["pitch_type"] != "None")].copy()
    p["entity_id"] = p["pitcher"]
    p["is_breaking"] = (~p["pitch_type"].isin(FASTBALL_TYPES)).astype(int)
    p["leverage_cell"] = (p["strikes"] > p["balls"]).map({True: "ahead", False: "not_ahead"})
    wide = _two_cell(p, "leverage_cell", "is_breaking", "ahead", "not_ahead",
                      "breaking_share_ahead", "n_ahead", "breaking_share_not_ahead", "n_not_ahead")
    wide["raw_value"] = wide["breaking_share_ahead"] - wide["breaking_share_not_ahead"]
    wide["n"] = wide[["n_ahead", "n_not_ahead"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "breaking_share_ahead": round(float(r.breaking_share_ahead), 4), "n_ahead": int(r.n_ahead),
        "breaking_share_not_ahead": round(float(r.breaking_share_not_ahead), 4), "n_not_ahead": int(r.n_not_ahead),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_velo_band(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches.dropna(subset=["release_speed"]).copy()
    g = p.groupby("pitcher")["release_speed"].agg(velo_mean="mean", velo_std="std", n="size").reset_index()
    g = g.rename(columns={"pitcher": "entity_id"})
    g["raw_value"] = g["velo_mean"]
    g["ingredients"] = g.apply(lambda r: {
        "velo_mean": round(float(r.velo_mean), 2),
        "velo_std": round(float(r.velo_std), 2) if pd.notna(r.velo_std) else None,
        "n_pitches": int(r.n),
    }, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_TTO_durability(pitches: pd.DataFrame) -> pd.DataFrame:
    """TTO must be numbered over ALL PA-terminal rows (events.notna()) BEFORE
    dropping the ~1% missing estimated_woba_using_speedangle (mlb_tto_claims.py's
    own documented gap) -- dropping first would skip a PA in the cumcount and
    silently misnumber every later PA in that game for this pitcher/batter pair."""
    term = pitches[pitches["events"].notna()].copy()
    term = add_tto(term)
    term = term.dropna(subset=["estimated_woba_using_speedangle"])
    term["entity_id"] = term["pitcher"]
    term["tto_cell"] = term["tto"].map(lambda t: "tto1" if t == 1 else ("tto3plus" if t >= 3 else None))
    term = term.dropna(subset=["tto_cell"])
    wide = _two_cell(term, "tto_cell", "estimated_woba_using_speedangle", "tto1", "tto3plus",
                      "woba_tto1", "n_tto1", "woba_tto3plus", "n_tto3plus")
    wide["raw_value"] = wide["woba_tto3plus"] - wide["woba_tto1"]
    wide["n"] = wide[["n_tto1", "n_tto3plus"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "woba_tto1": round(float(r.woba_tto1), 4), "n_tto1": int(r.n_tto1),
        "woba_tto3plus": round(float(r.woba_tto3plus), 4), "n_tto3plus": int(r.n_tto3plus),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_platoon_split(pitches: pd.DataFrame) -> pd.DataFrame:
    term = pitches[pitches["events"].notna()].copy()
    term = term[term["events"].isin(_POS_EVENTS | _NEG_EVENTS)]
    term["entity_id"] = term["pitcher"]
    term["reaches_base"] = term["events"].isin(_POS_EVENTS).astype(int)
    term["stand_cell"] = term["stand"].map({"R": "vs_r", "L": "vs_l"})
    term = term.dropna(subset=["stand_cell"])
    wide = _two_cell(term, "stand_cell", "reaches_base", "vs_r", "vs_l",
                      "reaches_base_vs_r", "n_vs_r", "reaches_base_vs_l", "n_vs_l")
    wide["raw_value"] = wide["reaches_base_vs_r"] - wide["reaches_base_vs_l"]
    wide["n"] = wide[["n_vs_r", "n_vs_l"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "reaches_base_vs_r": round(float(r.reaches_base_vs_r), 4), "n_vs_r": int(r.n_vs_r),
        "reaches_base_vs_l": round(float(r.reaches_base_vs_l), 4), "n_vs_l": int(r.n_vs_l),
    }, axis=1)
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def build_whiff_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    """SWING/MISS both keyed off `description` (the real per-pitch pitch-call
    code -- see prereg_shift_framing.py, present on this savant_full corpus
    unlike statcast_fuller). Bunt-variant descriptions excluded (small n,
    ambiguous swing intent), not silently folded in."""
    p = pitches[pitches["description"].isin(_SWING_DESCRIPTIONS)].copy()
    p["is_miss"] = p["description"].isin(_MISS_DESCRIPTIONS).astype(int)
    g = p.groupby("pitcher")["is_miss"].agg(whiff_rate="mean", n="size").reset_index()
    g = g.rename(columns={"pitcher": "entity_id"})
    g["raw_value"] = g["whiff_rate"]
    g["ingredients"] = g.apply(lambda r: {
        "whiff_rate": round(float(r.whiff_rate), 4), "n_swings": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_gb_tendency(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = hitcoords[(hitcoords["type"] == "X") & hitcoords["bb_type"].notna()
                    & (hitcoords["bb_type"] != "None")].copy()
    bip["is_groundball"] = (bip["bb_type"] == "ground_ball").astype(int)
    g = bip.groupby("pitcher")["is_groundball"].agg(gb_share="mean", n="size").reset_index()
    g = g.rename(columns={"pitcher": "entity_id"})
    g["raw_value"] = g["gb_share"]
    g["ingredients"] = g.apply(lambda r: {
        "gb_share": round(float(r.gb_share), 4), "n_bip": int(r.n)}, axis=1)
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "mix_by_leverage": build_mix_by_leverage,
    "velo_band": build_velo_band,
    "TTO_durability": build_TTO_durability,
    "platoon_split": build_platoon_split,
    "whiff_rate": build_whiff_rate,
    "gb_tendency": build_gb_tendency,
}
