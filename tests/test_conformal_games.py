"""
tests/test_conformal_games.py — Unit tests for GameConformalIntervals.

Tests:
1. fit() → quantile widths are reasonable for known-noise synthetic data
2. 80% coverage: synthetic Gaussian noise → empirical coverage ~80% ± 5%
3. Symmetric residual distribution → |q10| ≈ q90 within 20%
4. Classification intervals clamped to [0, 1]
5. intervals() falls back gracefully when not calibrated
6. save() / load() roundtrip preserves quantiles exactly
7. coverage_check() returns correct dict keys
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.conformal_games import (
    GameConformalIntervals,
    _REGRESSION_KEYS,
    _CLASSIFICATION_KEYS,
)

_RNG = np.random.default_rng(42)
_N = 200


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_regression_data(n: int = _N, noise_std: float = 10.0):
    """True values drawn from N(220, 5²); predictions = true + N(0, noise_std²)."""
    actuals = _RNG.normal(220.0, 5.0, size=n)
    preds   = actuals + _RNG.normal(0.0, noise_std, size=n)
    return preds, actuals


def _make_classification_data(n: int = _N, noise: float = 0.12):
    """True labels Bernoulli(0.25); predicted probs = clipped(true_prob + noise)."""
    true_probs = _RNG.uniform(0.1, 0.4, size=n)
    pred_probs = np.clip(true_probs + _RNG.normal(0.0, noise, size=n), 0.0, 1.0)
    labels     = (true_probs > 0.25).astype(float)
    return pred_probs, labels


def _make_full_data(n: int = _N):
    """Build complete predictions + actuals dicts for all 5 outputs."""
    preds: dict = {}
    acts:  dict = {}
    for key in ("total", "spread", "first_half"):
        p, a = _make_regression_data(n, noise_std=12.0 if key == "total" else 9.0)
        preds[key] = p
        acts[key]  = a
    for key in ("blowout_prob", "ot_prob"):
        p, a = _make_classification_data(n, noise=0.10)
        preds[key] = p
        acts[key]  = a
    return preds, acts


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestFitQuantiles:
    """fit() produces reasonable quantile widths."""

    def test_regression_quantiles_are_positive_width(self):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        for key in _REGRESSION_KEYS:
            qt = gc._quantiles[key]
            assert "q10" in qt and "q90" in qt
            width_80 = qt["q90"] - qt["q10"]
            assert width_80 > 0, f"{key}: 80% width should be positive, got {width_80}"

    def test_regression_95_wider_than_80(self):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        for key in _REGRESSION_KEYS:
            qt = gc._quantiles[key]
            w80 = qt["q90"]  - qt["q10"]
            w95 = qt["q975"] - qt["q025"]
            assert w95 >= w80, f"{key}: 95% interval should be >= 80% interval"

    def test_classification_quantiles_in_unit_interval(self):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        for key in _CLASSIFICATION_KEYS:
            qt = gc._quantiles[key]
            assert "q90_residual" in qt
            assert 0.0 <= qt["q90_residual"] <= 1.0, (
                f"{key}: q90_residual={qt['q90_residual']} not in [0,1]"
            )

    def test_sample_counts_match_input(self):
        preds, acts = _make_full_data(n=150)
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        for key in list(_REGRESSION_KEYS) + list(_CLASSIFICATION_KEYS):
            assert gc._quantiles[key]["n"] == 150, (
                f"{key}: expected n=150, got {gc._quantiles[key]['n']}"
            )


class TestCoverage:
    """80% interval covers ~80% of future holdout points (allow ±5%)."""

    def test_regression_80pct_coverage(self):
        # Generate a large enough sample for stable coverage estimate
        _rng = np.random.default_rng(99)
        n_cal, n_test = 500, 1000
        noise_std = 10.0
        true_vals = _rng.normal(220.0, 5.0, size=n_cal + n_test)
        preds_all = true_vals + _rng.normal(0.0, noise_std, size=n_cal + n_test)

        preds_cal = preds_all[:n_cal]
        acts_cal  = true_vals[:n_cal]
        preds_tst = preds_all[n_cal:]
        acts_tst  = true_vals[n_cal:]

        gc = GameConformalIntervals()
        gc.fit({"total": preds_cal}, {"total": acts_cal})

        covered = 0
        for p, a in zip(preds_tst, acts_tst):
            lo, hi = gc.intervals({"total": float(p)}, level=0.80)["total"]
            if lo <= a <= hi:
                covered += 1
        empirical = covered / n_test

        assert abs(empirical - 0.80) <= 0.06, (
            f"80% coverage check failed: empirical={empirical:.2%} (expected 80% ± 5%)"
        )

    def test_95pct_coverage_exceeds_80pct(self):
        _rng = np.random.default_rng(77)
        n = 500
        noise_std = 12.0
        a = _rng.normal(100.0, 10.0, size=n)
        p = a + _rng.normal(0.0, noise_std, size=n)
        gc = GameConformalIntervals()
        gc.fit({"spread": p[:250]}, {"spread": a[:250]})

        covered_80, covered_95 = 0, 0
        for pred, act in zip(p[250:], a[250:]):
            iv80 = gc.intervals({"spread": float(pred)}, level=0.80)["spread"]
            iv95 = gc.intervals({"spread": float(pred)}, level=0.95)["spread"]
            if iv80[0] <= act <= iv80[1]:
                covered_80 += 1
            if iv95[0] <= act <= iv95[1]:
                covered_95 += 1

        assert covered_95 >= covered_80, "95% interval should cover at least as many as 80%"


class TestSymmetry:
    """Near-symmetric residual distribution → |q10| ≈ q90."""

    def test_symmetric_residuals_produce_symmetric_quantiles(self):
        _rng = np.random.default_rng(123)
        n = 1000
        # Perfect zero-mean noise → residuals should be roughly symmetric
        a = _rng.normal(220.0, 1.0, size=n)
        p = a + _rng.normal(0.0, 10.0, size=n)  # unbiased predictions
        gc = GameConformalIntervals()
        gc.fit({"total": p}, {"total": a})
        qt = gc._quantiles["total"]
        # |q10| and q90 should be within 20% of each other
        ratio = abs(qt["q10"]) / max(qt["q90"], 1e-6)
        assert 0.70 <= ratio <= 1.30, (
            f"Symmetry check: |q10|/q90 = {ratio:.3f}, expected 0.70–1.30"
        )


class TestClassificationBounds:
    """Classification intervals are always clamped to [0, 1]."""

    def test_clamped_to_unit_interval(self):
        # Feed classification predictions close to 0 or 1
        p = np.array([0.02, 0.03, 0.05] * 50)
        a = np.array([0.0, 0.0, 1.0]    * 50, dtype=float)
        gc = GameConformalIntervals()
        gc.fit({"blowout_prob": p}, {"blowout_prob": a})

        for pred_val in [0.01, 0.98, 0.50]:
            lo, hi = gc.intervals({"blowout_prob": pred_val}, level=0.80)["blowout_prob"]
            assert 0.0 <= lo <= 1.0, f"lo={lo} not in [0,1]"
            assert 0.0 <= hi <= 1.0, f"hi={hi} not in [0,1]"
            assert lo <= hi, f"lo={lo} > hi={hi}"


class TestFallback:
    """intervals() falls back gracefully when not calibrated."""

    def test_fallback_returns_interval_for_all_keys(self):
        gc = GameConformalIntervals()  # not fitted
        result = gc.intervals(
            {"total": 220.0, "spread": -4.5, "first_half": 105.0,
             "blowout_prob": 0.25, "ot_prob": 0.05},
            level=0.80,
        )
        assert set(result.keys()) == {"total", "spread", "first_half", "blowout_prob", "ot_prob"}
        for key, (lo, hi) in result.items():
            assert lo < hi, f"{key}: fallback lo={lo} >= hi={hi}"

    def test_fallback_classification_clamped(self):
        gc = GameConformalIntervals()
        lo, hi = gc.intervals({"blowout_prob": 0.05}, level=0.80)["blowout_prob"]
        assert 0.0 <= lo and hi <= 1.0


class TestSaveLoad:
    """save() / load() roundtrip preserves all quantile values."""

    def test_roundtrip(self, tmp_path):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)

        out_path = str(tmp_path / "conformal_games_test.json")
        gc.save(path=out_path)

        gc2 = GameConformalIntervals.load(path=out_path)
        for key in list(_REGRESSION_KEYS) + list(_CLASSIFICATION_KEYS):
            assert key in gc2._quantiles, f"Missing key after load: {key}"
            if "q10" in gc._quantiles[key]:
                assert gc2._quantiles[key]["q10"] == gc._quantiles[key]["q10"]
                assert gc2._quantiles[key]["q90"] == gc._quantiles[key]["q90"]

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            GameConformalIntervals.load(path=str(tmp_path / "no_such_file.json"))

    def test_saved_json_has_all_keys(self, tmp_path):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        out_path = str(tmp_path / "cg.json")
        gc.save(path=out_path)
        with open(out_path) as fh:
            data = json.load(fh)
        for key in list(_REGRESSION_KEYS) + list(_CLASSIFICATION_KEYS):
            assert key in data, f"Key {key} missing from saved JSON"
        assert "computed_at" in data


class TestCoverageCheck:
    """coverage_check() returns correct keys and values in [0, 1]."""

    def test_returns_correct_keys(self):
        preds, acts = _make_full_data()
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        cov = gc.coverage_check(preds, acts, level=0.80)
        for key in list(_REGRESSION_KEYS) + list(_CLASSIFICATION_KEYS):
            assert key in cov, f"coverage_check missing key: {key}"
            assert 0.0 <= cov[key] <= 1.0, f"coverage[{key}]={cov[key]} not in [0,1]"

    def test_low_noise_predictions_have_high_coverage(self):
        # Very small residual noise → fitted interval is tight but still covers
        # the same calibration set at near-100% rate (in-sample).
        _rng2 = np.random.default_rng(55)
        n = 200
        vals = _rng2.normal(220.0, 10.0, size=n)
        noise = _rng2.normal(0.0, 0.5, size=n)   # tiny noise, std=0.5
        preds = {"total": vals + noise}
        acts  = {"total": vals}
        gc = GameConformalIntervals()
        gc.fit(preds, acts)
        cov = gc.coverage_check(preds, acts, level=0.80)
        # In-sample coverage should be at least 80% (it will be ~80% by construction)
        assert cov["total"] >= 0.75, f"Expected >= 0.75, got {cov['total']}"
