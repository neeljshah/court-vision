"""Construct checks for the effective sample-size bounds."""
from __future__ import annotations

import math

import pandas as pd

from scripts.platformkit.ingame import gap_effective_n


def test_effective_sample_size_bound_and_cluster_identity_for_rho_sweep(monkeypatch) -> None:
    """n = 4 (CONSTRUCT): rho = 0, 0.3, 0.7, 1.0 on unequal game sizes 2/3/5/8."""
    rows = pd.DataFrame([
        {"game": "g%d" % game, "loss_differential": float(index)}
        for game, size in enumerate((2, 3, 5, 8))
        for index in range(size)
    ])
    n_ticks = len(rows)
    n_games = int(rows["game"].nunique())
    for rho in (0.0, 0.3, 0.7, 1.0):
        monkeypatch.setattr(gap_effective_n, "intraclass_correlation", lambda *_args, value=rho, **_kwargs: value)
        summary = gap_effective_n.effective_sample_size(rows)
        expected_deff = gap_effective_n.design_effect(rho, n_ticks / n_games)
        expected_n_eff = n_ticks / expected_deff
        expected_gap = (n_ticks - n_games) * (1.0 - rho) / expected_deff
        assert math.isclose(summary["n_eff"], expected_n_eff, rel_tol=0.0, abs_tol=1e-12)
        assert summary["n_eff"] <= summary["n_ticks"]
        assert summary["n_eff"] >= summary["n_games"]
        assert math.isclose(summary["n_eff"] - n_games, expected_gap, rel_tol=0.0, abs_tol=1e-12)
        assert summary["n_eff_bound_ok"] is True
