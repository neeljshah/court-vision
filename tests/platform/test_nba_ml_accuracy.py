"""Per-file test for scripts/platformkit/proof_nba/ml_accuracy.py.

The moneyline beat-the-close test: our box-based MOV-Elo win-prob vs the devigged close.
Structural asserts (robust to corpus growth). Calibration/accuracy only; no edge.

Run: python -m pytest tests/platform/test_nba_ml_accuracy.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.proof_nba import ml_accuracy as mod


def test_american_to_prob():
    assert mod.american_to_prob(-200) == pytest.approx(2 / 3, abs=1e-9)
    assert mod.american_to_prob(+100) == pytest.approx(0.5, abs=1e-9)
    assert mod.american_to_prob(+150) == pytest.approx(0.4, abs=1e-9)
    # favourite implied prob > 0.5, underdog < 0.5
    assert mod.american_to_prob(-150) > 0.5 > mod.american_to_prob(+150)


def test_p_home_monotone_and_hfa():
    # equal ratings -> home favoured by HFA
    assert mod._p_home(1500, 1500) > 0.5
    assert mod._p_home(1600, 1500) > mod._p_home(1500, 1600)


def test_run_matches_close_within_noise():
    rep = mod.run()
    if rep.get("status") != "ok":
        pytest.skip(f"data_limited n={rep.get('n_overlap')}")
    assert rep["n_overlap"] >= 60
    for k in ("model_brier", "market_brier"):
        assert 0.10 < rep[k] < 0.30          # NBA ML Brier band
    # our model tracks the market closely and is competitive (small gap)
    assert rep["corr_model_market"] > 0.6
    assert rep["brier_gap_to_market"] < 0.02   # within striking distance of the close
    assert isinstance(rep["verdict"], str)
