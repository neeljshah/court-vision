"""tests/soccer/test_ingame_ht_calibration.py — in-game (HT) calibration helpers.

Covers the leak-free recalibration added to
scripts/platformkit/proof_soccer/ingame_ht_accuracy.py:
  * _fit_platt  recovers calibration on a deliberately over-confident input
  * _calibrate  fits on TRAIN ONLY, applies to HELD-OUT (leak-free), reduces ECE
                without worsening Brier, and picks a valid method name.

These run on synthetic arrays (no corpus needed) so they are fast + deterministic.
Per-file run:
  python -m pytest tests/soccer/test_ingame_ht_calibration.py -q
calibration != edge.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.calibration_ladder import reliability
from scripts.platformkit.proof_soccer.ingame_ht_accuracy import _calibrate, _fit_platt


def _overconfident(seed: int = 7, n: int = 4000):
    """True p ~ U(0.25,0.75); raw pushed away from 0.5 (over-confident)."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.25, 0.75, n)
    raw = np.clip(0.5 + (true_p - 0.5) * 2.0, 0.02, 0.98)
    y = rng.binomial(1, true_p).astype(float)
    return raw, y


def test_fit_platt_shrinks_overconfident():
    raw, y = _overconfident()
    a, b = _fit_platt(raw, y)
    # Over-confident -> slope a should be < 1 (pull predictions toward base rate).
    assert 0.0 < a < 1.0
    assert np.isfinite(b)


def test_calibrate_is_leak_free_and_improves_ece():
    raw, y = _overconfident()
    mid = len(raw) // 2
    p_tr, y_tr = raw[:mid], y[:mid]
    p_te, y_te = raw[mid:], y[mid:]

    out = _calibrate(p_tr, y_tr, p_te, y_te)
    assert out["method"] in ("platt", "temperature")
    assert out["probs"].shape == p_te.shape

    ece_raw = float(reliability(p_te, y_te)["ece"])
    ece_recal = float(reliability(out["probs"], y_te)["ece"])
    brier_raw = float(np.mean((p_te - y_te) ** 2))
    brier_recal = float(np.mean((out["probs"] - y_te) ** 2))

    # Recalibration must reduce ECE on the held-out half and not worsen Brier.
    assert ece_recal < ece_raw
    assert brier_recal <= brier_raw + 1e-6


def test_calibrate_does_not_peek_at_heldout_outcomes():
    """Permuting held-out OUTCOMES must not change the recalibrated PROBS
    (params come from TRAIN only) -> proves no held-out leakage."""
    raw, y = _overconfident()
    mid = len(raw) // 2
    p_tr, y_tr = raw[:mid], y[:mid]
    p_te, y_te = raw[mid:], y[mid:]

    out_a = _calibrate(p_tr, y_tr, p_te, y_te)
    out_b = _calibrate(p_tr, y_tr, p_te, np.flip(y_te).copy())
    # Probs depend only on (train, p_te), not on held-out outcomes.
    assert np.allclose(out_a["probs"], out_b["probs"])
