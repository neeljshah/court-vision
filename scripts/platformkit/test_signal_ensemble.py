"""Focused synthetic tests for the leak-safe weak-signal combining layer."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.signal_ensemble import evaluate_ensemble


def _frame(weak: np.ndarray, base_signal: np.ndarray | None = None) -> pd.DataFrame:
    """Make a chronological frame where the target needs combined weak inputs."""
    size = len(weak)
    if base_signal is None:
        base_signal = np.full(size, 30.0)
    target = 20.0 + weak.sum(axis=1) * 2.0
    data: dict[str, object] = {
        "gameDate": pd.date_range("2024-01-01", periods=size, freq="D"),
        "minutes": target,
        "minutes_expanding": np.full(size, 30.0),
        "minutes_l5": np.full(size, 30.0),
        "tracking_per36_l5": base_signal,
    }
    for number in range(weak.shape[1]):
        data["weak_{0}".format(number)] = weak[:, number]
    return pd.DataFrame(data)


def test_three_individually_weak_signals_combine_to_improve() -> None:
    """Three low-amplitude components clear the ensemble improvement boundary."""
    rng = np.random.default_rng(13)
    weak = rng.normal(scale=0.35, size=(240, 3))
    frame = _frame(weak)
    frame["minutes"] = 20.0 + weak.sum(axis=1) * 0.3

    individual = [evaluate_ensemble(frame, ["weak_{0}".format(number)]) for number in range(3)]
    result = evaluate_ensemble(frame, ["weak_0", "weak_1", "weak_2"])

    assert [item["verdict"] for item in individual] == ["FLAT", "FLAT", "FLAT"]
    assert result["verdict"] == "IMPROVED"
    assert result["delta"] < 0.0


def test_pure_noise_stays_flat_without_degradation() -> None:
    """Pure noise cannot degrade an already exact baseline beyond tolerance."""
    size = 240
    noise = np.random.default_rng(7).normal(size=(size, 3))
    frame = _frame(noise)
    frame["minutes"] = 30.0

    result = evaluate_ensemble(frame, ["weak_0", "weak_1", "weak_2"])

    assert result["verdict"] == "FLAT"
    assert result["delta"] <= 0.05
