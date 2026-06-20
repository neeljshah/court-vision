"""scripts/platformkit/test_calib_drift_monitor.py -- Per-file tests for calib_drift_monitor.

Acceptance criteria from pa-drift spec:
  1. Stationary stream -> NOT_STALE (status and stale=False).
  2. Injected regime shift -> STALE flag + correct offending_window_index.
  3. Fewer than 2 windows -> INSUFFICIENT_DATA (stale always False).
  4. stale-never-green: INSUFFICIENT_DATA never sets stale=True.
  5. No $ / roi / pnl keys in as_dict() output.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_calib_drift_monitor.py -q

Design note on window_size:
  ECE on n=100-observation windows has high sampling variance (+-0.06+) because
  calibration bins are populated sparsely.  Tests use window_size=200 so per-window
  ECE is stable enough to cleanly separate stationary (ECE delta ~0.02) from a hard
  regime shift (ECE delta ~0.40).  The acceptance thresholds (ece=0.05, brier=0.03)
  are appropriate for n>=200 windows; smaller windows need wider thresholds.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.calib_drift_monitor import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NOT_STALE,
    STATUS_STALE,
    check_drift,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)

# Window size used in most tests -- large enough for stable per-window ECE.
_WIN = 200


def _make_stationary(n: int, base_prob: float = 0.55) -> tuple:
    """Well-calibrated stationary stream: probs near base_prob, outcomes match."""
    probs = np.clip(RNG.normal(base_prob, 0.05, n), 0.01, 0.99)
    outcomes = (RNG.uniform(size=n) < probs).astype(float)
    return probs.tolist(), outcomes.tolist()


def _make_shifted(n_baseline: int, n_shift: int, shift_to: float = 0.1) -> tuple:
    """Stream with a calibration regime shift: baseline near 0.55, then shift.

    In the shifted window the probs stay at 0.55 but outcomes shift to shift_to,
    creating a large ECE jump (probs say 0.55 but outcomes average shift_to).
    """
    base_probs = np.clip(RNG.normal(0.55, 0.05, n_baseline), 0.01, 0.99)
    base_outcomes = (RNG.uniform(size=n_baseline) < base_probs).astype(float)

    # Regime shift: probs still 0.55 but observed rate = shift_to
    shift_probs = np.full(n_shift, 0.55)
    shift_outcomes = (RNG.uniform(size=n_shift) < shift_to).astype(float)

    probs = np.concatenate([base_probs, shift_probs])
    outcomes = np.concatenate([base_outcomes, shift_outcomes])
    return probs.tolist(), outcomes.tolist()


# ---------------------------------------------------------------------------
# Test 1: stationary stream -> NOT_STALE
# ---------------------------------------------------------------------------


def test_stationary_not_stale():
    """A well-calibrated, stationary stream must NOT be flagged stale.

    Uses window_size=200 for stable per-window ECE (n=1000 -> 5 windows).
    """
    probs, outcomes = _make_stationary(1000)
    result = check_drift(probs, outcomes, window_size=_WIN,
                         threshold_ece=0.05, threshold_brier=0.03)
    assert result.status == STATUS_NOT_STALE, (
        f"Expected NOT_STALE on stationary stream; "
        f"offending_window_index={result.offending_window_index}, "
        f"windows={[(w.window_index, round(w.ece, 4), round(w.brier, 4)) for w in result.windows]}"
    )
    assert result.stale is False
    assert result.offending_window_index is None
    assert len(result.windows) == 5  # 1000 / 200


# ---------------------------------------------------------------------------
# Test 2: injected regime shift -> STALE + correct window index
# ---------------------------------------------------------------------------


def test_regime_shift_stale():
    """After a regime shift the monitor must set status=STALE and report the window."""
    # 200 baseline + 400 shifted (2 shifted windows of size 200)
    probs, outcomes = _make_shifted(n_baseline=_WIN, n_shift=_WIN * 2, shift_to=0.1)
    result = check_drift(probs, outcomes, window_size=_WIN,
                         threshold_ece=0.05, threshold_brier=0.03)
    assert result.status == STATUS_STALE
    assert result.stale is True
    # The first shifted window is window_index=1
    assert result.offending_window_index is not None
    assert result.offending_window_index >= 1


def test_regime_shift_reports_first_offending_window():
    """offending_window_index must be the FIRST window that crosses the threshold."""
    # 1 baseline window + 3 shifted windows = 4 windows total
    probs, outcomes = _make_shifted(n_baseline=_WIN, n_shift=_WIN * 3, shift_to=0.05)
    result = check_drift(probs, outcomes, window_size=_WIN,
                         threshold_ece=0.05, threshold_brier=0.03)
    assert result.stale is True
    # First offending is the earliest shifted window (index 1), not later ones
    assert result.offending_window_index == 1


# ---------------------------------------------------------------------------
# Test 3: < 2 windows -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


def test_fewer_than_two_windows_insufficient():
    """With only 1 full window the monitor must return INSUFFICIENT_DATA."""
    probs, outcomes = _make_stationary(80)  # < 100 -> 0 windows
    result = check_drift(probs, outcomes, window_size=100)
    assert result.status == STATUS_INSUFFICIENT_DATA

    probs2, outcomes2 = _make_stationary(150)  # 1 full window
    result2 = check_drift(probs2, outcomes2, window_size=100)
    assert result2.status == STATUS_INSUFFICIENT_DATA


def test_exactly_zero_observations_insufficient():
    """Empty sequences -> INSUFFICIENT_DATA."""
    result = check_drift([], [], window_size=50)
    assert result.status == STATUS_INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Test 4: stale-never-green -- INSUFFICIENT_DATA never sets stale=True
# ---------------------------------------------------------------------------


def test_stale_never_green():
    """INSUFFICIENT_DATA must never set stale=True (stale-never-green invariant)."""
    for n in (0, 10, 50, 99):
        probs, outcomes = _make_stationary(n) if n > 0 else ([], [])
        result = check_drift(probs, outcomes, window_size=100)
        assert result.status == STATUS_INSUFFICIENT_DATA
        assert result.stale is False, (
            f"stale-never-green violated: stale=True on n={n} (INSUFFICIENT_DATA)"
        )


# ---------------------------------------------------------------------------
# Test 5: no $ / roi / pnl keys in as_dict() output
# ---------------------------------------------------------------------------


def test_no_dollar_keys_in_dict():
    """as_dict() must not contain any dollar / roi / pnl related keys."""
    probs, outcomes = _make_stationary(600)
    result = check_drift(probs, outcomes, window_size=_WIN)
    d = result.as_dict()
    forbidden = {"roi", "pnl", "profit", "dollar", "edge", "ev", "expected_value"}
    keys_lower = {k.lower() for k in d.keys()}
    bad = keys_lower & forbidden
    assert not bad, f"Forbidden keys found in as_dict(): {bad}"
    # Also check window sub-dicts
    for w in d.get("windows", []):
        w_keys = {k.lower() for k in w.keys()}
        assert not (w_keys & forbidden), f"Forbidden keys in window dict: {w_keys & forbidden}"


# ---------------------------------------------------------------------------
# Test 6: windows field has correct count and bounds
# ---------------------------------------------------------------------------


def test_window_count_and_bounds():
    """Windows cover the input without overlap and in order."""
    probs, outcomes = _make_stationary(1000)
    result = check_drift(probs, outcomes, window_size=_WIN)
    assert len(result.windows) == 5  # 1000 / 200
    for i, w in enumerate(result.windows):
        assert w.window_index == i
        assert w.start == i * _WIN
        assert w.end == (i + 1) * _WIN
        assert w.n == _WIN
        assert 0.0 <= w.ece <= 1.0
        assert 0.0 <= w.brier <= 1.0


# ---------------------------------------------------------------------------
# Test 7: length mismatch raises
# ---------------------------------------------------------------------------


def test_length_mismatch_raises():
    """Mismatched probs/outcomes must raise ValueError."""
    with pytest.raises(ValueError):
        check_drift([0.5, 0.6], [1.0], window_size=1)


# ---------------------------------------------------------------------------
# Test 8: as_dict round-trip contains status and note
# ---------------------------------------------------------------------------


def test_as_dict_has_required_keys():
    """as_dict() must always include status, stale, note, n_windows."""
    probs, outcomes = _make_stationary(600)
    result = check_drift(probs, outcomes, window_size=_WIN)
    d = result.as_dict()
    for key in ("status", "stale", "offending_window_index",
                "baseline_ece", "baseline_brier", "n_windows", "windows", "note"):
        assert key in d, f"Missing key in as_dict(): {key}"
    assert "calibration != edge" in d["note"]
