"""Per-file test for scripts.platformkit.proof_tennis.ingame_calib.

Confirms the leak-free in-game recalibrator: ECE/reliability helpers are sane, and
fitting on the TRAIN half + applying to the EVAL half (a) never refits on eval,
(b) reduces ECE on an over-confident forecaster, (c) does not worsen Brier much.
calibration != edge. Run: python -m pytest tests/test_tennis_ingame_calib.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_tennis.ingame_calib import (
    ece10, reliability_slope, recalibrate_holdout,
)


def _overconfident(n: int = 4000, seed: int = 7):
    """Make an over-confident binary forecaster: true_p mild, raw pushed toward 0/1."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.2, 0.85, n)
    raw = np.clip(0.5 + (true_p - 0.5) * 2.0, 0.02, 0.98)
    y = rng.binomial(1, true_p).astype(float)
    return raw, y


def test_ece_perfect_is_zero():
    p = np.array([0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3])
    y = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1, 1.0])  # 30% in the 0.3 bin
    assert ece10(p, y) < 1e-9


def test_reliability_slope_overconfident_below_one():
    raw, y = _overconfident()
    assert reliability_slope(raw, y) < 1.0


def test_recal_reduces_ece_on_overconfident():
    raw, y = _overconfident()
    out = recalibrate_holdout(raw, y)
    assert out["ece_recal"] < out["ece_raw"]
    assert out["recal_method"] in ("temperature", "platt")
    assert out["n_eval"] == len(raw) - len(raw) // 2
    # Brier should not meaningfully worsen.
    assert out["brier_recal"] <= out["brier_raw"] + 1e-3


def test_leak_free_eval_half_untouched_by_fit():
    """Permuting EVAL-half labels must NOT change the fitted recalibrator's params
    (the recalibrator is fit on TRAIN only). We check the chosen params are identical."""
    raw, y = _overconfident()
    cut = len(raw) // 2
    out1 = recalibrate_holdout(raw, y)
    y2 = y.copy()
    rng = np.random.default_rng(99)
    y2[cut:] = rng.permutation(y2[cut:])  # scramble EVAL labels only
    out2 = recalibrate_holdout(raw, y2)
    assert out1["recal_method"] == out2["recal_method"]
    assert out1["recal_params"] == out2["recal_params"]


def test_calibrated_input_recal_adds_little():
    """A well-calibrated raw forecaster -> recal should not blow up ECE."""
    rng = np.random.default_rng(3)
    p = rng.uniform(0.05, 0.95, 4000)
    y = rng.binomial(1, p).astype(float)
    out = recalibrate_holdout(p, y)
    assert out["ece_recal"] < 0.05
