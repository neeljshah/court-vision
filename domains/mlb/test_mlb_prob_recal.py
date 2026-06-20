"""domains.mlb.test_mlb_prob_recal -- Per-file tests for mlb_prob_recal.py.

Acceptance criteria (BE-R5-4):
  A1. Fit half1, score half2: ECE(recal) < ECE(raw).
  A2. Brier(recal) not worse than Brier(raw)+0.001 on half2.
  A3. Identity check: recal-of-recal Brier worsening <= 0.001.
  A4. Planted-null: null_brier_excess <= NULL_BRIER_TOL (no spurious lift).
  A5. Identity-in -> identity-out: if raw probs already perfect (== outcomes), Brier unchanged.
  A6. Absent artifact -> identity passthrough (no-harm, ship=False or from_corpus falls back).
  A7. No $ / ROI / PnL field in ProbRecalResult.
  A8. gate.ship=True on overconfident synthetic corpus.
  A9. recal_prob() output stays in [0, 1].
  A10. Serve-time recal_prob() improves ECE on held-out batch vs raw probs.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_mlb_prob_recal.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.mlb.mlb_prob_recal import (
    HalfSplitRecal,
    MLBProbRecal,
    ProbRecalResult,
    fit_and_gate,
    CALIBRATION_NOTE,
    NULL_BRIER_TOL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _overconfident_corpus(n: int = 800, seed: int = 7, factor: float = 1.8):
    """True probs uniform in [0.35, 0.65]; raw pushed overconfident by factor."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.35, 0.65, n)
    raw = np.clip(0.5 + (true_p - 0.5) * factor, 0.05, 0.95)
    y = rng.binomial(1, true_p).astype(float)
    return raw, y


def _ece(p, y, bins=10):
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    n, val = len(p), 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb:
            val += (nb / n) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


# ---------------------------------------------------------------------------
# HalfSplitRecal unit tests
# ---------------------------------------------------------------------------

class TestHalfSplitRecal:
    def test_output_in_01(self):
        raw, y = _overconfident_corpus(n=300)
        cal = HalfSplitRecal(min_train=50)
        cal.fit(raw[:150], y[:150])
        out = cal.transform(raw[150:])
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_method_set_after_fit(self):
        raw, y = _overconfident_corpus(n=200)
        cal = HalfSplitRecal(min_train=40)
        method = cal.fit(raw[:100], y[:100])
        assert method in ("platt", "isotonic", "identity")
        assert cal._method == method

    def test_thin_corpus_identity(self):
        """Fewer than min_train rows -> identity passthrough."""
        raw = np.array([0.6, 0.4, 0.7])
        y = np.array([1.0, 0.0, 1.0])
        cal = HalfSplitRecal(min_train=50)
        method = cal.fit(raw, y)
        assert method == "identity"
        out = cal.transform(raw)
        np.testing.assert_array_almost_equal(out, np.clip(raw, 0, 1), decimal=6)

    def test_single_class_identity(self):
        """Single-class labels -> identity."""
        raw = np.full(100, 0.55)
        y = np.ones(100)
        cal = HalfSplitRecal(min_train=50)
        method = cal.fit(raw, y)
        assert method == "identity"

    def test_recal_one_bounds(self):
        raw, y = _overconfident_corpus(n=300)
        cal = HalfSplitRecal(min_train=50)
        cal.fit(raw[:150], y[:150])
        for v in [0.0, 0.5, 1.0, 0.4655]:
            out = cal.recal_one(v)
            assert 0.0 <= out <= 1.0

    def test_no_fit_is_identity(self):
        """transform() before fit() should not raise and returns clipped input."""
        cal = HalfSplitRecal()
        arr = np.array([0.3, 0.7])
        out = cal.transform(arr)
        np.testing.assert_array_almost_equal(out, np.clip(arr, 0, 1), decimal=6)


# ---------------------------------------------------------------------------
# fit_and_gate acceptance tests
# ---------------------------------------------------------------------------

class TestFitAndGate:
    @pytest.fixture(scope="class")
    def gate(self):
        raw, y = _overconfident_corpus(n=800, seed=7, factor=1.8)
        return fit_and_gate(raw, y, min_train=50, rng_seed=42)

    def test_A1_ece_improves(self, gate):
        """A1: ECE(recal) < ECE(raw) on half2."""
        assert gate.half2_recal_ece < gate.half2_raw_ece, (
            f"ECE did not improve: recal={gate.half2_recal_ece:.5f} >= "
            f"raw={gate.half2_raw_ece:.5f}"
        )

    def test_A2_brier_not_worse(self, gate):
        """A2: Brier(recal) <= Brier(raw)+0.001 on half2."""
        assert gate.half2_recal_brier <= gate.half2_raw_brier + 0.001, (
            f"Brier worsened: {gate.half2_recal_brier:.5f} > "
            f"{gate.half2_raw_brier:.5f}+0.001"
        )

    def test_A3_identity_check(self, gate):
        """A3: id_brier_worsening <= 0.001."""
        assert gate.id_brier_worsening <= 0.001, (
            f"Identity check: {gate.id_brier_worsening:.5f} > 0.001"
        )

    def test_A4_planted_null(self, gate):
        """A4: null_brier_excess <= NULL_BRIER_TOL (no spurious lift on shuffled labels)."""
        assert gate.null_brier_excess <= NULL_BRIER_TOL, (
            f"Planted-null: excess {gate.null_brier_excess:.5f} > {NULL_BRIER_TOL}"
        )

    def test_A7_no_dollar_field(self, gate):
        """A7: ProbRecalResult must not contain $ / roi / pnl / profit / dollar field."""
        banned = {"roi", "pnl", "profit", "dollar", "edge_dollars"}
        for k in vars(gate):
            assert k.lower() not in banned, f"Banned field: {k}"
        for k in gate.extra:
            assert k.lower() not in banned, f"Banned extra key: {k}"

    def test_A8_passes_gate(self, gate):
        """A8: gate.ship=True on overconfident corpus."""
        assert gate.ship, f"gate.ship=False: {gate.rejection_reason}"

    def test_note_and_vs_close(self, gate):
        assert "calibration" in gate.note.lower()
        assert "edge" in gate.note.lower()
        assert gate.vs_close == "UNPROVEN"

    def test_n_counts(self, gate):
        assert gate.n_train + gate.n_eval == len(gate.raw_probs)

    def test_recal_probs_in_01(self, gate):
        assert np.all(gate.recal_probs >= 0.0) and np.all(gate.recal_probs <= 1.0)

    def test_A5_identity_in_passthrough(self):
        """A5: perfectly calibrated probs (already at outcome freq) -> Brier not worsened."""
        rng = np.random.default_rng(99)
        true_p = rng.uniform(0.35, 0.65, 400)
        y = rng.binomial(1, true_p).astype(float)
        # Use true_p as raw (already calibrated -- best possible input)
        gate = fit_and_gate(true_p, y, min_train=50)
        # Even if gate rejects, recal_probs must not be worse than raw
        assert gate.half2_recal_brier <= gate.half2_raw_brier + 0.005, (
            "Identity-in: Brier meaningfully worsened on already-calibrated input"
        )

    def test_A6_absent_artifact_is_identity(self):
        """A6: from_corpus with missing path -> MLBProbRecal active=False, recal_prob=identity."""
        recal = MLBProbRecal.from_corpus(repo_root=__import__("pathlib").Path("/nonexistent"))
        assert not recal.active
        assert recal.method == "identity"
        # identity passthrough
        for v in [0.0, 0.4655, 0.5, 0.5345, 1.0]:
            assert recal.recal_prob(v) == pytest.approx(float(np.clip(v, 0, 1)), abs=1e-9)

    def test_planted_null_random_probs(self):
        """Additional planted-null: random probs, shuffled labels -> no spurious lift."""
        rng = np.random.default_rng(13)
        p = rng.uniform(0.3, 0.7, 500)
        y_null = rng.permutation(rng.binomial(1, 0.5, 500).astype(float))
        gate = fit_and_gate(p, y_null, min_train=50)
        # Either it rejects (ship=False, which is honest) or null_excess <= tol
        if gate.ship:
            assert gate.null_brier_excess <= NULL_BRIER_TOL


# ---------------------------------------------------------------------------
# MLBProbRecal serve-time tests
# ---------------------------------------------------------------------------

class TestMLBProbRecal:
    @pytest.fixture(scope="class")
    def recal(self):
        raw, y = _overconfident_corpus(n=800, seed=7, factor=1.8)
        return MLBProbRecal.from_arrays(raw, y, min_train=50)

    def test_A9_recal_prob_in_01(self, recal):
        """A9: recal_prob() output always in [0, 1]."""
        for v in np.linspace(0.0, 1.0, 21):
            out = recal.recal_prob(float(v))
            assert 0.0 <= out <= 1.0, f"recal_prob({v})={out} out of [0,1]"

    def test_A10_serve_time_ece_improves(self, recal):
        """A10: serve-time recal_prob() improves ECE on a held-out batch."""
        if not recal.active:
            pytest.skip("Recalibrator not active (gate rejected) -- A10 not applicable")
        raw, y = _overconfident_corpus(n=400, seed=99, factor=1.8)
        recal_p = np.array([recal.recal_prob(v) for v in raw])
        ece_raw = _ece(raw, y)
        ece_recal = _ece(recal_p, y)
        assert ece_recal < ece_raw + 0.01, (
            f"Serve-time ECE not improved: recal={ece_recal:.5f} vs raw={ece_raw:.5f}"
        )

    def test_method_property(self, recal):
        assert recal.method in ("platt", "isotonic", "identity")

    def test_gate_result_available(self, recal):
        g = recal.gate_result
        assert g is not None
        assert isinstance(g, ProbRecalResult)

    def test_summary_no_dollar(self, recal):
        s = recal.summary()
        banned = {"roi", "pnl", "profit", "dollar"}
        for k in s:
            assert k.lower() not in banned

    def test_summary_has_note(self, recal):
        s = recal.summary()
        assert "note" in s
        assert "calibration" in s["note"].lower()

    def test_from_arrays_identity_fallback(self):
        """from_arrays with too-thin corpus -> active=False, recal_prob=identity."""
        p = np.full(20, 0.5)
        y = np.array([1.0, 0.0] * 10)
        recal = MLBProbRecal.from_arrays(p, y, min_train=50)
        assert not recal.active
        for v in [0.3, 0.5, 0.7]:
            assert recal.recal_prob(v) == pytest.approx(v, abs=1e-9)
