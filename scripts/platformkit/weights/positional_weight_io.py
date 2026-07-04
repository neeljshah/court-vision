"""Data plumbing for the LANE positional-weights gate.

Joins the per-cutoff leak-free tables from
domains.basketball_nba.quality_validity_gate.rank_at_cutoff (naive_pctile,
ts_pct/efg_pct/ft_pct pre-T, realized_ts_pct target, fga) to the coarse
posgroup label from domains.basketball_nba.atlas_player_position
(guard/forward/center -- mapped from the on-disk GUARD/WING/BIG enum).

No new stats logic here (that lives in positional_weight_gate.py) -- pure
load + merge + coverage reporting, kept separate to respect the 300-LOC cap.
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.atlas_player_position import (
    OUT_PATH as POSITION_ATLAS_PATH,
    coverage_report,
    materialize as materialize_position_atlas,
)
from domains.basketball_nba.quality_indices import (
    aggregate_season,
    load_boxscores,
    qualifying_pool,
)
from domains.basketball_nba.quality_validity_gate import (
    CUTOFFS_2024_25,
    REPLICATION_CUTOFF,
    rank_at_cutoff,
)

POSGROUPS = ("guard", "forward", "center")
MIN_COVERAGE_PCT = 0.85


def load_position_atlas() -> pd.DataFrame:
    try:
        return pd.read_parquet(POSITION_ATLAS_PATH)
    except FileNotFoundError:
        return materialize_position_atlas()


def qualifier_coverage() -> dict:
    """329-qualifier coverage of the position atlas (STEP 1 report, re-run
    live here so the gate always checks against the current on-disk data,
    never a stale cached number)."""
    atlas = load_position_atlas()
    box = load_boxscores()
    agg = aggregate_season(box)
    qual = qualifying_pool(agg)
    return coverage_report(atlas, qual["player_id"])


def cutoff_tables_with_position() -> tuple[list[pd.DataFrame], list[str]]:
    """Leak-free per-cutoff tables (rank_at_cutoff), inner-joined to posgroup.
    Players without a position label are dropped for this gate (position is
    the whole point of the hypothesis) -- reported via row-count deltas by
    the caller, never imputed."""
    box = load_boxscores()
    atlas = load_position_atlas()[["player_id", "posgroup"]]
    tables, ok_cutoffs = [], []
    for cutoff in CUTOFFS_2024_25:
        r = rank_at_cutoff(box, cutoff)
        if r is None:
            continue
        merged = r["table"].merge(atlas, on="player_id", how="inner")
        if len(merged) < 30:  # too few positioned players to fit 3 group weight sets
            continue
        tables.append(merged.reset_index(drop=True))
        ok_cutoffs.append(cutoff)
    return tables, ok_cutoffs


def replication_table_with_position() -> pd.DataFrame | None:
    box = load_boxscores()
    r = rank_at_cutoff(box, REPLICATION_CUTOFF)
    if r is None:
        return None
    atlas = load_position_atlas()[["player_id", "posgroup"]]
    merged = r["table"].merge(atlas, on="player_id", how="inner")
    if len(merged) < 30:
        return None
    return merged.reset_index(drop=True)
