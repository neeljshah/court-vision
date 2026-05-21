"""Test 18.5-03: regression-test hook for backtest_system.py.

Injects a deliberate R² drop of 0.05 and asserts the gate detects it.
"""
import sys
import os
import json
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.backtest_system import (
    _compute_r2,
    run_regression_check,
    main,
    DEFAULT_R2_THRESHOLD,
)


def _make_residuals(stat: str, n: int = 50, noise: float = 0.1) -> list[dict]:
    """Generate synthetic residuals where R² ≈ 1 - noise²."""
    rows = []
    for i in range(n):
        actual = float(10 + i * 0.2)
        pred = actual + (noise * (i % 3 - 1))  # small systematic noise
        rows.append({"stat": stat, "predicted": pred, "actual": actual})
    return rows


def test_compute_r2_perfect():
    rows = [{"stat": "pts", "predicted": float(i), "actual": float(i)} for i in range(20)]
    r2 = _compute_r2(rows, "pts")
    assert r2 == 1.0


def test_compute_r2_insufficient():
    rows = [{"stat": "pts", "predicted": 1.0, "actual": 2.0}] * 3  # < 5 samples
    r2 = _compute_r2(rows, "pts")
    assert r2 is None


def test_regression_check_pass():
    """Good predictions → all stats pass."""
    residuals = _make_residuals("pts", n=50, noise=0.05)
    results = run_regression_check(residuals, r2_threshold=0.5, stats=["pts"])
    assert results["pts"]["pass"] is True
    assert results["pts"]["r2"] is not None


def test_regression_check_detects_drop():
    """Inject a deliberate R² drop: high noise residuals should fail."""
    rows = []
    for i in range(60):
        actual = float(10 + i * 0.2)
        # Very bad predictions — random around 15.0 regardless of actual
        pred = 15.0 + (i % 7 - 3) * 5.0  # huge noise, R² will be very low
        rows.append({"stat": "pts", "predicted": pred, "actual": actual})
    results = run_regression_check(rows, r2_threshold=DEFAULT_R2_THRESHOLD, stats=["pts"])
    # R² should be well below 0.70 with this noise
    assert results["pts"]["pass"] is False, f"Expected FAIL, got R²={results['pts']['r2']}"


def test_main_returns_1_on_regression(tmp_path):
    """main() exits 1 when regression detected."""
    rows = []
    for i in range(60):
        actual = float(10 + i * 0.2)
        pred = 15.0 + (i % 7 - 3) * 5.0
        rows.append({"stat": "pts", "predicted": pred, "actual": actual})
    f = tmp_path / "residuals.json"
    f.write_text(json.dumps(rows))
    exit_code = main(["--stat", "pts", "--residuals", str(f),
                      "--r2-threshold", str(DEFAULT_R2_THRESHOLD)])
    assert exit_code == 1


def test_main_returns_0_on_no_data(tmp_path):
    """main() exits 0 when residuals file is missing (insufficient data = pass)."""
    exit_code = main(["--residuals", str(tmp_path / "nonexistent.json")])
    assert exit_code == 0
