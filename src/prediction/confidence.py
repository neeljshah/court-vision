"""src/prediction/confidence.py — combined-signal prediction confidence score.

Most bet selection uses model EV alone. But two bets with the same EV can
differ wildly in CONFIDENCE — driven by:
  - model variance       (q90 - q10) / max(q50, 1)
  - lineup status        Confirmed > Expected > Projected > Unknown
  - lineup classification starter > questionable > bench
  - injury status        AVAILABLE > PROBABLE > QUESTIONABLE
  - data freshness        not modeled here — caller can adjust

This module produces a 0-100 score combining the above. Higher = more
confident. Conservative bettors can filter to >= 70; aggressive bettors
might bet down to 40.

Designed to be wired into compare_to_lines / nightly_report as an extra
column; doesn't change EV / Kelly arithmetic.
"""
from __future__ import annotations

from typing import Optional


# Bands the score multiplies through (higher = more confident).
_LINEUP_STATUS_WEIGHT = {
    "Confirmed": 1.00,
    "Expected":  0.85,
    "Projected": 0.65,
    "Unknown":   0.50,    # no lineup data — fall back to model alone
}

_LINEUP_CLS_WEIGHT = {
    "starter":      1.00,
    "questionable": 0.55,
    "bench":        0.20,
    "no-game":      0.00,
    "unknown":      1.00,
}

_INJURY_WEIGHT = {
    "AVAILABLE":   1.00,
    "PROBABLE":    0.90,
    "QUESTIONABLE": 0.60,
    "DOUBTFUL":    0.20,
    "OUT":         0.00,
    "NOT WITH TEAM": 0.00,
    None:          1.00,   # no injury listed → no penalty
    "":            1.00,
}


def variance_score(q10: Optional[float], q50: Optional[float],
                    q90: Optional[float]) -> float:
    """Return 0-1: tighter quantile interval (relative to mean) → higher score.

    Uses (q90 - q10) / max(q50, 1) as the coefficient-of-variation proxy.
    A CoV of 0.4 → score ~0.6; CoV of 1.0 → score ~0.3; CoV of 2.0 → ~0.1.
    """
    if q10 is None or q50 is None or q90 is None:
        return 0.5    # no quantiles → neutral
    width = q90 - q10
    if width <= 0:
        return 1.0    # zero-width interval (degenerate but possible)
    cov = width / max(float(q50), 1.0)
    # Exponential decay: cov=0 → 1.0, cov=0.5 → ~0.61, cov=1.0 → ~0.37, cov=2.0 → ~0.14
    import math
    return float(math.exp(-cov))


def confidence_score(
    q10: Optional[float] = None,
    q50: Optional[float] = None,
    q90: Optional[float] = None,
    lineup_status: Optional[str] = None,
    lineup_class: Optional[str] = None,
    injury_status: Optional[str] = None,
) -> int:
    """Return 0-100 integer score. Higher = more confident.

    All inputs optional — missing signals fall back to neutral weights
    so the score still produces a useful number from partial information.
    """
    v = variance_score(q10, q50, q90)
    ls = _LINEUP_STATUS_WEIGHT.get(lineup_status or "Unknown", 0.5)
    lc = _LINEUP_CLS_WEIGHT.get((lineup_class or "unknown").lower(), 1.0)
    inj = _INJURY_WEIGHT.get(
        (injury_status or "").upper() if injury_status is not None else None,
        1.0,
    )
    # Geometric mean smooths a single zero-ish factor; multiplicative would
    # let one missing signal zero everything out. Weight: variance gets 2x
    # weight since it's the only "model-internal" signal.
    raw = (v ** 2 * ls * lc * inj) ** (1 / 5)
    return int(round(100 * max(0.0, min(1.0, raw))))
