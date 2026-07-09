"""domains.basketball_nba.feature_spec -- the frozen NBA base-feature contract.

Single source of truth for the base matrix the NBAAdapter builds inline in
feature_bundle(). Declaring it here (and proving build_base_matrix reproduces the
adapter byte-for-byte, see tests/platformkit/test_feature_spec_nba.py) means any
future train OR inference path constructs the SAME columns in the SAME order with
the SAME defaults -- the parity seam.

Default contract is nba-base-v1 (8 cols) -- bit-identical to pre-2026-07-11
behaviour. v2 (gap ledger rank 1) appends 2 SHIP-verdict as-of reclaim cols
(def_fg_pct_allowed_diff_asof, def_pts_allowed_per36_diff_asof;
data/domains/basketball_nba/reclaim_gate_defender_rollup_summary.json) that are
~66% NaN outside the box-tracking era -- OPT-IN ONLY via include_asof=True, because
an unlisted consumer (scripts/platformkit/nba_winprob_model.py) fed the widened
bundle into the calibration tuner unvalidated and regressed NBA improved-ECE from
0.01755 to 0.03113 (worse than the 0.02614 naive baseline). See
docs/research/bundle_regression_fix_2026-07-11.md.

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

# Order + defaults + casts mirror domains/basketball_nba/adapter.py exactly:
#   float(row["elo_home"]), float(row["elo_away"]), float(row["elo_diff_hfa"]),
#   float(row.get("rest_days_home", 5.0)), float(row.get("rest_days_away", 5.0)),
#   float(bool(row.get("home_b2b", False))), float(bool(row.get("away_b2b", False))),
#   float(row.get("rolling_win10_home", 0.5))
_BASE_FIELDS = (
    FeatureField("elo_home", "elo_home", default=None, cast=CAST_FLOAT),
    FeatureField("elo_away", "elo_away", default=None, cast=CAST_FLOAT),
    FeatureField("elo_diff_hfa", "elo_diff_hfa", default=None, cast=CAST_FLOAT),
    FeatureField("rest_days_home", "rest_days_home", default=5.0, cast=CAST_FLOAT),
    FeatureField("rest_days_away", "rest_days_away", default=5.0, cast=CAST_FLOAT),
    FeatureField("home_b2b", "home_b2b", default=0.0, cast=CAST_BOOL_FLOAT),
    FeatureField("away_b2b", "away_b2b", default=0.0, cast=CAST_BOOL_FLOAT),
    FeatureField("rolling_win10_home", "rolling_win10_home", default=0.5, cast=CAST_FLOAT),
)
_ASOF_FIELDS = (
    FeatureField("def_fg_pct_allowed_diff_asof", "def_fg_pct_allowed_diff_asof",
                 default=None, cast=CAST_FLOAT),
    FeatureField("def_pts_allowed_per36_diff_asof", "def_pts_allowed_per36_diff_asof",
                 default=None, cast=CAST_FLOAT),
)

# Default contract: 8-col, bit-identical to pre-87ba5f78.
NBA_BASE_SPEC = FeatureSpec(sport="basketball_nba", version="nba-base-v1", fields=_BASE_FIELDS)
# Opt-in contract: 10-col, appends the 2 SHIP asof reclaim cols.
NBA_ASOF_SPEC = FeatureSpec(sport="basketball_nba", version="nba-base-v2",
                             fields=_BASE_FIELDS + _ASOF_FIELDS)


def build_nba_base(df: pd.DataFrame, include_asof: bool = False) -> Tuple[np.ndarray, List[str]]:
    """Build the NBA base matrix from a walk-forward frame (the parity entrypoint).

    include_asof=False (default): 8-col nba-base-v1, bit-identical to pre-2026-07-11.
    include_asof=True: 10-col nba-base-v2, adds the 2 SHIP-verdict as-of reclaim cols.
    """
    spec = NBA_ASOF_SPEC if include_asof else NBA_BASE_SPEC
    return build_base_matrix(spec, df)


def catalog(include_asof: bool = False) -> List[str]:
    return (NBA_ASOF_SPEC if include_asof else NBA_BASE_SPEC).col_names()
