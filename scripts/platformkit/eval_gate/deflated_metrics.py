"""scripts.platformkit.eval_gate.deflated_metrics -- trial-count-aware significance.

Canonicalizes the Bonferroni-style deflation the repo already applies in a few
places (scripts/platformkit/combo/fwer_budget.py:eps_eff deflates alpha by k;
scripts/platformkit/signal_foundry.py:report_significance deflates the z bar the
same way) into one shared module, plus a power pre-check so a future claim's
required (n, k) can be sized BEFORE any games are scored. Calibration tooling
only -- no $ / ROI / edge claim lives here (see .claude/rules/no-edge-claims.md).
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
from scipy import integrate, stats

_NORMAL = NormalDist()


def _check_k(k: int) -> int:
    """k is a TRIAL COUNT, so k < 1 is an upstream bug (an empty trial ledger,
    an off-by-one). Clamping it to 1 would silently return an UNDEFLATED result
    on a significance path -- fail open, in the one direction that manufactures
    false discoveries. Raise instead, matching expected_max_z."""
    k = int(k)
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    return k


def expected_max_z(k: int) -> float:
    """Expected value of the maximum of k iid standard normal draws.

    Exact via numerical integration (not the sqrt(2 ln k) asymptotic form): the
    max of k iid N(0,1) has density f(x) = k * phi(x) * Phi(x)**(k-1), so
    E[max] = integral of x * f(x) dx over the real line. scipy.integrate.quad
    is adaptive and exact to its tolerance for any k -- no separate large-k
    asymptotic branch needed, and no special-casing beyond k=1 (handled in
    closed form: E[max of 1 draw] = E[Z] = 0).

    Golden checks (see test_deflated_metrics.py):
      k=1  -> 0.0 (trivial, E[Z]=0 by symmetry)
      k=2  -> 1/sqrt(pi) = 0.5641895835477563 (textbook closed form: for
              X,Y iid N(0,1), max(X,Y) = (X+Y)/2 + |X-Y|/2; (X+Y)/2 has mean 0,
              (X-Y)/2 ~ N(0, 1/2) so E|X-Y|/2 = sqrt(1/(2*pi)) * sqrt(2) ... the
              standard result is E[max] = 1/sqrt(pi))
      k=10 -> 1.538752730835173 (reference value from this same integral,
              computed independently at authoring time; scipy.integrate.quad
              reports its own error estimate ~1.9e-10 at this k)
    """
    k = _check_k(k)
    if k == 1:
        return 0.0

    def integrand(x: float) -> float:
        return x * k * stats.norm.pdf(x) * stats.norm.cdf(x) ** (k - 1)

    value, _err = integrate.quad(integrand, -np.inf, np.inf, limit=200)
    return float(value)


def deflated_p(raw_p: float, k: int) -> float:
    """Bonferroni-deflate a raw p-value for k charged trials: min(1.0, raw_p * k).

    The p-value-side dual of the alpha-side deflation already used in
    combo/fwer_budget.py (eps_eff = alpha / k) and signal_foundry.py
    (report_significance's inv_cdf(1 - alpha/(2*trials)) z bar):
    raw_p <= alpha/k  <=>  deflated_p(raw_p, k) <= alpha. One canonical
    function so every caller deflates identically.

    Golden checks: deflated_p(0.01, 5) -> 0.05; deflated_p(0.5, 10) -> 1.0
    (capped, not 5.0); deflated_p(x, 1) -> x (k=1 is a no-op).
    """
    if not (0.0 <= raw_p <= 1.0):
        raise ValueError(f"raw_p must be in [0,1], got {raw_p}")
    k = _check_k(k)
    return min(1.0, float(raw_p) * k)


def min_detectable_brier_edge(n: int, k: int, alpha: float = 0.05,
                              power: float = 0.5) -> float:
    """Smallest mean Brier improvement detectable at `alpha`, two-sided,
    Bonferroni-deflated across k charged trials, over n paired game
    observations, at the requested `power`.

        MDE = (z_(1 - alpha/(2k)) + z_power) * sigma_max / sqrt(n),  sigma_max = 1

    The two knobs point in OPPOSITE directions, so read the result as a bound
    only on the sigma axis:

    - sigma: conservative. A per-game Brier score lies in [0,1], so a paired
      difference lies in [-1,1] and by Popoviciu's inequality its variance is at
      most ((1-(-1))/2)**2 = 1. No empirical sigma is needed, so a future claim's
      (n, k) is sizeable before a single game is scored. Substituting a measured
      per-game sigma can only shrink the MDE.
    - power: NOT conservative below 0.8. The default power=0.5 makes the second
      term z_0.5 = 0, which reduces the expression to the bare critical value --
      the effect size you would merely be as likely as not to detect. Anyone
      SIZING a study (choosing n) should pass power=0.8, which is ~43% larger and
      is the honest requirement; the default exists so the function reports the
      rejection threshold by default rather than silently assuming a power level.

    Golden checks (power=0.5, so z_power=0 and the term drops out):
    n=100, k=1, alpha=0.05 -> z=NormalDist().inv_cdf(0.975)=1.9599639845400536,
    MDE=1.9599639845400536/10=0.19599639845400535.
    n=400, k=5, alpha=0.05 -> z=inv_cdf(1-0.005)=2.5758293035489,
    MDE=2.5758293035489/20=0.128791465177445.
    """
    n = int(n)
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"alpha must be in (0,1], got {alpha}")
    if not (0.0 < power < 1.0):
        raise ValueError(f"power must be in (0,1), got {power}")
    k = _check_k(k)
    z_alpha = _NORMAL.inv_cdf(1.0 - alpha / (2.0 * k))
    z_power = _NORMAL.inv_cdf(power)  # 0.0 at power=0.5
    return (z_alpha + z_power) / math.sqrt(n)
