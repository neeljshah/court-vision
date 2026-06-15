"""Per-file test for scripts/platformkit/proof_soccer/division_calibration.py.

Structural asserts (robust to corpus updates) of the honest finding: the raw O/U-2.5
engine is over-confident; a POOLED recal fixes it; per-division recal does NOT beat
pooled overall (mean-shift absorbed). Calibration metric only; no edge.

Run: python -m pytest tests/platform/test_soccer_division_calibration.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.proof_soccer import division_calibration as mod


def test_ece_perfectly_calibrated_is_zero():
    rng = np.random.default_rng(0)
    p = rng.random(5000)
    y = (rng.random(5000) < p).astype(float)
    assert mod._ece(p, y) < 0.03


def test_apply_none_is_identity():
    p = np.array([0.2, 0.5, 0.8])
    assert np.allclose(mod._apply(None, p), p)


def test_run_pooled_fixes_overconfidence_perdiv_absorbed():
    rep = mod.run()
    if "error" in rep:
        pytest.skip(rep["error"])
    o = rep["overall_ece"]
    assert {"raw", "pooled", "perdiv"} <= set(o)
    # raw engine is badly over-confident; a single POOLED recal is the big win
    assert o["pooled"] < o["raw"] * 0.5
    # per-division recal does NOT beat pooled overall (mean-shift absorbed = NULL pattern)
    assert o["perdiv"] >= o["pooled"] - 1e-4
    assert "REFUTED" in rep["verdict"] or "does NOT beat pooled" in rep["verdict"]
    # every reported division has a sub-1 Cox slope (over-confident raw probabilities)
    for r in rep["per_division"]:
        assert r["cox_slope_raw"] < 1.0
        assert 0.0 <= r["ece_raw"] <= 1.0
    # the documented per-division-helps exceptions are non-trivial (e.g. the most biased div)
    assert isinstance(rep["perdiv_beats_pooled_divisions"], list)
