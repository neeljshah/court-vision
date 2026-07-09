"""domains.basketball_nba.feature_spec -- the frozen NBA base-feature contract.

Single source of truth for the 10-column base matrix the NBAAdapter builds inline in
feature_bundle(). Declaring it here (and proving build_base_matrix reproduces the
adapter byte-for-byte, see tests/platformkit/test_feature_spec_nba.py) means any
future train OR inference path constructs the SAME columns in the SAME order with
the SAME defaults -- the parity seam.

v2 (gap ledger rank 1): appends the 2 SHIP-verdict as-of reclaim cols
(def_fg_pct_allowed_diff_asof, def_pts_allowed_per36_diff_asof;
data/domains/basketball_nba/reclaim_gate_defender_rollup_summary.json) that the
adapter now merges in from asof_defender_rollup.parquet by game_id.

ADOPTION IS ADDITIVE: this module does not modify the adapter. It mirrors the
adapter's current contract so the adapter can later delegate to it without changing
behaviour. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.feature_spec_core import (
    CAST_BOOL_FLOAT,
    CAST_FLOAT,
    FeatureField,
    FeatureSpec,
    build_base_matrix,
)

# Order + defaults + casts mirror domains/basketball_nba/adapter.py:175-183 exactly:
#   float(row["elo_home"]), float(row["elo_away"]), float(row["elo_diff_hfa"]),
#   float(row.get("rest_days_home", 5.0)), float(row.get("rest_days_away", 5.0)),
#   float(bool(row.get("home_b2b", False))), float(bool(row.get("away_b2b", False))),
#   float(row.get("rolling_win10_home", 0.5))
NBA_BASE_SPEC = FeatureSpec(
    sport="basketball_nba",
    version="nba-base-v2",
    fields=(
        FeatureField("elo_home", "elo_home", default=None, cast=CAST_FLOAT),
        FeatureField("elo_away", "elo_away", default=None, cast=CAST_FLOAT),
        FeatureField("elo_diff_hfa", "elo_diff_hfa", default=None, cast=CAST_FLOAT),
        FeatureField("rest_days_home", "rest_days_home", default=5.0, cast=CAST_FLOAT),
        FeatureField("rest_days_away", "rest_days_away", default=5.0, cast=CAST_FLOAT),
        FeatureField("home_b2b", "home_b2b", default=0.0, cast=CAST_BOOL_FLOAT),
        FeatureField("away_b2b", "away_b2b", default=0.0, cast=CAST_BOOL_FLOAT),
        FeatureField("rolling_win10_home", "rolling_win10_home", default=0.5, cast=CAST_FLOAT),
        FeatureField("def_fg_pct_allowed_diff_asof", "def_fg_pct_allowed_diff_asof",
                     default=None, cast=CAST_FLOAT),
        FeatureField("def_pts_allowed_per36_diff_asof", "def_pts_allowed_per36_diff_asof",
                     default=None, cast=CAST_FLOAT),
    ),
)


def build_nba_base(df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the NBA base matrix from a walk-forward frame (the parity entrypoint)."""
    return build_base_matrix(NBA_BASE_SPEC, df)


def catalog() -> List[str]:
    return NBA_BASE_SPEC.col_names()
