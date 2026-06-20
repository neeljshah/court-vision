"""scripts/platformkit/test_resolution_collapse_guard.py -- per-file tests.

Acceptance criteria (all must pass):
  (1) degenerate corpus (every prob == base rate, 1-2 distinct values)
      -> verdict==COLLAPSED, resolution ~= 0, distinct_prob_ratio below floor
  (2) healthy spread corpus (probs span 0.2..0.8, high RES) -> verdict==DISCRIMINATING
  (3) borderline: RES above floor but distinct-prob ratio below floor
      -> COLLAPSED, failing_reason names the tripping axis
  (4) n < MIN_N -> INSUFFICIENT_DATA, never fabricates DISCRIMINATING
  (5) resolution value reconciles with calib_decomp.decompose on a hand corpus within 1e-6
  (6) loader/empty -> INSUFFICIENT_DATA sentinel, never raises
  (7) no $/roi/pnl/edge/profit key anywhere in any result dict

Per-file only: python -m pytest scripts/platformkit/test_resolution_collapse_guard.py -q
Never run full pytest suite (freezes the box).
ASCII only. Calibration not edge. Units only.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pytest

from scripts.platformkit.calib_decomp import decompose as calib_decompose
from scripts.platformkit.resolution_collapse_guard import (
    DISTINCT_PROB_FLOOR,
    MIN_N,
    RES_FLOOR,
    check_sport,
    measure,
)

# ---------------------------------------------------------------------------
# Forbidden keys (no dollar / ROI / edge / profit claims)
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = re.compile(
    r"(\$|roi|pnl|edge|profit|dollar|revenue|winnings)",
    re.IGNORECASE,
)


def _assert_no_forbidden(result: dict, label: str = "") -> None:
    """Fail if any key in result matches a forbidden pattern."""
    for key in result:
        assert not _FORBIDDEN_KEYS.search(str(key)), (
            f"Forbidden key '{key}' in result dict [{label}]"
        )


# ---------------------------------------------------------------------------
# Synthetic corpus builders
# ---------------------------------------------------------------------------

def _degenerate_corpus(n: int = 200, base: float = 0.55, seed: int = 42):
    """All predictions equal base rate -> RES == 0."""
    rng = np.random.default_rng(seed)
    p = np.full(n, base)
    y = (rng.uniform(size=n) < base).astype(float)
    return p, y


def _two_value_corpus(n: int = 200, v1: float = 0.50, v2: float = 0.55, seed: int = 42):
    """Two distinct prediction values -> still effectively collapsed."""
    rng = np.random.default_rng(seed)
    # Alternate v1/v2 deterministically
    p = np.where(np.arange(n) % 2 == 0, v1, v2)
    y = (rng.uniform(size=n) < p).astype(float)
    return p, y


def _healthy_corpus(n: int = 300, lo: float = 0.2, hi: float = 0.8, seed: int = 7):
    """Probs span [lo, hi]; model is informative."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(lo, hi, n)
    y = (rng.uniform(size=n) < p).astype(float)
    return p, y


def _borderline_corpus(n: int = 300, seed: int = 99):
    """Few distinct probability values but RES happens to be above RES_FLOOR.

    Achieves this by creating a small number (3) of distinct prob values that
    are spread enough for RES > RES_FLOOR, but far fewer distinct probs than
    DISTINCT_PROB_FLOOR * n, tripping the ratio gate.
    """
    rng = np.random.default_rng(seed)
    # 3 distinct probs: 0.3, 0.5, 0.7 -- chosen so RES should be > 0.001
    vals = [0.3, 0.5, 0.7]
    indices = rng.integers(0, 3, n)
    p = np.array([vals[i] for i in indices])
    y = (rng.uniform(size=n) < p).astype(float)
    return p, y


# ---------------------------------------------------------------------------
# Test (1): degenerate corpus -> COLLAPSED, RES ~= 0, distinct_prob_ratio below floor
# ---------------------------------------------------------------------------

def test_degenerate_single_value_is_collapsed():
    """All probs == base_rate -> COLLAPSED, resolution near zero."""
    p, y = _degenerate_corpus(n=200, base=0.55)
    result = measure(p, y)

    _assert_no_forbidden(result, "degenerate_single_value")
    assert result["verdict"] == "COLLAPSED", (
        f"Expected COLLAPSED, got {result['verdict']}; "
        f"RES={result['resolution']}, dp_ratio={result['distinct_prob_ratio']}"
    )
    # Resolution must be at or very near zero (within float noise)
    assert result["resolution"] is not None
    assert result["resolution"] < RES_FLOOR, (
        f"RES={result['resolution']} should be below RES_FLOOR={RES_FLOOR}"
    )
    # Distinct prob ratio must be below floor
    assert result["distinct_prob_ratio"] is not None
    assert result["distinct_prob_ratio"] < DISTINCT_PROB_FLOOR, (
        f"distinct_prob_ratio={result['distinct_prob_ratio']} should be below "
        f"DISTINCT_PROB_FLOOR={DISTINCT_PROB_FLOOR}"
    )
    # failing_reason must be populated
    assert result["failing_reason"] is not None and len(result["failing_reason"]) > 0
    # Calibration note must be present
    assert "calibration" in result["note"].lower()


def test_degenerate_two_values_is_collapsed():
    """Two distinct prediction values (effectively constant) -> COLLAPSED."""
    p, y = _two_value_corpus(n=200)
    result = measure(p, y)

    _assert_no_forbidden(result, "degenerate_two_values")
    assert result["verdict"] == "COLLAPSED", (
        f"Expected COLLAPSED for 2-value corpus; got {result['verdict']}"
    )
    assert result["distinct_prob_count"] <= 2


# ---------------------------------------------------------------------------
# Test (2): healthy spread corpus -> DISCRIMINATING
# ---------------------------------------------------------------------------

def test_healthy_spread_is_discriminating():
    """Probs spanning 0.2..0.8 with calibrated outcomes -> DISCRIMINATING."""
    p, y = _healthy_corpus(n=400)
    result = measure(p, y)

    _assert_no_forbidden(result, "healthy_spread")
    assert result["verdict"] == "DISCRIMINATING", (
        f"Expected DISCRIMINATING; got {result['verdict']}; "
        f"RES={result['resolution']}, dp_ratio={result['distinct_prob_ratio']}, "
        f"reason={result['failing_reason']}"
    )
    assert result["resolution"] is not None
    assert result["resolution"] >= RES_FLOOR
    assert result["distinct_prob_ratio"] is not None
    assert result["distinct_prob_ratio"] >= DISTINCT_PROB_FLOOR
    # No failing_reason on DISCRIMINATING
    assert result["failing_reason"] is None


# ---------------------------------------------------------------------------
# Test (3): borderline -- RES above floor, distinct-prob ratio below floor -> COLLAPSED
# ---------------------------------------------------------------------------

def test_borderline_high_res_low_dp_ratio_is_collapsed():
    """3 distinct probs -> dp_ratio well below floor -> COLLAPSED even if RES ok."""
    p, y = _borderline_corpus(n=300)
    result = measure(p, y)

    _assert_no_forbidden(result, "borderline")
    # With only 3 distinct values over 300 rows: ratio = 3/300 = 0.01 < DISTINCT_PROB_FLOOR
    assert result["distinct_prob_ratio"] < DISTINCT_PROB_FLOOR, (
        f"Expected dp_ratio < {DISTINCT_PROB_FLOOR}; "
        f"got {result['distinct_prob_ratio']} (n_distinct={result['distinct_prob_count']})"
    )
    assert result["verdict"] == "COLLAPSED", (
        f"Expected COLLAPSED (dp_ratio floor); got {result['verdict']}"
    )
    # failing_reason must name the distinct-prob axis
    assert result["failing_reason"] is not None
    assert "distinct" in result["failing_reason"].lower() or "ratio" in result["failing_reason"].lower(), (
        f"failing_reason should name distinct-prob axis; got: {result['failing_reason']}"
    )


# ---------------------------------------------------------------------------
# Test (4): n < MIN_N -> INSUFFICIENT_DATA, never DISCRIMINATING
# ---------------------------------------------------------------------------

def test_insufficient_data_small_n():
    """n < MIN_N -> INSUFFICIENT_DATA; never fabricates DISCRIMINATING."""
    rng = np.random.default_rng(1)
    n_small = MIN_N - 1
    p = rng.uniform(0.1, 0.9, n_small)
    y = (rng.uniform(size=n_small) < p).astype(float)
    result = measure(p, y)

    _assert_no_forbidden(result, "insufficient_data")
    assert result["verdict"] == "INSUFFICIENT_DATA", (
        f"n={n_small} < MIN_N={MIN_N} should give INSUFFICIENT_DATA; "
        f"got {result['verdict']}"
    )
    # Must not claim DISCRIMINATING
    assert result["verdict"] != "DISCRIMINATING"
    assert result["resolution"] is None
    assert result["n"] == n_small


def test_insufficient_data_zero_rows():
    """n=0 -> INSUFFICIENT_DATA."""
    result = measure([], [])
    _assert_no_forbidden(result, "zero_rows")
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["verdict"] != "DISCRIMINATING"


def test_insufficient_data_exactly_min_n_minus_1():
    """Exactly MIN_N - 1 rows -> INSUFFICIENT_DATA."""
    rng = np.random.default_rng(2)
    n = MIN_N - 1
    p = rng.uniform(0.2, 0.8, n)
    y = (rng.uniform(size=n) < p).astype(float)
    result = measure(p, y)
    assert result["verdict"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Test (5): resolution reconciles with calib_decomp.decompose within 1e-6
# ---------------------------------------------------------------------------

def test_resolution_reconciles_with_calib_decomp():
    """measure() resolution == calib_decomp.decompose() resolution within 1e-6."""
    p, y = _healthy_corpus(n=300, seed=42)
    guard_result = measure(p, y)
    decomp_result = calib_decompose(p, y)

    assert guard_result["resolution"] is not None
    assert decomp_result.get("status") == "ok"

    guard_res = guard_result["resolution"]
    decomp_res = float(decomp_result["resolution"])

    assert abs(guard_res - decomp_res) < 1e-6, (
        f"Resolution mismatch: guard={guard_res:.8f} vs decomp={decomp_res:.8f}"
    )

    # Also check decomp pass-through in result
    assert guard_result["decomp"] is not None
    assert abs(float(guard_result["decomp"]["resolution"]) - decomp_res) < 1e-6


def test_resolution_reconciles_degenerate():
    """For degenerate corpus, both guard and calib_decomp report near-zero RES."""
    p, y = _degenerate_corpus(n=200)
    guard_result = measure(p, y)
    decomp_result = calib_decompose(p, y)

    assert decomp_result.get("status") == "ok"
    guard_res = guard_result["resolution"]
    decomp_res = float(decomp_result["resolution"])

    assert abs(guard_res - decomp_res) < 1e-6, (
        f"Resolution mismatch on degenerate: guard={guard_res} vs decomp={decomp_res}"
    )


# ---------------------------------------------------------------------------
# Test (6): loader error / empty -> INSUFFICIENT_DATA sentinel, never raises
# ---------------------------------------------------------------------------

def _failing_loader(sport: str):
    raise RuntimeError(f"Simulated load failure for sport={sport}")


def _empty_loader(sport: str):
    return np.array([]), np.array([])


def test_loader_error_gives_insufficient_data():
    """Loader that raises -> INSUFFICIENT_DATA sentinel, no exception propagates."""
    result = check_sport("nba", loader=_failing_loader)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    _assert_no_forbidden(result, "loader_error")
    assert "loader error" in (result["failing_reason"] or "").lower()


def test_empty_loader_gives_insufficient_data():
    """Loader that returns empty arrays -> INSUFFICIENT_DATA, never raises."""
    result = check_sport("mlb", loader=_empty_loader)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    _assert_no_forbidden(result, "empty_loader")
    assert result["verdict"] != "DISCRIMINATING"


def test_loader_never_raises_on_unknown_sport():
    """check_sport with a failing loader for an unknown sport -> sentinel, no exception."""
    result = check_sport("unknown_sport_xyz", loader=_failing_loader)
    # Should not raise; must return a sentinel
    assert "verdict" in result
    assert result["verdict"] != "DISCRIMINATING"


# ---------------------------------------------------------------------------
# Test (7): no forbidden keys in any result (sampled across multiple paths)
# ---------------------------------------------------------------------------

def test_no_forbidden_keys_healthy():
    p, y = _healthy_corpus(n=200)
    _assert_no_forbidden(measure(p, y), "healthy")


def test_no_forbidden_keys_degenerate():
    p, y = _degenerate_corpus(n=200)
    _assert_no_forbidden(measure(p, y), "degenerate")


def test_no_forbidden_keys_insufficient():
    _assert_no_forbidden(measure([], []), "empty")
    _assert_no_forbidden(measure([0.5] * 5, [0.0] * 5), "small_n")


def test_no_forbidden_keys_check_sport():
    result = check_sport("nba", loader=_failing_loader)
    _assert_no_forbidden(result, "check_sport_error")


# ---------------------------------------------------------------------------
# Additional edge-case / robustness checks
# ---------------------------------------------------------------------------

def test_exactly_min_n_rows_does_not_collapse_prematurely():
    """At exactly MIN_N rows the function proceeds (not INSUFFICIENT_DATA)."""
    rng = np.random.default_rng(3)
    p = rng.uniform(0.2, 0.8, MIN_N)
    y = (rng.uniform(size=MIN_N) < p).astype(float)
    result = measure(p, y)
    # Verdict should be DISCRIMINATING or COLLAPSED based on data, not INSUFFICIENT_DATA
    # (MIN_N rows is the exact boundary; we check it does NOT auto-return INSUFFICIENT_DATA)
    # Note: calib_decomp also uses MIN_N_TOTAL=30 so result should be ok-status
    assert result["verdict"] in ("DISCRIMINATING", "COLLAPSED"), (
        f"At exactly MIN_N={MIN_N} rows, expected a real verdict; got {result['verdict']}"
    )


def test_collapsed_verdict_reports_failing_reason():
    """COLLAPSED verdict always populates failing_reason with a non-empty string."""
    p, y = _degenerate_corpus(n=200)
    result = measure(p, y)
    assert result["verdict"] == "COLLAPSED"
    assert result["failing_reason"] is not None
    assert len(result["failing_reason"]) > 10, "failing_reason too short to be meaningful"


def test_discriminating_has_no_failing_reason():
    """DISCRIMINATING verdict has failing_reason == None."""
    p, y = _healthy_corpus(n=400)
    result = measure(p, y)
    assert result["verdict"] == "DISCRIMINATING"
    assert result["failing_reason"] is None


def test_calibration_note_present_in_all_verdicts():
    """Every result dict carries the calibration-not-edge note."""
    cases = [
        _healthy_corpus(n=300),
        _degenerate_corpus(n=200),
    ]
    for p, y in cases:
        result = measure(p, y)
        assert "note" in result
        assert "calibration" in result["note"].lower()
    # Also INSUFFICIENT_DATA
    result_insuf = measure([], [])
    assert "calibration" in result_insuf["note"].lower()


def test_check_sport_returns_sport_key():
    """check_sport result always includes the sport key."""
    result = check_sport("mlb", loader=_empty_loader)
    assert result.get("sport") == "mlb"
