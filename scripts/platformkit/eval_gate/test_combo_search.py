"""Focused tests for the regularized pre-registered combo family."""
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.combo_search import run_combo_search


def _frame(n=180):
    rng = np.random.default_rng(7)
    close = np.clip(rng.uniform(.2, .8, n), .05, .95)
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n), "game_id": [f"g{i}" for i in range(n)], "outcome": rng.binomial(1, close), "close_prob": close, "noise": rng.normal(size=n), "zero": 0.0})


def test_path_is_charged_cumulatively_and_zeroes_constant_signal(tmp_path: Path):
    ledger = tmp_path / "ledger.json"
    first = run_combo_search(_frame(), ["noise", "zero"], ledger_path=ledger, lambdas=(.1, 1.0),
                             allow_unregistered_search=True)
    second = run_combo_search(_frame(), ["noise", "zero"], ledger_path=ledger, lambdas=(.1, 1.0),
                              allow_unregistered_search=True)
    assert first.k_cycle == 2 and first.k_cumulative == 2
    assert second.k_cumulative == 4
    assert "zero" not in first.coefficients
    assert first.detail["truncation_invariance"] is True


def test_small_corpus_is_not_testable_but_still_charged(tmp_path: Path):
    result = run_combo_search(_frame(80), ["noise", "zero"], ledger_path=tmp_path / "k.json", lambdas=(.1, 1.0, 10.0),
                              allow_unregistered_search=True)
    assert result.verdict == "NOT_TESTABLE"
    assert result.k_cumulative == 3
