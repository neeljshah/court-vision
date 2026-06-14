"""Tests for scripts.platformkit.calibrator_select — synthetic injected loader only.

No pandas / no real corpus: a fake loader returns numpy arrays so the wiring +
selection logic is exercised pytest-clean.  The real adapter path is exercised by
the CLI, not here.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.calibrator_select import (
    select_all_sports,
    select_for_sport,
)


def _overconfident_loader(seed: int = 0):
    """Return a loader producing an overconfident (probs, outcomes) series."""
    def _load(sport: str):
        rng = np.random.default_rng(seed + len(sport))
        n = 600
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(0.5 + (true_p - 0.5) * 2.3, 0.01, 0.99)
        y = rng.binomial(1, true_p).astype(float)
        return raw.astype(float), y
    return _load


def test_select_for_sport_picks_a_calibrator(monkeypatch=None):
    res = select_for_sport("nba", min_history=50, refit_every=10,
                           loader=_overconfident_loader())
    assert res["sport"] == "nba"
    assert res["n"] == 600
    assert res["n_eval"] > 0
    # overconfident -> a shrinking calibrator should win, not identity
    assert res["chosen_method"] != "identity"
    methods = {r["method"] for r in res["table"]}
    assert methods == {"identity", "temperature", "platt", "beta", "isotonic"}
    assert "edge" not in res["note"].lower() or "no market edge" in res["note"].lower()


def test_load_failure_reported_as_error():
    def _bad_loader(sport: str):
        raise FileNotFoundError("corpus absent")
    res = select_for_sport("mlb", loader=_bad_loader)
    assert "error" in res and "corpus absent" in res["error"]
    assert "chosen_method" not in res


def test_too_few_events_is_honest_error():
    def _tiny(sport: str):
        return np.array([0.4, 0.6, 0.5]), np.array([0.0, 1.0, 1.0])
    res = select_for_sport("soccer", min_history=100, loader=_tiny)
    assert "error" in res and "too few" in res["error"]


def test_select_all_sports_runs_each():
    out = select_all_sports(["nba", "soccer"], min_history=50, refit_every=20,
                            loader=_overconfident_loader())
    assert set(out) == {"nba", "soccer"}
    for res in out.values():
        assert res["chosen_method"] in {
            "identity", "temperature", "platt", "beta", "isotonic"}
