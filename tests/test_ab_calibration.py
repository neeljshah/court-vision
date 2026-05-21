"""tests/test_ab_calibration.py — Tests for A/B calibration logic in fit_prop_calibration."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile

import pytest

# Ensure project root is importable
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

joblib = pytest.importorskip("joblib")
sklearn = pytest.importorskip("sklearn")

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

import fit_prop_calibration as fpc

STATS = fpc.STATS


def _synthetic_residuals(n: int = 50) -> list[dict]:
    """Create n synthetic residual rows per stat with realistic values."""
    rng = np.random.default_rng(42)
    rows = []
    for stat in STATS:
        for i in range(n):
            pred = float(rng.uniform(5, 30))
            actual = float(rng.uniform(0, 40))
            line = float(pred + rng.uniform(-2, 2))
            rows.append({"stat": stat, "predicted": pred, "actual": actual, "line": line})
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: empty residuals → all stats get promoted=False, reason=insufficient_data
# ──────────────────────────────────────────────────────────────────────────────

def test_ab_test_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(fpc, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "MIN_SAMPLES", 30)

    results = fpc.ab_test_calibration([])

    assert set(results.keys()) == set(STATS)
    for stat, r in results.items():
        assert r["promoted"] is False, f"{stat} should not be promoted with no data"
        assert r.get("reason") == "insufficient_data"
        assert r["n"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: 50 rows/stat, no existing calibrators → all promoted=True
# ──────────────────────────────────────────────────────────────────────────────

def test_ab_test_promotes_when_no_old(tmp_path, monkeypatch):
    monkeypatch.setattr(fpc, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "MIN_SAMPLES", 10)

    residuals = _synthetic_residuals(50)
    results = fpc.ab_test_calibration(residuals)

    assert set(results.keys()) == set(STATS)
    for stat, r in results.items():
        assert "reason" not in r, f"{stat} should not be skipped: {r}"
        assert r["promoted"] is True, f"{stat} should be promoted when no old calibrator exists"
        assert r["n"] == 50
        # Calibrator file should now exist
        calib_path = os.path.join(str(tmp_path), f"calibration_{stat}.joblib")
        assert os.path.exists(calib_path), f"calibration file missing for {stat}"


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: perfect old calibrator → new should not beat it → promoted=False
# ──────────────────────────────────────────────────────────────────────────────

def test_ab_test_keeps_old_when_better(tmp_path, monkeypatch):
    monkeypatch.setattr(fpc, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "MIN_SAMPLES", 10)

    residuals = _synthetic_residuals(60)

    # Build test-set probs/outcomes for "pts" the same way ab_test_calibration does
    stat = "pts"
    rows = [r for r in residuals if r["stat"] == stat]
    n_holdout = max(1, int(len(rows) * 0.2))
    test_rows = rows[-n_holdout:]

    preds = np.array([float(r["predicted"]) for r in test_rows])
    actuals = np.array([float(r["actual"]) for r in test_rows])
    lines = np.array([float(r.get("line") or r["predicted"]) for r in test_rows])
    std = max(preds.std(), 0.1)
    test_p = 1.0 / (1.0 + np.exp(-(preds - lines) / std))
    test_o = (actuals > lines).astype(float)

    # Create a "perfect" old calibrator: fits exactly on the test outcomes
    perfect_calib = IsotonicRegression(out_of_bounds="clip")
    perfect_calib.fit(test_p, test_o)

    old_path = os.path.join(str(tmp_path), f"calibration_{stat}.joblib")
    joblib.dump(perfect_calib, old_path)

    results = fpc.ab_test_calibration(residuals)

    r = results[stat]
    # Perfect old calibrator: brier=0, new trained on train set will be > 0
    # So new should NOT beat old → promoted=False
    assert r["promoted"] is False, (
        f"Should keep old perfect calibrator; old_brier={r.get('old_brier')}, "
        f"new_brier={r.get('new_brier')}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: terrible old calibrator → new should beat it → promoted=True
# ──────────────────────────────────────────────────────────────────────────────

def test_ab_test_promotes_when_new_better(tmp_path, monkeypatch):
    monkeypatch.setattr(fpc, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(fpc, "MIN_SAMPLES", 10)

    residuals = _synthetic_residuals(60)

    stat = "pts"
    rows = [r for r in residuals if r["stat"] == stat]
    n_holdout = max(1, int(len(rows) * 0.2))
    test_rows = rows[-n_holdout:]

    preds = np.array([float(r["predicted"]) for r in test_rows])
    actuals = np.array([float(r["actual"]) for r in test_rows])
    lines = np.array([float(r.get("line") or r["predicted"]) for r in test_rows])
    std = max(preds.std(), 0.1)
    test_p = 1.0 / (1.0 + np.exp(-(preds - lines) / std))
    test_o = (actuals > lines).astype(float)

    # Create a terrible calibrator that predicts the *opposite* of reality
    terrible_calib = IsotonicRegression(out_of_bounds="clip")
    terrible_calib.fit(test_p, 1.0 - test_o)  # inverted labels → worst possible

    old_path = os.path.join(str(tmp_path), f"calibration_{stat}.joblib")
    joblib.dump(terrible_calib, old_path)

    results = fpc.ab_test_calibration(residuals)

    r = results[stat]
    assert r["promoted"] is True, (
        f"Should promote new calibrator over terrible old one; "
        f"old_brier={r.get('old_brier')}, new_brier={r.get('new_brier')}"
    )
    assert isinstance(r["old_brier"], float)
    assert r["new_brier"] < r["old_brier"], (
        f"new_brier ({r['new_brier']}) should be < old_brier ({r['old_brier']})"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: weekly_review.main() with no residuals file exits cleanly
# ──────────────────────────────────────────────────────────────────────────────

def test_weekly_review_runs(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
    import weekly_review

    # Point _RESIDUALS_PATH to a nonexistent file inside tmp_path
    fake_path = os.path.join(str(tmp_path), "prop_residuals.json")
    monkeypatch.setattr(weekly_review, "_RESIDUALS_PATH", fake_path)

    # Should not raise
    weekly_review.main(min_samples=30)

    captured = capsys.readouterr()
    assert "Weekly Review" in captured.out
    assert "No residuals" in captured.out
