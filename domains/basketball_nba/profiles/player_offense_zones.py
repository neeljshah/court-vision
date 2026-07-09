"""PLAYER offense-zone/context/clutch attribute computation -- reads the
per-(game,player) wide table composition/player_offense_events.py builds
(one PBP pass per season, already zone/transition/late-clock/clutch
resolved) and applies floors + finalize_rows, same shape as every other
*_attributes.py module in this package.

24 new attributes across 3 families, all sourced from the SAME season file:
  zone_{attempt_share,efg,assisted_share}_<zone>  x5 zones = 15
  {transition,halfcourt,late_clock}_{efg,attempt_share}           = 6
  clutch_{efg,ft_rate,fga_per_game}                                = 3

CLUTCH FGA/GAME (not FGA/36): true clutch on-court MINUTES needs joint
roster+running-score tracking (which player was on court AND the score was
within 10 AND period>=4 AND clock<=5min, simultaneously) -- no artifact on
disk carries that joint state. clutch_fga_per_game (attempts per game the
player logged >=1 clutch attempt) is used instead, a deliberate, documented
substitution -- ponytail: real per-36 needs stint-membership x running-score
joint tracking, out of scope here.

NETWORK: zero.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import ZONES
from domains.basketball_nba.profiles.profile_compute import (
    REPO_ROOT, exclude_negative_ids, finalize_rows, rel_sources,
)

_COMPOSITION = REPO_ROOT / "data" / "cache" / "team_system" / "composition"
_THREE_ZONES = {"corner3", "above_break_3"}

ZONE_FLOOR_FGA = 25.0
CONTEXT_FLOOR_FGA = 25.0
CLUTCH_FLOOR_FGA = 30.0


def _window(season: str) -> str:
    return f"season_{season}"


def _season_src(season: str) -> Path:
    return _COMPOSITION / f"player_offense_events_{season}.parquet"


def _load_season_table(season: str) -> pd.DataFrame:
    src = _season_src(season)
    if not src.exists():
        return pd.DataFrame()
    return exclude_negative_ids(pd.read_parquet(src), "player_id")


def _season_agg(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    agg = {c: (c, "sum") for c in cols}
    agg["player_name"] = ("player_name", "first")
    return df.groupby("player_id").agg(**agg).reset_index()


def build_zone_shooting(season: str) -> list[dict]:
    df = _load_season_table(season)
    if df.empty:
        return []
    zone_cols = [f"{z}_{m}" for z in ZONES for m in ("fga", "fgm", "assisted")]
    agg = _season_agg(df, ["total_fga", "total_fgm"] + zone_cols)
    src = rel_sources(_season_src(season))
    rows: list[dict] = []
    for z in ZONES:
        mult = 1.5 if z in _THREE_ZONES else 1.0
        zdf = agg[agg[f"{z}_fga"] >= ZONE_FLOOR_FGA].copy()
        if zdf.empty:
            continue
        zdf["attempt_share"] = zdf[f"{z}_fga"] / zdf["total_fga"]
        zdf["efg"] = (zdf[f"{z}_fgm"] * mult) / zdf[f"{z}_fga"]
        rows.extend(finalize_rows(
            zdf, entity_col="player_id", name_col="player_name", raw_col="attempt_share", n_col=f"{z}_fga",
            window=_window(season), attribute=f"zone_attempt_share_{z}", status="DESCRIPTIVE", sources=src,
            ingredient_cols=[f"{z}_fga", "total_fga"],
        ))
        rows.extend(finalize_rows(
            zdf, entity_col="player_id", name_col="player_name", raw_col="efg", n_col=f"{z}_fga",
            window=_window(season), attribute=f"zone_efg_{z}", status="DESCRIPTIVE", sources=src,
            ingredient_cols=[f"{z}_fgm", f"{z}_fga"],
        ))
        assisted_ok = zdf[zdf[f"{z}_fgm"] > 0].copy()
        assisted_ok["assisted_share"] = assisted_ok[f"{z}_assisted"] / assisted_ok[f"{z}_fgm"]
        rows.extend(finalize_rows(
            assisted_ok, entity_col="player_id", name_col="player_name", raw_col="assisted_share", n_col=f"{z}_fga",
            window=_window(season), attribute=f"zone_assisted_share_{z}", status="DESCRIPTIVE", sources=src,
            ingredient_cols=[f"{z}_assisted", f"{z}_fgm"],
        ))
    return rows


def build_play_context(season: str) -> list[dict]:
    df = _load_season_table(season)
    if df.empty:
        return []
    cols = [
        "total_fga", "transition_fga", "transition_fgm", "transition_fg3m",
        "halfcourt_fga", "halfcourt_fgm", "halfcourt_fg3m",
        "late_clock_fga", "late_clock_fgm", "late_clock_fg3m",
    ]
    agg = _season_agg(df, cols)
    src = rel_sources(_season_src(season))
    rows: list[dict] = []
    for prefix in ("transition", "halfcourt", "late_clock"):
        sub = agg[agg[f"{prefix}_fga"] >= CONTEXT_FLOOR_FGA].copy()
        if sub.empty:
            continue
        sub["efg"] = (sub[f"{prefix}_fgm"] + 0.5 * sub[f"{prefix}_fg3m"]) / sub[f"{prefix}_fga"]
        sub["attempt_share"] = sub[f"{prefix}_fga"] / sub["total_fga"]
        rows.extend(finalize_rows(
            sub, entity_col="player_id", name_col="player_name", raw_col="efg", n_col=f"{prefix}_fga",
            window=_window(season), attribute=f"{prefix}_efg", status="DESCRIPTIVE", sources=src,
            ingredient_cols=[f"{prefix}_fgm", f"{prefix}_fg3m", f"{prefix}_fga"],
        ))
        rows.extend(finalize_rows(
            sub, entity_col="player_id", name_col="player_name", raw_col="attempt_share", n_col=f"{prefix}_fga",
            window=_window(season), attribute=f"{prefix}_attempt_share", status="DESCRIPTIVE", sources=src,
            ingredient_cols=[f"{prefix}_fga", "total_fga"],
        ))
    return rows


def build_clutch(season: str) -> list[dict]:
    df = _load_season_table(season)
    if df.empty:
        return []
    agg = _season_agg(df, ["clutch_fga", "clutch_fgm", "clutch_fg3m", "clutch_fta"])
    games = df[df["clutch_fga"] > 0].groupby("player_id")["game_id"].nunique().rename("n_games")
    agg = agg.merge(games, on="player_id", how="left").fillna({"n_games": 0})
    agg = agg[agg["clutch_fga"] >= CLUTCH_FLOOR_FGA].copy()
    if agg.empty:
        return []
    agg["efg"] = (agg["clutch_fgm"] + 0.5 * agg["clutch_fg3m"]) / agg["clutch_fga"]
    agg["ft_rate"] = agg["clutch_fta"] / agg["clutch_fga"]
    agg["fga_per_game"] = agg["clutch_fga"] / agg["n_games"]
    src = rel_sources(_season_src(season))
    rows: list[dict] = []
    rows.extend(finalize_rows(
        agg, entity_col="player_id", name_col="player_name", raw_col="efg", n_col="clutch_fga",
        window=_window(season), attribute="clutch_efg", status="DESCRIPTIVE", sources=src,
        ingredient_cols=["clutch_fgm", "clutch_fg3m", "clutch_fga"],
    ))
    rows.extend(finalize_rows(
        agg, entity_col="player_id", name_col="player_name", raw_col="ft_rate", n_col="clutch_fga",
        window=_window(season), attribute="clutch_ft_rate", status="DESCRIPTIVE", sources=src,
        ingredient_cols=["clutch_fta", "clutch_fga"],
    ))
    rows.extend(finalize_rows(
        agg, entity_col="player_id", name_col="player_name", raw_col="fga_per_game", n_col="clutch_fga",
        window=_window(season), attribute="clutch_fga_per_game", status="DESCRIPTIVE", sources=src,
        ingredient_cols=["clutch_fga", "n_games"],
    ))
    return rows


BUILDERS = [build_zone_shooting, build_play_context, build_clutch]


def build_all_player_offense_zone_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
