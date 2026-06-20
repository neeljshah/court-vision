"""domains.tennis.feature_spec -- the frozen Tennis base-feature contract.

Single source of truth for the 5-column base matrix the TennisAdapter builds (see
scripts.platformkit.proof_tennis.gate_test_asof._build_base_bundle_with_ids, which
replicates adapter_helpers._feature_bundle_impl exactly):

  elo_diff         = p1_elo - p2_elo                  (default 1500.0 per operand)
  surface_elo_diff = p1_surface_elo - p2_surface_elo  (default 1500.0 per operand)
  best_of          (default 3.0)
  rest_days_a      (default 15.0)
  rest_days_b      (default 15.0)

elo_diff / surface_elo_diff use the OP_DIFF feature (added to feature_spec_core for
tennis) so the derivation lives in the spec, not scattered across callers. ADDITIVE:
the adapter is not modified. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.feature_spec_core import (
    CAST_FLOAT,
    OP_DIFF,
    FeatureField,
    FeatureSpec,
    build_base_matrix,
)

TENNIS_BASE_SPEC = FeatureSpec(
    sport="tennis",
    version="tennis-base-v1",
    fields=(
        FeatureField("elo_diff", "p1_elo", default=1500.0, cast=CAST_FLOAT,
                     source2="p2_elo", op=OP_DIFF),
        FeatureField("surface_elo_diff", "p1_surface_elo", default=1500.0, cast=CAST_FLOAT,
                     source2="p2_surface_elo", op=OP_DIFF),
        FeatureField("best_of", "best_of", default=3.0, cast=CAST_FLOAT),
        FeatureField("rest_days_a", "rest_days_a", default=15.0, cast=CAST_FLOAT),
        FeatureField("rest_days_b", "rest_days_b", default=15.0, cast=CAST_FLOAT),
    ),
)


def build_tennis_base(df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the Tennis base matrix from a walk-forward frame (the parity entrypoint)."""
    return build_base_matrix(TENNIS_BASE_SPEC, df)


def catalog() -> List[str]:
    return TENNIS_BASE_SPEC.col_names()
