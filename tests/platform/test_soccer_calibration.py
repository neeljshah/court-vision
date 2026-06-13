"""tests.platform.test_soccer_calibration — Leak-free walk-forward calibration tests.

IMPORTANT: calibration != edge.
Better-calibrated probabilities do NOT imply beating the market.
This file verifies reliability improvement only.

Coverage:
  1. Synthetic miscalibrated generator: calibrated ECE < raw ECE.
  2. Leak-free proof: calibrator for event i is independent of outcomes >= i.
  3. Real soccer corpus (skipped if absent): calibrated ECE < raw, probs in [0,1].
  4. No edge-claim language in CALIBRATION_NOTE.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CORPUS_PATH = REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_miscalibrated(
    n: int = 500, seed: int = 42, raw_bias: float = 0.12
) -> Tuple[np.ndarray, np.ndarray]:
    """Synthetic corpus with systematic upward bias → known miscalibration."""
    rng = np.random.default_rng(seed)
    true_p = np.clip(rng.normal(0.50, 0.15, size=n), 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    raw_probs = np.clip(true_p + raw_bias, 0.01, 0.99)
    return raw_probs, outcomes


def _ece(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Inline ECE — identical to kernel.validation.proof_metrics.ece."""
    p, y = np.asarray(probs, float), np.asarray(outcomes, float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total, val = len(p), 0.0
    if total == 0:
        return 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb == 0:
            continue
        val += (nb / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def calib_module():
    return importlib.import_module("domains.soccer.calibration")


@pytest.fixture(scope="module")
def real_bundle():
    if not REAL_CORPUS_PATH.exists():
        pytest.skip("Real soccer corpus absent — skipping real-corpus tests.")
    try:
        import pandas as pd
        from domains.soccer.adapter import SoccerAdapter
        df = pd.read_parquet(str(REAL_CORPUS_PATH))
        seasons = sorted(df["season"].unique().tolist())
        return SoccerAdapter(repo_root=REPO_ROOT).feature_bundle(
            hypothesis=None, seasons=seasons
        )
    except Exception as exc:
        pytest.skip(f"Could not load soccer feature bundle: {exc}")


# ---------------------------------------------------------------------------
# 1. Synthetic: miscalibrated → calibrated ECE improves
# ---------------------------------------------------------------------------


def test_synthetic_calibrated_ece_lower_than_raw(calib_module):
    """Walk-forward calibration reduces ECE on a known-miscalibrated synthetic corpus."""
    raw, outcomes = _generate_miscalibrated(n=500, seed=42)
    calibrated = calib_module.walk_forward_calibrate(raw, outcomes, min_history=30)
    raw_ece, cal_ece = _ece(raw, outcomes), _ece(calibrated, outcomes)
    assert cal_ece < raw_ece, (
        f"Calibrated ECE ({cal_ece:.4f}) not < raw ECE ({raw_ece:.4f})."
    )


def test_synthetic_probs_in_unit_interval(calib_module):
    """All calibrated probs must lie in [0, 1]."""
    raw, outcomes = _generate_miscalibrated(n=200, seed=7)
    cal = calib_module.walk_forward_calibrate(raw, outcomes, min_history=20)
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0)


def test_synthetic_output_length_preserved(calib_module):
    raw, outcomes = _generate_miscalibrated(n=150, seed=3)
    cal = calib_module.walk_forward_calibrate(raw, outcomes, min_history=10)
    assert len(cal) == len(raw)


def test_synthetic_warmup_passthrough(calib_module):
    """Events before min_history must be passed through as-is."""
    raw, outcomes = _generate_miscalibrated(n=80, seed=99)
    min_h = 40
    cal = calib_module.walk_forward_calibrate(raw, outcomes, min_history=min_h)
    np.testing.assert_array_equal(cal[:min_h], raw[:min_h])


def test_synthetic_length_mismatch_raises(calib_module):
    with pytest.raises(ValueError):
        calib_module.walk_forward_calibrate([0.4, 0.5, 0.6], [0, 1])


# ---------------------------------------------------------------------------
# 2. Leak-free proof
# ---------------------------------------------------------------------------


def test_no_future_leak_by_construction(calib_module):
    """Calibrated[i < pivot] must be unchanged when outcomes[pivot:] are all flipped.

    If futures leaked, flipping all outcomes >= pivot would change calibrated[i] for
    i < pivot.  It cannot, because calibrated[i] is fitted on outcomes[:i] only.
    """
    n, pivot, min_h = 200, 100, 30
    raw, outcomes_base = _generate_miscalibrated(n=n, seed=77)
    outcomes_flipped = outcomes_base.copy()
    outcomes_flipped[pivot:] = 1.0 - outcomes_flipped[pivot:]

    cal_base = calib_module.walk_forward_calibrate(raw, outcomes_base, min_history=min_h)
    cal_flip = calib_module.walk_forward_calibrate(raw, outcomes_flipped, min_history=min_h)

    np.testing.assert_array_equal(
        cal_base[:pivot], cal_flip[:pivot],
        err_msg="LEAK: flipping future outcomes changed strictly-prior calibrated probs.",
    )


def test_no_future_leak_single_event(calib_module):
    """Calibrated[i] must not change when outcome[i] itself is flipped."""
    n, min_h = 100, 20
    raw, outcomes = _generate_miscalibrated(n=n, seed=55)
    for idx in [20, 50, 80]:
        flipped = outcomes.copy()
        flipped[idx] = 1.0 - flipped[idx]
        cal_base = calib_module.walk_forward_calibrate(raw, outcomes, min_history=min_h)
        cal_flip = calib_module.walk_forward_calibrate(raw, flipped, min_history=min_h)
        if idx > 0:
            np.testing.assert_array_equal(
                cal_base[:idx], cal_flip[:idx],
                err_msg=f"Flip at {idx} changed prior calibrated probs — LEAK.",
            )


# ---------------------------------------------------------------------------
# 3. Real corpus (skipped if absent)
# ---------------------------------------------------------------------------


def test_real_corpus_calibration(calib_module, real_bundle):
    """On real corpus: ECE improves, probs in [0,1], no NaN, length preserved.

    NOTE: calibration != edge.
    """
    raw = real_bundle.signal_col.copy()
    outcomes = real_bundle.target.copy()
    cal = calib_module.walk_forward_calibrate(raw, outcomes)

    raw_ece = _ece(raw, outcomes)
    cal_ece = _ece(cal, outcomes)
    print(f"\nReal corpus: n={len(raw)}, raw_ECE={raw_ece:.4f}, cal_ECE={cal_ece:.4f}")

    assert len(cal) == len(raw), "Length mismatch"
    assert np.all(cal >= 0.0) and np.all(cal <= 1.0), "Probs outside [0,1]"
    assert not np.any(np.isnan(cal)), "NaN in calibrated probs"
    assert cal_ece < raw_ece, (
        f"Walk-forward calibration did NOT reduce ECE: raw={raw_ece:.4f}, cal={cal_ece:.4f}."
    )


# ---------------------------------------------------------------------------
# 4. No edge-claim language
# ---------------------------------------------------------------------------


def test_calibration_note_is_honest(calib_module):
    """CALIBRATION_NOTE must disclaim edge and must not claim edge."""
    note = calib_module.CALIBRATION_NOTE
    assert isinstance(note, str) and len(note) > 0
    note_lower = note.lower()
    assert "calibration" in note_lower
    assert "edge" in note_lower
    assert any(w in note_lower for w in ("not", "do not", "does not"))
    for bad in ("profit", "beat the market", "edge claim", "+ev", "roi advantage"):
        assert bad not in note_lower, f"Forbidden phrase in CALIBRATION_NOTE: '{bad}'"


def test_module_docstring_disclaims_edge(calib_module):
    doc = (calib_module.__doc__ or "").lower()
    assert "not" in doc and "edge" in doc


# ---------------------------------------------------------------------------
# 5. ECE utility
# ---------------------------------------------------------------------------


def test_compute_ece_near_zero_for_true_probs(calib_module):
    rng = np.random.default_rng(0)
    true_p = np.linspace(0.1, 0.9, 1000)
    outcomes = rng.binomial(1, true_p).astype(float)
    assert calib_module.compute_ece(true_p, outcomes) < 0.10


def test_compute_ece_high_for_wrong_probs(calib_module):
    raw = np.full(200, 0.9)
    outcomes = np.array([float(i % 2) for i in range(200)])
    assert calib_module.compute_ece(raw, outcomes) > 0.30
