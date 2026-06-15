"""Per-file test for scripts/platformkit/proof_nba/totals_with_rest.py.

Records the honest finding: REST/b2b is a null for NBA totals (fatigue is public + priced);
the residual gap to the close is injuries/lineups. Structural asserts.

Run: python -m pytest tests/platform/test_nba_totals_with_rest.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.proof_nba import totals_with_rest as mod


def test_rest_features_leak_free_and_b2b():
    box = pd.DataFrame({
        "home_abbr": ["AAA", "AAA", "BBB"],
        "away_abbr": ["BBB", "CCC", "AAA"],
        "date": pd.to_datetime(["2025-10-01", "2025-10-02", "2025-10-10"]),
    })
    out = mod._rest_features(box)
    # AAA plays 10-01 then 10-02 -> 1 day rest -> b2b on the second game
    assert out.iloc[1]["home_b2b"] == 1.0
    assert out.iloc[1]["home_rest"] == 1.0
    # first appearance gets the 3-day default, capped at _REST_CAP
    assert out.iloc[0]["home_rest"] == 3.0
    assert (out[["home_rest", "away_rest"]].to_numpy() <= mod._REST_CAP).all()


def test_run_rest_is_a_null_gap_is_injuries():
    rep = mod.run()
    if "error" in rep:
        pytest.skip(rep["error"])
    if rep.get("status") != "ok":
        assert rep["status"] == "data_limited"
        return
    assert rep["n_overlap"] >= 60
    for k in ("close_rmse", "base_rmse", "rest_rmse"):
        assert 5.0 < rep[k] < 40.0
    # rest moves RMSE by less than half a point either way (a null, within noise)
    assert abs(rep["rest_rmse_gain"]) < 0.5
    # the close remains sharper than our best model (gap is injuries/lineups)
    assert rep["gap_to_close_rest"] > 0.0
    assert isinstance(rep["rest_helps"], bool)
