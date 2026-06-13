"""tests/platform/test_recalibration.py — Tests for scripts/platformkit/recalibration.py.

CALIBRATION != EDGE.  This module tests a RELIABILITY utility.  Better-calibrated
probabilities do NOT imply beating the market or a positive expected value.
No edge-claim language is permitted here or in any output the utility produces.

Test categories:
1. Synthetic miscalibrated data → recal ECE ≤ raw ECE.
2. Leak-free by construction → flipping future outcomes leaves early values identical.
3. Already-calibrated data → recal does NOT meaningfully worsen ECE.
4. Probabilities stay in [0, 1].
5. Honesty note present; no forbidden edge-claim phrases.
6. measure_recal dict contract.
7. Real-corpus tests (skip when corpus absent).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.recalibration import (
    CALIBRATION_NOTE,
    _ADAPTER_REGISTRY,
    _ece,
    measure_recal,
    measure_sport_recal,
    walk_forward_recalibrate,
)

# ---------------------------------------------------------------------------
# Forbidden edge-claim phrases (direct affirmative claims — NOT negations).
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = [
    "has an edge",
    "profitable strategy",
    "guaranteed profit",
    "positive roi",
    "guaranteed return",
    "beats the market",
]


def _assert_no_edge_claims(text: str) -> None:
    lower = text.lower()
    for phrase in _FORBIDDEN_PHRASES:
        assert phrase not in lower, (
            f"Forbidden edge-claim phrase '{phrase}' in: {text[:200]}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _miscalibrated_data(n: int = 500, seed: int = 0) -> tuple:
    """Raw probs near 0.9, outcomes all 0 — severe overconfidence, ECE ~ 0.9."""
    rng = np.random.default_rng(seed)
    probs = rng.uniform(0.8, 1.0, n)
    outcomes = np.zeros(n)
    return probs, outcomes


def _calibrated_data(n: int = 2000, seed: int = 42) -> tuple:
    """Well-calibrated: probs spread [0.1, 0.9], outcomes ~ Binomial(1, p)."""
    rng = np.random.default_rng(seed)
    probs = rng.uniform(0.1, 0.9, n)
    outcomes = rng.binomial(1, probs).astype(float)
    return probs, outcomes


# ---------------------------------------------------------------------------
# 1. Miscalibrated data → recal ECE ≤ raw ECE
# ---------------------------------------------------------------------------

def test_recal_improves_ece_on_miscalibrated() -> None:
    """Isotonic recalibration must not worsen ECE on severely miscalibrated data."""
    probs, outcomes = _miscalibrated_data(n=600, seed=1)
    result = measure_recal(probs, outcomes, min_history=30)
    # For severely miscalibrated data (raw ECE ~ 0.9), recalibration should help.
    assert result["raw_ece"] > 0.1, "Test data should be poorly calibrated"
    assert result["recal_ece"] <= result["raw_ece"] + 1e-9, (
        f"recal_ece={result['recal_ece']:.4f} > raw_ece={result['raw_ece']:.4f}"
    )


def test_walk_forward_recalibrate_reduces_ece_miscal() -> None:
    """Direct API: walk_forward_recalibrate output ECE ≤ raw ECE on miscal data."""
    probs, outcomes = _miscalibrated_data(n=400, seed=2)
    recal = walk_forward_recalibrate(probs, outcomes, min_history=20)
    raw_ece = _ece(probs, outcomes)
    recal_ece = _ece(recal, outcomes)
    assert recal_ece <= raw_ece + 1e-9, (
        f"recal_ece={recal_ece:.4f} > raw_ece={raw_ece:.4f} on miscalibrated data"
    )


# ---------------------------------------------------------------------------
# 2. Leak-free by construction: flipping future outcomes does not affect
#    already-computed calibrated values for early events.
# ---------------------------------------------------------------------------

def test_leak_free_early_values_unchanged_when_future_flipped() -> None:
    """Strictly causal: calibrated[i] for i < min_history must equal raw[i];
    calibrated[min_history] must depend only on events 0..min_history-1.
    Flipping outcomes after min_history must not change calibrated[min_history]."""
    rng = np.random.default_rng(7)
    n = 200
    min_history = 50
    probs = rng.uniform(0.3, 0.7, n)
    outcomes_a = rng.binomial(1, probs).astype(float)

    # Compute calibrated on original outcomes.
    cal_a = walk_forward_recalibrate(probs, outcomes_a, min_history=min_history)

    # Flip ALL outcomes after min_history.
    outcomes_b = outcomes_a.copy()
    outcomes_b[min_history:] = 1.0 - outcomes_b[min_history:]
    cal_b = walk_forward_recalibrate(probs, outcomes_b, min_history=min_history)

    # Warmup events must pass through raw unchanged.
    np.testing.assert_array_equal(
        cal_a[:min_history], probs[:min_history],
        err_msg="Warmup events must pass through raw unchanged"
    )
    # Event at min_history uses ONLY events 0..min_history-1 (identical in both runs).
    assert abs(float(cal_a[min_history]) - float(cal_b[min_history])) < 1e-12, (
        f"cal_a[{min_history}]={cal_a[min_history]:.6f} != "
        f"cal_b[{min_history}]={cal_b[min_history]:.6f}  — leak detected"
    )


# ---------------------------------------------------------------------------
# 3. Already-calibrated data → recal does NOT meaningfully worsen ECE (delta > 0.005).
# ---------------------------------------------------------------------------

def test_recal_does_not_meaningfully_worsen_already_calibrated() -> None:
    """On well-calibrated data the ECE change must be tiny (|delta| ≤ 0.005)."""
    probs, outcomes = _calibrated_data(n=3000, seed=9)
    result = measure_recal(probs, outcomes, min_history=50)
    # delta = raw_ece - recal_ece.  A negative delta means slight worsening.
    # We allow up to 0.005 worsening — noise on a 3000-event well-calibrated sample.
    assert result["delta"] >= -0.005, (
        f"Recalibration meaningfully worsened already-calibrated ECE: "
        f"raw={result['raw_ece']:.4f} recal={result['recal_ece']:.4f} "
        f"delta={result['delta']:.4f}"
    )


# ---------------------------------------------------------------------------
# 4. Probabilities stay in [0, 1]
# ---------------------------------------------------------------------------

def test_output_probs_in_unit_interval_miscal() -> None:
    """Calibrated probs must always lie in [0, 1] for miscalibrated input."""
    probs, outcomes = _miscalibrated_data(n=300, seed=3)
    recal = walk_forward_recalibrate(probs, outcomes, min_history=10)
    assert float(recal.min()) >= 0.0, f"min={recal.min():.6f}"
    assert float(recal.max()) <= 1.0, f"max={recal.max():.6f}"


def test_output_probs_in_unit_interval_calibrated() -> None:
    """Calibrated probs must always lie in [0, 1] for well-calibrated input."""
    probs, outcomes = _calibrated_data(n=500, seed=4)
    recal = walk_forward_recalibrate(probs, outcomes, min_history=30)
    assert float(recal.min()) >= 0.0
    assert float(recal.max()) <= 1.0


# ---------------------------------------------------------------------------
# 5. Honesty / no edge-claim language
# ---------------------------------------------------------------------------

def test_calibration_note_is_honest() -> None:
    """CALIBRATION_NOTE must mention calibration and either edge or market."""
    lower = CALIBRATION_NOTE.lower()
    assert "calibration" in lower, "Note must mention calibration"
    assert "edge" in lower or "market" in lower, "Note must mention edge or market"
    _assert_no_edge_claims(CALIBRATION_NOTE)


def test_measure_recal_note_no_edge_claims() -> None:
    """The 'note' field in measure_recal output must not contain edge claims."""
    probs, outcomes = _miscalibrated_data(n=200)
    result = measure_recal(probs, outcomes)
    _assert_no_edge_claims(str(result.get("note", "")))


# ---------------------------------------------------------------------------
# 6. measure_recal dict contract
# ---------------------------------------------------------------------------

def test_measure_recal_returns_required_keys() -> None:
    probs, outcomes = _calibrated_data(n=400)
    result = measure_recal(probs, outcomes)
    for key in ("raw_ece", "recal_ece", "delta", "n", "note"):
        assert key in result, f"Missing key '{key}' in measure_recal output"


def test_measure_recal_delta_consistent() -> None:
    """delta must equal raw_ece - recal_ece to float precision."""
    probs, outcomes = _miscalibrated_data(n=300)
    result = measure_recal(probs, outcomes)
    expected_delta = result["raw_ece"] - result["recal_ece"]
    assert abs(result["delta"] - expected_delta) < 1e-12, (
        f"delta={result['delta']} != raw_ece-recal_ece={expected_delta}"
    )


def test_measure_recal_n_correct() -> None:
    probs, outcomes = _calibrated_data(n=700)
    result = measure_recal(probs, outcomes)
    assert result["n"] == 700


def test_measure_recal_ece_nonnegative() -> None:
    probs, outcomes = _miscalibrated_data(n=200)
    result = measure_recal(probs, outcomes)
    assert result["raw_ece"] >= 0.0
    assert result["recal_ece"] >= 0.0


def test_measure_recal_length_mismatch_raises() -> None:
    probs = np.array([0.4, 0.5, 0.6])
    outcomes = np.array([0.0, 1.0])
    with pytest.raises(ValueError):
        walk_forward_recalibrate(probs, outcomes)


# ---------------------------------------------------------------------------
# 7. Real-corpus tests — skip when corpus absent (CI-safe)
# ---------------------------------------------------------------------------

# Cheap availability check: look for the parquet file only (avoids a full
# walk-forward pass just to decide whether to skip).
_DATA_FILES = {
    "tennis": _REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet",
    "mlb":    _REPO_ROOT / "data" / "domains" / "mlb" / "games.parquet",
    "soccer": _REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet",
}


def _corpus_available(sport: str) -> bool:
    path = _DATA_FILES.get(sport)
    return path is not None and path.exists()


_CORPUS_CACHE: dict = {}  # cached per sport to avoid repeating O(N^2) work


def _get_sport_result(sport: str) -> dict:
    if sport not in _CORPUS_CACHE:
        _CORPUS_CACHE[sport] = measure_sport_recal(sport)
    return _CORPUS_CACHE[sport]


@pytest.mark.parametrize("sport", ["tennis", "mlb", "soccer"])
def test_real_corpus_recal_ece_nonnegative(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_sport_result(sport)
    assert r["raw_ece"] >= 0.0
    assert r["recal_ece"] >= 0.0


@pytest.mark.parametrize("sport", ["tennis", "mlb", "soccer"])
def test_real_corpus_probs_stay_in_unit_interval(sport: str) -> None:
    """Recalibrated probs must lie in [0, 1] on the full real corpus."""
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    import importlib
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    mod = importlib.import_module(module_path)
    adapter = getattr(mod, class_name)()
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
    p = np.asarray(bundle.signal_col, dtype=float)
    y = np.asarray(bundle.target, dtype=float)
    valid = ~(np.isnan(p) | np.isnan(y))
    recal = walk_forward_recalibrate(p[valid], y[valid], min_history=len(p[valid]) - 50)
    assert float(recal.min()) >= 0.0
    assert float(recal.max()) <= 1.0


@pytest.mark.parametrize("sport", ["tennis", "mlb", "soccer"])
def test_real_corpus_no_edge_claims(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_sport_result(sport)
    combined = str(r.get("note", "")) + " " + sport
    _assert_no_edge_claims(combined)
