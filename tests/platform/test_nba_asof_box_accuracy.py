"""Per-file test for scripts/platformkit/proof_nba/asof_box_accuracy.py.

The "beat-the-best-predictions" harness: our as-of box model vs the market close on RMSE
to realized totals. Structural asserts (robust to corpus growth / data-limited state).

Run: python -m pytest tests/platform/test_nba_asof_box_accuracy.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.proof_nba import asof_box_accuracy as mod


def test_rmse_mae_basic():
    pred = np.array([1.0, 2.0, 3.0])
    truth = np.array([1.0, 2.0, 3.0])
    rmse, mae = mod._rmse_mae(pred, truth)
    assert rmse == pytest.approx(0.0) and mae == pytest.approx(0.0)
    rmse, mae = mod._rmse_mae(np.array([0.0, 0.0]), np.array([3.0, 4.0]))
    assert rmse == pytest.approx(3.5355, abs=1e-3) and mae == pytest.approx(3.5)


def test_run_structure():
    rep = mod.run()
    if "error" in rep:
        pytest.skip(rep["error"])
    if rep.get("status") != "ok":
        # data-limited until more 2025-26 games are ingested — a valid honest state
        assert rep["status"] == "data_limited"
        assert "note" in rep
        return
    assert rep["n_overlap"] >= 40
    assert 5.0 < rep["close_rmse_vs_realized"] < 40.0   # NBA totals errors live in this band
    for key in ("pooled_model", "split_model", "poss_model"):
        d = rep[key]
        assert 5.0 < d["rmse"] < 40.0
        assert 0.0 <= d["ece"] <= 0.3
    # richer possessions/efficiency data should not be WORSE than the crude pooled model
    assert rep["poss_model"]["rmse"] <= rep["pooled_model"]["rmse"] + 0.5
    assert isinstance(rep["gap_to_close_rmse"], float)
    assert isinstance(rep["verdict"], str)
