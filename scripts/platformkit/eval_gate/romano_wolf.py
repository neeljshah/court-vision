"""Game-clustered Romano-Wolf max-statistic stepdown for eval-gate screens.

The null bootstrap resamples whole game_id blocks, never individual states.  It
uses the exact block construction from dm_test, then compares each ordered DM
statistic with the max statistic among the hypotheses still under consideration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

try:  # bare run from eval_gate cwd
    from dm_test import cluster_blocks, diebold_mariano
except ImportError:  # package run
    from .dm_test import cluster_blocks, diebold_mariano


@dataclass(frozen=True)
class RomanoWolfResult:
    adjusted_p: tuple
    rejected: tuple
    n_bootstrap: int


def _bootstrap_stat(values: np.ndarray, groups: dict, rng: np.random.Generator) -> float:
    """One centered, game-block bootstrap DM statistic under the joint null."""
    keys = list(groups)
    if not keys:
        return 0.0
    chosen = rng.integers(0, len(keys), size=len(keys))
    blocks = [np.asarray(groups[keys[i]], dtype=float) - values.mean() for i in chosen]
    draw = np.concatenate(blocks)
    draw_ids = [block_id for block_id, block in enumerate(blocks) for _ in block]
    return max(0.0, diebold_mariano(draw, draw_ids).dm_stat)


def romano_wolf_stepdown(loss_diffs: Sequence[Sequence[float]],
                         game_ids: Sequence[Sequence], *, alpha: float = 0.05,
                         n_bootstrap: int = 2000, seed: int = 2718) -> RomanoWolfResult:
    """Return FWER-adjusted one-sided p-values for positive clustered DM tests.

    ``loss_diffs[i]`` uses the eval-gate convention (positive favors the model).
    A shared RNG makes results reproducible; each statistic still resamples its
    own complete game blocks, so no within-game state is treated as independent.
    """
    if len(loss_diffs) != len(game_ids):
        raise ValueError("loss_diffs and game_ids must have the same length")
    k = len(loss_diffs)
    if k == 0:
        return RomanoWolfResult((), (), int(n_bootstrap))
    n_bootstrap = max(1, int(n_bootstrap))
    values = [np.asarray(x, dtype=float) for x in loss_diffs]
    observed = np.array([max(0.0, diebold_mariano(x, ids).dm_stat)
                         for x, ids in zip(values, game_ids)], dtype=float)
    groups = [cluster_blocks(x, ids) for x, ids in zip(values, game_ids)]
    rng = np.random.default_rng(seed)
    boot = np.empty((n_bootstrap, k), dtype=float)
    for b in range(n_bootstrap):
        for j in range(k):
            boot[b, j] = _bootstrap_stat(values[j], groups[j], rng)
    order = np.argsort(-observed, kind="stable")
    adjusted = np.ones(k, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        remaining = order[rank:]
        p = (1.0 + float(np.sum(np.max(boot[:, remaining], axis=1) >= observed[index]))) / (n_bootstrap + 1.0)
        running = max(running, p)
        adjusted[index] = running
    return RomanoWolfResult(tuple(float(x) for x in adjusted),
                            tuple(bool(x <= alpha and observed[i] > 0.0)
                                  for i, x in enumerate(adjusted)), n_bootstrap)


__all__ = ["RomanoWolfResult", "romano_wolf_stepdown"]
