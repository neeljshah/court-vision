"""domains.mlb.feature_spec -- the frozen MLB base-feature contract.

Single source of truth for the 6-column base matrix the MLBAdapter builds inline
in feature_bundle() (see domains/mlb/adapter.py:219-223):

    [elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate]

Declaring it here (and proving build_base_matrix reproduces the adapter byte-for-
byte in tests/platformkit/test_mlb_parity.py) means any future train OR inference
path constructs the SAME columns in the SAME order with the SAME defaults -- the
parity seam.

ADOPTION IS ADDITIVE: this module does not modify the adapter. It mirrors the
adapter's current contract so the adapter can later delegate to it without changing
behaviour. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.feature_spec_core import (
    CAST_FLOAT,
    FeatureField,
    FeatureSpec,
    build_base_matrix,
)

# Order + defaults + casts mirror domains/mlb/adapter.py:219-223 exactly:
#   float(row["elo_home"]), float(row["elo_away"]), float(row["elo_diff_hfa"]),
#   float(row.get("rest_days_home", 5.0)), float(row.get("rest_days_away", 5.0)),
#   float(row.get("h2h_rate", 0.5))
MLB_BASE_SPEC = FeatureSpec(
    sport="mlb",
    version="mlb-base-v1",
    fields=(
        FeatureField("elo_home", "elo_home", default=None, cast=CAST_FLOAT),
        FeatureField("elo_away", "elo_away", default=None, cast=CAST_FLOAT),
        FeatureField("elo_diff_hfa", "elo_diff_hfa", default=None, cast=CAST_FLOAT),
        FeatureField("rest_days_home", "rest_days_home", default=5.0, cast=CAST_FLOAT),
        FeatureField("rest_days_away", "rest_days_away", default=5.0, cast=CAST_FLOAT),
        FeatureField("h2h_rate", "h2h_rate", default=0.5, cast=CAST_FLOAT),
    ),
)


def build_mlb_base(df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the MLB base matrix from a walk-forward frame (the parity entrypoint)."""
    return build_base_matrix(MLB_BASE_SPEC, df)


def catalog() -> List[str]:
    return MLB_BASE_SPEC.col_names()
