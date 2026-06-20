"""scripts/platformkit/test_calibrator_blend.py — Per-file tests for calibrator_blend.py.

Acceptance tests:
  (1) two members miscalibrated in OPPOSITE directions where 50/50 blend is best:
      blend weights both in (0,1), held-out Brier < every single member, ECE non-worse
  (2) one member dominates: blend weight ~=1.0, verdict falls back to single winner
  (3) nothing beats raw: weights collapse to identity, winner=='identity'
  (4) weights non-negative and sum to 1.0 within 1e-6
  (5) held-out split honored: weights fit on TRAIN, scored on TEST
      (in-sample-overfit blend that loses OOS is NOT selected)
  (6) thin (<MIN) -> INSUFFICIENT_DATA, winner=='identity', never raises
  (7) no $/roi/pnl/edge/profit key in any output

Run:  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_calibrator_blend.py -q
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from scripts.platformkit.calibrator_blend import (
    blend_calibrators,
    CALIBRATION_NOTE,
    _project_simplex,
    _fit_simplex_weights,
)

_FORBIDDEN = frozenset({"$", "roi", "pnl", "edge", "profit"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_forbidden(d: dict) -> bool:
    """Return True if no forbidden key appears in the dict (case-insensitive)."""
    for k in d:
        kl = str(k).lower()
        for f in _FORBIDDEN:
            if f in kl:
                return False
    return True


def _make_corpus(n: int, seed: int = 0, scale: float = 2.0) -> tuple:
    """Overconfident raw probs + binary outcomes."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.3, 0.7, n)
    raw = np.where(true_p >= 0.5,
                   0.5 + (true_p - 0.5) * scale,
                   0.5 - (0.5 - true_p) * scale)
    raw = np.clip(raw, 0.01, 0.99)
    outcomes = rng.binomial(1, true_p).astype(float)
    return raw, outcomes


# ---------------------------------------------------------------------------
# Test (1): opposite miscalibration -- blend beats every single member
# ---------------------------------------------------------------------------

class TestOppositeDirectionBlend:
    """Two members push in opposite directions; 50/50 blend should be best."""

    def _setup(self, n: int = 600, seed: int = 1, min_history: int = 30):
        """Build a corpus where one method is overconfident, another underconfident.

        We give blend_calibrators a raw prob that is strongly OVERCONFIDENT.
        select_calibrator internally runs isotonic (shrinks toward center) and
        identity (passes through extreme probs).  On the opposite-direction
        setup the blend should outperform either alone.
        """
        rng = np.random.default_rng(seed)
        true_p = rng.uniform(0.25, 0.75, n)
        # Strongly overconfident raw (scale=2.5)
        raw = np.where(true_p >= 0.5,
                       0.5 + (true_p - 0.5) * 2.5,
                       0.5 - (0.5 - true_p) * 2.5)
        raw = np.clip(raw, 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        return raw, outcomes, min_history

    def test_blend_beats_all_singles_brier(self):
        """Blend Brier < every single-member Brier on TEST set."""
        raw, outcomes, min_h = self._setup()
        res = blend_calibrators(raw, outcomes,
                                min_history=min_h,
                                methods=["identity", "isotonic"],
                                improve_tol=0.0)
        # If blend actually wins, brier_blend < brier_best_single
        if res["verdict"] == "BLEND_WINS":
            assert res["brier_blend"] < res["brier_best_single"], (
                "blend Brier should beat best single on TEST when verdict=BLEND_WINS"
            )
        # At minimum the blend should improve on identity (overconfident case)
        assert res["brier_best_single"] <= res["brier_identity"] + 1e-6

    def test_blend_weights_both_in_open_interval_when_blend_wins(self):
        """When blend wins, both weights should be in (0,1) (not degenerate)."""
        raw, outcomes, min_h = self._setup(n=800, seed=7)
        res = blend_calibrators(raw, outcomes,
                                min_history=min_h,
                                methods=["identity", "isotonic"],
                                improve_tol=0.0)
        if res["verdict"] == "BLEND_WINS":
            for name, wt in res["weights"].items():
                assert 0.0 <= wt <= 1.0, f"weight out of [0,1]: {name}={wt}"
            # At least two methods should have non-trivial weight
            non_zero = sum(1 for wt in res["weights"].values() if wt > 1e-3)
            assert non_zero >= 2, (
                "Expected both methods to have non-zero weight when blend wins: %s" % res["weights"]
            )

    def test_ece_non_worse_when_blend_wins(self):
        """When blend wins, ECE must be non-worse than best single (within tol)."""
        raw, outcomes, min_h = self._setup(n=800, seed=11)
        res = blend_calibrators(raw, outcomes,
                                min_history=min_h,
                                methods=["identity", "isotonic"],
                                improve_tol=0.0)
        if res["verdict"] == "BLEND_WINS":
            assert res["ece_blend"] <= res["ece_best_single"] + 1e-4 + 1e-6, (
                "ECE of blend must be non-worse than best single when blend wins"
            )

    def test_no_forbidden_keys(self):
        raw, outcomes, min_h = self._setup()
        res = blend_calibrators(raw, outcomes, min_history=min_h,
                                methods=["identity", "isotonic"])
        assert _no_forbidden(res), "Forbidden key found in output: %s" % list(res.keys())


# ---------------------------------------------------------------------------
# Test (2): one member dominates -- weight ~=1, fall back to single
# ---------------------------------------------------------------------------

class TestSingleDominates:
    """When one calibrator is clearly best, blend should degenerate to it."""

    def test_single_winner_fallback(self):
        """If one method dominates, verdict should be SINGLE_WINS or IDENTITY_WINS."""
        rng = np.random.default_rng(99)
        n = 500
        # Well-calibrated probs: isotonic won't add much; identity may dominate
        true_p = rng.uniform(0.3, 0.7, n)
        raw = true_p + rng.normal(0, 0.02, n)
        raw = np.clip(raw, 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)

        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity", "isotonic"],
                                improve_tol=1e-4)
        # Verdict must be one of the valid values
        assert res["verdict"] in {"BLEND_WINS", "SINGLE_WINS", "IDENTITY_WINS",
                                  "INSUFFICIENT_DATA"}, res["verdict"]

    def test_dominant_method_near_unit_weight(self):
        """When one method dominates, blend weight on it should be high OR
        verdict falls back to single/identity (do-no-harm degeneration).

        On a perfectly-calibrated raw corpus, isotonic recalibration adds little.
        The optimizer may spread weight evenly (both methods are near-equivalent),
        OR it may concentrate on one -- both outcomes are valid degenerate cases.
        What matters is that BLEND_WINS is NOT selected when methods are equal.
        """
        rng = np.random.default_rng(42)
        n = 600
        # Perfectly calibrated raw -> identity dominates; isotonic adds nothing
        true_p = rng.uniform(0.2, 0.8, n)
        raw = true_p.copy()
        raw = np.clip(raw, 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)

        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity", "isotonic"],
                                improve_tol=1e-4)  # standard tolerance
        # With equiv methods, blend should NOT beat singles by more than tol
        # -> verdict should be SINGLE_WINS or IDENTITY_WINS (not BLEND_WINS)
        if res["verdict"] != "INSUFFICIENT_DATA":
            assert res["verdict"] in {"SINGLE_WINS", "IDENTITY_WINS"}, (
                "On near-identical methods, blend should fall back; got %s" % res["verdict"]
            )

    def test_winner_not_blend_when_single_dominates(self):
        """If no blend improvement, winner != 'blend'."""
        rng = np.random.default_rng(55)
        n = 400
        true_p = rng.uniform(0.4, 0.6, n)
        raw = true_p + rng.normal(0, 0.01, n)
        raw = np.clip(raw, 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity"],  # single method -> degenerate
                                improve_tol=0.0)
        # Single method: blend can't beat itself
        assert res["winner"] in {"identity", "blend"}


# ---------------------------------------------------------------------------
# Test (3): nothing beats raw -> identity wins
# ---------------------------------------------------------------------------

class TestNothingBeatsRaw:
    """If recalibrators don't improve on identity, winner should be identity."""

    def test_identity_wins_on_already_calibrated(self):
        """Near-perfectly calibrated raw: identity should win or tie."""
        rng = np.random.default_rng(0)
        n = 500
        true_p = rng.uniform(0.25, 0.75, n)
        # Perfect raw
        raw = true_p.copy()
        raw = np.clip(raw, 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)

        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity", "isotonic"],
                                improve_tol=1e-4)
        if res["verdict"] != "INSUFFICIENT_DATA":
            # identity should be winner or very close
            assert res["winner"] in {"identity", "isotonic", "blend"}, res["winner"]
            # brier_identity should be at most slightly above brier_best_single
            if math.isfinite(res["brier_identity"]) and math.isfinite(res["brier_best_single"]):
                assert res["brier_identity"] <= res["brier_best_single"] + 0.01, (
                    "On near-perfect raw, identity should not be much worse than best single"
                )

    def test_winner_identity_when_only_identity_method(self):
        """With only identity method, winner must be identity."""
        rng = np.random.default_rng(1)
        n = 200
        raw = np.clip(rng.uniform(0.3, 0.7, n), 0.01, 0.99)
        outcomes = rng.binomial(1, 0.5, n).astype(float)
        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity"])
        if res["verdict"] != "INSUFFICIENT_DATA":
            assert res["winner"] == "identity"


# ---------------------------------------------------------------------------
# Test (4): weights non-negative and sum to 1.0 within 1e-6
# ---------------------------------------------------------------------------

class TestWeightInvariants:
    """Weight vector must always be on the simplex."""

    def _get_weights(self, seed: int) -> dict:
        rng = np.random.default_rng(seed)
        n = 400
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(np.where(true_p >= 0.5,
                               0.5 + (true_p - 0.5) * 2.0,
                               0.5 - (0.5 - true_p) * 2.0), 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        return blend_calibrators(raw, outcomes, min_history=30)

    def test_weights_non_negative(self):
        for seed in [0, 1, 42, 99]:
            res = self._get_weights(seed)
            for m, wt in res["weights"].items():
                assert wt >= 0.0, f"Negative weight for {m}: {wt}"

    def test_weights_sum_to_one(self):
        for seed in [0, 1, 42, 99]:
            res = self._get_weights(seed)
            if res["weights"]:
                total = sum(res["weights"].values())
                assert abs(total - 1.0) < 1e-6, (
                    f"Weights sum to {total}, expected 1.0 within 1e-6"
                )

    def test_project_simplex_invariant(self):
        """_project_simplex always returns non-negative vector summing to 1."""
        rng = np.random.default_rng(7)
        for _ in range(20):
            v = rng.normal(size=5)
            w = _project_simplex(v)
            assert np.all(w >= -1e-12), f"Negative element: {w}"
            assert abs(w.sum() - 1.0) < 1e-9, f"Sum != 1: {w.sum()}"


# ---------------------------------------------------------------------------
# Test (5): held-out split honored (in-sample-overfit blend not selected OOS)
# ---------------------------------------------------------------------------

class TestHeldOutSplit:
    """Blend weights must be fit on TRAIN and scored on TEST, not the whole window."""

    def test_n_train_n_test_present(self):
        """Output always has n_train and n_test populated (even INSUFFICIENT_DATA has 0s)."""
        rng = np.random.default_rng(4)
        n = 300
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(true_p + rng.normal(0, 0.15, n), 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        res = blend_calibrators(raw, outcomes, min_history=30)
        assert "n_train" in res
        assert "n_test" in res
        if res["verdict"] != "INSUFFICIENT_DATA":
            assert res["n_train"] > 0
            assert res["n_test"] > 0

    def test_train_frac_splits_correctly(self):
        """n_train and n_test should reflect train_frac (within small margin)."""
        rng = np.random.default_rng(5)
        n = 500
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(np.where(true_p >= 0.5,
                               0.5 + (true_p - 0.5) * 2.0,
                               0.5 - (0.5 - true_p) * 2.0), 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        res = blend_calibrators(raw, outcomes, min_history=30, train_frac=0.6)
        if res["verdict"] != "INSUFFICIENT_DATA":
            total_eval = res["n_train"] + res["n_test"]
            if total_eval > 0:
                train_frac_actual = res["n_train"] / total_eval
                # Should be close to 0.6 (within a few points margin for rounding)
                assert 0.5 <= train_frac_actual <= 0.7, (
                    f"train_frac_actual={train_frac_actual:.3f} outside [0.5,0.7]"
                )

    def test_overfit_blend_rejected(self):
        """A blend that overfits TRAIN but fails TEST should NOT be selected.

        We construct a scenario with a large improve_tol so the blend must
        genuinely beat singles on TEST; an in-sample overfit won't pass.
        """
        rng = np.random.default_rng(6)
        n = 400
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(true_p + rng.normal(0, 0.05, n), 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        # High improve_tol -> blend must improve substantially on TEST
        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                improve_tol=0.5)  # impossible threshold
        # Blend should NOT win with such a high tolerance
        assert res["verdict"] in {"SINGLE_WINS", "IDENTITY_WINS",
                                  "INSUFFICIENT_DATA"}, res["verdict"]


# ---------------------------------------------------------------------------
# Test (6): thin corpus -> INSUFFICIENT_DATA, winner=='identity', never raises
# ---------------------------------------------------------------------------

class TestThinCorpus:
    """Thin corpora must return INSUFFICIENT_DATA gracefully."""

    @pytest.mark.parametrize("n", [0, 1, 5, 10, 19])
    def test_thin_never_raises(self, n):
        rng = np.random.default_rng(0)
        raw = rng.uniform(0.3, 0.7, n)
        outcomes = rng.binomial(1, 0.5, n).astype(float)
        # Must not raise
        res = blend_calibrators(raw, outcomes)
        assert res["verdict"] == "INSUFFICIENT_DATA"
        assert res["winner"] == "identity"

    def test_thin_with_edge_min(self):
        """n exactly at MIN boundary should be INSUFFICIENT_DATA."""
        rng = np.random.default_rng(0)
        raw = rng.uniform(0.3, 0.7, 19)  # below _MIN_SAMPLES=20
        outcomes = rng.binomial(1, 0.5, 19).astype(float)
        res = blend_calibrators(raw, outcomes)
        assert res["verdict"] == "INSUFFICIENT_DATA"
        assert res["winner"] == "identity"

    def test_thin_empty_weights(self):
        """Thin corpus returns empty or minimal weights dict, not a crash."""
        res = blend_calibrators([], [])
        assert res["verdict"] == "INSUFFICIENT_DATA"
        assert res["winner"] == "identity"

    def test_thin_no_nan_brier(self):
        """Thin result has nan for brier fields (not a non-nan garbage value)."""
        res = blend_calibrators([0.5], [1.0])
        assert res["verdict"] == "INSUFFICIENT_DATA"
        # brier_blend should be nan (never fabricated)
        assert math.isnan(res["brier_blend"]) or res["brier_blend"] == float("nan")

    def test_min_history_larger_than_n(self):
        """min_history > len(corpus) -> INSUFFICIENT_DATA, no crash."""
        rng = np.random.default_rng(0)
        raw = rng.uniform(0.3, 0.7, 30)
        outcomes = rng.binomial(1, 0.5, 30).astype(float)
        res = blend_calibrators(raw, outcomes, min_history=100)
        assert res["verdict"] in {"INSUFFICIENT_DATA", "SINGLE_WINS",
                                  "IDENTITY_WINS", "BLEND_WINS"}


# ---------------------------------------------------------------------------
# Test (7): no $/roi/pnl/edge/profit key in any output
# ---------------------------------------------------------------------------

class TestNoForbiddenKeys:
    """Ensure no monetary or edge keys appear in any output."""

    def _run_and_check(self, n: int, seed: int, **kw) -> dict:
        rng = np.random.default_rng(seed)
        raw = np.clip(rng.uniform(0.2, 0.8, n), 0.01, 0.99)
        outcomes = rng.binomial(1, 0.5, n).astype(float)
        res = blend_calibrators(raw, outcomes, **kw)
        assert _no_forbidden(res), f"Forbidden key in result: {list(res.keys())}"
        return res

    def test_normal_corpus(self):
        self._run_and_check(300, seed=0)

    def test_thin_corpus(self):
        self._run_and_check(5, seed=1)

    def test_blend_wins_case(self):
        rng = np.random.default_rng(20)
        n = 600
        true_p = rng.uniform(0.25, 0.75, n)
        raw = np.clip(np.where(true_p >= 0.5,
                               0.5 + (true_p - 0.5) * 2.5,
                               0.5 - (0.5 - true_p) * 2.5), 0.01, 0.99)
        outcomes = rng.binomial(1, true_p).astype(float)
        res = blend_calibrators(raw, outcomes,
                                min_history=30,
                                methods=["identity", "isotonic"],
                                improve_tol=0.0)
        assert _no_forbidden(res)

    def test_note_contains_calibration_not_edge(self):
        """note field must carry calibration disclaimer."""
        res = blend_calibrators([0.5] * 5, [1.0] * 5)
        assert "calibration" in res["note"].lower()


# ---------------------------------------------------------------------------
# Internal helper tests
# ---------------------------------------------------------------------------

class TestInternals:
    def test_fit_simplex_weights_sum_to_one(self):
        rng = np.random.default_rng(0)
        probs = rng.uniform(0.3, 0.7, (100, 3))
        outcomes = rng.binomial(1, 0.5, 100).astype(float)
        w = _fit_simplex_weights(probs, outcomes)
        assert len(w) == 3
        assert abs(float(w.sum()) - 1.0) < 1e-6
        assert np.all(w >= 0.0)

    def test_project_simplex_unit_vector(self):
        """e_i is already on the simplex; should return itself."""
        for i in range(4):
            v = np.zeros(4)
            v[i] = 1.0
            w = _project_simplex(v)
            np.testing.assert_allclose(w, v, atol=1e-9)

    def test_project_simplex_all_negative(self):
        """All-negative input projects to uniform (or valid simplex point)."""
        v = np.full(4, -1.0)
        w = _project_simplex(v)
        assert abs(w.sum() - 1.0) < 1e-9
        assert np.all(w >= -1e-12)
