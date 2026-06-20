"""predict_service.tests.test_recal_pregame_guards -- guard tests for recal_pregame.

Acceptance criteria covered here (split from test_recal_pregame.py for LOC cap):
  3. Empty / thin data (n < min_history) -> INSUFFICIENT_DATA passthrough;
     calibrated_probs == raw; no crash.
  6. Length mismatch -> INSUFFICIENT_DATA.
  extra. chosen_method is valid; n_total / n_eval are non-negative.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_recal_pregame_guards.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so the module import resolves cleanly.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.recal_pregame import (  # noqa: E402
    MIN_HISTORY,
    recal_pregame,
)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _overconfident_probs(n: int, seed: int = 42) -> tuple:
    """Systematically overconfident (miscalibrated) probs for guard tests."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.7, n)
    raw = np.where(
        true_p >= 0.5,
        0.5 + (true_p - 0.5) * 2.2,
        0.5 - (0.5 - true_p) * 2.2,
    )
    raw = np.clip(raw, 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    return raw.tolist(), outcomes.tolist()


# ---------------------------------------------------------------------------
# AC-3: Empty / thin data -> INSUFFICIENT_DATA passthrough.
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """AC-3: thin or empty data returns INSUFFICIENT_DATA without crashing."""

    @pytest.mark.parametrize("n", [0, 1, 10, 49, 50])
    def test_thin_is_insufficient(self, n):
        """n <= MIN_HISTORY -> INSUFFICIENT_DATA (0 eval rows when n==MIN_HISTORY)."""
        if n > 0:
            rng = np.random.default_rng(n)
            raw = rng.uniform(0.3, 0.7, n).tolist()
            outcomes = rng.binomial(1, np.asarray(raw)).astype(float).tolist()
        else:
            raw, outcomes = [], []
        result = recal_pregame(raw, outcomes, min_history=MIN_HISTORY)
        assert result.status == "INSUFFICIENT_DATA", (
            f"n={n}: expected INSUFFICIENT_DATA, got {result.status}"
        )

    @pytest.mark.parametrize("n", [0, 1, 10, 49, 50])
    def test_thin_ece_is_none(self, n):
        """Thin/boundary input -> raw_ece and recal_ece must be None."""
        if n > 0:
            rng = np.random.default_rng(n + 100)
            raw = rng.uniform(0.3, 0.7, n).tolist()
            outcomes = rng.binomial(1, np.asarray(raw)).astype(float).tolist()
        else:
            raw, outcomes = [], []
        result = recal_pregame(raw, outcomes)
        assert result.raw_ece is None
        assert result.recal_ece is None

    @pytest.mark.parametrize("n", [0, 1, 49, 50])
    def test_thin_calibrated_probs_passthrough(self, n):
        """Thin: calibrated_probs is passthrough (clip of raw), not modified."""
        if n > 0:
            rng = np.random.default_rng(n + 200)
            raw = rng.uniform(0.1, 0.9, n).tolist()
            outcomes = rng.binomial(1, np.asarray(raw)).astype(float).tolist()
        else:
            raw, outcomes = [], []
        result = recal_pregame(raw, outcomes)
        expected = np.clip(np.asarray(raw, dtype=float), 0.0, 1.0)
        np.testing.assert_array_almost_equal(
            result.calibrated_probs, expected, decimal=10,
            err_msg="Thin data: calibrated_probs must be raw passthrough",
        )

    def test_exactly_min_history_is_insufficient(self):
        """n == min_history: eval window has 0 rows -> INSUFFICIENT_DATA, no crash."""
        N = MIN_HISTORY
        raw, outcomes = _overconfident_probs(N, seed=77)
        result = recal_pregame(raw, outcomes, min_history=MIN_HISTORY)
        # With n == min_history, the entire sequence is the warmup window;
        # there are 0 eval rows. We treat this as INSUFFICIENT_DATA (guard
        # also prevents a ValueError in select_calibrator's tied-list logic).
        assert result.status == "INSUFFICIENT_DATA", (
            f"n=min_history: expected INSUFFICIENT_DATA, got {result.status}"
        )
        assert result.n_total == N
        assert result.n_eval == 0


# ---------------------------------------------------------------------------
# AC-6: Length mismatch -> INSUFFICIENT_DATA, no crash.
# ---------------------------------------------------------------------------

class TestLengthMismatch:
    """AC-6: mismatched probs/outcomes lengths -> INSUFFICIENT_DATA."""

    def test_mismatch_is_insufficient(self):
        raw = [0.5] * 200
        outcomes = [1.0] * 199
        result = recal_pregame(raw, outcomes)
        assert result.status == "INSUFFICIENT_DATA"

    def test_mismatch_ece_is_none(self):
        raw = [0.6] * 100
        outcomes = [0.0] * 80
        result = recal_pregame(raw, outcomes)
        assert result.raw_ece is None
        assert result.recal_ece is None

    def test_mismatch_n_total_is_zero(self):
        """n_total should be 0 for a length-mismatch case."""
        result = recal_pregame([0.5] * 10, [1.0] * 5)
        assert result.n_total == 0


# ---------------------------------------------------------------------------
# AC-extra: chosen_method is a valid string; n_total / n_eval are non-negative.
# ---------------------------------------------------------------------------

class TestResultInvariants:
    """RecalResult invariants hold for any valid input."""

    _VALID_METHODS = {"identity", "temperature", "platt", "beta", "isotonic"}

    def test_chosen_method_is_valid(self):
        N = 300
        raw, outcomes = _overconfident_probs(N, seed=8)
        result = recal_pregame(raw, outcomes)
        assert result.chosen_method in self._VALID_METHODS, (
            f"Unknown chosen_method: {result.chosen_method}"
        )

    def test_n_total_matches_input(self):
        N = 250
        raw, outcomes = _overconfident_probs(N, seed=9)
        result = recal_pregame(raw, outcomes)
        assert result.n_total == N

    def test_n_eval_non_negative(self):
        N = 200
        raw, outcomes = _overconfident_probs(N, seed=10)
        result = recal_pregame(raw, outcomes)
        assert result.n_eval >= 0

    def test_n_eval_at_most_n_total(self):
        N = 200
        raw, outcomes = _overconfident_probs(N, seed=14)
        result = recal_pregame(raw, outcomes)
        assert result.n_eval <= result.n_total

    def test_status_values(self):
        """status is one of the two documented values."""
        for n, seed in [(0, 0), (30, 1), (200, 2)]:
            if n > 0:
                raw, outcomes = _overconfident_probs(n, seed=seed)
            else:
                raw, outcomes = [], []
            result = recal_pregame(raw, outcomes)
            assert result.status in ("ok", "INSUFFICIENT_DATA"), (
                f"n={n}: unexpected status '{result.status}'"
            )

    def test_custom_min_history(self):
        """Custom min_history=100 should work: n=150 should produce ok status."""
        N = 150
        raw, outcomes = _overconfident_probs(N, seed=15)
        result = recal_pregame(raw, outcomes, min_history=100)
        assert result.status == "ok", (
            f"n=150 with min_history=100: expected ok, got {result.status}"
        )
        assert result.n_total == N

    def test_custom_min_history_thin(self):
        """n < custom min_history -> INSUFFICIENT_DATA."""
        N = 80
        raw, outcomes = _overconfident_probs(N, seed=16)
        result = recal_pregame(raw, outcomes, min_history=100)
        assert result.status == "INSUFFICIENT_DATA"
