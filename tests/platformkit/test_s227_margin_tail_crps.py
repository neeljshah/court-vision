"""Focused unit checks for S227's frozen CRPS measurement primitives."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit import s227_margin_tail_crps as s227
from scripts.platformkit.s227_margin_tail_crps import FROZEN_LADDER, gaussian_crps


def test_known_standard_gaussian_draw_and_frozen_ladder():
    value = gaussian_crps(np.array([0.0]), np.array([1.0]), np.array([0.0]))[0]
    assert value == pytest.approx((np.sqrt(2.0) - 1.0) / np.sqrt(np.pi))
    assert FROZEN_LADDER == (5, 10, 15, 20, 25, 30)


def _two_cell_train() -> pd.DataFrame:
    return pd.DataFrame({
        "cell": ["A"] * 4 + ["B"] * 4,
        "margin": [0.0] * 8,
        "rem_fraction": [1.0] * 8,
        "p0_asof": [0.5] * 8,
        "final_margin": [0.0] * 4 + [-20.0, 20.0, -20.0, 20.0],
    })


def test_fit_sigma_uses_each_cells_own_targets(monkeypatch):
    seen = []

    def record(mu, scale, observed):
        seen.append(observed.copy())
        return np.zeros(len(observed))

    monkeypatch.setattr(s227, "SIGMA_GRID", np.array([3.0, 20.0]))
    monkeypatch.setattr(s227, "MIN_CELL_TRAIN", 4)
    monkeypatch.setattr(s227, "gaussian_crps", record)
    train = _two_cell_train()
    s227._fit_sigma(train)
    assert all(np.array_equal(values, train.loc[train["cell"] == "A", "final_margin"])
               for values in seen[:2])
    assert all(np.array_equal(values, train.loc[train["cell"] == "B", "final_margin"])
               for values in seen[2:])


def test_planted_cell_target_permutation_changes_fitted_crps(monkeypatch):
    monkeypatch.setattr(s227, "SIGMA_GRID", np.array([3.0, 20.0]))
    monkeypatch.setattr(s227, "MIN_CELL_TRAIN", 4)
    train = _two_cell_train()
    fitted = s227._fit_sigma(train)
    permuted = train.copy()
    permuted["final_margin"] = np.roll(permuted["final_margin"].to_numpy(float), 4)
    fitted_permuted = s227._fit_sigma(permuted)
    sigma = train["cell"].map(fitted).to_numpy(float)
    permuted_sigma = train["cell"].map(fitted_permuted).to_numpy(float)
    mu, scale = s227._distribution(train, sigma)
    permuted_mu, permuted_scale = s227._distribution(train, permuted_sigma)
    baseline = gaussian_crps(mu, scale, train["final_margin"].to_numpy(float)).mean()
    planted = gaussian_crps(permuted_mu, permuted_scale, train["final_margin"].to_numpy(float)).mean()
    assert planted != pytest.approx(baseline)
