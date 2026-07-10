"""scripts.platformkit.benchmarks.crps_market.shape_control -- shape-matched
market baseline for the in-game CRPS benchmark (ingame_mlb.py).

Split out to respect the <=300 LOC/file rail (same precedent as ask.py ->
ask_index.py, claims_validator.py -> claims_validator_batch.py).

WHY: crps_ensemble (model, integer-valued run/margin samples) vs crps_gaussian
(market, continuous closed-form) is not a shape-matched comparison -- an
integer-valued ensemble gets a structural CRPS edge over a continuous
baseline on an integer-valued target. market_crps_discretized re-expresses
the market Gaussian as a rounded-to-integer ensemble scored with the SAME
crps_ensemble estimator; shape_controlled_verdict then downgrades a raw
MODEL_SHARPER verdict to UNDERPOWERED unless this shape-controlled delta
agrees, so a MODEL_SHARPER claim can't be a distribution-family artifact.

Tests: python -m pytest tests/platformkit/test_ingame_crps_mlb.py -q
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

from domains.basketball_nba.sim2.simulator import crps_ensemble


def market_crps_discretized(mu: float, sigma: float, realized: float,
                             n: int, seed: int) -> float:
    """Market's Gaussian re-expressed as an INTEGER-valued ensemble (same
    crps_ensemble estimator + same discrete support as the model's run/
    margin samples), so a MODEL_SHARPER verdict can't just be the
    structural CRPS advantage an integer-valued ensemble gets over a
    continuous closed-form baseline on an integer-valued target."""
    rng = np.random.default_rng(seed)
    samples = np.round(rng.normal(mu, max(float(sigma), 1e-9), n))
    return crps_ensemble(samples, realized)


def shape_controlled_verdict(raw_verdict: str, disc_verdict: str) -> Tuple[str, str]:
    """A raw MODEL_SHARPER only stands if the shape-controlled (integer-
    discretized market baseline) delta ALSO says MODEL_SHARPER; otherwise
    it's a continuous-vs-integer distribution-family artifact, not genuine
    conditioning skill, and gets downgraded to UNDERPOWERED."""
    if raw_verdict == "MODEL_SHARPER" and disc_verdict != "MODEL_SHARPER":
        return "UNDERPOWERED", (
            "Shape-control FAILED: raw MODEL_SHARPER delta does not survive "
            "when the market baseline is discretized to the model's integer "
            "support (crps_ensemble on rounded N(mu,sigma) samples) -- "
            "treated as a distribution-family artifact, not genuine "
            "conditioning skill.")
    return raw_verdict, ""
