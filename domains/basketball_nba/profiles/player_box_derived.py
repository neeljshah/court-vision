"""PLAYER box-derived rate attributes: oreb_per36/oreb_share, dreb_per36/
dreb_share, stocks_per36 (stl+blk), ast_to_tov -- all cheap, direct
player_boxscores.parquet aggregates (same pattern as player_fouls.py's
pf_per36: no PBP join, no lineup on/off split). These close the "derivable
boxscore stat" gap (coverage_stress: "What is Julius Randle's offensive
rebound rate?" had no answerable attribute even though oreb/dreb/reb are
already on disk) WITHOUT duplicating the existing PBP-joined oreb_pct/
dreb_pct attributes in player_rebounding.py (those are a different,
harder-won opportunity-share proxy; these are the plain per-36/ratio reads).

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_BOX_SEASONS = {"2024_25", "2025_26"}
_MIN_FLOOR = 200.0


def _window(season: str) -> str:
    return f"season_{season}"


def _load_box(season: str) -> pd.DataFrame | None:
    if season not in _BOX_SEASONS or not _BOX.exists():
        return None
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == season.replace("_", "-")]
    return exclude_negative_ids(box, "player_id")


def build_oreb_rate(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    grp = box.groupby("player_id").agg(
        oreb=("oreb", "sum"), reb=("reb", "sum"), min=("min", "sum"),
        entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[grp["min"] >= _MIN_FLOOR].copy()
    rows = []
    grp["raw_value"] = grp["oreb"] / grp["min"] * 36.0
    rows += finalize_rows(
        grp, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="oreb_per36", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["oreb", "min"],
    )
    share = grp[grp["reb"] > 0].copy()
    share["raw_value"] = share["oreb"] / share["reb"]
    rows += finalize_rows(
        share, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="oreb_share", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["oreb", "reb"],
    )
    return rows


def build_dreb_rate(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    grp = box.groupby("player_id").agg(
        dreb=("dreb", "sum"), reb=("reb", "sum"), min=("min", "sum"),
        entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[grp["min"] >= _MIN_FLOOR].copy()
    rows = []
    grp["raw_value"] = grp["dreb"] / grp["min"] * 36.0
    rows += finalize_rows(
        grp, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="dreb_per36", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["dreb", "min"],
    )
    share = grp[grp["reb"] > 0].copy()
    share["raw_value"] = share["dreb"] / share["reb"]
    rows += finalize_rows(
        share, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="dreb_share", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["dreb", "reb"],
    )
    return rows


def build_stocks_per36(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    grp = box.groupby("player_id").agg(
        stl=("stl", "sum"), blk=("blk", "sum"), min=("min", "sum"),
        entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[grp["min"] >= _MIN_FLOOR].copy()
    grp["raw_value"] = (grp["stl"] + grp["blk"]) / grp["min"] * 36.0
    return finalize_rows(
        grp, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="stocks_per36", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["stl", "blk", "min"],
    )


def build_ast_to_tov(season: str) -> list[dict]:
    box = _load_box(season)
    if box is None:
        return []
    grp = box.groupby("player_id").agg(
        ast=("ast", "sum"), tov=("tov", "sum"), min=("min", "sum"),
        entity_name=("player_name", "first"),
    ).reset_index()
    grp = grp[(grp["min"] >= _MIN_FLOOR) & (grp["tov"] > 0)].copy()
    grp["raw_value"] = grp["ast"] / grp["tov"]
    return finalize_rows(
        grp, entity_col="player_id", name_col="entity_name", raw_col="raw_value", n_col="min",
        window=_window(season), attribute="ast_to_tov", status="DESCRIPTIVE", sources=rel_sources(_BOX),
        ingredient_cols=["ast", "tov"],
    )


BUILDERS = [build_oreb_rate, build_dreb_rate, build_stocks_per36, build_ast_to_tov]


def build_all_player_box_derived_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
