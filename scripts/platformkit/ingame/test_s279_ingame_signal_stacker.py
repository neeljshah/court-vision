"""Focused synthetic regression test for S279's maximum-shrinkage fallback."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.ingame.s279_ingame_signal_stacker import _logit, fit_shrinkage_path


def test_maximum_shrinkage_is_exact_recalibrated_null_prediction():
    rng = np.random.default_rng(279)
    base = rng.uniform(0.08, 0.92, size=180)
    signal = (base + rng.normal(0.0, 0.12, size=180)).reshape(-1, 1)
    y = rng.binomial(1, base).astype(int)
    path = fit_shrinkage_path(base, signal, y)
    null = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(_logit(base).reshape(-1, 1), y)
    expected = null.predict_proba(_logit(base).reshape(-1, 1))[:, 1]
    assert "0.01" in path and "100.0" in path and "maximum" in path
    assert np.array_equal(path["maximum"]["prediction"], expected)
    assert path["maximum"]["weights"].shape == (3,)
