"""domains.mlb.profiles.ingredients_pitcher_grid -- pitch-class x count-state
grid builders (29 attributes) extending ingredients_pitcher.py's flat
6-attribute set. Same tidy shape as ingredients_pitcher/batter.py
(entity_id, raw_value, n, ingredients). All DESCRIPTIVE (no new prereg
replication run for these finer-grained splits -- mix_by_leverage's 2-cell
ahead/not-ahead pitch-mix mechanism stays the ONE VALIDATED_MECHANISM pitch
mix attribute; this grid decomposes the same idea into 9 raw cells for
presentation, not a re-run of the hypothesis test).

Pitch classes: FASTBALL_TYPES reused from mlb_hypotheses; BREAKING_TYPES /
OFFSPEED_TYPES declared here from the savant pitch_type census (PO=pitchout,
UN=unknown, None/NaN fall out of all three sets and are DROPPED, never
force-classified -- same discipline as the existing is_breaking machinery).

LANDMINE guard (see ingredients_batter.py docstring): every grid table below
groups on real observed rows via .size()/unstack(fill_value=0) on combos
that actually occurred -- a class with zero pitches in an observed
(entity, state) cell is a legitimate 0.0; an entity absent from the whole
state (never pitched there) is simply absent, never backfilled.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from domains.mlb.prereg.mlb_hypotheses import FASTBALL_TYPES, _NEG_EVENTS, _POS_EVENTS
from domains.mlb.prereg_shift_framing import classify_borderline
from domains.mlb.profiles.ingredients_batter import _K_EVENTS, _SWING_DESCRIPTIONS, _two_cell

PITCH_CLASSES = ("fastball", "breaking", "offspeed")
BREAKING_TYPES = {"SL", "ST", "CU", "KC", "SV", "CS"}
OFFSPEED_TYPES = {"CH", "FS", "EP", "SC", "FO", "KN"}
_MISS_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked"}
_TAKEN_DESCRIPTIONS = {"called_strike", "ball"}


def classify_pitch_class(pitch_type: pd.Series) -> pd.Series:
    """fastball/breaking/offspeed, or None (dropped by callers) for anything
    outside all three sets (pitchouts, unknowns, missing)."""
    return pd.Series(np.where(pitch_type.isin(FASTBALL_TYPES), "fastball",
                      np.where(pitch_type.isin(BREAKING_TYPES), "breaking",
                      np.where(pitch_type.isin(OFFSPEED_TYPES), "offspeed", None))),
                      index=pitch_type.index)


def _count_state(balls: pd.Series, strikes: pd.Series) -> pd.Series:
    return pd.Series(np.select([strikes > balls, balls > strikes], ["ahead", "behind"], default="even"),
                      index=balls.index)


def _prep(pitches: pd.DataFrame) -> pd.DataFrame:
    p = pitches[pitches["pitch_type"].notna() & (pitches["pitch_type"] != "None")].copy()
    p["entity_id"] = p["pitcher"]
    p["pitch_class"] = classify_pitch_class(p["pitch_type"])
    p = p.dropna(subset=["pitch_class"])
    p["count_state"] = _count_state(p["balls"], p["strikes"])
    return p


def _mix_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    counts = p.groupby(["entity_id", "count_state", "pitch_class"]).size().unstack("pitch_class", fill_value=0)
    counts = counts.reindex(columns=list(PITCH_CLASSES), fill_value=0)
    counts["total"] = counts[list(PITCH_CLASSES)].sum(axis=1)
    for cls in PITCH_CLASSES:
        counts[f"share_{cls}"] = counts[cls] / counts["total"]
    return counts.reset_index()


def _make_mix_builder(cls: str, state: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        t = _mix_table(pitches)
        sub = t[t["count_state"] == state].copy()
        sub["raw_value"] = sub[f"share_{cls}"]
        sub["n"] = sub["total"].astype(int)
        sub["ingredients"] = sub.apply(lambda r: {
            f"share_{cls}_{state}": round(float(r[f"share_{cls}"]), 4), "n_total_pitches": int(r["total"])
        }, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


MIX_BUILDERS = {f"mix_{cls}_{state}": _make_mix_builder(cls, state)
                for cls in PITCH_CLASSES for state in ("ahead", "even", "behind")}


def build_first_pitch_strike_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    fp = pitches[(pitches["balls"] == 0) & (pitches["strikes"] == 0)].copy()
    fp["entity_id"] = fp["pitcher"]
    fp["is_strike"] = fp["type"].isin(["S", "X"]).astype(int)
    g = fp.groupby("entity_id")["is_strike"].agg(fps_rate="mean", n="size").reset_index()
    g["raw_value"] = g["fps_rate"]
    g["ingredients"] = g.apply(lambda r: {"fps_rate": round(float(r.fps_rate), 4),
                                           "n_first_pitches": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_putaway_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    """2-strike PA reached (max strikes this PA >= 2) -> did it end in a K."""
    flag = pitches.groupby(["game_pk", "pitcher", "batter", "at_bat_number"])["strikes"].max()
    flag = flag.rename("max_strikes").reset_index()
    term = pitches[pitches["events"].notna()].copy()
    term = term[term["events"].isin(_POS_EVENTS | _NEG_EVENTS)]
    term = term.merge(flag, on=["game_pk", "pitcher", "batter", "at_bat_number"], how="left")
    term = term[term["max_strikes"] >= 2]
    term["entity_id"] = term["pitcher"]
    term["is_k"] = term["events"].isin(_K_EVENTS).astype(int)
    g = term.groupby("entity_id")["is_k"].agg(putaway_rate="mean", n="size").reset_index()
    g["raw_value"] = g["putaway_rate"]
    g["ingredients"] = g.apply(lambda r: {"putaway_rate": round(float(r.putaway_rate), 4),
                                           "n_two_strike_pa": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def _swing_class_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    sw = p[p["description"].isin(_SWING_DESCRIPTIONS)].copy()
    sw["is_miss"] = sw["description"].isin(_MISS_DESCRIPTIONS).astype(int)
    return sw.groupby(["entity_id", "pitch_class"])["is_miss"].agg(whiff_rate="mean", n="size").reset_index()


def _make_whiff_class_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _swing_class_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["whiff_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"whiff_rate": round(float(r.whiff_rate), 4),
                                                    "n_swings": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _taken_class_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    tk = p[p["description"].isin(_TAKEN_DESCRIPTIONS)].copy()
    tk["is_strike"] = (tk["description"] == "called_strike").astype(int)
    return tk.groupby(["entity_id", "pitch_class"])["is_strike"].agg(
        called_strike_rate="mean", n="size").reset_index()


def _make_called_strike_class_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _taken_class_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["called_strike_rate"]
        sub["ingredients"] = sub.apply(lambda r: {"called_strike_rate": round(float(r.called_strike_rate), 4),
                                                    "n_taken": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _bip_class_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches)
    bip = p[(p["type"] == "X") & p["estimated_woba_using_speedangle"].notna()].copy()
    return bip.groupby(["entity_id", "pitch_class"])["estimated_woba_using_speedangle"].agg(
        xwoba="mean", n="size").reset_index()


def _make_xwoba_class_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _bip_class_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["xwoba"]
        sub["ingredients"] = sub.apply(lambda r: {"xwoba_against": round(float(r.xwoba), 4),
                                                    "n_bip": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


WHIFF_CLASS_BUILDERS = {f"whiff_by_class_{c}": _make_whiff_class_builder(c) for c in PITCH_CLASSES}
CALLED_STRIKE_CLASS_BUILDERS = {f"called_strike_by_class_{c}": _make_called_strike_class_builder(c)
                                 for c in PITCH_CLASSES}
XWOBA_AGAINST_CLASS_BUILDERS = {f"xwoba_against_by_class_{c}": _make_xwoba_class_builder(c)
                                 for c in PITCH_CLASSES}


def _velo_class_table(pitches: pd.DataFrame) -> pd.DataFrame:
    p = _prep(pitches).dropna(subset=["release_speed"])
    return p.groupby(["entity_id", "pitch_class"])["release_speed"].agg(
        velo_mean="mean", velo_std="std", n="size").reset_index()


def _make_velo_mean_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _velo_class_table(pitches)
        sub = g[g["pitch_class"] == cls].copy()
        sub["raw_value"] = sub["velo_mean"]
        sub["ingredients"] = sub.apply(lambda r: {"velo_mean": round(float(r.velo_mean), 2),
                                                    "n_pitches": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


def _make_velo_std_builder(cls: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def build(pitches: pd.DataFrame) -> pd.DataFrame:
        g = _velo_class_table(pitches)
        sub = g[g["pitch_class"] == cls].dropna(subset=["velo_std"]).copy()
        sub["raw_value"] = sub["velo_std"]
        sub["ingredients"] = sub.apply(lambda r: {"velo_std": round(float(r.velo_std), 2),
                                                    "n_pitches": int(r.n)}, axis=1, result_type="reduce")
        return sub[["entity_id", "raw_value", "n", "ingredients"]]
    return build


VELO_MEAN_BUILDERS = {f"velo_mean_{c}": _make_velo_mean_builder(c) for c in PITCH_CLASSES}
VELO_STD_BUILDERS = {f"velo_std_{c}": _make_velo_std_builder(c) for c in PITCH_CLASSES}


def build_velo_decline_in_game(pitches: pd.DataFrame) -> pd.DataFrame:
    """game_pitch_num = cumulative pitch count THIS GAME for this pitcher
    (pitch_number on this corpus is only the PA-local count). Descriptive
    split only -- velo x TTO was tested and FAILED_REPLICATION, see
    TTO_durability's docstring; no causal claim attached here either."""
    p = pitches.dropna(subset=["release_speed"]).sort_values(
        ["game_pk", "pitcher", "at_bat_number", "pitch_number"]).copy()
    p["game_pitch_num"] = p.groupby(["game_pk", "pitcher"]).cumcount() + 1
    p["entity_id"] = p["pitcher"]
    p["bucket"] = np.where(p["game_pitch_num"] <= 25, "first25",
                   np.where(p["game_pitch_num"] > 75, "after75", None))
    p = p.dropna(subset=["bucket"])
    wide = _two_cell(p, "bucket", "release_speed", "first25", "after75",
                      "velo_first25", "n_first25", "velo_after75", "n_after75")
    wide["raw_value"] = wide["velo_after75"] - wide["velo_first25"]
    wide["n"] = wide[["n_first25", "n_after75"]].min(axis=1)
    wide["ingredients"] = wide.apply(lambda r: {
        "velo_first25": round(float(r.velo_first25), 2), "n_first25": int(r.n_first25),
        "velo_after75": round(float(r.velo_after75), 2), "n_after75": int(r.n_after75),
    }, axis=1, result_type="reduce")
    return wide[["entity_id", "raw_value", "n", "ingredients"]]


def _taken_pitcher_frame(pitches: pd.DataFrame) -> pd.DataFrame:
    taken = pitches[pitches["description"].isin(_TAKEN_DESCRIPTIONS)].copy()
    taken = taken.dropna(subset=["plate_x", "plate_z", "sz_top", "sz_bot"])
    taken["entity_id"] = taken["pitcher"]
    taken["is_border"] = classify_borderline(taken).astype(int)
    return taken


def build_command_edge_share(pitches: pd.DataFrame) -> pd.DataFrame:
    t = _taken_pitcher_frame(pitches)
    g = t.groupby("entity_id")["is_border"].agg(edge_share="mean", n="size").reset_index()
    g["raw_value"] = g["edge_share"]
    g["ingredients"] = g.apply(lambda r: {"edge_share": round(float(r.edge_share), 4),
                                           "n_taken": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_command_edge_share_behind(pitches: pd.DataFrame) -> pd.DataFrame:
    t = _taken_pitcher_frame(pitches)
    t = t[t["balls"] > t["strikes"]]
    g = t.groupby("entity_id")["is_border"].agg(edge_share="mean", n="size").reset_index()
    g["raw_value"] = g["edge_share"]
    g["ingredients"] = g.apply(lambda r: {"edge_share": round(float(r.edge_share), 4),
                                           "n_taken_behind": int(r.n)}, axis=1, result_type="reduce")
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    **MIX_BUILDERS,
    "first_pitch_strike_rate": build_first_pitch_strike_rate,
    "putaway_rate": build_putaway_rate,
    **WHIFF_CLASS_BUILDERS,
    **CALLED_STRIKE_CLASS_BUILDERS,
    **XWOBA_AGAINST_CLASS_BUILDERS,
    **VELO_MEAN_BUILDERS,
    **VELO_STD_BUILDERS,
    "velo_decline_in_game": build_velo_decline_in_game,
    "command_edge_share": build_command_edge_share,
    "command_edge_share_behind": build_command_edge_share_behind,
}
