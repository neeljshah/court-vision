"""predict_service.uncertainty -- a leak-free interval from HELD-OUT residuals.

WAVE 3. Attaches an uncertainty Interval to a probability estimate WITHOUT
leaking the future: the band is built ONLY from held-out (out-of-fold / OOS)
residuals supplied by the caller, never from the in-sample fit that produced the
point estimate. The residual is (observed_outcome - predicted_prob) on held-out
games; we take the symmetric central quantile of those residuals at the requested
coverage *level* and add it to the point estimate, clamped to [0, 1].

Why residual-quantile (not a parametric sigma): it makes the leak-freeness
auditable -- the band is a function of a residual SAMPLE the caller passes in, so
a test can prove the interval moves with the held-out residuals and would be
EMPTY (None) if no held-out residuals are available. No distribution is assumed.

HONESTY: probability/units only; NO $ field. An interval is returned as a
contracts.Interval (method='heldout_residual_quantile') or None when there is no
held-out residual evidence -- we never fabricate a band from thin air.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse contracts.Interval verbatim.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from predict_service.contracts import Interval

# Minimum held-out residuals required before we will quote a band. Below this an
# interval is not statistically meaningful, so we return None (honest, not a
# fabricated tight band).
_MIN_RESIDUALS = 8


def _clamp01(x: float) -> float:
    """Clamp a probability to [0.0, 1.0]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already-sorted sequence (q in [0,1])."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    pos = q * (n - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, n - 1)
    frac = pos - lo_i
    return float(sorted_vals[lo_i]) * (1.0 - frac) + float(sorted_vals[hi_i]) * frac


def interval_from_residuals(
    prob: float,
    heldout_residuals: Optional[Sequence[float]],
    level: float = 0.80,
) -> Optional[Interval]:
    """Central interval around *prob* from HELD-OUT residuals only (leak-free).

    *heldout_residuals* are (observed - predicted) residuals measured on held-out
    games -- NOT the in-sample fit. We take the central *level* quantile band of
    those residuals and add it to the point estimate, clamping to [0, 1]. Returns
    None when fewer than _MIN_RESIDUALS are supplied (no fabricated band).

    The interval WIDENS with more dispersed held-out residuals and is symmetric in
    residual-space (lo from the lower tail, hi from the upper tail). method is
    stamped 'heldout_residual_quantile' so a reader can confirm the source.
    """
    if heldout_residuals is None:
        return None
    res: List[float] = []
    for r in heldout_residuals:
        try:
            res.append(float(r))
        except (TypeError, ValueError):
            continue
    if len(res) < _MIN_RESIDUALS:
        return None
    if not (0.0 < level < 1.0):
        level = 0.80
    res.sort()
    alpha = (1.0 - level) / 2.0
    lo_resid = _quantile(res, alpha)
    hi_resid = _quantile(res, 1.0 - alpha)
    lo = _clamp01(prob + lo_resid)
    hi = _clamp01(prob + hi_resid)
    if hi < lo:  # numerical guard; never invert
        lo, hi = hi, lo
    return Interval(lo=round(lo, 6), hi=round(hi, 6), level=round(float(level), 4),
                    method="heldout_residual_quantile")


__all__ = ["interval_from_residuals"]
