"""last20_<season> window multipliers -- recency-windowed variants of the
requested highest-value player attributes. Reuses the SAME 'last_n_games'
mechanic scripts/platformkit/intel_validation/aggregate_recompute.py's
window_spec applies for claims (sort by date, tail(n) per group), so profile
rows and any future claim on them agree mechanically.

Only 2 of the requested 6 attributes (gravity, usage_absorption, scoring
zones rim/three eFG, spacing_contribution) have per-GAME granularity on disk
to slice a last-20 window from: gravity_proxy_<season>.parquet, usage_
redistribution_<season>.parquet, and lineup_spacing_<season>.parquet are all
SEASON-level aggregates (verified: no game_id/date column). Windowing those
would mean rebuilding the underlying on/off or lineup-membership mechanism
at per-game grain -- out of scope for this pass. DEFERRED, not faked:
gravity/usage_absorption/spacing_contribution have no last20 window here.

WHAT IS BUILT: last20 zone_efg_rim (from this lane's own player_offense_
events_<season>.parquet, aggregated per-game already) and last20 shot_zone_
three_efg (from player_boxscores.parquet's own per-game rows -- reuses that
attribute's EXACT existing formula/ingredients, just windowed).

Because each source is loaded from a SINGLE season's own file (composition
table is one-file-per-season; player_boxscores is filtered to `season==
label` before windowing), 'last 20 games' can never cross a season boundary
by construction -- see test_player_offense_windows.py's leak check.

NETWORK: zero.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.profiles.player_attributes import _BOX
from domains.basketball_nba.profiles.player_offense_zones import (
    _load_season_table, _season_src,
)
from domains.basketball_nba.profiles.profile_compute import (
    exclude_negative_ids, finalize_rows, rel_sources,
)

LAST_N_GAMES = 20
RIM_LAST20_FLOOR_FGA = 10.0
THREE_LAST20_FLOOR_FGA = 15.0


def last_n_games(df: pd.DataFrame, group_col: str, date_col: str, n: int) -> pd.DataFrame:
    """SAME mechanic as aggregate_recompute.apply_window_spec's
    'last_n_games' kind: sort by date ascending, keep the LAST n rows per
    group. Pure, no disk I/O -- unit-tested directly."""
    return df.sort_values(date_col).groupby(group_col, group_keys=False).tail(n)


def _last20_window(season: str) -> str:
    return f"last20_{season}"


def build_last20_zone_efg_rim(season: str) -> list[dict]:
    df = _load_season_table(season)
    if df.empty or "date" not in df.columns:
        return []
    df = df.dropna(subset=["date"])
    windowed = last_n_games(df, "player_id", "date", LAST_N_GAMES)
    agg = windowed.groupby("player_id").agg(
        rim_fga=("rim_fga", "sum"), rim_fgm=("rim_fgm", "sum"),
        n_games=("game_id", "nunique"), player_name=("player_name", "first"),
    ).reset_index()
    agg = agg[agg["rim_fga"] >= RIM_LAST20_FLOOR_FGA].copy()
    if agg.empty:
        return []
    agg["efg"] = agg["rim_fgm"] / agg["rim_fga"]  # rim is always a 2pt attempt
    return finalize_rows(
        agg, entity_col="player_id", name_col="player_name", raw_col="efg", n_col="rim_fga",
        window=_last20_window(season), attribute="zone_efg_rim", status="DESCRIPTIVE",
        sources=rel_sources(_season_src(season)), ingredient_cols=["rim_fgm", "rim_fga", "n_games"],
    )


def build_last20_shot_zone_three_efg(season: str) -> list[dict]:
    label = season.replace("_", "-")
    if not _BOX.exists():
        return []
    box = pd.read_parquet(_BOX)
    box = box[box["season"] == label]
    if box.empty:
        return []
    box = exclude_negative_ids(box, "player_id").dropna(subset=["date"])
    windowed = last_n_games(box, "player_id", "date", LAST_N_GAMES)
    agg = windowed.groupby("player_id").agg(
        fg3a=("fg3a", "sum"), fg3m=("fg3m", "sum"), n_games=("game_id", "nunique"),
        player_name=("player_name", "first"),
    ).reset_index()
    agg = agg[agg["fg3a"] >= THREE_LAST20_FLOOR_FGA].copy()
    if agg.empty:
        return []
    agg["efg"] = agg["fg3m"] * 1.5 / agg["fg3a"]
    return finalize_rows(
        agg, entity_col="player_id", name_col="player_name", raw_col="efg", n_col="fg3a",
        window=_last20_window(season), attribute="shot_zone_three_efg", status="DESCRIPTIVE",
        sources=rel_sources(_BOX), ingredient_cols=["fg3m", "fg3a", "n_games"],
    )


BUILDERS = [build_last20_zone_efg_rim, build_last20_shot_zone_three_efg]


def build_all_player_offense_window_rows(seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for season in seasons:
        for fn in BUILDERS:
            rows.extend(fn(season))
    return rows
