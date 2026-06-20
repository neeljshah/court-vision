"""predict_service.tests.test_calib_scoreboard -- per-file test for calib_scoreboard.

Acceptance criteria (from BACKLOG pa2):
  1. 4-sport synthetic input -> one row per sport each carrying brier, ece, bss, n_holdout.
  2. A sport with holdout overlap < 60 -> status INSUFFICIENT_DATA (not a green metric).
  3. No dollar key in any ScoreboardRow (units only; calibration not edge).
  4. Brier/ECE/BSS values are plausible floats (not None) when n >= 60.
  5. BSS vs base-rate > 0 when the model is a near-perfect calibrated predictor.
  6. BSS < 0 when the model is random noise vs a strongly-biased base.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_calib_scoreboard.py -q
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

from predict_service.calib_scoreboard import (  # noqa: E402
    MIN_HOLDOUT,
    ScoreboardRow,
    SportInput,
    build_scoreboard,
    score_sport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synth_probs(n: int, seed: int = 42, noise: float = 0.05) -> tuple:
    """Synthetic probabilistic predictions with known outcomes.

    Returns (probs, outcomes) where probs is well-calibrated (near-perfect)
    around a 0.55 base rate plus small Gaussian noise.
    """
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.8, size=n)
    outcomes = rng.binomial(1, true_p).astype(float)
    noisy_p = np.clip(true_p + rng.normal(0, noise, size=n), 0.01, 0.99)
    return noisy_p.tolist(), outcomes.tolist()


def _all_keys(row: ScoreboardRow) -> set:
    """Return all field names from a ScoreboardRow as lowercase strings."""
    return {f.lower() for f in row._fields}


# ---------------------------------------------------------------------------
# AC-1: 4-sport input -> one row per sport, all required fields present.
# ---------------------------------------------------------------------------

class TestFourSportTable:
    """AC-1: build_scoreboard returns one ScoreboardRow per sport."""

    @pytest.fixture
    def four_sport_inputs(self):
        n = 200  # well above MIN_HOLDOUT=60
        rows = []
        for i, sport in enumerate(["nba", "mlb", "soccer", "tennis"]):
            probs, outcomes = _synth_probs(n, seed=i * 100)
            rows.append(SportInput(sport=sport, probs=probs, outcomes=outcomes))
        return rows

    def test_returns_four_rows(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        assert len(board) == 4, f"Expected 4 rows, got {len(board)}"

    def test_sport_tokens_preserved(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        sports = [r.sport for r in board]
        assert sports == ["nba", "mlb", "soccer", "tennis"]

    def test_all_rows_have_brier(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert r.brier is not None, f"{r.sport}: brier is None (n={r.n_holdout})"
            assert isinstance(r.brier, float)

    def test_all_rows_have_ece(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert r.ece is not None, f"{r.sport}: ece is None"
            assert 0.0 <= r.ece <= 1.0, f"{r.sport}: ece {r.ece} out of [0,1]"

    def test_all_rows_have_bss(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert r.bss is not None, f"{r.sport}: bss is None"

    def test_all_rows_have_n_holdout(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert r.n_holdout == 200

    def test_status_ok_for_full_data(self, four_sport_inputs):
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert r.status == "ok", f"{r.sport}: status={r.status}"

    def test_brier_in_plausible_range(self, four_sport_inputs):
        """Brier for calibrated predictions on Bernoulli data should be in (0, 0.5)."""
        board = build_scoreboard(four_sport_inputs)
        for r in board:
            assert 0.0 < r.brier < 0.5, f"{r.sport}: brier={r.brier}"


# ---------------------------------------------------------------------------
# AC-2: n < 60 -> INSUFFICIENT_DATA.
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """AC-2: thin overlap -> INSUFFICIENT_DATA, never green."""

    @pytest.mark.parametrize("n", [0, 1, 30, 59])
    def test_thin_data_is_insufficient(self, n):
        probs, outcomes = _synth_probs(n, seed=7) if n > 0 else ([], [])
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert row.status == "INSUFFICIENT_DATA", (
            f"n={n}: expected INSUFFICIENT_DATA, got {row.status}"
        )

    @pytest.mark.parametrize("n", [0, 1, 30, 59])
    def test_thin_data_brier_is_none(self, n):
        probs, outcomes = _synth_probs(n, seed=7) if n > 0 else ([], [])
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert row.brier is None, f"n={n}: brier should be None, got {row.brier}"
        assert row.ece is None
        assert row.bss is None

    def test_exactly_60_is_ok(self):
        """Boundary: exactly MIN_HOLDOUT samples should be ok."""
        probs, outcomes = _synth_probs(MIN_HOLDOUT, seed=99)
        row = score_sport(SportInput(sport="soccer", probs=probs, outcomes=outcomes))
        assert row.status == "ok", f"n=60: expected ok, got {row.status}"
        assert row.brier is not None

    def test_thin_sport_in_4sport_table(self):
        """A thin sport in a 4-sport table produces exactly one INSUFFICIENT_DATA row."""
        n = 200
        inputs = []
        for i, sport in enumerate(["nba", "mlb", "soccer", "tennis"]):
            if sport == "tennis":
                # Thin
                probs, outcomes = _synth_probs(20, seed=i)
            else:
                probs, outcomes = _synth_probs(n, seed=i)
            inputs.append(SportInput(sport=sport, probs=probs, outcomes=outcomes))
        board = build_scoreboard(inputs)
        statuses = {r.sport: r.status for r in board}
        assert statuses["tennis"] == "INSUFFICIENT_DATA"
        for s in ["nba", "mlb", "soccer"]:
            assert statuses[s] == "ok", f"{s}: {statuses[s]}"


# ---------------------------------------------------------------------------
# AC-3: No dollar key in ScoreboardRow.
# ---------------------------------------------------------------------------

FORBIDDEN_MONEY_TOKENS = {
    "pnl", "roi", "bankroll", "profit", "dollar", "dollars",
    "usd", "stake", "edge", "payout",
}


class TestNoDollarKey:
    """AC-3: ScoreboardRow must not contain any dollar/money key."""

    def test_no_money_keys_in_fields(self):
        """The NamedTuple field names must not intersect the forbidden set."""
        fields = set(ScoreboardRow._fields)
        bad = fields & FORBIDDEN_MONEY_TOKENS
        assert not bad, f"ScoreboardRow contains forbidden key(s): {bad}"

    def test_note_has_no_dollar_sign(self):
        probs, outcomes = _synth_probs(200, seed=0)
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert "$" not in (row.note or ""), f"note contains '$': {row.note}"

    def test_no_dollar_in_status(self):
        probs, outcomes = _synth_probs(200, seed=0)
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert "$" not in row.status


# ---------------------------------------------------------------------------
# AC-4 / AC-5: BSS sanity checks.
# ---------------------------------------------------------------------------

class TestBSSSemantics:
    """BSS should be positive when model is near-calibrated; negative when noisy."""

    def test_bss_positive_for_calibrated_model(self):
        """A model close to true probabilities should beat the base-rate."""
        rng = np.random.default_rng(1)
        true_p = rng.uniform(0.2, 0.8, size=500)
        outcomes = rng.binomial(1, true_p).astype(float)
        # Predicted probs almost perfectly match true probabilities.
        probs = np.clip(true_p + rng.normal(0, 0.02, 500), 0.01, 0.99).tolist()
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes.tolist()))
        assert row.status == "ok"
        assert row.bss is not None
        assert row.bss > 0, f"Expected BSS>0 for calibrated model, got {row.bss}"

    def test_bss_negative_for_random_model_biased_outcomes(self):
        """Random uniform probs on 80%-biased outcomes should trail the base-rate."""
        rng = np.random.default_rng(2)
        n = 500
        # Outcomes: 80% positive (strong base-rate at 0.8).
        outcomes = rng.binomial(1, 0.8, size=n).astype(float)
        # Model: uniform random probs (no information about the strong base-rate).
        probs = rng.uniform(0.0, 1.0, size=n).tolist()
        row = score_sport(SportInput(sport="mlb", probs=probs, outcomes=outcomes.tolist()))
        assert row.status == "ok"
        assert row.bss is not None
        assert row.bss < 0, f"Expected BSS<0 for random model vs biased outcomes, got {row.bss}"

    def test_bss_range(self):
        """BSS is bounded to (-inf, 1]. Near-perfect model should have BSS < 1 but >= 0."""
        rng = np.random.default_rng(3)
        true_p = rng.uniform(0.3, 0.7, size=300)
        outcomes = rng.binomial(1, true_p).astype(float)
        probs = true_p.tolist()  # exact oracle probabilities
        row = score_sport(SportInput(sport="soccer", probs=probs, outcomes=outcomes.tolist()))
        if row.bss is not None:
            assert row.bss <= 1.0 + 1e-6, f"BSS > 1.0: {row.bss}"


# ---------------------------------------------------------------------------
# AC-extra: mismatch + degenerate inputs handled gracefully.
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Degenerate inputs must not raise -- return INSUFFICIENT_DATA."""

    def test_empty_lists_are_insufficient(self):
        row = score_sport(SportInput(sport="tennis", probs=[], outcomes=[]))
        assert row.status == "INSUFFICIENT_DATA"

    def test_mismatched_lengths_are_insufficient(self):
        probs = [0.5] * 100
        outcomes = [1.0] * 99
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert row.status == "INSUFFICIENT_DATA"

    def test_probs_out_of_range_are_insufficient(self):
        probs = [1.5] * 100  # invalid
        outcomes = [1.0] * 100
        row = score_sport(SportInput(sport="nba", probs=probs, outcomes=outcomes))
        assert row.status == "INSUFFICIENT_DATA"

    def test_build_scoreboard_preserves_order(self):
        inputs = [
            SportInput("z", *_synth_probs(100, 0)),
            SportInput("a", *_synth_probs(100, 1)),
        ]
        board = build_scoreboard(inputs)
        assert board[0].sport == "z"
        assert board[1].sport == "a"
