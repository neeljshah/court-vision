"""Focused tests for the static candidate-metric upper-bound screen."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.novel_metric_lift import evaluate_lift


def _frame(candidate: np.ndarray, base_has_signal: bool = False) -> pd.DataFrame:
    size = len(candidate)
    signal = np.asarray([(number * 17) % 13 for number in range(size)], dtype=float)
    return pd.DataFrame({
        "gameDate": pd.date_range("2024-01-01", periods=size, freq="D"),
        "gameId": ["002240{0:04d}".format(number) for number in range(size)],
        "personId": np.arange(size),
        "minutes": signal * 3.0,
        "minutes_expanding": 30.0,
        "minutes_l5": 30.0,
        "tracking_per36_l5": signal if base_has_signal else 2.0,
        "cum_distance_7d": 4.0,
        "style_embedding_1": 0.5,
        "candidate": candidate,
    })


def test_engineered_signal_is_screen_positive() -> None:
    """A candidate that carries the target signal clears the screen threshold."""
    signal = np.asarray([(number * 17) % 13 for number in range(240)], dtype=float)

    result = evaluate_lift(_frame(signal), ["candidate"])

    assert result["verdict"] == "SCREEN-POSITIVE"
    assert result["delta"] < 0.0


def test_random_noise_is_flat() -> None:
    """Deterministic random noise cannot clear the practical screen margin."""
    result = evaluate_lift(_frame(np.random.default_rng(7).normal(size=240), base_has_signal=True), ["candidate"])

    assert result["verdict"] == "FLAT"
