"""Per-file test for scripts/platformkit/proof_nba/totals_calibration.py.

Structural asserts (robust to corpus updates) of the honest finding: the leak-free EW
totals model is UNDER-dispersed (reliability slope>1), and a leak-free dispersion SHAPE
fix improves O/U calibration. Calibration metric only; no edge.

Run: python -m pytest tests/platform/test_nba_totals_calibration.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.platformkit.proof_nba import totals_calibration as mod


def test_phi_standard_normal():
    assert mod._phi(0.0) == pytest.approx(0.5, abs=1e-9)
    assert mod._phi(10.0) == pytest.approx(1.0, abs=1e-6)
    assert mod._phi(-10.0) == pytest.approx(0.0, abs=1e-6)


def test_ece_calibrated_is_low():
    rng = np.random.default_rng(0)
    p = rng.random(4000)
    y = (rng.random(4000) < p).astype(float)
    assert mod._ece(p, y) < 0.03


def test_run_shape_fix_improves_calibration():
    rep = mod.run()
    if "error" in rep:
        pytest.skip(rep["error"])
    assert rep["market"] == "nba_total"
    assert rep["n_games"] > 500
    # the EW point model is under-dispersed: realized varies more than predicted (slope>1)
    assert rep["regression_slope_realized_on_pred"] > 1.0
    # sigma is a plausible NBA total spread
    assert 12.0 < rep["resid_sigma"] < 28.0
    # the leak-free dispersion SHAPE fix improves pooled ECE (shape fixes win)
    d = rep["dispersion_fix"]
    assert d["improves"] is True
    assert d["ece_corrected"] < rep["pooled_ece"]
    assert d["ece_corrected"] < 0.03
    # honest market side-note is data-limited, never an edge
    ov = rep["odds_overlap"]
    assert ov["status"] in ("ok", "data_limited", "no_odds_file")
    assert "not a market edge" in rep["note"].lower() or "not an edge" in rep["note"].lower()
