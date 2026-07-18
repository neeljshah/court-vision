"""domains.mlb.profiles.ingredients_batted_ball -- builder functions for the
mlb_batted_ball_quality family (spec_mlb.md Family 1): raw contact-quality
metrics missing from the original 14-attribute registry (exit velocity /
hard-hit rate / barrel rate / BABIP), plus the overall chase_rate builder
that backs a PRE-EXISTING registry entry that was never wired to a builder
(see build_profiles.UNBACKED_ATTRS at the time this was added).

Same builder contract as ingredients_batter.py: each function takes the
season's savant_hitcoords frame (already loaded once per season by
build_profiles.build_all) and returns a tidy per-batter frame with columns
`entity_id`, `raw_value`, `n`, `ingredients`. Reused into the SAME season
loop as every other batter attribute -- no new source path, no new season
set (still savant_hitcoords__{2023,2024,2025}.parquet per build_profiles.py).

BIP (ball in play) = type=='X' (Statcast convention), matching
ingredients_batter.build_pull_tendency/build_contact_quality's own filter.
Verified against real 2024 data before shipping: BIP=124,129, EV present on
123,750 (99.7%), avg EV 88.32, hard-hit share 0.390, barrel share 0.078,
league BABIP 0.290, league chase rate 0.284 -- all in the expected MLB range.

barrel_rate reuses ingredients_batter.build_contact_quality's EXACT formula
(launch_speed_angle==6, Statcast's own published barrel classification --
NOT hand-re-derived from the EV>=98/LA 26-30 widening envelope) under a
second, token-matchable attribute name: "barrel rate" tokenizes to
{barrel, rate}, which the leaderboard resolver's fuzzy matcher can find
directly, while "contact_quality" shares neither token (verified: it never
even reaches the resolver's tie set for that literal phrasing -- see the
spec's resolver-wiring note). Same number, second name, on purpose.

babip = (H - HR) / (AB - K - HR + SF); AB excludes walk/intent_walk/HBP/
sac-fly/sac-bunt/catcher-interference events (standard MLB at-bat
definition). floor=100 AB/season is a SELF-DECLARED qualifying threshold
(spec_mlb.md gave no number) -- roughly a half-season-of-appearances cut.

DESCRIPTIVE only, no causal/predictive claim -- no forecasting/market/$ edge.
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.profiles.ingredients_batter import _SWING_DESCRIPTIONS

_HIT_EVENTS = {"single", "double", "triple", "home_run"}
_HR_EVENT = "home_run"
_K_EVENTS = {"strikeout", "strikeout_double_play"}
_SF_EVENTS = {"sac_fly", "sac_fly_double_play"}
_NON_AB_EVENTS = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_fly_double_play",
                  "sac_bunt", "sac_bunt_double_play", "catcher_interf"}
HARD_HIT_MPH = 95.0


def _bip(frame: pd.DataFrame) -> pd.DataFrame:
    """Balls in play: type=='X', matching ingredients_batter's own filter."""
    return frame[frame["type"] == "X"].copy()


def _ingredients_col(g: pd.DataFrame, row_to_dict) -> pd.Series:
    """g.apply(row_to_dict, axis=1) on a ZERO-ROW frame returns an empty
    DataFrame, not a Series -- a real pandas landmine (a batter-empty season,
    e.g. zero BIP/zero out-of-zone pitches, is a legitimate input here, not
    a hypothetical). Guard it once, shared by every builder below."""
    if g.empty:
        return pd.Series([], dtype=object, index=g.index)
    return g.apply(row_to_dict, axis=1)


def build_avg_exit_velocity(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = _bip(hitcoords).dropna(subset=["launch_speed"])
    g = bip.groupby("batter")["launch_speed"].agg(avg_exit_velocity="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["avg_exit_velocity"]
    g["ingredients"] = _ingredients_col(g, lambda r: {
        "avg_exit_velocity": round(float(r.avg_exit_velocity), 2), "n_batted_balls": int(r.n)})
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_hard_hit_rate(hitcoords: pd.DataFrame) -> pd.DataFrame:
    bip = _bip(hitcoords).dropna(subset=["launch_speed"]).copy()
    bip["is_hard_hit"] = (bip["launch_speed"] >= HARD_HIT_MPH).astype(int)
    g = bip.groupby("batter")["is_hard_hit"].agg(hard_hit_rate="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["hard_hit_rate"]
    g["ingredients"] = _ingredients_col(g, lambda r: {
        "hard_hit_rate": round(float(r.hard_hit_rate), 4), "n_batted_balls": int(r.n)})
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_barrel_rate(hitcoords: pd.DataFrame) -> pd.DataFrame:
    """Same formula as ingredients_batter.build_contact_quality -- see module
    docstring for why this is a second name, not a reimplementation."""
    bip = hitcoords.dropna(subset=["launch_speed_angle"]).copy()
    bip["is_barrel"] = (bip["launch_speed_angle"] == 6).astype(int)
    g = bip.groupby("batter")["is_barrel"].agg(barrel_rate="mean", n="size").reset_index()
    g = g.rename(columns={"batter": "entity_id"})
    g["raw_value"] = g["barrel_rate"]
    g["ingredients"] = _ingredients_col(g, lambda r: {
        "barrel_rate": round(float(r.barrel_rate), 4), "n_batted_balls": int(r.n)})
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_babip(hitcoords: pd.DataFrame) -> pd.DataFrame:
    term = hitcoords[hitcoords["events"].notna()].copy()
    term["entity_id"] = term["batter"]
    term["is_hit"] = term["events"].isin(_HIT_EVENTS).astype(int)
    term["is_hr"] = (term["events"] == _HR_EVENT).astype(int)
    term["is_k"] = term["events"].isin(_K_EVENTS).astype(int)
    term["is_sf"] = term["events"].isin(_SF_EVENTS).astype(int)
    term["is_ab"] = (~term["events"].isin(_NON_AB_EVENTS)).astype(int)
    g = term.groupby("entity_id").agg(
        n_h=("is_hit", "sum"), n_hr=("is_hr", "sum"), n_k=("is_k", "sum"),
        n_sf=("is_sf", "sum"), n_ab=("is_ab", "sum"),
    ).reset_index()
    g["ab_denom"] = g["n_ab"] - g["n_k"] - g["n_hr"] + g["n_sf"]
    g = g[g["ab_denom"] > 0].copy()
    g["raw_value"] = (g["n_h"] - g["n_hr"]) / g["ab_denom"]
    g["n"] = g["n_ab"]
    g["ingredients"] = _ingredients_col(g, lambda r: {
        "n_h": int(r.n_h), "n_hr": int(r.n_hr), "n_k": int(r.n_k),
        "n_sf": int(r.n_sf), "n_ab": int(r.n_ab)})
    return g[["entity_id", "raw_value", "n", "ingredients"]]


def build_chase_rate(pitches: pd.DataFrame) -> pd.DataFrame:
    """Backs the PRE-EXISTING chase_rate registry entry (added for the
    two_strike_chase_rate_rises knowledge-ledger factory mapping, never
    wired to a builder until now -- zero reimplementation of
    ingredients_batter._SWING_DESCRIPTIONS)."""
    p = pitches[pitches["zone"].notna() & (pitches["zone"] >= 11)].copy()
    p["entity_id"] = p["batter"]
    p["is_swing"] = p["description"].isin(_SWING_DESCRIPTIONS).astype(int)
    g = p.groupby("entity_id")["is_swing"].agg(chase_rate="mean", n="size").reset_index()
    g["raw_value"] = g["chase_rate"]
    g["ingredients"] = _ingredients_col(g, lambda r: {
        "chase_rate": round(float(r.chase_rate), 4), "n_out_of_zone": int(r.n)})
    return g[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "avg_exit_velocity": build_avg_exit_velocity,
    "hard_hit_rate": build_hard_hit_rate,
    "barrel_rate": build_barrel_rate,
    "babip": build_babip,
    "chase_rate": build_chase_rate,
}
