"""Devig: convert vigged sportsbook prices into fair probabilities.

Two methods exposed:
- `proportional_devig` — symmetric power-sum / normalization (the naive default
  used in most retail tooling). Over-corrects favourites at the expense of
  longshots, because it assumes the vig is split evenly across outcomes.
- `shin_devig`         — Shin (1992) bisection solver for the
  insider-trading model. Recovers an estimate of `z` (the inferred fraction
  of bets coming from informed traders) and returns probabilities consistent
  with that z. Shin loads the vig asymmetrically — more onto the longshot
  to protect against informed flow — so on heavy-favourite markets it
  returns a HIGHER probability for the favourite than proportional does,
  and a LOWER probability for the longshot. See Štrumbelj (2014) and the
  references in `docs/research/validation-methodology.md`.

Both take and return probabilities (not American odds). Use
`american_to_prob` to convert. Inputs may sum to >1 (the overround); outputs
always sum to 1.0 within 1e-9.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def american_to_prob(odds: int) -> float:
    """American odds -> raw implied probability (still vigged)."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def proportional_devig(vigged: Sequence[float]) -> list[float]:
    """Symmetric power-sum: divide each prob by the overround.

    Standard retail devig. Cheap but biased on favourite-longshot lines.
    """
    total = sum(vigged)
    if total <= 0:
        n = len(vigged)
        return [1.0 / n] * n
    return [p / total for p in vigged]


def shin_devig(vigged: Sequence[float], *, max_iter: int = 64,
               tol: float = 1e-12) -> list[float]:
    """Shin (1992) devig. Returns probabilities summing to 1.0.

    Solves for z in [0, 1) such that, given vigged probabilities `pi`,
    the implied true probabilities

        p_i(z) = (sqrt(z^2 + 4*(1-z) * pi_i^2 / S) - z) / (2 * (1 - z))

    sum to 1, where S = sum(pi). Bisection on z; convex and well-behaved.

    Falls back to `proportional_devig` if the overround is non-positive or
    numerically degenerate.
    """
    pi = list(vigged)
    s = sum(pi)
    if s <= 1.0 + 1e-12 or any(p <= 0 for p in pi):
        return proportional_devig(pi)

    def p_of_z(z: float, q: float) -> float:
        return (math.sqrt(z * z + 4.0 * (1.0 - z) * q * q / s) - z) / (2.0 * (1.0 - z))

    def sum_p(z: float) -> float:
        return sum(p_of_z(z, q) for q in pi)

    lo, hi = 0.0, 1.0 - 1e-9
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if sum_p(mid) > 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break

    z = 0.5 * (lo + hi)
    out = [p_of_z(z, q) for q in pi]
    total = sum(out)
    return [p / total for p in out]


def shin_devig_pair(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Convenience wrapper for the common over/under American-odds case."""
    pair = shin_devig([american_to_prob(over_odds), american_to_prob(under_odds)])
    return pair[0], pair[1]


__all__ = [
    "american_to_prob",
    "proportional_devig",
    "shin_devig",
    "shin_devig_pair",
]
