"""Synthetic coverage for regime-specific calibration and fallback behavior."""
from __future__ import annotations

from scripts.platformkit.regime_calibration import fit_per_regime, heterogeneity


def test_biased_regime_is_flagged_fixed_and_small_regime_falls_back() -> None:
    preds = [0.25] * 400 + [0.75] * 400 + [0.50] * 20
    outcomes = ([1, 0, 0, 0] * 100) + ([1, 0, 0, 0] * 100) + ([0, 1] * 10)
    keys = ["fair"] * 400 + ["biased"] * 400 + ["small"] * 20
    result = heterogeneity(preds, outcomes, keys)
    biased = next(row for row in result["buckets"] if row["bucket"] == "biased")
    assert biased["status"] == "SIGNIFICANT"
    fits = fit_per_regime(preds, outcomes, keys)
    assert fits["small"] is fits["GLOBAL"]
    before = sum((pred - outcome) ** 2 for pred, outcome in zip(preds[400:800], outcomes[400:800])) / 400
    after = sum((pred - outcome) ** 2 for pred, outcome in zip(fits["biased"].apply(preds[400:800]), outcomes[400:800])) / 400
    assert after < before
