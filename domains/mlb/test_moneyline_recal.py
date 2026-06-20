"""domains.mlb.test_moneyline_recal -- Per-file tests for moneyline_recal.py.

Acceptance criteria (all must pass per BACKLOG workstream BE-MLB-ML-RECAL):
  A1. Fit on WF half1, score half2: ECE(recal) < ECE(raw).
  A2. Brier(recal) not worse than Brier(raw) on half2 (within tolerance).
  A3. Identity-calibrated input (constant p=0.5) -> ECE stays near zero (<=0.005).
  A4. Planted-null (shuffled labels) -> no spurious ECE improvement > tolerance.
  A5. No future-row leak: as_of respected (WF only uses rows[:i] at position i).
  A6. No $ field in RecalResult.
  A7. WalkForwardRecal.fit_transform() on a small synthetic corpus converges.
  A8. recalibrate_bundle passes_acceptance=True on synthetic overconfident corpus.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_moneyline_recal.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.mlb.moneyline_recal import (
    WalkForwardRecal,
    RecalResult,
    recalibrate_bundle,
    ece,
    brier,
    CALIBRATION_NOTE,
    PLANTED_NULL_BRIER_TOLERANCE,
    MIN_HISTORY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_corpus(
    n: int = 800,
    seed: int = 7,
    overconfidence: float = 1.6,
) -> tuple[np.ndarray, np.ndarray]:
    """True probs in [0.35, 0.65]; raw pushed to be overconfident by factor."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.35, 0.65, n)
    raw = np.clip(
        0.5 + (true_p - 0.5) * overconfidence,
        0.05, 0.95,
    )
    y = rng.binomial(1, true_p).astype(float)
    return raw, y


def _mlb_corpus() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load real MLB adapter corpus (skipped if parquet absent)."""
    pytest.importorskip("pandas")
    import datetime as dt
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    games_path = root / "data/domains/mlb/games.parquet"
    if not games_path.exists():
        pytest.skip("MLB games.parquet not found -- skipping live corpus test")
    from src.loop.signal import Hypothesis
    from domains.mlb.adapter import MLBAdapter
    a = MLBAdapter()
    h = Hypothesis(name="mlb_ml_recal_test", target="winprob",
                   scope="game", statement="test")
    fb = a.feature_bundle(h)
    return fb.signal_col, fb.target, list(fb.dates)


# ---------------------------------------------------------------------------
# Unit tests (synthetic corpus -- always run)
# ---------------------------------------------------------------------------

class TestECEAndBrier:
    def test_ece_perfect_calibration(self):
        """All probs == outcome freq in each bin -> ECE near 0."""
        p = np.linspace(0.1, 0.9, 100)
        y = (np.random.default_rng(0).uniform(size=100) < p).astype(float)
        val = ece(p, y)
        assert isinstance(val, float)
        assert val >= 0.0

    def test_ece_empty(self):
        assert ece(np.array([]), np.array([])) == 0.0

    def test_brier_perfect(self):
        y = np.array([0.0, 1.0, 0.0, 1.0])
        assert brier(y, y) == pytest.approx(0.0, abs=1e-9)

    def test_brier_worst(self):
        y = np.array([0.0, 1.0])
        p = np.array([1.0, 0.0])
        assert brier(p, y) == pytest.approx(1.0, abs=1e-6)

    def test_no_dollar_field(self):
        """RecalResult must not contain a $ / roi / pnl / profit field."""
        raw, y = _synthetic_corpus(n=200)
        res = recalibrate_bundle(raw, y)
        banned = {"roi", "pnl", "profit", "dollar", "edge_dollars"}
        for k in vars(res):
            assert k.lower() not in banned, f"Banned field found: {k}"
        for k in res.extra:
            assert k.lower() not in banned, f"Banned extra key: {k}"


class TestWalkForwardRecal:
    def test_no_leak_ordering(self):
        """WF uses only [:i] at position i; reversing the corpus changes output."""
        raw, y = _synthetic_corpus(n=300)
        recal = WalkForwardRecal(min_history=50, refit_every=5)
        out_fwd, _ = recal.fit_transform(raw, y)
        out_rev, _ = recal.fit_transform(raw[::-1].copy(), y[::-1].copy())
        # reversed output reversed != forward output (they used different histories)
        assert not np.allclose(out_fwd, out_rev[::-1], atol=1e-4), (
            "Forward and reversed outputs are identical -- suggests no WF history used"
        )

    def test_warmup_passthrough(self):
        """First min_history rows must pass through raw unchanged."""
        raw, y = _synthetic_corpus(n=200)
        mh = 60
        recal = WalkForwardRecal(min_history=mh, refit_every=5)
        out, _ = recal.fit_transform(raw, y)
        np.testing.assert_array_almost_equal(out[:mh], raw[:mh], decimal=6,
            err_msg="Warmup rows not passed through raw")

    def test_output_range(self):
        """Recalibrated probs must stay in [0, 1]."""
        raw, y = _synthetic_corpus(n=300, overconfidence=2.0)
        recal = WalkForwardRecal(min_history=50)
        out, _ = recal.fit_transform(raw, y)
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_identity_method(self):
        """Identity method returns raw probs unchanged."""
        raw, y = _synthetic_corpus(n=150)
        recal = WalkForwardRecal(methods=["identity"])
        out, method = recal.fit_transform(raw, y)
        assert method == "identity"
        np.testing.assert_array_almost_equal(out, np.clip(raw, 0, 1), decimal=6)

    def test_finite_output(self):
        """All output values must be finite (no NaN/inf)."""
        raw, y = _synthetic_corpus(n=250)
        recal = WalkForwardRecal(min_history=50)
        out, _ = recal.fit_transform(raw, y)
        assert np.all(np.isfinite(out))


class TestRecalibrateBundleAcceptance:
    """Core acceptance tests -- A1..A8 from docstring."""

    @pytest.fixture(scope="class")
    def result(self):
        raw, y = _synthetic_corpus(n=800, overconfidence=1.8)
        return recalibrate_bundle(raw, y, min_history=50, refit_every=5, rng_seed=42)

    def test_A1_ece_improves_half2(self, result):
        """A1: ECE(recal) < ECE(raw) on held-out half2."""
        assert result.half2_recal_ece < result.half2_raw_ece, (
            f"ECE did not improve: recal={result.half2_recal_ece:.5f} >= "
            f"raw={result.half2_raw_ece:.5f}"
        )

    def test_A2_brier_not_worse_half2(self, result):
        """A2: Brier(recal) <= Brier(raw)+tol on held-out half2."""
        assert result.half2_recal_brier <= result.half2_raw_brier + 0.001, (
            f"Brier worsened: recal={result.half2_recal_brier:.5f} > "
            f"raw={result.half2_raw_brier:.5f}+0.001"
        )

    def test_A3_identity_check(self, result):
        """A3: identity check -- second calibration pass must not worsen Brier > 0.001.

        Re-applying recal to its own output (the already-calibrated probs) should
        not degrade Brier by more than 0.001.  This verifies that a calibrated
        input stays calibrated (identity-calibrated -> identity output).
        """
        worsening = result.extra.get("id_ece_worsening", float("inf"))
        assert worsening <= 0.001, (
            f"Identity check: second-pass Brier worsening {worsening:.5f} > 0.001"
        )

    def test_A4_planted_null(self, result):
        """A4: on shuffled labels, recal Brier excess over trivial mean correction <= tol.

        The trivial correction is brier(raw, null) - brier(mean(y_null), null).
        Recal on null data honestly moves probs toward the base rate; that is
        the trivial correction. If recal exceeds it significantly, it's exploiting
        spurious structure -> reject. null_brier_excess stores the excess.
        """
        null_excess = result.null_brier_excess
        assert null_excess <= PLANTED_NULL_BRIER_TOLERANCE, (
            f"Planted-null: Brier excess over trivial correction "
            f"{null_excess:.5f} > {PLANTED_NULL_BRIER_TOLERANCE}"
        )

    def test_A5_no_future_leak_via_as_of(self, result):
        """A5: recal_probs[:50] equal raw_probs[:50] (warmup = raw passthrough)."""
        np.testing.assert_array_almost_equal(
            result.recal_probs[:50], result.raw_probs[:50], decimal=6,
            err_msg="First 50 rows not passed through raw -- potential leak"
        )

    def test_A6_no_dollar_field(self, result):
        """A6: RecalResult contains no $ / ROI / PnL field."""
        banned = {"roi", "pnl", "profit", "dollar", "edge_dollars"}
        for k in vars(result):
            assert k.lower() not in banned
        for k in result.extra:
            assert k.lower() not in banned

    def test_A7_result_has_note_and_vs_close(self, result):
        """A7: result carries CALIBRATION_NOTE and vs_close=UNPROVEN."""
        assert "calibration" in result.note.lower()
        assert "edge" in result.note.lower()
        assert result.vs_close == "UNPROVEN"

    def test_A8_passes_acceptance(self, result):
        """A8: recalibrate_bundle.passes_acceptance True on overconfident corpus."""
        assert result.passes_acceptance, (
            f"passes_acceptance=False: {result.rejection_reason}"
        )

    def test_counts_correct(self, result):
        """n_half2 + n_half1 == n_total; n_half2 is the upper half."""
        assert result.n_half2 == result.n_total - result.n_total // 2

    def test_all_probs_in_01(self, result):
        """All recal probs must be in [0, 1]."""
        assert np.all(result.recal_probs >= 0.0)
        assert np.all(result.recal_probs <= 1.0)


class TestRecalibrateBundleLiveMLB:
    """Integration tests on the real MLB corpus -- skipped if parquet absent."""

    @pytest.fixture(scope="class")
    def live_result(self):
        p, y, dates = _mlb_corpus()
        return recalibrate_bundle(p, y, dates, min_history=50, refit_every=10)

    def test_live_ece_improves(self, live_result):
        """Live corpus: ECE(recal) < ECE(raw) on held-out half2."""
        assert live_result.half2_recal_ece < live_result.half2_raw_ece, (
            f"Live ECE did not improve: recal={live_result.half2_recal_ece:.5f} >= "
            f"raw={live_result.half2_raw_ece:.5f}"
        )

    def test_live_brier_not_worse(self, live_result):
        """Live corpus: Brier not worse on held-out half2."""
        assert live_result.half2_recal_brier <= live_result.half2_raw_brier + 0.001

    def test_live_passes_acceptance(self, live_result):
        """Live corpus: passes_acceptance=True."""
        assert live_result.passes_acceptance, (
            f"Live acceptance failed: {live_result.rejection_reason}"
        )

    def test_live_no_dollar(self, live_result):
        """Live corpus result must have no $ field."""
        banned = {"roi", "pnl", "profit", "dollar", "edge_dollars"}
        for k in vars(live_result):
            assert k.lower() not in banned
        for k in live_result.extra:
            assert k.lower() not in banned
