"""Per-file test for scripts/platformkit/proof_tennis/wta_recal_temp_iso.py.

Asserts STRUCTURAL properties of the WTA temperature/isotonic recal proof (robust to
small corpus updates — no brittle exact-ECE asserts). Calibration metric only; no edge.

Run: python -m pytest tests/platform/test_wta_recal_temp_iso.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.proof_tennis import wta_recal_temp_iso as mod


def test_fit_temperature_recovers_overconfidence():
    """If labels are LESS extreme than the logits imply, fitted T>1 (shrink to 0.5)."""
    rng = np.random.default_rng(0)
    # over-confident logits: true p is a shrunk sigmoid of the logit
    logits = rng.normal(0, 2.5, 4000)
    true_p = 1.0 / (1.0 + np.exp(-logits / 2.0))   # truth is logit/2 -> model over-confident
    y = (rng.random(4000) < true_p).astype(float)
    T = mod._fit_temperature(logits, y)
    assert T > 1.0


def test_fit_temperature_unit_when_calibrated():
    rng = np.random.default_rng(1)
    logits = rng.normal(0, 1.5, 6000)
    p = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.random(6000) < p).astype(float)
    T = mod._fit_temperature(logits, y)
    assert 0.8 < T < 1.25   # already calibrated -> T ~ 1


def test_run_structure_and_honest_verdict():
    rep = mod.run()
    if "error" in rep:
        pytest.skip(rep["error"])
    assert rep["corpus"] == "WTA"
    assert set(rep["methods"]) == {"raw", "platt", "temperature", "isotonic"}
    # WTA Elo is over-confident -> fitted train-era temperature > 1
    assert rep["train_era_temperature"] > 1.0
    # every method reports both eval windows
    for rows in rep["methods"].values():
        assert {r["window"] for r in rows} == {"2023-2024", "2025+"}
        for r in rows:
            assert 0.0 <= r["ece"] <= 1.0 and 0.0 <= r["brier"] <= 1.0
    # documented structural FAIL: nothing crosses the threshold on BOTH windows
    assert rep["passed_both_windows"] == []
    assert "FAIL" in rep["verdict"]
    # temperature is the right tool: it beats Platt on the larger 2023-2024 window ECE
    t_ece = next(r["ece"] for r in rep["methods"]["temperature"] if r["window"] == "2023-2024")
    p_ece = next(r["ece"] for r in rep["methods"]["platt"] if r["window"] == "2023-2024")
    assert t_ece < p_ece
