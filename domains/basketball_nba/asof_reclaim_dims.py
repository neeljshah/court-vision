"""domains.basketball_nba.asof_reclaim_dims -- untested reclaim-target diff columns.

The NBA "ON-DISK RECLAIM TARGETS" audit (docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md,
row #1) lists six as-of dims that are BUILT and leak-free but never gate-tested:

    home/away_pace_asof, oreb_pg_asof, tov_pg_asof   (asof_features.parquet)
    dreb/fg3m/stl/blk_diff_asof                      (asof_box_extra.parquet)

``ast_rate_diff_asof`` (also in asof_features.parquet) was ALREADY gated vs Elo on
2026-06-27 -> HONEST REJECT (see domains.basketball_nba.asof_ast_rate_eval / MEMORY.md
project_reject_ledger + nba_fit_validity_reject notes).  It is intentionally excluded
from RECLAIM_DIFF_COLS below; do not re-gate it here.

dreb/fg3m/stl/blk already ship as home-minus-away ``*_diff_asof`` columns in
asof_box_extra.parquet.  pace/oreb/tov ship ONLY as home/away pairs -- this module
adds the missing ``*_diff_asof`` = home - away transform so all six dims can run
through the identical parameterized gate harness (asof_ast_rate_eval.gate_feature).

LEAK-NOTE: this module performs NO new aggregation and reads NO raw box data.  It is
a pure column-arithmetic transform (home - away) of values already computed by
asof_features.py's snapshot-before-update walk (see that module's docstring for the
leak argument).  Because subtraction of two already-leak-free prior-only columns
cannot introduce information about the target game, the diff columns inherit
leak-freeness from their inputs.  The per-file test verifies this by construction
(diff == home - away, NaN propagates, and recomputation from a synthetic prior-only
frame matches) plus an explicit "no column depends on the same game_id's own row"
check via monotonic n_prior growth.

CANDIDATE-ONLY: this module does not touch NBAAdapter.feature_bundle, predictor.py,
or any live wiring.  No flags are flipped.  Catalog/notes registration only.

F5: NO domains.mlb / domains.tennis / domains.soccer / src.* / kernel.* imports.
PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASOF_FEATURES = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_features.parquet"
_ASOF_BOX_EXTRA = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_box_extra.parquet"

# Dims from asof_features.parquet that ship as home/away pairs only (no diff yet).
# Maps output diff column name -> (home_col, away_col).
_PAIR_DIFFS: Dict[str, tuple] = {
    "pace_diff_asof": ("home_pace_asof", "away_pace_asof"),
    "oreb_pg_diff_asof": ("home_oreb_pg_asof", "away_oreb_pg_asof"),
    "tov_pg_diff_asof": ("home_tov_pg_asof", "away_tov_pg_asof"),
}

# Dims from asof_box_extra.parquet that ALREADY ship as home-minus-away diffs.
# Listed here only so callers can enumerate the full reclaim set from one place.
_PREBUILT_DIFFS = ("dreb_diff_asof", "fg3m_diff_asof", "stl_diff_asof", "blk_diff_asof")

# ast_rate_diff_asof deliberately excluded: already gated 2026-06-27 -> REJECT.
PREVIOUSLY_REJECTED = ("ast_rate_diff_asof",)

# The full set of UNTESTED reclaim-target diff columns this sweep gates.
RECLAIM_DIFF_COLS = tuple(_PAIR_DIFFS.keys()) + _PREBUILT_DIFFS


def add_pair_diffs(asof_features: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Return asof_features with the three missing ``*_diff_asof`` columns added.

    ``diff = home - away``; NaN propagates honestly when either side lacks prior
    coverage (n_prior == 0 upstream).  No row is dropped; game_id + home/away_n_prior
    + the new diff columns are the columns callers need for the gate merge.
    """
    df = (
        asof_features.copy()
        if isinstance(asof_features, pd.DataFrame)
        else pd.read_parquet(_ASOF_FEATURES)
    )
    for diff_col, (hcol, acol) in _PAIR_DIFFS.items():
        df[diff_col] = df[hcol] - df[acol]
    return df


def load_reclaim_frame(
    asof_features: Optional[pd.DataFrame] = None,
    asof_box_extra: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """One game_id-keyed frame carrying all six untested diff cols + n_prior.

    Left-outer merges asof_features (+ derived pair diffs) with asof_box_extra on
    game_id.  Both inputs already carry home_n_prior/away_n_prior with identical
    semantics (same underlying player_boxscores.parquet walk-forward); the merge
    keeps the asof_features side's n_prior columns as the coverage gate (the two
    sources are built from the same sidecar so counts agree by construction).
    """
    feat = add_pair_diffs(asof_features)
    box = (
        asof_box_extra.copy()
        if isinstance(asof_box_extra, pd.DataFrame)
        else pd.read_parquet(_ASOF_BOX_EXTRA)
    )
    box_cols = ["game_id"] + list(_PREBUILT_DIFFS)
    box = box[[c for c in box_cols if c in box.columns]].copy()

    feat["game_id"] = feat["game_id"].astype(str)
    box["game_id"] = box["game_id"].astype(str)
    out = feat.merge(box, on="game_id", how="left")
    return out


def main() -> int:
    df = load_reclaim_frame()
    print("NBA reclaim-target diff columns (untested; single frame for the gate sweep).")
    print(f"Rows: {len(df)}")
    print(f"Reclaim dims ({len(RECLAIM_DIFF_COLS)}): {list(RECLAIM_DIFF_COLS)}")
    print(f"Previously-rejected (excluded, do not re-gate): {list(PREVIOUSLY_REJECTED)}")
    for c in RECLAIM_DIFF_COLS:
        n_ok = int(df[c].notna().sum()) if c in df.columns else 0
        print(f"  {c}: {n_ok}/{len(df)} non-null")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
