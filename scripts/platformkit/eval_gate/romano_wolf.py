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
    from spa_test import game_cluster_matrix, stationary_indices, studentized_stats
except ImportError:  # package run
    from .spa_test import game_cluster_matrix, stationary_indices, studentized_stats


@dataclass(frozen=True)
class RomanoWolfResult:
    adjusted_p: tuple
    rejected: tuple
    n_bootstrap: int


def romano_wolf_stepdown(loss_diffs: Sequence[Sequence[float]],
                         game_ids: Sequence[Sequence], *, alpha: float = 0.05,
                         n_bootstrap: int = 2000, seed: int = 2718,
                         mean_block_length: float = 5.0) -> RomanoWolfResult:
    """Return FWER-adjusted one-sided p-values for positive clustered DM tests.

    ``loss_diffs[i]`` uses the eval-gate convention (positive favors the model).
    A shared RNG makes results reproducible; each statistic still resamples its
    own complete game blocks, so no within-game state is treated as independent.
    """
    if len(loss_diffs) != len(game_ids):
        raise ValueError("loss_diffs and game_ids must have the same length")
    if not loss_diffs:
        return RomanoWolfResult((), (), int(n_bootstrap))
    try:
        matrix = game_cluster_matrix(loss_diffs, game_ids)
    except ValueError as exc:
        if "same game_id clusters" not in str(exc):
            raise
        matrix = None
    k = len(loss_diffs)
    n_bootstrap = max(1, int(n_bootstrap))
    if matrix is not None:
        n_games = matrix.shape[1]
        observed = np.maximum(0.0, studentized_stats(matrix))
        centered = matrix - matrix.mean(axis=1, keepdims=True)
        scales = np.std(matrix, axis=1, ddof=1)
        independent = None
    else:
        # Existing gate rows are separate corpora, not one shared game family.
        # Preserve their original independent-cluster behavior; common-game
        # families take the joint, dependence-preserving branch above.
        independent = [game_cluster_matrix([values], [ids])[0]
                       for values, ids in zip(loss_diffs, game_ids)]
        observed = np.array([max(0.0, studentized_stats(row[None, :])[0])
                             for row in independent])
    rng = np.random.default_rng(seed)
    boot = np.empty((n_bootstrap, k), dtype=float)
    for b in range(n_bootstrap):
        if independent is None:
            draw = centered[:, stationary_indices(n_games, rng, mean_block_length)]
            boot[b] = np.maximum(0.0, np.sqrt(n_games) * draw.mean(axis=1) / scales)
        else:
            for j, row in enumerate(independent):
                draw = row - row.mean()
                scale = float(np.std(row, ddof=1))
                boot[b, j] = (0.0 if scale == 0.0 else max(
                    0.0, np.sqrt(len(row)) * draw[stationary_indices(
                        len(row), rng, mean_block_length)].mean() / scale))
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
