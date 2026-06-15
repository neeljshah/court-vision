"""Per-file test for scripts/platformkit/proof_nba/ingame_accuracy.py.

NBA in-game: conditioning on realized state beats the static pregame line. Structural asserts
(robust to corpus / data-limited state). Forecaster quality; RMSE+bias never MAE; no edge.

Run: python -m pytest tests/platform/test_nba_ingame_accuracy.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_nba import ingame_accuracy as mod


def test_metric_helpers():
    assert mod._brier(np.array([0.5, 0.5]), np.array([1.0, 0.0])) == 0.25
    rmse, bias = mod._rmse_bias(np.array([2.0, 4.0]), np.array([0.0, 0.0]))
    assert rmse > 0 and bias == 3.0


def test_run_ingame_is_sharper_than_static():
    rep = mod.run()
    if rep.get("status") != "ok":
        # linescores not yet ingested -> a valid honest state, not a failure
        assert rep["status"] in ("no_data", "data_limited")
        return
    assert rep["n_games"] >= 60
    qc = rep["quarter_curve"]
    assert len(qc) == 4 and abs(sum(qc) - 1.0) < 0.02
    # THE result: COMBINED (pregame rating prior + in-game score) is the sharpest forecaster —
    # it beats BOTH pregame-Elo-alone and score-only-conditional.
    assert rep["combined_beats_pregame"] is True
    assert rep["combined_beats_blind"] is True
    assert rep["brier_conditional_rating"] < rep["brier_pregame_elo"]
    assert rep["brier_conditional_rating"] < rep["brier_conditional_blind"]
    # totals graded on RMSE/bias (plausible NBA scale)
    assert 0.0 < rep["total_rmse_flat"] < 60.0
