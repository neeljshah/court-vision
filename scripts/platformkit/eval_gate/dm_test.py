"""Cluster-robust Diebold-Mariano test for "does model beat the close?" (blueprint N1).

Self-contained (numpy + stdlib). The SE clusters by game_id because many states
within one game are highly correlated -- a naive i.i.d. SE runs ~3x too narrow and
manufactures fake significance. This is the bug the package's QA caught in the
in-game blueprint; this reference is the correct, clustered version both gates reuse.

d_t = loss_close(t) - loss_model(t)  (POSITIVE mean => model is better).
"""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, lgamma, log, sqrt
from typing import Sequence
import numpy as np


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Evaluate the continued fraction used by the regularized beta function."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            return h
    return h


def _regularized_beta(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta I_x(a, b), using only the stdlib."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = exp(lgamma(a + b) - lgamma(a) - lgamma(b)
                + a * log(x) + b * log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_two_tailed_pvalue(stat: float, degrees_of_freedom: int) -> float:
    """Two-tailed Student-t p-value via the regularized incomplete beta."""
    x = degrees_of_freedom / (degrees_of_freedom + stat * stat)
    return _regularized_beta(x, degrees_of_freedom / 2.0, 0.5)


def _student_t_two_tailed_quantile(alpha: float, degrees_of_freedom: int) -> float:
    """The t value whose two-tailed tail mass is `alpha`, by bisection on the SAME
    p-value function the test reports.

    S40b / RT-4: `ci95` used the normal 1.96 while `p_value` used Student-t with g-1 df,
    so at small cluster counts the two disagreed. Measured (g=4, d=[0.7,0.2,0.2,0.7]):
    p_value(t,3)=0.0526 -- NOT significant -- yet the reported ci95=(0.16710, 0.73290)
    EXCLUDED 0 and read as significant; the honest t(3) interval (-0.00934, 0.90934)
    straddles 0. `run_gate._verdict` and `hedge_trial_runner.verdict_of` both read the
    interval's sign, so the mismatch could flip a printed verdict. Deriving the quantile
    from `_student_t_two_tailed_pvalue` makes the two provably the same distribution.
    """
    lo, hi = 0.0, 1.0e3
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _student_t_two_tailed_pvalue(mid, degrees_of_freedom) > alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class DMResult:
    dm_stat: float
    p_value: float          # two-tailed
    mean_diff: float
    ci95: tuple             # (lo, hi) on the mean loss difference
    n: int
    n_clusters: int


def cluster_blocks(values: Sequence[float], cluster_ids: Sequence) -> dict:
    """Return the game-id blocks used by every clustered eval-gate statistic.

    Keeping this small grouping primitive here prevents the bootstrap correction
    from silently drifting from the DM test's game-level clustering contract.
    """
    groups: dict = {}
    for value, cluster_id in zip(values, cluster_ids):
        groups.setdefault(cluster_id, []).append(float(value))
    return groups


def diebold_mariano(d: Sequence[float], cluster_ids: Sequence) -> DMResult:
    """Cluster-robust DM test on per-state loss differences d_t.

    Variance of the mean uses a cluster-sum estimator with a (G/(G-1)) finite
    -cluster correction, clustering by `cluster_ids` (e.g. game_id).
    """
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n == 0:
        return DMResult(0.0, 1.0, 0.0, (0.0, 0.0), 0, 0)
    if len(cluster_ids) != n:
        raise ValueError(
            f"cluster_ids length ({len(cluster_ids)}) must match d length ({n})"
        )
    groups = cluster_blocks(d, cluster_ids)
    g = len(groups)
    if g < 2:
        raise ValueError(f"at least 2 clusters are required; got {g}")
    md = float(d.mean())
    # sum of within-cluster deviations from the grand mean
    gsum = np.array([np.sum(np.asarray(v) - md) for v in groups.values()])
    var = float((gsum @ gsum) / (n * n) * (g / (g - 1)))
    se = sqrt(var) if var > 0 else 0.0
    dm = md / se if se > 0 else 0.0
    p = _student_t_two_tailed_pvalue(abs(dm), g - 1)
    # Same distribution as the p-value above -- never the normal 1.96 (RT-4).
    crit = _student_t_two_tailed_quantile(0.05, g - 1)
    ci = (md - crit * se, md + crit * se)
    return DMResult(float(dm), float(p), md, ci, n, g)
