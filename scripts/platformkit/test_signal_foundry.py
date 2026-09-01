"""Focused synthetic coverage for Signal Foundry."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import signal_foundry as foundry


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(4); size = 180
    left = rng.integers(0, 2, size); right = rng.integers(0, 2, size)
    planted = rng.normal(size=size); noise = rng.normal(size=size)
    return pd.DataFrame({"gameDate": pd.date_range("2024-01-01", periods=size, freq="D"),
                         "base": rng.normal(size=size), "true": planted, "noise": noise,
                         "left": left, "right": right,
                         "target": 3.0 * planted + 5.0 * left * right + rng.normal(scale=.15, size=size)})


def _folds(frame: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    dates = frame["gameDate"].to_numpy(); blocks = np.array_split(dates, 5); result = []
    for number in range(4): result.append((np.flatnonzero(frame.gameDate.isin(np.concatenate(blocks[:number + 1]))), np.flatnonzero(frame.gameDate.isin(blocks[number + 1]))))
    return result


def test_planted_signal_beats_noise_and_deflation_rises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(foundry, "_LEDGER_PATH", (tmp_path / "foundry.jsonl").resolve())
    frame = _frame(); folds = _folds(frame)
    true = foundry.evaluate_signal(frame, "target", foundry.SignalSpec("true", "nba", "row", "none", "true"), folds)
    noise = foundry.evaluate_signal(frame, "target", foundry.SignalSpec("noise", "nba", "row", "none", "noise"), folds)
    assert true["grade"] in {"STRONG", "WEAK"}
    assert true["lift"] > noise["lift"]
    assert foundry.report_significance(4.0, 10)["threshold"] > foundry.report_significance(4.0, 1)["threshold"]


def test_pool_surfaces_planted_interaction() -> None:
    frame = _frame()
    specs = [foundry.SignalSpec(name, "nba", "row", "none", name) for name in ("left", "right", "noise")]
    result = foundry.combine_pool(frame, "target", specs, _folds(frame))
    assert result["candidate_interactions"][0]["pair"] == ["left", "right"]
