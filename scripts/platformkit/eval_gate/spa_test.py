"""Hansen SPA family test using a stationary bootstrap of whole game clusters.

Loss differences use the eval-gate sign convention: positive means a candidate
has lower loss than the devigged-close benchmark.  Each game contributes one
mean differential, so repeated in-game states cannot create fake evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    from dm_test import cluster_blocks
except ImportError:  # pragma: no cover - package import exercised by tests
    from .dm_test import cluster_blocks


@dataclass(frozen=True)
class SPAResult:
    """One-sided consistent SPA result for a family of candidate models."""

    family_p: float
    studentized_stats: tuple
    rejected: bool
    n_bootstrap: int
    n_clusters: int


def game_cluster_matrix(loss_diffs: Sequence[Sequence[float]],
                        game_ids: Sequence[Sequence]) -> np.ndarray:
    """Aggregate every candidate to aligned game means, rejecting misalignment."""
    if len(loss_diffs) != len(game_ids):
        raise ValueError("loss_diffs and game_ids must have the same length")
    if not loss_diffs:
        raise ValueError("at least one candidate is required")
    rows, reference_keys = [], None
    for values, ids in zip(loss_diffs, game_ids):
        if len(values) != len(ids):
            raise ValueError("each loss-diff vector must match its game_ids")
        groups = cluster_blocks(values, ids)
        keys = tuple(groups)
        if reference_keys is None:
            reference_keys = keys
        elif set(keys) != set(reference_keys):
            raise ValueError("all candidates must use the same game_id clusters")
        rows.append([float(np.mean(groups[key])) for key in reference_keys])
    matrix = np.asarray(rows, dtype=float)
    if matrix.shape[1] < 2:
        raise ValueError("at least 2 game clusters are required")
    if not np.isfinite(matrix).all():
        raise ValueError("loss differentials must be finite")
    return matrix


def studentized_stats(game_means: np.ndarray) -> np.ndarray:
    """Return one-sided game-cluster t statistics for each candidate."""
    n_games = game_means.shape[1]
    scale = np.std(game_means, axis=1, ddof=1)
    stats = np.zeros(game_means.shape[0], dtype=float)
    nonzero = scale > 0.0
    stats[nonzero] = np.sqrt(n_games) * game_means[nonzero].mean(axis=1) / scale[nonzero]
    return stats


def stationary_indices(n_games: int, rng: np.random.Generator,
                       mean_block_length: float) -> np.ndarray:
    """Draw stationary-bootstrap game indices with geometric restart lengths."""
    if n_games < 1 or mean_block_length <= 0.0:
        raise ValueError("n_games and mean_block_length must be positive")
    restart = min(1.0, 1.0 / float(mean_block_length))
    indices = np.empty(n_games, dtype=int)
    for pos in range(n_games):
        if pos == 0 or rng.random() < restart:
            indices[pos] = int(rng.integers(n_games))
        else:
            indices[pos] = (indices[pos - 1] + 1) % n_games
    return indices


def hansen_spa(loss_diffs: Sequence[Sequence[float]], game_ids: Sequence[Sequence], *,
               alpha: float = 0.05, n_bootstrap: int = 2000, seed: int = 2718,
               mean_block_length: float = 5.0) -> SPAResult:
    """Test whether any candidate beats the benchmark with Hansen's consistent SPA p.

    Candidates share each stationary draw.  Therefore duplicated candidates remain
    perfectly dependent and yield precisely the one-candidate family p-value.
    """
    matrix = game_cluster_matrix(loss_diffs, game_ids)
    n_games = matrix.shape[1]
    n_bootstrap = max(1, int(n_bootstrap))
    observed = studentized_stats(matrix)
    observed_max = float(max(0.0, observed.max()))
    threshold = np.sqrt(max(0.0, 2.0 * np.log(np.log(n_games))))
    means = matrix.mean(axis=1)
    # Hansen's consistent recentering retains clearly inferior candidates
    # uncentered, while centering candidates that can affect the family maximum.
    recenter = np.where(observed >= -threshold, means, 0.0)
    scales = np.std(matrix, axis=1, ddof=1)
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(n_bootstrap):
        draw = matrix[:, stationary_indices(n_games, rng, mean_block_length)]
        boot = np.zeros(matrix.shape[0], dtype=float)
        usable = scales > 0.0
        boot[usable] = (np.sqrt(n_games) * (draw[usable].mean(axis=1) - recenter[usable])
                        / scales[usable])
        if float(max(0.0, boot.max())) >= observed_max:
            exceed += 1
    p_value = (1.0 + exceed) / (n_bootstrap + 1.0)
    return SPAResult(float(p_value), tuple(float(x) for x in observed),
                     bool(observed_max > 0.0 and p_value <= alpha),
                     n_bootstrap, n_games)


def render_catalog_report(signals: Sequence[tuple[str, str]]) -> str:
    """Record the honest catalog cross-check boundary when loss vectors are absent."""
    lines = [
        "HANSEN SPA CATALOG CROSS-CHECK",
        "benchmark=devigged_close",
        "family_spa_p=NA (historical per-signal loss differentials are not archived)",
        "per-signal studentized statistics=NA; no SPA survivor can be inferred",
        "retro_verdict_comparison=NOT_EVALUABLE (not an agreement claim)",
        "",
        "signal                                      studentized_stat  spa_verdict",
        "------------------------------------------  ----------------  -----------",
    ]
    for domain, name in signals:
        lines.append(f"{(domain + ':' + name)[:42]:<42}  {'NA':>16}  {'NOT_EVALUABLE':<11}")
    lines += ["", f"catalog_signals_on_disk={len(signals)}",
              "documented_retro_survivors=0", ""]
    return "\n".join(lines)


def write_catalog_report(path: Path | None = None) -> str:
    """Write the catalog evidence-boundary report alongside this module."""
    try:
        from retro_correction import catalog_signals
    except ImportError:  # pragma: no cover - package import exercised by tests
        from .retro_correction import catalog_signals
    text = render_catalog_report(catalog_signals())
    target = path or Path(__file__).with_name("spa_catalog_report.txt")
    target.write_text(text, encoding="ascii")
    return text


if __name__ == "__main__":  # pragma: no cover
    print(write_catalog_report(), end="")
