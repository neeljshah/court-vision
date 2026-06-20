"""scripts.platformkit.bestbets.confidence_score -- honest confidence scorer.

BBQ5-2 (P1): The 'confidence' field on every BestBetCard is currently set to
raw model_prob, which means a 0.95 favourite with ZERO divergence from the market
reads as max-confidence.  That is a misnomer -- high model_prob on a well-priced
favourite is not decision-support sharpness.

This module replaces that with a pure function:

    score, label = score_card(card)

Where:

    score  in [0.0, 1.0]  -- composite sharpness score (NOT win probability, NOT $)
    label  in {LOW, MED, HIGH}  -- decision-support confidence tier

DESIGN
------
Three independent axes, each in [0, 1], combined by a weighted geometric mean:

1. divergence_axis  -- how far is model_prob from market_prob, normalised.
   Uses scripts.platformkit.bestbets.divergence_rank.divergence_score internally.
   Saturates at ~3 sigma (asymptote toward 1.0).  A card with zero divergence
   scores 0.0 on this axis regardless of model_prob.

2. sample_axis  -- how many samples back the model calibration.
   n_samples < THIN_THRESHOLD -> 0.0 (thin floor).
   n_samples >= AMPLE_THRESHOLD -> 1.0.
   Linear interpolation in between.
   Missing n_samples is treated as thin (fail-closed).

3. clv_axis  -- how much CLV signal quality we have.
   clv_is_proxy=True  -> 0.5 (proxy signal, not real close).
   clv_is_proxy=False -> 1.0 (real liquid close available).
   CLV axis only modulates the score; it does NOT cap it on its own.

CAPS (hard, applied after the raw score):
- divergence_axis==0.0 -> label caps at LOW  (no market edge visible; don't reward model_prob).
- clv_is_proxy=True    -> label caps at MED  (score left unchanged, only label capped).
- sample_axis==0.0     -> label caps at LOW  (score left unchanged, only label capped).

THRESHOLDS:
    raw_score >= HIGH_THRESHOLD  -> HIGH
    raw_score >= MED_THRESHOLD   -> MED
    else                         -> LOW

RAILS (binding):
  * UNITS not $.  No dollar / ROI / PnL key anywhere.
  * confidence is decision-support sharpness, NOT win probability, NOT edge.
  * Pure module: no IO, no network, no global state mutation.
  * Does NOT import bestbets_compute (read-only build_on divergence_rank only).
  * Empty / garbage card -> (score=0.0, label=LOW); never raises.
  * <=300 LOC; ASCII only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from scripts.platformkit.bestbets.divergence_rank import (
    DEFAULT_SIGMA,
    divergence_score as _raw_divergence,
)

# ---------------------------------------------------------------------------
# Tunable thresholds (calibration discipline -- not edge).
# ---------------------------------------------------------------------------

# n_samples below this -> sample axis = 0.0 (thin).
THIN_THRESHOLD: int = 30
# n_samples at or above this -> sample axis = 1.0 (ample).
AMPLE_THRESHOLD: int = 200

# Divergence saturation: beyond SAT_SIGMA standard-deviations the axis
# approaches 1.0 asymptotically.  We use a simple clip-and-scale so the
# function stays in [0, 1] without infinite tails.
SAT_SIGMA: float = 3.0  # divergence_score = 3.0 -> axis = 1.0

# Composite score thresholds for the LOW/MED/HIGH label.
HIGH_THRESHOLD: float = 0.60
MED_THRESHOLD: float = 0.30

# Axis weights for the weighted AVERAGE (geometric would require all > 0 always).
# Divergence is the primary signal; sample and CLV are moderating factors.
WEIGHT_DIV: float = 0.60
WEIGHT_SAMPLE: float = 0.25
WEIGHT_CLV: float = 0.15

# Valid output labels.
LABEL_LOW: str = "LOW"
LABEL_MED: str = "MED"
LABEL_HIGH: str = "HIGH"


# ---------------------------------------------------------------------------
# Internal axis scorers (each returns a float in [0, 1]).
# ---------------------------------------------------------------------------

def _divergence_axis(model_prob: Any, market_prob: Any, sigma: Any) -> float:
    """Normalised |model_prob - market_prob| / sigma, clipped to [0, 1]."""
    try:
        mp = float(model_prob)
        mk = float(market_prob)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(mp) and math.isfinite(mk)):
        return 0.0
    if not (0.0 <= mp <= 1.0 and 0.0 <= mk <= 1.0):
        return 0.0

    sig: float
    try:
        sig = float(sigma) if sigma is not None else DEFAULT_SIGMA
    except (TypeError, ValueError):
        sig = DEFAULT_SIGMA
    if not math.isfinite(sig) or sig <= 0.0:
        sig = DEFAULT_SIGMA

    raw = _raw_divergence(mp, mk, sig)   # |mp - mk| / sig  (>= 0)
    # Scale so SAT_SIGMA -> 1.0; clip at 1.0.
    scaled = raw / SAT_SIGMA
    return min(1.0, max(0.0, scaled))


def _sample_axis(n_samples: Any) -> float:
    """Returns 0.0 (thin), linear interp, or 1.0 (ample). Missing -> thin."""
    if n_samples is None:
        return 0.0
    try:
        n = int(n_samples)
    except (TypeError, ValueError):
        return 0.0
    if n < THIN_THRESHOLD:
        return 0.0
    if n >= AMPLE_THRESHOLD:
        return 1.0
    span = AMPLE_THRESHOLD - THIN_THRESHOLD
    return (n - THIN_THRESHOLD) / span


def _clv_axis(clv_is_proxy: Any) -> float:
    """Proxy CLV -> 0.5; real liquid close available -> 1.0."""
    try:
        is_proxy = bool(clv_is_proxy)
    except (TypeError, ValueError):
        is_proxy = True   # fail-closed: treat unknown as proxy
    return 0.5 if is_proxy else 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_card(card: Any) -> Tuple[float, str]:
    """Compute (score, label) for *card*.

    Parameters
    ----------
    card:
        A dict-like BestBetCard with any subset of:
            model_prob     float -- calibrated model probability
            market_prob    float -- devigged market probability
            sigma          float -- optional uncertainty spread
            n_samples      int   -- sample count behind the model
            clv_is_proxy   bool  -- True if CLV uses a proxy close

        Missing or invalid values degrade gracefully (never raises).

    Returns
    -------
    (score, label)
        score  : float in [0.0, 1.0]; composite sharpness (not win-prob, not $).
        label  : str in {"LOW", "MED", "HIGH"}; decision-support tier.

    HONESTY INVARIANTS:
        - High model_prob with zero divergence -> LOW (not raw prob).
        - clv_is_proxy=True caps label at MED regardless of score.
        - missing n_samples treated as thin -> caps label at LOW.
        - No $ / roi / pnl key is ever produced.
    """
    if not isinstance(card, dict):
        return 0.0, LABEL_LOW

    # Extract fields -- all are optional; bad values degrade to defaults.
    model_prob = card.get("model_prob")
    market_prob = card.get("market_prob")
    sigma = card.get("sigma")
    n_samples = card.get("n_samples")
    clv_is_proxy = card.get("clv_is_proxy", True)

    # Compute axes.
    div_ax = _divergence_axis(model_prob, market_prob, sigma)
    samp_ax = _sample_axis(n_samples)
    clv_ax = _clv_axis(clv_is_proxy)

    # Weighted average of the three axes.
    raw_score = (
        WEIGHT_DIV * div_ax
        + WEIGHT_SAMPLE * samp_ax
        + WEIGHT_CLV * clv_ax
    )
    # Clamp to [0, 1] (should always hold, but be defensive).
    score = max(0.0, min(1.0, raw_score))

    # Determine raw label from score.
    if score >= HIGH_THRESHOLD:
        label = LABEL_HIGH
    elif score >= MED_THRESHOLD:
        label = LABEL_MED
    else:
        label = LABEL_LOW

    # Hard cap: zero divergence -> at most LOW.
    # A card with no measurable market departure has no decision-support sharpness
    # regardless of how confident the model is in the raw probability.
    if div_ax == 0.0:
        label = LABEL_LOW

    # Hard cap: thin sample -> at most LOW.
    if samp_ax == 0.0:
        label = LABEL_LOW

    # Hard cap: proxy CLV -> at most MED.
    if clv_is_proxy_safe(clv_is_proxy) and label == LABEL_HIGH:
        label = LABEL_MED

    return score, label


def clv_is_proxy_safe(clv_is_proxy: Any) -> bool:
    """Return True when CLV is a proxy (fail-closed: unknown -> True)."""
    try:
        return bool(clv_is_proxy)
    except (TypeError, ValueError):
        return True


def score_batch(cards: Any) -> list:
    """Score a list of cards.  Returns list of (score, label) tuples.

    Empty / non-list input -> []; never raises.
    """
    if not isinstance(cards, (list, tuple)):
        return []
    out = []
    for card in cards:
        try:
            out.append(score_card(card))
        except Exception:  # noqa: BLE001
            out.append((0.0, LABEL_LOW))
    return out


__all__ = [
    "THIN_THRESHOLD",
    "AMPLE_THRESHOLD",
    "SAT_SIGMA",
    "HIGH_THRESHOLD",
    "MED_THRESHOLD",
    "LABEL_LOW",
    "LABEL_MED",
    "LABEL_HIGH",
    "score_card",
    "score_batch",
    "clv_is_proxy_safe",
]
