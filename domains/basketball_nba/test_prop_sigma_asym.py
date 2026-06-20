"""Per-file test for domains.basketball_nba.prop_sigma_asym.

Acceptance criteria (7 cases):
  (1) synthetic right-skewed residuals -> asymmetric==True, k_up>k_down, both >=1.0
  (2) symmetric Gaussian residuals -> asymmetric==False, k_up~=k_down~=1.0 within tol
  (3) coverage math: residuals whose realized over-tail rate exceeds Gaussian-nominal
      -> over_coverage shortfall flagged, k_up>1
  (4) never deflates: any computed k<1 clamps to exactly 1.0
  (5) n < MIN_N per stat -> INSUFFICIENT_DATA, k_up==k_down==1.0
  (6) absent OOF / empty -> safe INSUFFICIENT_DATA, never raises
  (7) no $/roi/pnl/edge/profit key anywhere; calibration-only framing

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_prop_sigma_asym.py -q
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.prop_sigma_asym import (
    INSUFFICIENT_DATA,
    MIN_N,
    _robust_sigma,
    _stat_result,
    _UPPER_NOMINAL,
    measure_asymmetry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_BANNED_KEYS = {"roi", "pnl", "edge", "profit", "dollar", "$"}


def _no_banned_keys(d: dict) -> bool:
    """Return True if no $-framing key appears in the result dict."""
    for k in d:
        if any(b in k.lower() for b in _BANNED_KEYS):
            return False
    return True


def _make_oof_parquet(residuals_by_stat: dict[str, np.ndarray]) -> Path:
    """Write a minimal OOF parquet to a temp file and return the path."""
    rows = []
    for stat, resids in residuals_by_stat.items():
        for i, r in enumerate(resids):
            rows.append({
                "game_id": f"G{i:04d}",
                "player_id": i % 50,
                "stat": stat,
                "oof_pred": 5.0,       # constant prediction
                "actual": 5.0 + r,     # actual = pred + residual
                "game_date": "2024-01-01",
                "fold": 0,
                "season": "2024",
            })
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    df.to_parquet(tmp.name, index=False)
    return Path(tmp.name)


def _right_skewed_residuals(n: int = 3000, seed: int = 42) -> np.ndarray:
    """Return right-skewed residuals: Gaussian body + exponential positive tail.

    The IQR-based sigma captures the central body; the heavy right tail then
    causes k_up > 1 > k_down (clamped to 1).
    """
    rng = np.random.default_rng(seed)
    body = rng.normal(0.0, 2.0, size=int(n * 0.82))
    tail = rng.exponential(5.0, size=int(n * 0.18))
    return np.concatenate([body, tail])


# ---------------------------------------------------------------------------
# Test 1: right-skewed residuals -> asymmetric==True, k_up>k_down, both >=1.0
# ---------------------------------------------------------------------------
def test_right_skewed_asymmetric():
    """Gaussian body + exponential right tail -> asymmetric==True, k_up > k_down."""
    residuals = _right_skewed_residuals(n=3000, seed=42)

    result = _stat_result("pts", residuals, min_n=MIN_N)

    assert result["status"] == "ok", f"Expected ok, got {result['status']}"
    assert result["asymmetric"] is True, (
        f"Expected asymmetric=True for right-skewed mixture; "
        f"k_up={result['suggested_k_up']:.3f}, k_down={result['suggested_k_down']:.3f}"
    )
    assert result["suggested_k_up"] > result["suggested_k_down"], (
        f"Expected k_up > k_down for right-skew; "
        f"k_up={result['suggested_k_up']:.3f}, k_down={result['suggested_k_down']:.3f}"
    )
    assert result["suggested_k_up"] >= 1.0, f"k_up should be >= 1.0"
    assert result["suggested_k_down"] >= 1.0, f"k_down should be >= 1.0"
    assert _no_banned_keys(result)


# ---------------------------------------------------------------------------
# Test 2: symmetric Gaussian residuals -> asymmetric==False, k~=1.0 both sides
# ---------------------------------------------------------------------------
def test_symmetric_gaussian_not_asymmetric():
    """Symmetric N(0,sigma) residuals: both k's near 1.0, asymmetric==False."""
    rng = np.random.default_rng(99)
    sigma_true = 3.5
    residuals = rng.normal(0.0, sigma_true, size=8000)

    result = _stat_result("pts", residuals, min_n=MIN_N)

    assert result["status"] == "ok"
    assert result["asymmetric"] is False, (
        f"Symmetric residuals should not flag asymmetric; "
        f"k_up={result['suggested_k_up']:.4f}, k_down={result['suggested_k_down']:.4f}"
    )
    # For Gaussian data, IQR/1.349 ~= std, so 84.13th pct of r/sigma_iqr ~= 1
    assert abs(result["suggested_k_up"] - 1.0) < 0.3, (
        f"k_up too far from 1.0: {result['suggested_k_up']:.4f}"
    )
    assert abs(result["suggested_k_down"] - 1.0) < 0.3, (
        f"k_down too far from 1.0: {result['suggested_k_down']:.4f}"
    )
    assert _no_banned_keys(result)


# ---------------------------------------------------------------------------
# Test 3: heavy over-tail -> over_coverage > nominal, k_up > 1
# ---------------------------------------------------------------------------
def test_heavy_over_tail_k_up_greater_than_one():
    """Heavy right tail causes over_coverage > nominal and k_up > 1."""
    residuals = _right_skewed_residuals(n=3000, seed=7)

    result = _stat_result("pts", residuals, min_n=MIN_N)

    assert result["status"] == "ok"
    # With IQR-based sigma, the heavy right tail makes over_coverage > nominal
    assert result["over_coverage"] > _UPPER_NOMINAL, (
        f"Expected over_coverage > nominal ({_UPPER_NOMINAL:.4f}); "
        f"got {result['over_coverage']:.4f}"
    )
    assert result["suggested_k_up"] > 1.0, (
        f"Expected k_up > 1.0 for heavy over-tail; got {result['suggested_k_up']:.4f}"
    )
    assert _no_banned_keys(result)


# ---------------------------------------------------------------------------
# Test 4: never deflates -- any k_raw < 1 must clamp to exactly 1.0
# ---------------------------------------------------------------------------
def test_never_deflates():
    """Very tight (sub-Gaussian) residuals: both k's must stay >= 1.0."""
    rng = np.random.default_rng(13)
    # Very tight uniform residuals: most fall well within 1-sigma
    residuals = rng.uniform(-0.05, 0.05, size=1000)

    result = _stat_result("blk", residuals, min_n=MIN_N)

    assert result["status"] == "ok"
    assert result["suggested_k_up"] >= 1.0, (
        f"k_up should never be < 1.0; got {result['suggested_k_up']:.4f}"
    )
    assert result["suggested_k_down"] >= 1.0, (
        f"k_down should never be < 1.0; got {result['suggested_k_down']:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 5: n < MIN_N -> INSUFFICIENT_DATA, k_up == k_down == 1.0
# ---------------------------------------------------------------------------
def test_thin_stat_insufficient_data():
    """Fewer than MIN_N residuals -> INSUFFICIENT_DATA sentinel, k's=1.0."""
    residuals = np.array([1.0, -2.0, 3.0, -1.5, 2.5])  # far below MIN_N=200
    result = _stat_result("stl", residuals, min_n=MIN_N)

    assert result["status"] == INSUFFICIENT_DATA, (
        f"Expected INSUFFICIENT_DATA; got {result['status']}"
    )
    assert result["suggested_k_up"] == 1.0
    assert result["suggested_k_down"] == 1.0
    assert result["asymmetric"] is False
    assert _no_banned_keys(result)


# ---------------------------------------------------------------------------
# Test 6a: absent OOF file -> safe INSUFFICIENT_DATA, never raises
# ---------------------------------------------------------------------------
def test_absent_oof_safe():
    """Absent OOF file must return INSUFFICIENT_DATA dict, not raise."""
    result = measure_asymmetry(
        oof_path=Path("/nonexistent/path/pregame_oof.parquet"),
        stats=["pts", "reb"],
    )
    assert isinstance(result, dict), "Should return a dict even for absent OOF"
    for stat, r in result.items():
        assert r["status"] == INSUFFICIENT_DATA
        assert r["suggested_k_up"] == 1.0
        assert r["suggested_k_down"] == 1.0


# ---------------------------------------------------------------------------
# Test 6b: empty DataFrame -> safe INSUFFICIENT_DATA, never raises
# ---------------------------------------------------------------------------
def test_empty_oof_safe():
    """Empty OOF parquet must return INSUFFICIENT_DATA, never raise."""
    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    pd.DataFrame(
        columns=["stat", "oof_pred", "actual", "player_id", "game_date"]
    ).to_parquet(tmp.name, index=False)

    result = measure_asymmetry(oof_path=Path(tmp.name), stats=["pts"])
    assert isinstance(result, dict)
    for stat, r in result.items():
        assert r["status"] == INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Test 7: no banned keys in any result dict
# ---------------------------------------------------------------------------
def test_no_dollar_or_edge_keys_in_output():
    """No $/roi/pnl/edge/profit/dollar key should appear in any result."""
    rng = np.random.default_rng(55)
    residuals_by_stat = {
        "pts": _right_skewed_residuals(n=600, seed=55),
        "reb": rng.normal(0.0, 2.0, size=600),
    }
    path = _make_oof_parquet(residuals_by_stat)
    results = measure_asymmetry(oof_path=path, min_n=50)
    for stat, r in results.items():
        assert _no_banned_keys(r), (
            f"Banned key found in stat={stat} result: {list(r.keys())}"
        )


# ---------------------------------------------------------------------------
# Bonus: end-to-end via real OOF if available (read-only, non-blocking)
# ---------------------------------------------------------------------------
def test_real_oof_if_available():
    """If real OOF exists, run measure_asymmetry and validate structure."""
    real_path = Path("data/cache/pregame_oof.parquet")
    if not real_path.exists():
        pytest.skip("Real OOF not available; skipping integration check")

    results = measure_asymmetry(oof_path=real_path)
    assert isinstance(results, dict)
    for stat, r in results.items():
        assert "status" in r
        assert "suggested_k_up" in r
        assert "suggested_k_down" in r
        assert r["suggested_k_up"] >= 1.0
        assert r["suggested_k_down"] >= 1.0
        assert _no_banned_keys(r)
        assert r["status"] in ("ok", INSUFFICIENT_DATA)
        if r["status"] == "ok":
            # Real NBA data is right-skewed: k_up should be >= k_down
            assert r["suggested_k_up"] >= r["suggested_k_down"], (
                f"stat={stat}: k_up={r['suggested_k_up']:.3f} < k_down={r['suggested_k_down']:.3f}"
            )
