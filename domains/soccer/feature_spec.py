"""domains.soccer.feature_spec -- the frozen soccer (club O/U) base-feature contract.

Single source of truth for the 5-column base matrix the SoccerAdapter builds
inline in feature_bundle() (see domains/soccer/adapter.py:237-240):

    [lam_home, lam_away, lam_total, rest_days_home, rest_days_away]

Declaring it here (and proving build_base_matrix reproduces the adapter byte-for-
byte in tests/platformkit/test_soccer_parity.py) means any future train OR
inference path constructs the SAME columns in the SAME order with the SAME
defaults -- the parity seam.

ADOPTION IS ADDITIVE: this module does not modify the adapter. It mirrors the
adapter's current contract so the adapter can later delegate to it without
changing behaviour. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
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

# Order + defaults + casts mirror domains/soccer/adapter.py:237-240 exactly:
#   float(row["lam_home"]), float(row["lam_away"]), float(row["lam_total"]),
#   float(row.get("rest_days_home", 15.0)), float(row.get("rest_days_away", 15.0))
SOCCER_BASE_SPEC = FeatureSpec(
    sport="soccer",
    version="soccer-base-v1",
    fields=(
        FeatureField("lam_home", "lam_home", default=None, cast=CAST_FLOAT),
        FeatureField("lam_away", "lam_away", default=None, cast=CAST_FLOAT),
        FeatureField("lam_total", "lam_total", default=None, cast=CAST_FLOAT),
        FeatureField("rest_days_home", "rest_days_home", default=15.0, cast=CAST_FLOAT),
        FeatureField("rest_days_away", "rest_days_away", default=15.0, cast=CAST_FLOAT),
    ),
)


def build_soccer_base(df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the soccer base matrix from a walk-forward frame (the parity entrypoint)."""
    return build_base_matrix(SOCCER_BASE_SPEC, df)


def catalog() -> List[str]:
    return SOCCER_BASE_SPEC.col_names()
