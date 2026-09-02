"""Shin (1992/93) devigging -- the correct, tested reference (blueprint N1/N2).

The QA pass found the Shin closed-form quoted in the older validation-methodology.md
does NOT normalize to 1. This is the vetted version: a general n-outcome solver that
recovers fair probabilities summing to exactly 1, accounting for the favorite-longshot
bias (insider-trading proportion z). numpy + stdlib only.

Devigging matters because the eval gate scores calibration vs the DEVIGGED close --
a multiplicative devig flatters a model on lopsided markets (FLB); Shin is the
defensible baseline. Use this only as the reference; in production prefer mberk/shin
or kernel.devig2 if vetted equivalent.

This computes fair probabilities only; it never computes or implies a dollar edge.
"""
from __future__ import annotations
from typing import List, Sequence, Tuple
import numpy as np


def implied_from_decimal(odds: Sequence[float]) -> np.ndarray:
    """Quoted implied probabilities pi_i = 1/decimal_odds_i (NOT normalized)."""
    o = np.asarray(odds, dtype=float)
    # raise, not assert: `python -O` strips asserts, and a stripped price guard
    # returns silently-wrong fair probabilities from a corrupted book.
    if not (np.all(np.isfinite(o)) and np.all(o > 1.0)):
        raise ValueError("decimal odds must be finite and > 1, got %s" % (o.tolist(),))
    return 1.0 / o


def _fair_probs_given_z(pi: np.ndarray, z: float) -> np.ndarray:
    """Shin fair probabilities for a given insider proportion z in [0, 1)."""
    B = float(pi.sum())
    # p_i(z) = (sqrt(z^2 + 4(1-z) pi_i^2 / B) - z) / (2(1-z))
    inside = z * z + 4.0 * (1.0 - z) * (pi ** 2) / B
    return (np.sqrt(inside) - z) / (2.0 * (1.0 - z))


def shin_devig(pi: Sequence[float], tol: float = 1e-12, max_iter: int = 200) -> Tuple[np.ndarray, float]:
    """Return (fair_probabilities summing to 1, estimated z).

    `pi` are the quoted implied probs (1/odds), summing to the booksum B >= 1.
    Solves for z by bisection so that sum_i p_i(z) == 1. z=0 reduces to the
    no-vig case (returns pi unchanged when B == 1).
    """
    pi = np.asarray(pi, dtype=float)
    # raise, not assert (survives `python -O`). An implied prob outside (0, 1] is not
    # a price: pi > 1 solved to a plausible-looking z and returned fair probabilities
    # that were silently wrong.
    if not (np.all(np.isfinite(pi)) and np.all(pi > 0.0) and np.all(pi <= 1.0)):
        raise ValueError("implied probs must be finite and in (0, 1], got %s" % (pi.tolist(),))
    B = float(pi.sum())
    if abs(B - 1.0) < tol:
        return pi.copy(), 0.0           # already fair, no overround
    if B <= 1.0:
        raise ValueError("booksum %s < 1 (arbitrage / bad input)" % B)

    lo, hi = 0.0, 0.999999              # z in [0, 1)
    converged = False
    # sum_i p_i(z) decreases monotonically in z; bisect to hit sum == 1
    for _ in range(max_iter):
        z = 0.5 * (lo + hi)
        s = float(_fair_probs_given_z(pi, z).sum())
        if abs(s - 1.0) < tol:
            converged = True
            break
        # larger z -> smaller sum (more shrinkage); adjust accordingly
        if s > 1.0:
            lo = z
        else:
            hi = z
    p = _fair_probs_given_z(pi, z)
    residual = abs(float(p.sum()) - 1.0)
    # The normalization below is a rounding clean-up (residual ~1e-13), never a rescue:
    # a bisection that never reached sum == 1 is a LABELLED failure, not a fair price.
    if not converged and residual > 1e-9:
        raise ValueError("shin bisection did not converge: |sum(p) - 1| = %.3e "
                         "after %d iterations" % (residual, max_iter))
    p = p / p.sum()                     # numerical clean-up; sum is ~1 already
    return p, z


def shin_devig_decimal(odds: Sequence[float]) -> Tuple[List[float], float]:
    """Convenience: devig from decimal odds -> (fair probs, z)."""
    p, z = shin_devig(implied_from_decimal(odds))
    return p.tolist(), float(z)
