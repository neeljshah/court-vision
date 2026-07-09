"""domains.tennis.profiles.ingredients -- shared ingredient builders for the
tennis attribute engine. REUSES prereg_point_mechanisms.py (charting point
extraction + match-level agg), pressure_claims.py (break-point mechanism
snapshot), and serve_return_profiles.py (match-aggregate serve/return) --
no reimplementation of any of that machinery.

Entity key: name_aliases.normalize_name(name, source="sackmann") -- the SAME
canonical key space this domain already uses to join tennis-data odds to
Sackmann matches, so charting-parsed names ("Rafael_Nadal") and
matches.parquet/serve_return_profiles p1_name/player_name ("Rafael Nadal")
land on the identical entity_id with zero new joining logic.

Windows: "YYYY" (calendar year) or "career_to_2026" (whole corpus). A
per-year row is built whenever THAT year alone clears the attribute's
floor; a career_to_2026 row is ALSO always attempted from full history, so
a player who never clears one year can still surface once career volume
accumulates -- both windows emitted, never just one (declared, see task's
"prefer per-year where n allows").

surface_splits is career-only (declared in attribute_registry.py): cutting
an already-yearly-thin point corpus 3 ways by surface starves almost every
per-year floor.

NETWORK: zero.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from domains.tennis.name_aliases import normalize_name
from domains.tennis.prereg_point_mechanisms import (
    REPO_ROOT, _charting_match_ids, _id_frame, _match_level_agg, charting_point_state,
)
from domains.tennis.pressure_claims import CLAIMS_SNAPSHOT_PATH, build_pressure_claims
from domains.tennis.serve_return_profiles import build_profiles as build_match_agg_profiles

_RAW_CHARTING_DIR = REPO_ROOT / "data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject"
CAREER_WINDOW = "career_to_2026"


def _entity_from_underscored(name: str) -> tuple[str, str]:
    """'Rafael_Nadal' (charting match_id token) -> (entity_id, display_name)."""
    display = str(name).replace("_", " ").strip()
    return normalize_name(display, source="sackmann"), display


def charting_match_level(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """One row per (match_id, entity_id): serve_won/serve_n/return_won/
    return_n/date, via prereg_point_mechanisms' OWN _match_level_agg --
    zero reimplementation."""
    ids = _charting_match_ids(chart_raw["match_id"])
    state = charting_point_state(chart_raw)
    agg = _match_level_agg(state, ids)
    ent = agg["player_id"].map(_entity_from_underscored)
    agg = agg.assign(entity_id=[t[0] for t in ent], entity_name=[t[1] for t in ent])
    agg["year"] = pd.to_datetime(agg["date"]).dt.year
    return agg


def _window_rollup(match_lvl: pd.DataFrame, won_col: str, n_col: str, floor: int) -> pd.DataFrame:
    """Per-entity per-year rows clearing `floor` on n_col, PLUS one
    per-entity career_to_2026 row (summed across all years) if it clears
    floor too. Returns entity_id/entity_name/window/won/n/rate."""
    def _rollup(df: pd.DataFrame) -> pd.DataFrame:
        g = df.groupby(["entity_id", "entity_name", "window"], as_index=False).agg(
            won=(won_col, "sum"), n=(n_col, "sum"))
        return g[g["n"] >= floor]

    yearly = match_lvl.assign(window=match_lvl["year"].astype(int).astype(str))
    career = match_lvl.assign(window=CAREER_WINDOW)
    out = pd.concat([_rollup(yearly), _rollup(career)], ignore_index=True)
    out["rate"] = out["won"] / out["n"]
    return out


def point_serve_ingredient(chart_raw: pd.DataFrame, floor: int) -> pd.DataFrame:
    ml = charting_match_level(chart_raw)
    return _window_rollup(ml, "serve_won", "serve_n", floor)


def point_return_ingredient(chart_raw: pd.DataFrame, floor: int) -> pd.DataFrame:
    ml = charting_match_level(chart_raw)
    return _window_rollup(ml, "return_won", "return_n", floor)


def match_agg_ingredient() -> pd.DataFrame:
    """serve_return_profiles' own per (player_id, season, tour) serve/return
    strengths, re-keyed to entity_id -- ATP+WTA tour collapsed (weighted by
    n_matches; real player-name collisions across tours are not expected)
    and ALSO rolled up into one career_to_2026 row."""
    prof = build_match_agg_profiles().copy()
    prof["entity_id"] = prof["player_name"].map(lambda n: normalize_name(n, source="sackmann"))
    prof["_sw"] = prof["serve_strength"] * prof["n_matches"]
    prof["_rw"] = prof["return_strength"] * prof["n_matches"]

    def _rollup(df: pd.DataFrame) -> pd.DataFrame:
        g = df.groupby(["entity_id", "window"], as_index=False).agg(
            entity_name=("player_name", "first"), sw=("_sw", "sum"), rw=("_rw", "sum"),
            n_matches=("n_matches", "sum"))
        g["serve_strength"] = g["sw"] / g["n_matches"]
        g["return_strength"] = g["rw"] / g["n_matches"]
        return g[["entity_id", "entity_name", "window", "serve_strength", "return_strength", "n_matches"]]

    yearly = prof.assign(window=prof["season"].astype(int).astype(str))
    career = prof.assign(window=CAREER_WINDOW)
    return pd.concat([_rollup(yearly), _rollup(career)], ignore_index=True)


def charting_serve_split(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """Per point: entity_id/entity_name/year/is_second_serve/won, straight
    off server/point_winner/is_second_serve -- NO score-state filtering
    (unlike charting_point_state, which drops non-standard/tiebreak rows;
    irrelevant here since 1st-vs-2nd-serve win rate is well-defined on
    every point, tiebreak or not)."""
    d = chart_raw[(chart_raw["date_source"] != "missing")
                  & chart_raw["server"].isin((1, 2))
                  & chart_raw["point_winner"].isin((1, 2))].copy()
    idf = _id_frame(_charting_match_ids(d["match_id"]))
    d = d.merge(idf, on="match_id", how="left")
    server = d["server"].astype(int)
    name = np.where(server == 1, d["p1_id"], d["p2_id"])
    ent = pd.Series(name).map(_entity_from_underscored)
    d["entity_id"] = [t[0] for t in ent]
    d["entity_name"] = [t[1] for t in ent]
    d["won"] = (d["point_winner"].astype(int) == server.to_numpy()).astype(int)
    d["year"] = pd.to_datetime(d["date"]).dt.year
    return d[["entity_id", "entity_name", "year", "is_second_serve", "won"]]


def second_serve_ingredient(chart_raw: pd.DataFrame, floor_each: int) -> pd.DataFrame:
    """entity_id/entity_name/window/first_rate/second_rate/first_n/second_n,
    both sides floored independently."""
    d = charting_serve_split(chart_raw)

    def _side(is_second: bool, label: str) -> pd.DataFrame:
        sub = d[d["is_second_serve"] == is_second]
        yearly = sub.assign(window=sub["year"].astype(int).astype(str))
        career = sub.assign(window=CAREER_WINDOW)
        g = pd.concat([yearly, career], ignore_index=True).groupby(
            ["entity_id", "entity_name", "window"], as_index=False).agg(won=("won", "sum"), n=("won", "count"))
        return g.rename(columns={"won": f"{label}_won", "n": f"{label}_n"})

    merged = _side(False, "first").merge(_side(True, "second"), on=["entity_id", "entity_name", "window"], how="inner")
    merged = merged[(merged["first_n"] >= floor_each) & (merged["second_n"] >= floor_each)].copy()
    merged["first_rate"] = merged["first_won"] / merged["first_n"]
    merged["second_rate"] = merged["second_won"] / merged["second_n"]
    return merged


def _charting_surfaces() -> pd.DataFrame:
    """match_id -> surface, from charting-m/w-matches.csv's own Surface
    column (100% coverage against charting_points.parquet match_ids,
    verified). Drops a handful of corrupt CSV rows + rare Carpet."""
    frames = [pd.read_csv(_RAW_CHARTING_DIR / f, dtype=str, usecols=["match_id", "Surface"])
              for f in ("charting-m-matches.csv", "charting-w-matches.csv")]
    out = pd.concat(frames, ignore_index=True).rename(columns={"Surface": "surface"})
    return out[out["surface"].isin(("Hard", "Clay", "Grass"))]


def surface_ingredient(chart_raw: pd.DataFrame, floor: int) -> pd.DataFrame:
    """Career-only serve/return win rate by surface."""
    ml = charting_match_level(chart_raw)
    surf = _charting_surfaces()
    ml = ml.merge(surf, on="match_id", how="inner")
    g = ml.groupby(["entity_id", "entity_name", "surface"], as_index=False).agg(
        serve_won=("serve_won", "sum"), serve_n=("serve_n", "sum"),
        return_won=("return_won", "sum"), return_n=("return_n", "sum"))
    g["serve_rate"] = g["serve_won"] / g["serve_n"]
    g["return_rate"] = g["return_won"] / g["return_n"]
    return g[(g["serve_n"] >= floor) | (g["return_n"] >= floor)]


def pressure_ingredient(chart_raw: pd.DataFrame) -> pd.DataFrame:
    """REUSES pressure_claims.build_pressure_claims verbatim (it writes its
    own UNFILTERED snapshot at CLAIMS_SNAPSHOT_PATH) and reads that snapshot
    back -- zero reimplementation of the break-point mechanism math."""
    build_pressure_claims(chart_raw)
    snap = pd.read_parquet(CLAIMS_SNAPSHOT_PATH)
    ent = snap["player_name"].map(_entity_from_underscored)
    snap = snap.assign(entity_id=[t[0] for t in ent], entity_name=[t[1] for t in ent])
    return snap
