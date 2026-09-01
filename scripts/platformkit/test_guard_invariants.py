"""Regression coverage for binding safety and Signal Foundry null invariants."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import signal_foundry as foundry
from scripts.platformkit.answers import resolver_registry as registry


class _CapturingRidge:
    fits: list[tuple[np.ndarray, np.ndarray]] = []
    predictions: list[np.ndarray] = []

    def __init__(self, **_kwargs) -> None:
        pass

    def fit(self, x, y):
        self.fits.append((np.asarray(x).copy(), np.asarray(y).copy()))
        return self

    def predict(self, x):
        self.predictions.append(np.asarray(x).copy())
        return np.zeros(len(x))


def _fold_frame() -> tuple[pd.DataFrame, list[tuple[np.ndarray, np.ndarray]]]:
    frame = pd.DataFrame({"gameDate": pd.date_range("2024-01-01", periods=12, freq="D"),
                          "base": np.arange(12.0), "signal": np.arange(12.0),
                          "target": np.arange(12.0)})
    return frame, [(np.arange(6), np.arange(6, 9))]


def _captured_lift(monkeypatch, shuffled: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame, folds = _fold_frame()
    _CapturingRidge.fits, _CapturingRidge.predictions = [], []
    monkeypatch.setattr(foundry, "Ridge", _CapturingRidge)
    foundry._lift(frame, "target", ["base"], frame["signal"], folds, shuffled=shuffled)
    return (_CapturingRidge.fits[1][0][:, -1], _CapturingRidge.fits[1][1],
            _CapturingRidge.predictions[1][:, -1])


def test_permutation_null_shuffles_signal_within_fold_not_labels(monkeypatch) -> None:
    plain_train, plain_y, plain_test = _captured_lift(monkeypatch, shuffled=False)
    null_train, null_y, null_test = _captured_lift(monkeypatch, shuffled=True)
    assert np.array_equal(null_y, plain_y)
    assert not np.array_equal(null_train, plain_train)
    assert not np.array_equal(null_test, plain_test)
    assert np.allclose(np.sort(null_train), np.sort(plain_train))


def test_weak_grade_uses_deflated_threshold(monkeypatch) -> None:
    lifts = iter(((3.0, [1.0, 1.0]), (1.0, []), (2.0, [])))
    monkeypatch.setattr(foundry, "PERMUTATIONS", 2)
    monkeypatch.setattr(foundry, "_lift", lambda *_args, **_kwargs: next(lifts))
    monkeypatch.setattr(foundry, "_trials", lambda: 0)
    monkeypatch.setattr(foundry, "_append", lambda *_args: {})
    monkeypatch.setattr(foundry, "report_significance",
                        lambda z, n: {"z": z, "n_trials": n, "threshold": 3.0, "significant": False})
    frame, folds = _fold_frame()
    result = foundry.evaluate_signal(frame, "target", foundry.SignalSpec("signal", "nba", "row", "", "signal"), folds)
    assert result["z"] < result["significance"]["threshold"]
    assert result["grade"] == "REJECT"


def test_ledger_counter_ignores_rebound_public_path(tmp_path, monkeypatch) -> None:
    fixed = (tmp_path / "fixed.jsonl").resolve()
    fixed.write_text('{"trial": 1}\n', encoding="utf-8")
    monkeypatch.setattr(foundry, "_LEDGER_PATH", fixed)
    monkeypatch.setattr(foundry, "LEDGER_PATH", tmp_path / "reset.jsonl")
    assert foundry._trials() == 1


def test_explicit_category_cannot_bypass_edge_refusal() -> None:
    result = registry.resolve("Show the ROI for this signal", category="player_stat")
    assert result["status"] == "refused"
    assert result["category"] == "edge_language"
