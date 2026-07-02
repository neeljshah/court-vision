"""improve.seed_stability -- multi-seed bootstrap stability guard (Milestone-8 ratchet).

A single-seed estimator driving a metric jump is a known artifact (see
feedback_seed_stability_check.md). This module provides the guard:

  stable(metric_fn, data, *, seeds, n_boot, alpha) -> StabilityResult

Bootstrap-resample `data` under each seed, apply `metric_fn` to both the
resample and the corresponding complement/held-out portion, accumulate the
per-resample improvement, then inspect the FULL distribution across all
(seed x n_boot) draws. stable=True only when the 10th-percentile (p10) lower
bound of that distribution is >= 0 -- i.e., the improvement holds even in the
unlucky tail. A jump that collapses under resampling yields p10 < 0 -> REJECT.

Honesty invariants (binding):
- stable() is PURE: deterministic given the same seeds, never raises, never
  reads or writes any file, never makes a $ claim.
- stable=False is a SUCCESS (an honest REJECT), not a failure of the guard.
- The guard operates on an improvement delta (candidate minus baseline).
  The caller supplies metric_fn so the sign convention is EXPLICIT: the fn
  must return LOWER-IS-BETTER scores (Brier, CRPS, pinball, log-loss).
  improvement = baseline_score - candidate_score (positive => candidate wins).
- Never accesses src/ kernel/ api/ human-gated trees.

API:
  stable(metric_fn, data, *, seeds=..., n_boot=..., alpha=0.10)
      -> StabilityResult(stable, p10, mean, seeds_used, n_draws, deltas_pct)

stdlib + numpy only (no scipy, no sklearn, no external deps).
<=300 LOC / ASCII only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

# Default seed list -- varied enough to expose single-seed bias.
_DEFAULT_SEEDS: Tuple[int, ...] = (0, 1, 2, 3, 7, 42, 137, 1337)
_DEFAULT_N_BOOT: int = 200


@dataclass(frozen=True)
class StabilityResult:
    """Immutable result from stable().

    stable       : True iff p10 >= 0 across all (seed x draw) resamples.
    p10          : 10th percentile of the improvement distribution. The primary
                   gate criterion: must be >= 0 to SHIP.
    mean         : mean improvement across all draws (diagnostic).
    seeds_used   : the seed list actually used (reproducibility record).
    n_draws      : total number of bootstrap draws evaluated.
    deltas_pct   : fraction of draws where improvement > 0 (0-1, diagnostic).
    """
    stable: bool
    p10: float
    mean: float
    seeds_used: Tuple[int, ...]
    n_draws: int
    deltas_pct: float


def stable(
    metric_fn: Callable[[Sequence, Sequence], float],
    data: Sequence,
    *,
    seeds: Optional[Sequence[int]] = None,
    n_boot: int = _DEFAULT_N_BOOT,
    alpha: float = 0.10,
) -> StabilityResult:
    """Multi-seed bootstrap stability guard for a candidate's improvement.

    Parameters
    ----------
    metric_fn:
        Callable(train_rows, test_rows) -> float.  Lower-is-better (Brier,
        CRPS, pinball, log-loss).  The caller controls train/test split
        semantics inside the fn; stable() only supplies the bootstrap indices.
        The fn must not raise -- exceptions are silently treated as NaN draws
        and do not contribute to the distribution (they count toward n_draws
        only if they produce a numeric result).
    data:
        The dataset rows passed to metric_fn (a sequence indexable by a numpy
        integer index array).
    seeds:
        Iterable of integer seeds.  Each seed independently drives n_boot
        draws.  Defaults to _DEFAULT_SEEDS (8 seeds).  Pass a single-element
        list to replicate the naive single-seed check and observe the artifact.
    n_boot:
        Bootstrap draws per seed.  Total draws = len(seeds) * n_boot.
        Default 200 per seed.
    alpha:
        The percentile level for the lower bound.  Default 0.10 -> p10.
        stable=True iff np.percentile(deltas, alpha*100) >= 0.

    Returns
    -------
    StabilityResult (never raises).

    Notes
    -----
    Each draw re-samples len(data) rows WITH replacement (standard bootstrap).
    Out-of-bag rows form the test set.  metric_fn receives (boot_rows, oob_rows)
    as plain Python lists.  improvement = metric_fn(boot, oob) where the fn
    should return the BASELINE score when given (boot, oob) -- the guard
    accumulates (baseline_metric - candidate_metric) improvements.

    HOWEVER, the most common usage pattern is to bake both models INTO metric_fn:
      metric_fn(train_rows, test_rows) -> baseline_score - candidate_score
    and return the improvement directly (so the guard just checks sign).  That
    is how the ratchet uses it.  The guard does NOT care which convention the
    caller uses as long as POSITIVE delta == improvement.
    """
    if seeds is None:
        seeds = _DEFAULT_SEEDS
    seeds_used: Tuple[int, ...] = tuple(int(s) for s in seeds)

    n = len(data)
    if n == 0:
        return StabilityResult(
            stable=False, p10=0.0, mean=0.0,
            seeds_used=seeds_used, n_draws=0, deltas_pct=0.0,
        )

    data_arr = list(data)  # make indexable without copying bulk data
    all_deltas: List[float] = []

    for seed in seeds_used:
        rng = np.random.default_rng(int(seed))
        for _ in range(int(n_boot)):
            boot_idx = rng.integers(0, n, size=n)
            boot_set = set(boot_idx.tolist())
            oob_mask = [i for i in range(n) if i not in boot_set]
            if not oob_mask:
                # Pathological: all rows in the boot (vanishingly rare for n>1).
                continue
            boot_rows = [data_arr[i] for i in boot_idx]
            oob_rows = [data_arr[i] for i in oob_mask]
            try:
                delta = float(metric_fn(boot_rows, oob_rows))
            except Exception:
                continue
            if math.isfinite(delta):
                all_deltas.append(delta)

    if not all_deltas:
        # No numeric draws at all -- fail safe.
        return StabilityResult(
            stable=False, p10=float("nan"), mean=float("nan"),
            seeds_used=seeds_used, n_draws=0, deltas_pct=0.0,
        )

    arr = np.array(all_deltas, dtype=float)
    p10 = float(np.percentile(arr, alpha * 100.0))
    mean_val = float(arr.mean())
    pos_frac = float(np.mean(arr > 0.0))

    return StabilityResult(
        stable=bool(p10 >= 0.0),
        p10=p10,
        mean=mean_val,
        seeds_used=seeds_used,
        n_draws=len(all_deltas),
        deltas_pct=pos_frac,
    )


__all__ = ["stable", "StabilityResult"]
