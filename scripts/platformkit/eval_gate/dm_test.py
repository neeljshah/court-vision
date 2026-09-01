"""Cluster-robust Diebold-Mariano test for "does model beat the close?" (blueprint N1).

Self-contained (numpy + stdlib). The SE clusters by game_id because many states
within one game are highly correlated -- a naive i.i.d. SE runs ~3x too narrow and
manufactures fake significance. This is the bug the package's QA caught in the
in-game blueprint; this reference is the correct, clustered version both gates reuse.

d_t = loss_close(t) - loss_model(t)  (POSITIVE mean => model is better).
"""
from __future__ import annotations
from dataclasses import dataclass
from math import erf, sqrt
from typing import Sequence
import numpy as np


def _norm_sf(z: float) -> float:
    """Upper-tail of the standard normal via erf (no scipy dependency)."""
    return 0.5 * (1.0 - erf(z / sqrt(2.0)))


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
    md = float(d.mean())
    groups = cluster_blocks(d, cluster_ids)
    g = len(groups)
    if g > 1:
        # sum of within-cluster deviations from the grand mean
        gsum = np.array([np.sum(np.asarray(v) - md) for v in groups.values()])
        var = float((gsum @ gsum) / (n * n) * (g / (g - 1)))
    else:
        var = float(d.var(ddof=1) / n) if n > 1 else 0.0
    se = sqrt(var) if var > 0 else 0.0
    dm = md / se if se > 0 else 0.0
    p = 2.0 * _norm_sf(abs(dm))
    ci = (md - 1.96 * se, md + 1.96 * se)
    return DMResult(float(dm), float(p), md, ci, n, g)
