"""Game-clustered evidence summaries for in-game tick evaluations.

Ticks from one game share game state and therefore are not independent
observations.  This module keeps the game as the resampling and test unit.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd


INSUFFICIENT = "INSUFFICIENT"
OK = "OK"


def _require_columns(rows: pd.DataFrame, game_column: str, loss_column: str) -> pd.DataFrame:
    missing = {game_column, loss_column}.difference(rows.columns)
    if missing:
        raise ValueError("missing required columns: %s" % ", ".join(sorted(missing)))
    usable = rows[[game_column, loss_column]].dropna()
    if usable.empty:
        raise ValueError("no non-null game/loss rows")
    return usable


def intraclass_correlation(
    rows: pd.DataFrame, game_column: str = "game", loss_column: str = "loss_differential"
) -> float:
    """Estimate one-way random-effects ICC for tick loss differentials."""
    usable = _require_columns(rows, game_column, loss_column)
    groups = [group[loss_column].to_numpy(dtype=float) for _, group in usable.groupby(game_column, sort=False)]
    count = len(groups)
    total = sum(len(group) for group in groups)
    if count < 2 or total <= count:
        return 0.0
    means = np.asarray([group.mean() for group in groups])
    sizes = np.asarray([len(group) for group in groups], dtype=float)
    grand_mean = float(np.average(means, weights=sizes))
    between = float(np.sum(sizes * (means - grand_mean) ** 2) / (count - 1))
    within_sum = sum(float(np.sum((group - group.mean()) ** 2)) for group in groups)
    within = within_sum / (total - count)
    effective_size = (total - float(np.sum(sizes ** 2)) / total) / (count - 1)
    denominator = between + (effective_size - 1.0) * within
    if denominator <= 0.0:
        return 0.0
    return float(np.clip((between - within) / denominator, 0.0, 1.0))


def design_effect(rho: float, mean_ticks_per_game: float) -> float:
    """Compute the clustered-sample design effect from ICC and mean cluster size."""
    if not 0.0 <= rho <= 1.0:
        raise ValueError("rho must be between zero and one")
    if mean_ticks_per_game < 1.0:
        raise ValueError("mean_ticks_per_game must be at least one")
    return 1.0 + rho * (mean_ticks_per_game - 1.0)


def effective_sample_size(
    rows: pd.DataFrame, game_column: str = "game", loss_column: str = "loss_differential"
) -> dict[str, float | int]:
    """Return tick and game counts, ICC, design effect, and clustered ESS."""
    usable = _require_columns(rows, game_column, loss_column)
    n_ticks = len(usable)
    n_games = int(usable[game_column].nunique())
    mean_ticks_per_game = n_ticks / n_games
    rho = intraclass_correlation(usable, game_column, loss_column)
    deff = design_effect(rho, mean_ticks_per_game)
    return {
        "n_ticks": n_ticks,
        "n_games": n_games,
        "rho": rho,
        "design_effect": deff,
        "n_eff": n_ticks / deff,
    }


def cluster_bootstrap(
    rows: pd.DataFrame,
    metric: Callable[[pd.DataFrame], float],
    iterations: int = 1_000,
    seed: int = 20260831,
    game_column: str = "game",
) -> np.ndarray:
    """Bootstrap a metric by sampling whole games, never individual ticks."""
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if game_column not in rows.columns:
        raise ValueError("missing required column: %s" % game_column)
    games = [group for _, group in rows.groupby(game_column, sort=False)]
    if not games:
        raise ValueError("no games available for bootstrap")
    randomizer = np.random.default_rng(seed)
    values = []
    for _ in range(iterations):
        indices = randomizer.integers(0, len(games), size=len(games))
        sample = pd.concat([games[index] for index in indices], ignore_index=True)
        values.append(float(metric(sample)))
    return np.asarray(values, dtype=float)


def diebold_mariano_hln(
    rows: pd.DataFrame, game_column: str = "game", loss_column: str = "loss_differential", horizon: int = 1
) -> dict[str, float | int | str]:
    """Run game-level DM with the Harvey-Leybourne-Newbold correction."""
    if horizon < 1:
        raise ValueError("horizon must be at least one")
    usable = _require_columns(rows, game_column, loss_column)
    game_losses = usable.groupby(game_column, sort=False)[loss_column].mean().to_numpy(dtype=float)
    n_games = len(game_losses)
    if n_games < 2:
        return {"status": INSUFFICIENT, "n_games": n_games}
    centered = game_losses - game_losses.mean()
    long_run_variance = float(np.dot(centered, centered) / n_games)
    for lag in range(1, min(horizon, n_games)):
        covariance = float(np.dot(centered[lag:], centered[:-lag]) / n_games)
        long_run_variance += 2.0 * (1.0 - lag / horizon) * covariance
    if long_run_variance <= 0.0:
        return {"status": INSUFFICIENT, "n_games": n_games}
    statistic = float(game_losses.mean() / math.sqrt(long_run_variance / n_games))
    correction = math.sqrt((n_games + 1 - 2 * horizon + horizon * (horizon - 1) / n_games) / n_games)
    statistic *= correction
    p_value = math.erfc(abs(statistic) / math.sqrt(2.0))
    return {"status": OK, "n_games": n_games, "statistic": statistic, "p_value": p_value,
            "mean_loss_differential": float(game_losses.mean())}


def evaluate_folds(
    folds: Iterable[Mapping[str, Any]], minimum_training_games: int, game_column: str = "game",
    loss_column: str = "loss_differential",
) -> dict[str, Any]:
    """Exclude under-trained folds and report all retained evidence at game level.

    Each input mapping requires ``rows`` and ``train_games``; an optional ``name``
    makes render output stable for callers.
    """
    if minimum_training_games < 1:
        raise ValueError("minimum_training_games must be positive")
    reports: list[dict[str, Any]] = []
    retained: list[pd.DataFrame] = []
    for index, fold in enumerate(folds, start=1):
        train_games = int(fold["train_games"])
        report: dict[str, Any] = {"name": fold.get("name", "fold_%d" % index), "train_games": train_games}
        if train_games < minimum_training_games:
            report["status"] = INSUFFICIENT
        else:
            rows = fold["rows"]
            report.update(effective_sample_size(rows, game_column, loss_column))
            report["status"] = OK
            report["mean_loss_differential"] = float(rows[loss_column].mean())
            report["dm"] = diebold_mariano_hln(rows, game_column, loss_column)
            retained.append(rows)
        reports.append(report)
    pooled = {"status": INSUFFICIENT}
    if retained:
        combined = pd.concat(retained, ignore_index=True)
        pooled = {"status": OK, **effective_sample_size(combined, game_column, loss_column),
                  "mean_loss_differential": float(combined[loss_column].mean()),
                  "dm": diebold_mariano_hln(combined, game_column, loss_column)}
    return {"minimum_training_games": minimum_training_games, "folds": reports, "pooled": pooled}


def render(report: Mapping[str, Any]) -> str:
    """Render fold evidence with both tick and game counts in every data row."""
    lines = ["FOLD | STATUS | TRAIN_GAMES | N_TICKS | N_GAMES | RHO | DEFF | N_EFF | MEAN_LOSS_DIFF"]
    for fold in list(report.get("folds", [])) + [{"name": "POOLED", **report.get("pooled", {})}]:
        if fold.get("status") != OK:
            lines.append("%s | INSUFFICIENT | %s | - | - | - | - | - | -" %
                         (fold["name"], fold.get("train_games", "-")))
            continue
        lines.append("%s | OK | %s | %d | %d | %.6f | %.6f | %.2f | %.6f" %
                     (fold["name"], fold.get("train_games", "-"), fold["n_ticks"], fold["n_games"],
                      fold["rho"], fold["design_effect"], fold["n_eff"], fold["mean_loss_differential"]))
    return "\n".join(lines)
