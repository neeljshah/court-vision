"""Per-file test for totals_with_availability (run THIS file only; never full pytest).
Run: python -m pytest scripts/platformkit/proof_nba/test_totals_with_availability.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_nba import totals_with_availability as M


def test_rmse_bias_basic():
    rm, bias = M._rmse_bias(np.array([2.0, 4.0]), np.array([0.0, 0.0]))
    assert abs(rm - np.sqrt(10.0)) < 1e-9 and abs(bias - 3.0) < 1e-9


def test_build_games_leakfree_shape():
    pb = M.load_player_box()
    g = M._build_games(pb)
    # one row per real game, with the four required columns, vacated non-negative
    assert {"realized", "base", "vacated", "home_abbr", "away_abbr"} <= set(g.columns)
    assert len(g) > 500
    assert (g["vacated"] >= 0).all()
    # realized totals are in a sane NBA range (filter applied)
    assert g["realized"].between(150, 320).all()
    # vacated mean should be modest (recency gate); a runaway value signals the long-term-injury bug
    assert g["vacated"].mean() < 60.0


def test_run_returns_required_keys_and_null_or_signal():
    rep = M.run()
    assert rep.get("status") == "ok"
    for k in ("n", "rmse_model_only", "rmse_model_plus_avail", "rmse_close",
              "gap_before", "gap_after", "pct_of_gap_closed", "verdict",
              "fitted_vacated_fraction", "leak_reasoning"):
        assert k in rep, k
    # fraction is a clipped shrink in [0,1]
    assert 0.0 <= rep["fitted_vacated_fraction"] <= 1.0
    # bias must be reported for totals (graded RMSE+bias, never MAE)
    assert "bias_model_only" in rep and "bias_model_plus_avail" in rep
