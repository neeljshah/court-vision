"""domains.soccer_intl.feature_spec -- the frozen international (national-team)
soccer base-feature contract.

Single source of truth for the base matrix the IntlSoccerPredictor reads off the
walk-forward frame produced by domains/soccer_intl/ratings.walk_forward_goals.
That function genuinely emits, per match, the leak-free PRE-match Poisson rates:

    [lam_home, lam_away, lam_total]

plus the per-match ``neutral`` flag carried straight from the corpus (the World
Cup neutral-site signal that drops the home tilt). Those FOUR columns really
exist on every walk-forward row, so they -- and only they -- are declared here.

HONEST DIVERGENCE FROM domains/soccer: the club spec adds
[rest_days_home, rest_days_away]. The international corpus carries NO rest-days
data (martj42 results has no per-team schedule density), so fabricating rest
columns (or 0-filling them) would be dishonest. They are deliberately OMITTED.
``lam_total`` is a genuine column in the int'l walk-forward frame (the club
adapter computes it inline), so it is declared as a real source here, not derived.

Declaring it here (and proving build_base_matrix reproduces the walk-forward
columns in the per-file test) means any future train OR inference path constructs
the SAME columns in the SAME order with the SAME defaults -- the parity seam.

ADOPTION IS ADDITIVE: this module does not modify ratings.py or the predictor.
It mirrors the predictor's current read-contract so a model can later delegate to
it without changing behaviour. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
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

# Order + defaults mirror the genuine columns of ratings.walk_forward_goals:
#   lam_home, lam_away, lam_total are REQUIRED (default=None -> absent source
#   raises, never silent-zero); neutral is a real corpus bool carried through.
SOCCER_INTL_BASE_SPEC = FeatureSpec(
    sport="soccer_intl",
    version="soccer_intl-base-v1",
    fields=(
        FeatureField("lam_home", "lam_home", default=None, cast=CAST_FLOAT),
        FeatureField("lam_away", "lam_away", default=None, cast=CAST_FLOAT),
        FeatureField("lam_total", "lam_total", default=None, cast=CAST_FLOAT),
        FeatureField("neutral", "neutral", default=False, cast=CAST_FLOAT),
    ),
)


def build_soccer_intl_base(df: pd.DataFrame) -> Tuple[np.ndarray, List[str]]:
    """Build the int'l-soccer base matrix from a walk-forward frame (parity entry)."""
    return build_base_matrix(SOCCER_INTL_BASE_SPEC, df)


def catalog() -> List[str]:
    return SOCCER_INTL_BASE_SPEC.col_names()
