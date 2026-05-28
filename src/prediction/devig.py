"""Devig: convert vigged sportsbook prices into fair probabilities.

Four methods exposed:
- `proportional_devig` (alias: additive) — symmetric power-sum / normalization
  (the naive default used in most retail tooling). Over-corrects favourites at
  the expense of longshots, because it assumes the vig is split evenly across
  outcomes.
- `multiplicative_devig` — power-renormalization: find k such that
  sum(pi_i^k) = 1, then return pi_i^k. Equivalent to a log-odds shift.
- `power_devig`         — naive n-th root method: divide by 1/n in exponent
  before renormalising. Cheaper than multiplicative; defaults n = number of
  outcomes.
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


def prob_to_american(p: float) -> int:
    """Inverse of `american_to_prob`. Returns nearest integer American odds.

    For p == 0.5 returns +100 (a coin flip). Clamps to a tiny epsilon to avoid
    division-by-zero at the limits.
    """
    p = max(min(float(p), 1.0 - 1e-12), 1e-12)
    if p >= 0.5:
        # Favourite -> negative odds: -p/(1-p) * 100
        return int(round(-p / (1.0 - p) * 100.0))
    # Longshot -> positive odds: (1-p)/p * 100
    return int(round((1.0 - p) / p * 100.0))


def proportional_devig(vigged: Sequence[float]) -> list[float]:
    """Symmetric power-sum: divide each prob by the overround.

    Standard retail devig. Cheap but biased on favourite-longshot lines.
    """
    total = sum(vigged)
    if total <= 0:
        n = len(vigged)
        return [1.0 / n] * n
    return [p / total for p in vigged]


# additive == proportional for our purposes (additive splits the overround
# equally per outcome in log-space when expressed naively; in retail tooling
# the two terms are used interchangeably). We alias it.
additive_devig = proportional_devig


def multiplicative_devig(vigged: Sequence[float], *, max_iter: int = 200,
                         tol: float = 1e-12) -> list[float]:
    """Multiplicative (power-renormalisation) devig.

    Finds k such that sum(pi_i ** k) == 1, then returns pi_i ** k / Z (Z==1
    by construction, but we renormalise defensively for floating-point).

    Bisects k on [0.5, 8.0] which covers any sane sportsbook overround.
    """
    pi = [float(p) for p in vigged]
    if any(p <= 0 for p in pi):
        return proportional_devig(pi)
    s = sum(pi)
    if s <= 1.0 + 1e-12:
        # No vig — already fair.
        return proportional_devig(pi)

    def total(k: float) -> float:
        return sum(p ** k for p in pi)

    lo, hi = 0.5, 8.0
    # total(k) is monotonically decreasing in k for pi_i in (0,1).
    # At k=lo total > 1 (under-corrected), at k=hi total < 1.
    # If by some quirk the bracket doesn't hold, expand it.
    if total(lo) < 1.0:
        lo = 0.01
    if total(hi) > 1.0:
        hi = 32.0

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        t = total(mid)
        if t > 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break

    k = 0.5 * (lo + hi)
    out = [p ** k for p in pi]
    z = sum(out)
    return [x / z for x in out]


def power_devig(vigged: Sequence[float], n: int | None = None) -> list[float]:
    """Power devig: raise each implied prob to 1/n then renormalise.

    With n == len(vigged) this is the closed-form 'n-th root' devig that's
    common as a quick approximation to multiplicative when the overround is
    small. Always returns a distribution summing to 1.
    """
    pi = [float(p) for p in vigged]
    if any(p <= 0 for p in pi):
        return proportional_devig(pi)
    if n is None:
        n = len(pi)
    if n <= 0:
        return proportional_devig(pi)
    exp = 1.0 / float(n)
    out = [p ** exp for p in pi]
    z = sum(out)
    if z <= 0:
        return proportional_devig(pi)
    return [x / z for x in out]


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


def multiplicative_devig_pair(over_odds: int, under_odds: int) -> tuple[float, float]:
    """Convenience wrapper — multiplicative devig on an over/under pair."""
    pair = multiplicative_devig(
        [american_to_prob(over_odds), american_to_prob(under_odds)]
    )
    return pair[0], pair[1]


def power_devig_pair(over_odds: int, under_odds: int,
                     n: int | None = None) -> tuple[float, float]:
    """Convenience wrapper — power devig on an over/under pair."""
    pair = power_devig(
        [american_to_prob(over_odds), american_to_prob(under_odds)], n=n
    )
    return pair[0], pair[1]


_METHODS = {
    "additive": proportional_devig,
    "proportional": proportional_devig,
    "multiplicative": multiplicative_devig,
    "power": power_devig,
    "shin": shin_devig,
}


def devig(vigged: Sequence[float], method: str = "shin") -> list[float]:
    """Dispatcher for all supported devig methods.

    Accepted ``method`` values: ``additive``, ``proportional``,
    ``multiplicative``, ``power``, ``shin``. ``additive`` and ``proportional``
    are aliases.
    """
    key = (method or "shin").lower()
    if key not in _METHODS:
        raise ValueError(
            f"unknown devig method '{method}'. "
            f"Expected one of: {sorted(_METHODS)}"
        )
    return _METHODS[key](vigged)


__all__ = [
    "american_to_prob",
    "prob_to_american",
    "proportional_devig",
    "additive_devig",
    "multiplicative_devig",
    "power_devig",
    "shin_devig",
    "shin_devig_pair",
    "multiplicative_devig_pair",
    "power_devig_pair",
    "devig",
]
