"""tests/platform/test_calibration_conformance.py — Calibration-conformance tests.

Synthetic units (always run): perfect calibration → ECE≈0/PASS; severe
miscalibration → ECE>0.5/FAIL; verdict boundaries; _reliability_bins sum/NaN.
Real-corpus (skip if absent): metrics valid, bins sum to n, verdict valid,
honesty note present, no edge-claim language in output.
run_all_sports: returns 3 results, no uncaught exceptions.
"""
from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.calibration_conformance import (
    HONESTY_NOTE,
    ECE_PASS_THRESHOLD,
    ECE_WARN_THRESHOLD,
    CalibrationResult,
    _reliability_bins,
    _verdict,
    calibration_conformance,
    run_all_sports,
    _ADAPTER_REGISTRY,
)

# Affirmative edge-claim phrases that must not appear in output.
# Negations like "does NOT beat the market" are allowed; these are direct claims.
_FORBIDDEN = ["has an edge", "profitable strategy", "guaranteed profit",
               "positive roi", "guaranteed return"]


def _check_no_edge_claims(text: str) -> None:
    lower = text.lower()
    for phrase in _FORBIDDEN:
        assert phrase not in lower, f"Forbidden phrase '{phrase}' in: {text[:200]}"


def _check_has_honesty_note(text: str) -> None:
    lower = text.lower()
    assert "calibration" in lower and ("edge" in lower or "market" in lower), (
        f"Honesty note must mention calibration + edge/market: {text[:200]}"
    )


# ---------------------------------------------------------------------------
# Synthetic data factories
# ---------------------------------------------------------------------------

def _fake_adapter(probs: np.ndarray, targets: np.ndarray, sport: str = "synthetic") -> object:
    class _FB:
        signal_col = probs
        target = targets
    class _Adapter:
        pass
    a = _Adapter()
    a.sport = sport  # type: ignore[attr-defined]
    a.feature_bundle = lambda hypothesis, seasons: _FB()  # type: ignore[attr-defined]
    return a


def _perfect_adapter(n: int = 5000, n_bins: int = 10) -> object:
    """Perfectly calibrated: for each bin midpoint, outcomes ~ Binomial(1, p)."""
    rng = np.random.default_rng(42)
    mids = np.linspace(0.05, 0.95, n_bins)
    n_per = n // n_bins
    ps, ys = [], []
    for mid in mids:
        ps.append(np.full(n_per, mid))
        ys.append(rng.binomial(1, mid, size=n_per).astype(float))
    return _fake_adapter(np.concatenate(ps), np.concatenate(ys))


def _miscal_adapter(n: int = 2000) -> object:
    """Severely miscalibrated: probs ≈ 0.9, outcomes always 0 → ECE ≈ 0.9."""
    rng = np.random.default_rng(99)
    return _fake_adapter(rng.uniform(0.8, 1.0, n), np.zeros(n))


# ---------------------------------------------------------------------------
# Synthetic unit: perfect calibration
# ---------------------------------------------------------------------------

def test_synthetic_perfect_ece_near_zero() -> None:
    result = calibration_conformance(_perfect_adapter(5000), seasons=None)
    assert result.error is None
    assert result.ece < 0.05, f"ECE={result.ece:.4f} should be < 0.05"


def test_synthetic_perfect_brier_and_verdict() -> None:
    result = calibration_conformance(_perfect_adapter(5000), seasons=None)
    assert 0.0 <= result.brier_score <= 1.0
    assert result.verdict == "PASS"


def test_synthetic_perfect_honesty_note() -> None:
    result = calibration_conformance(_perfect_adapter(1000), seasons=None)
    _check_has_honesty_note(result.honesty_note)
    _check_no_edge_claims(result.honesty_note)


# ---------------------------------------------------------------------------
# Synthetic unit: miscalibration
# ---------------------------------------------------------------------------

def test_synthetic_miscal_ece_high() -> None:
    result = calibration_conformance(_miscal_adapter(2000), seasons=None)
    assert result.error is None
    assert result.ece > 0.5, f"ECE={result.ece:.4f} should be > 0.5"


def test_synthetic_miscal_verdict_and_brier() -> None:
    result = calibration_conformance(_miscal_adapter(2000), seasons=None)
    assert result.verdict == "FAIL"
    assert result.brier_score > 0.5


# ---------------------------------------------------------------------------
# Verdict boundary logic
# ---------------------------------------------------------------------------

def test_verdict_boundaries() -> None:
    assert _verdict(ECE_PASS_THRESHOLD - 0.001) == "PASS"
    assert _verdict(ECE_PASS_THRESHOLD) == "WARN"   # boundary: not PASS
    assert _verdict((ECE_PASS_THRESHOLD + ECE_WARN_THRESHOLD) / 2) == "WARN"
    assert _verdict(ECE_WARN_THRESHOLD) == "FAIL"
    assert _verdict(float("nan")) == "SKIP"


# ---------------------------------------------------------------------------
# _reliability_bins unit tests
# ---------------------------------------------------------------------------

def test_reliability_bins_count_and_sum() -> None:
    rng = np.random.default_rng(0)
    p, y = rng.uniform(0, 1, 300), rng.binomial(1, rng.uniform(0, 1, 300)).astype(float)
    bins = _reliability_bins(p, y, 10)
    assert len(bins) == 10
    assert sum(b.n for b in bins) == 300


def test_reliability_bins_empty_has_nan_and_obs_in_range() -> None:
    rng = np.random.default_rng(7)
    p, y = rng.uniform(0, 1, 500), rng.binomial(1, rng.uniform(0, 1, 500)).astype(float)
    bins = _reliability_bins(p, y, 10)
    for b in bins:
        if b.n > 0:
            assert 0.0 <= b.mean_obs <= 1.0 and 0.0 <= b.mean_pred <= 1.0
    # All-low probs: last bin is empty
    p2, y2 = np.full(100, 0.05), np.zeros(100)
    bins2 = _reliability_bins(p2, y2, 10)
    assert bins2[9].n == 0 and math.isnan(bins2[9].mean_pred)


# ---------------------------------------------------------------------------
# Corpus availability helper
# ---------------------------------------------------------------------------

def _corpus_available(sport: str) -> bool:
    if sport not in _ADAPTER_REGISTRY:
        return False
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    try:
        mod = importlib.import_module(module_path)
        adapter = getattr(mod, class_name)()
        if sport == "mlb":
            adapter._get_games()
        else:
            adapter._get_matches()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Real-corpus parametrized tests
# ---------------------------------------------------------------------------

_SPORTS = ["tennis", "soccer", "mlb"]


def _get_real_result(sport: str) -> CalibrationResult:
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    mod = importlib.import_module(module_path)
    return calibration_conformance(getattr(mod, class_name)(), seasons=None)


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_no_error(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    assert r.error is None, f"{sport}: {r.error}"
    assert r.n > 0


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_brier_valid_range(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    assert not math.isnan(r.brier_score)
    assert 0.0 <= r.brier_score <= 1.0


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_ece_nonnegative(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    assert r.ece >= 0.0


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_probs_in_unit_interval(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    mod = importlib.import_module(module_path)
    bundle = getattr(mod, class_name)().feature_bundle(hypothesis=None, seasons=[])
    probs = np.asarray(bundle.signal_col, dtype=float)
    valid = probs[~np.isnan(probs)]
    assert float(valid.min()) >= 0.0
    assert float(valid.max()) <= 1.0


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_bins_sum_to_n(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    assert sum(b.n for b in r.reliability_bins) == r.n


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_verdict_valid(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    assert r.verdict in {"PASS", "WARN", "FAIL", "SKIP"}


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_honesty_note(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    _check_has_honesty_note(r.honesty_note)


@pytest.mark.parametrize("sport", _SPORTS)
def test_real_corpus_no_edge_claim_language(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    r = _get_real_result(sport)
    combined = " ".join(filter(None, [r.verdict, r.sport, r.error or ""])).lower()
    _check_no_edge_claims(combined)


# ---------------------------------------------------------------------------
# run_all_sports integration
# ---------------------------------------------------------------------------

def test_run_all_sports() -> None:
    results = run_all_sports()
    assert len(results) == len(_ADAPTER_REGISTRY)
    for r in results:
        assert isinstance(r.sport, str) and r.sport
        assert r.verdict in {"PASS", "WARN", "FAIL", "SKIP"}


def test_honesty_note_constant_keywords() -> None:
    lower = HONESTY_NOTE.lower()
    assert "calibration" in lower
    assert "edge" in lower or "market" in lower
