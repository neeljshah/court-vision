"""PLAYER shooting-rate attributes (coverage_stress Family A, spec sec 11):
fg3_pct, ft_pct, fg_pct, efg, ts_pct, pts_per36, ppg -- direct player_box
scores.parquet aggregates, same "no PBP join" pattern as player_box_derived.py.

ROOT-CAUSE NOTE: claims_grid.py's nba_player_box_rate family already has a
pts_per_game dim, but that feeds the CLAIMS store (data/cache/intel_claims),
not data/cache/profiles/nba_player_profiles.parquet -- no player_stat/ranking
resolver reads it (grep confirmed, see spec_nba.md sec "Root-cause note").
claims_grid.py ALSO explicitly removed every shooting-PERCENTAGE dim
(fg_pct/fg3_pct/ft_pct/ts_pct/efg_pct) because its factory floors are
count_distinct-only (no sum-based volume floor) -- see claims_grid.py's
FIX-ROUND NOTE. This module builds those as first-class profile attributes
with a REAL attempt-volume floor (fg3a/fta/fga/min), stored as the attribute's
own `n` column so leaderboard_resolver's plain `n`-floor path works with no
_ZONE_DENOM_KEYS-style workaround.

Floors (attempt-based, the whole point -- a games-only floor lets a 2-3
attempt outlier top a percentage leaderboard, proven in claims_grid.py):
    fg3_pct        fg3a >= 100
    ft_pct         fta  >= 50
    fg_pct/efg/ts_pct   fga >= 200
    pts_per36/ppg  min  >= 200

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}

FLOOR_FG3A = 100.0
FLOOR_FTA = 50.0
FLOOR_FGA = 200.0
FLOOR_MIN = 200.0


def _window(season: str) -> str:
    return f"season_{season}"


def _load_box(season: str) -> pd.DataFrame | None:
    if season not in _BOX_SEASONS or not _BOX.exists():
        return None
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    if box.empty:
        return None
    return exclude_negative_ids(box, "player_id")


def _agg(box: pd.DataFrame) -> pd.DataFrame:
    return box.groupby("player_id").agg(
        pts=("pts", "sum"), min=("min", "sum"),
        fgm=("fgm", "sum"), fga=("fga", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"),
        n_games=("game_id", "nunique"),
        entity_name=("player_name", "first"),
    ).reset_index()


def build_fg3_pct(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["fg3a"] >= FLOOR_FG3A].copy()
    g["raw_value"] = g["fg3m"] / g["fg3a"]
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="fg3a",
        window=_window(season), attribute="fg3_pct", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["fg3m", "fg3a"],
    )


def build_ft_pct(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["fta"] >= FLOOR_FTA].copy()
    g["raw_value"] = g["ftm"] / g["fta"]
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="fta",
        window=_window(season), attribute="ft_pct", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["ftm", "fta"],
    )


def build_fg_pct(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["fga"] >= FLOOR_FGA].copy()
    g["raw_value"] = g["fgm"] / g["fga"]
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="fga",
        window=_window(season), attribute="fg_pct", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["fgm", "fga"],
    )


def build_efg(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["fga"] >= FLOOR_FGA].copy()
    g["raw_value"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"]
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="fga",
        window=_window(season), attribute="efg", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["fgm", "fg3m", "fga"],
    )


def build_ts_pct(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["fga"] >= FLOOR_FGA].copy()
    denom = 2.0 * (g["fga"] + 0.44 * g["fta"])
    g = g[denom > 0].copy()
    g["raw_value"] = g["pts"] / (2.0 * (g["fga"] + 0.44 * g["fta"]))
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="fga",
        window=_window(season), attribute="ts_pct", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["pts", "fga", "fta"],
    )


def build_pts_per36(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["min"] >= FLOOR_MIN].copy()
    g["raw_value"] = g["pts"] / g["min"] * 36.0
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="pts_per36", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["pts", "min"],
    )


def build_ppg(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    g = _agg(box)
    g = g[g["min"] >= FLOOR_MIN].copy()
    g["raw_value"] = g["pts"] / g["n_games"]
    return finalize_rows(
        g, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="n_games",
        window=_window(season), attribute="ppg", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["pts", "n_games"],
    )


BUILDERS = [build_fg3_pct, build_ft_pct, build_fg_pct, build_efg, build_ts_pct, build_pts_per36, build_ppg]


def build_all_player_box_shooting_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
