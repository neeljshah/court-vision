"""LINEUP attribute computation -- entity_id is the lineup_key string
(comma-joined sorted player_ids), floor >=100 min OR >=200s per attribute
(see attribute_registry.py).

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
_INTERACTIONS = REPO_ROOT / "data" / "cache" / "team_system" / "interactions"


def _window(season: str) -> str:
    return f"season_{season}"


def _lineup_min_member(lineup_key: str) -> int:
    parts = [p for p in str(lineup_key).split(",") if p.lstrip("-").isdigit()]
    return min((int(p) for p in parts), default=-1)


def build_spacing(season: str) -> list[dict]:
    src = _LINEUPS / f"lineup_spacing_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df["min_member_id"] = df["lineup_key"].map(_lineup_min_member)
    df = exclude_negative_ids(df, "min_member_id")
    df = df[df["n_shots"] >= 100.0]
    return finalize_rows(
        df, entity_col="lineup_key", name_col=None, raw_col="spacing_mean_dist", n_col="n_shots",
        window=_window(season), attribute="spacing", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["n_shots"], entity_id_int=False,
    )


def build_synergy_residual(season: str) -> list[dict]:
    src = _INTERACTIONS / f"lineup_synergy_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    df = exclude_negative_ids(df, "min_member_id")
    df = df[df["min"] >= 100.0].copy()
    df["raw_value"] = df["net_per48"] - df["expected_net_per48"]
    return finalize_rows(
        df, entity_col="lineup_key", name_col=None, raw_col="raw_value", n_col="min",
        window=_window(season), attribute="synergy_residual", status="VALIDATED_CLAIM", sources=rel_sources(src),
        ingredient_cols=["net_per48", "expected_net_per48"], entity_id_int=False,
    )


def build_continuity_s(season: str) -> list[dict]:
    src = _LINEUPS / f"stints_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    grp = df.groupby("lineup_key").agg(raw_value=("elapsed_s", "sum"), n_stints=("elapsed_s", "count")).reset_index()
    grp["min_member_id"] = grp["lineup_key"].map(_lineup_min_member)
    grp = exclude_negative_ids(grp, "min_member_id")
    grp = grp[grp["raw_value"] >= 200.0]
    return finalize_rows(
        grp, entity_col="lineup_key", name_col=None, raw_col="raw_value", n_col="n_stints",
        window=_window(season), attribute="continuity_s", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["n_stints"], entity_id_int=False,
    )


def build_matchup_net(season: str) -> list[dict]:
    src = _LINEUPS / f"lineup_matchups_{season}.parquet"
    if not src.exists():
        return []
    df = pd.read_parquet(src)
    side_a = df.rename(columns={"lineup_key_a": "lineup_key", "pts_a": "pts_for", "pts_b": "pts_against"})
    side_b = df.rename(columns={"lineup_key_b": "lineup_key", "pts_b": "pts_for", "pts_a": "pts_against"})
    both = pd.concat([side_a[["lineup_key", "pts_for", "pts_against", "overlap_s"]],
                       side_b[["lineup_key", "pts_for", "pts_against", "overlap_s"]]], ignore_index=True)
    both["net"] = both["pts_for"] - both["pts_against"]
    grp = both.groupby("lineup_key").agg(net_sum=("net", "sum"), overlap_s_sum=("overlap_s", "sum")).reset_index()
    grp["min_member_id"] = grp["lineup_key"].map(_lineup_min_member)
    grp = exclude_negative_ids(grp, "min_member_id")
    grp = grp[grp["overlap_s_sum"] >= 200.0].copy()
    grp["raw_value"] = grp["net_sum"] / grp["overlap_s_sum"] * 300.0
    return finalize_rows(
        grp, entity_col="lineup_key", name_col=None, raw_col="raw_value", n_col="overlap_s_sum",
        window=_window(season), attribute="matchup_net", status="DESCRIPTIVE", sources=rel_sources(src),
        ingredient_cols=["net_sum", "overlap_s_sum"], entity_id_int=False,
    )


BUILDERS = [build_spacing, build_synergy_residual, build_continuity_s, build_matchup_net]


def build_all_lineup_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
