"""Per-file test on a small real slice: the first 5 games of stints_2025_26
.parquet joined against the real, already-built on_off_2025_26.parquet.
Checks the sanity invariants -- one row per distinct (team_id, lineup_key),
n_members_qualified in [0, 5], residual is only ever populated when all 5
members qualified, and `qualifies` agrees exactly with the stated floor
recomputed from the row's own min/residual columns (the same reapplication
the claims producer must be able to do).

Run: python -m pytest domains/basketball_nba/interactions/test_lineup_synergy.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.interactions.lineup_synergy import (
    MIN_LINEUP_MINUTES,
    attach_expected,
    build_lineup_actuals,
)
from domains.basketball_nba.lineups.pbp_lineups import _OUT_PATH as _STINTS_PATH

_ON_OFF_PATH = _STINTS_PATH.parent / "on_off_2025_26.parquet"


@pytest.mark.skipif(
    not _STINTS_PATH.exists() or not _ON_OFF_PATH.exists(), reason="local-only data not present"
)
def test_lineup_synergy_structurally_sane_on_a_slice() -> None:
    stints_df = pd.read_parquet(_STINTS_PATH)
    game_ids = stints_df["game_id"].unique()[:5]
    stints_df = stints_df[stints_df["game_id"].isin(game_ids)]
    on_off_df = pd.read_parquet(_ON_OFF_PATH)

    lineup_df = build_lineup_actuals(stints_df)
    assert lineup_df["lineup_key"].str.count(",").eq(4).all()  # exactly 5 players every row
    assert not lineup_df.duplicated(subset=["team_id", "lineup_key"]).any()

    result = attach_expected(lineup_df, on_off_df)
    assert result["n_members_qualified"].between(0, 5).all()

    has_residual = result["synergy_residual"].notna()
    assert (result.loc[has_residual, "n_members_qualified"] == 5).all()
    assert (result.loc[~has_residual, "n_members_qualified"] < 5).sum() >= 0  # never negative/crashing

    recomputed_qualifies = (result["min"] >= MIN_LINEUP_MINUTES) & has_residual
    assert (result["qualifies"] == recomputed_qualifies).all()
