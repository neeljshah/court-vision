"""Focused synthetic checks for game-clustered in-game evidence."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.gap_effective_n import (
    INSUFFICIENT,
    cluster_bootstrap,
    effective_sample_size,
    evaluate_folds,
    render,
)


def _correlated_ticks(games: int = 40, ticks_per_game: int = 200) -> pd.DataFrame:
    generator = np.random.default_rng(3)
    rows = []
    for game_index in range(games):
        shared = generator.normal(scale=np.sqrt(0.5))
        values = shared + generator.normal(scale=np.sqrt(0.5), size=ticks_per_game)
        rows.extend({"game": "g%d" % game_index, "loss_differential": value} for value in values)
    return pd.DataFrame(rows)


def test_effective_sample_size_matches_correlated_design_effect() -> None:
    rows = _correlated_ticks()
    summary = effective_sample_size(rows)
    expected = len(rows) / (1.0 + 0.5 * 199)
    assert summary["n_games"] == 40
    assert abs(summary["n_eff"] - expected) / expected < 0.05


def test_cluster_bootstrap_resamples_complete_games() -> None:
    rows = _correlated_ticks(games=8, ticks_per_game=3)
    draws = cluster_bootstrap(rows, lambda sample: sample.groupby("game").size().max(), iterations=50, seed=5)
    assert draws.max() > 3


def test_undertrained_fold_is_excluded_and_renderer_names_games() -> None:
    first = pd.DataFrame({"game": ["a"] * 4, "loss_differential": [10.0] * 4})
    second = pd.DataFrame({"game": ["b", "c", "d", "e"] * 2, "loss_differential": [0.0] * 8})
    report = evaluate_folds([
        {"name": "fold_1", "train_games": 1, "rows": first},
        {"name": "fold_2", "train_games": 4, "rows": second},
    ], minimum_training_games=2)
    assert report["folds"][0]["status"] == INSUFFICIENT
    assert report["pooled"]["mean_loss_differential"] == 0.0
    assert report["pooled"]["mean_loss_differential"] != pd.concat([first, second])["loss_differential"].mean()
    output = render(report)
    assert "N_GAMES" in output
    assert "fold_1 | INSUFFICIENT | 1 | - | -" in output
