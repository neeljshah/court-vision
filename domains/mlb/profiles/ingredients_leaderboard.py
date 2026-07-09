"""domains.mlb.profiles.ingredients_leaderboard -- builder functions for the
leaderboard-sourced MLB attribute families (bat-tracking, outs-above-average,
catch-probability). Unlike ingredients_batter/pitcher/catcher.py (which take
the season's pitch-level savant_hitcoords frame), these read directly from a
Baseball Savant per-year LEADERBOARD csv (data/cache/statcast/leaderboards/,
see scripts/platformkit/data_frontier/savant_bat_tracking.py for the puller +
column semantics) -- one row per player-year already aggregated by Savant, so
raw_value is the leaderboard's own column, never re-derived from pitches.

Same OUTPUT shape as the other ingredients_*.py builders: entity_id /
raw_value / n / ingredients. Builder SIGNATURE differs on purpose --
Callable[[str], pd.DataFrame] keyed by YEAR, not the pitch-frame -- since
build_profiles.py's SEASONS pitch-frame loop has nothing to hand these; see
build_profiles.py's separate LEADERBOARD_YEARS loop.

outs_above_average's CSV carries no chances/qualification column of its own;
range_oaa's n is cross-joined from catch_probability's total chances (sum of
n_opp_Xstars across all 5 difficulty buckets, same player_id+year) -- an
honest documented join, not a fabricated denominator.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_DIR = REPO_ROOT / "data" / "cache" / "statcast" / "leaderboards"

ATTR_TO_FAMILY = {
    "swing_speed": "bat_tracking",
    "squared_up_rate": "bat_tracking",
    "blast_rate": "bat_tracking",
    "sword_rate": "bat_tracking",
    "range_oaa": "outs_above_average",
    "difficult_play_conversion": "catch_probability",
}


def _read(family: str, year: str) -> pd.DataFrame:
    return pd.read_csv(_DIR / f"{family}_{year}.csv", encoding="utf-8-sig")


def _bat_tracking(year: str) -> pd.DataFrame:
    df = _read("bat_tracking", year).rename(columns={"id": "entity_id"})
    df["n"] = df["swings_competitive"]
    return df


def build_swing_speed(year: str) -> pd.DataFrame:
    df = _bat_tracking(year)
    df["raw_value"] = df["avg_bat_speed"]
    df["ingredients"] = df.apply(lambda r: {
        "avg_bat_speed": round(float(r.avg_bat_speed), 4),
        "swings_competitive": int(r.swings_competitive)}, axis=1)
    return df[["entity_id", "raw_value", "n", "ingredients"]]


def build_squared_up_rate(year: str) -> pd.DataFrame:
    df = _bat_tracking(year)
    df["raw_value"] = df["squared_up_per_swing"]
    df["ingredients"] = df.apply(lambda r: {
        "squared_up_per_swing": round(float(r.squared_up_per_swing), 4),
        "swings_competitive": int(r.swings_competitive)}, axis=1)
    return df[["entity_id", "raw_value", "n", "ingredients"]]


def build_blast_rate(year: str) -> pd.DataFrame:
    df = _bat_tracking(year)
    df["raw_value"] = df["blast_per_swing"]
    df["ingredients"] = df.apply(lambda r: {
        "blast_per_swing": round(float(r.blast_per_swing), 4),
        "swings_competitive": int(r.swings_competitive)}, axis=1)
    return df[["entity_id", "raw_value", "n", "ingredients"]]


def build_sword_rate(year: str) -> pd.DataFrame:
    df = _bat_tracking(year)
    df = df[df["swings_competitive"] > 0].copy()
    df["raw_value"] = df["swords"] / df["swings_competitive"]
    df["ingredients"] = df.apply(lambda r: {
        "swords": int(r.swords), "swings_competitive": int(r.swings_competitive)}, axis=1)
    return df[["entity_id", "raw_value", "n", "ingredients"]]


def build_range_oaa(year: str) -> pd.DataFrame:
    oaa = _read("outs_above_average", year).rename(columns={"player_id": "entity_id"})
    cp = _read("catch_probability", year).rename(columns={"player_id": "entity_id"})
    star_cols = [c for c in cp.columns if c.startswith("n_opp_")]
    cp = cp.copy()
    cp["n"] = cp[star_cols].sum(axis=1)
    joined = oaa.merge(cp[["entity_id", "n"]], on="entity_id", how="inner")
    joined["raw_value"] = joined["outs_above_average"].astype(float)
    joined["ingredients"] = joined.apply(lambda r: {
        "outs_above_average": int(r.outs_above_average),
        "n_chances_catch_prob": int(r.n)}, axis=1)
    return joined[["entity_id", "raw_value", "n", "ingredients"]]


def build_difficult_play_conversion(year: str) -> pd.DataFrame:
    df = _read("catch_probability", year).rename(columns={"player_id": "entity_id"})
    df = df[df["n_opp_1stars"] > 0].copy()
    df["raw_value"] = df["n_fieldout_1stars"] / df["n_opp_1stars"]
    df["n"] = df["n_opp_1stars"]
    df["ingredients"] = df.apply(lambda r: {
        "n_fieldout_1stars": int(r.n_fieldout_1stars),
        "n_opp_1stars": int(r.n_opp_1stars)}, axis=1)
    return df[["entity_id", "raw_value", "n", "ingredients"]]


BUILDERS = {
    "swing_speed": build_swing_speed,
    "squared_up_rate": build_squared_up_rate,
    "blast_rate": build_blast_rate,
    "sword_rate": build_sword_rate,
    "range_oaa": build_range_oaa,
    "difficult_play_conversion": build_difficult_play_conversion,
}

assert set(BUILDERS) == set(ATTR_TO_FAMILY)
