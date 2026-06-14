"""tests.platform.test_sgp_pricer — Unit tests for scripts/platformkit/sgp_pricer.py.

All tests synthetic and fast (no network, no corpus).  Seeded RNG for reproducibility.
Python 3.9 compatible.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.platformkit.sgp_pricer import (  # noqa: E402
    _BANNED_WORDS, _HONEST_NOTE,
    jd_from_matrix, leg_over_total, leg_score_at_least, leg_side_win, price_parlay,
)
from scripts.platformkit.sim_framework import JointDistribution  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N = 40_000


def _pos_corr_jd(n: int = _N, seed: int = 42) -> JointDistribution:
    rng = np.random.default_rng(seed)
    base = rng.normal(5.0, 2.0, n)
    s = np.stack([np.clip(base + rng.normal(0, 0.5, n), 0, None),
                  np.clip(base + rng.normal(0, 0.5, n), 0, None)], axis=1)
    return JointDistribution(s, joint_quality="simulated")


def _neg_corr_jd(n: int = _N, seed: int = 42) -> JointDistribution:
    rng = np.random.default_rng(seed)
    a = rng.uniform(1.0, 9.0, n)
    b = np.clip(10.0 - a + rng.normal(0, 0.2, n), 0, None)
    return JointDistribution(np.stack([a, b], axis=1), joint_quality="simulated")


def _indep_jd(n: int = _N, seed: int = 42) -> JointDistribution:
    rng = np.random.default_rng(seed)
    s = np.stack([rng.normal(5.0, 2.0, n), rng.normal(5.0, 2.0, n)], axis=1)
    return JointDistribution(s, joint_quality="simulated")


# ---------------------------------------------------------------------------
# 1. jd_from_matrix — marginals reproduce PMF within MC tolerance
# ---------------------------------------------------------------------------

class TestJdFromMatrix:

    _P2x2 = np.array([[0.25, 0.25], [0.25, 0.25]])
    _P3x3: np.ndarray  # set below

    def setup_method(self) -> None:
        P = np.zeros((3, 3)); P[1, 1] = 0.6; P[0, 0] = 0.1; P[2, 2] = 0.1
        P[0, 2] = 0.1; P[2, 0] = 0.1
        self._P3x3 = P

    def test_uniform_row_marginal(self) -> None:
        jd = jd_from_matrix(self._P2x2, n_sims=80_000, seed=0)
        assert abs(float((jd._s[:, 0] == 0).mean()) - 0.5) < 0.02

    def test_uniform_col_marginal(self) -> None:
        jd = jd_from_matrix(self._P2x2, n_sims=80_000, seed=1)
        assert abs(float((jd._s[:, 1] == 0).mean()) - 0.5) < 0.02

    def test_peaked_dominant_cell(self) -> None:
        jd = jd_from_matrix(self._P3x3, n_sims=80_000, seed=2)
        p_11 = float(((jd._s[:, 0] == 1) & (jd._s[:, 1] == 1)).mean())
        assert abs(p_11 - 0.6) < 0.03

    def test_joint_quality_simulated(self) -> None:
        assert jd_from_matrix(self._P2x2, n_sims=100).joint_quality == "simulated"

    def test_output_shape(self) -> None:
        jd = jd_from_matrix(self._P3x3, n_sims=5000, seed=4)
        assert jd._s.shape == (5000, 2)

    def test_values_are_valid_indices(self) -> None:
        jd = jd_from_matrix(self._P3x3, n_sims=10_000, seed=5)
        assert set(jd._s[:, 0].astype(int)).issubset({0, 1, 2})
        assert set(jd._s[:, 1].astype(int)).issubset({0, 1, 2})

    def test_negative_P_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            jd_from_matrix(np.array([[-0.1, 0.5], [0.3, 0.3]]))

    def test_zero_mass_raises(self) -> None:
        with pytest.raises(ValueError, match="positive mass"):
            jd_from_matrix(np.zeros((3, 3)))

    def test_1d_raises(self) -> None:
        with pytest.raises(ValueError, match="2-D"):
            jd_from_matrix(np.array([0.5, 0.5]))


# ---------------------------------------------------------------------------
# 2. price_parlay — correlation direction, lift, and gating
# ---------------------------------------------------------------------------

class TestPriceParlay:

    def test_positive_lift_gt_1(self) -> None:
        r = price_parlay(_pos_corr_jd(), [lambda s: s[:, 0] > 6, lambda s: s[:, 1] > 6])
        assert r["lift"] > 1.0, f"lift={r['lift']:.4f}"
        assert r["correlation_sign"] == "positive"

    def test_negative_lift_lt_1(self) -> None:
        r = price_parlay(_neg_corr_jd(), [lambda s: s[:, 0] > 6, lambda s: s[:, 1] > 6])
        assert r["lift"] < 1.0, f"lift={r['lift']:.4f}"
        assert r["correlation_sign"] == "negative"

    def test_independent_lift_near_1(self) -> None:
        r = price_parlay(_indep_jd(), [lambda s: s[:, 0] > 5.5, lambda s: s[:, 1] > 5.5])
        assert 0.90 <= r["lift"] <= 1.10, f"lift={r['lift']:.4f}"

    def test_independent_jd_raises(self) -> None:
        s = np.random.default_rng(0).normal(0, 1, (1000, 2))
        jd = JointDistribution(s, joint_quality="independent")
        with pytest.raises(ValueError, match="joint_quality"):
            price_parlay(jd, [lambda x: x[:, 0] > 0])

    def test_empty_legs_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            price_parlay(_indep_jd(500), [])

    def test_n_legs_field(self) -> None:
        legs = [lambda s: s[:, 0] > 4, lambda s: s[:, 1] > 4, lambda s: s[:, 0] > 3]
        assert price_parlay(_indep_jd(500), legs)["n_legs"] == 3

    def test_fair_decimal_joint_is_reciprocal(self) -> None:
        r = price_parlay(_pos_corr_jd(2000), [lambda s: s[:, 0] > 5])
        if r["joint"] > 1e-9:
            assert abs(r["fair_decimal_joint"] - 1.0 / r["joint"]) < 1e-9

    def test_fair_decimal_independent_is_reciprocal(self) -> None:
        r = price_parlay(_indep_jd(2000), [lambda s: s[:, 0] > 4, lambda s: s[:, 1] > 3])
        if r["independent"] > 1e-9:
            assert abs(r["fair_decimal_independent"] - 1.0 / r["independent"]) < 1e-9

    def test_positive_corr_fair_joint_lt_fair_indep(self) -> None:
        """lift>1 -> joint>indep -> 1/joint < 1/indep (correlated parlay is 'cheaper')."""
        r = price_parlay(_pos_corr_jd(), [lambda s: s[:, 0] > 6, lambda s: s[:, 1] > 6])
        if r["lift"] > 1.02:
            assert r["fair_decimal_joint"] < r["fair_decimal_independent"]


# ---------------------------------------------------------------------------
# 3. Leg-builder helpers
# ---------------------------------------------------------------------------

class TestLegBuilders:

    _S = np.array([[1.0, 3.0], [5.0, 5.0], [8.0, 2.0]])

    def test_leg_over_total(self) -> None:
        # totals: 4, 10, 10 -> over 5: [F, T, T]
        assert list(leg_over_total(0, 1, 5.0)(self._S)) == [False, True, True]

    def test_leg_side_win_a(self) -> None:
        # col0 > col1: [1>3=F, 5>5=F, 8>2=T]
        assert list(leg_side_win(0, 1, "a")(self._S)) == [False, False, True]

    def test_leg_side_win_b(self) -> None:
        # col1 > col0: [3>1=T, 5>5=F, 2>8=F]
        assert list(leg_side_win(0, 1, "b")(self._S)) == [True, False, False]

    def test_leg_side_win_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="winner must be"):
            leg_side_win(0, 1, "x")

    def test_leg_score_at_least(self) -> None:
        # col0 >= 5: [1>=5=F, 5>=5=T, 8>=5=T]
        assert list(leg_score_at_least(0, 5.0)(self._S)) == [False, True, True]


# ---------------------------------------------------------------------------
# 4. Honest note — no banned words
# ---------------------------------------------------------------------------

class TestHonestNote:

    def test_no_banned_words_in_constant(self) -> None:
        lower = _HONEST_NOTE.lower()
        for w in _BANNED_WORDS:
            assert w not in lower, f"Banned word {w!r} in _HONEST_NOTE"

    def test_price_parlay_note_no_banned_words(self) -> None:
        r = price_parlay(_indep_jd(500), [lambda s: s[:, 0] > 4])
        lower = r["note"].lower()
        for w in _BANNED_WORDS:
            assert w not in lower, f"Banned word {w!r} in note"

    def test_note_is_nonempty_string(self) -> None:
        r = price_parlay(_indep_jd(500), [lambda s: s[:, 0] > 4])
        assert isinstance(r["note"], str) and len(r["note"]) > 20


# ---------------------------------------------------------------------------
# 5. Integration: jd_from_matrix + price_parlay round-trip
# ---------------------------------------------------------------------------

class TestIntegration:

    def _pmf(self) -> np.ndarray:
        P = np.array([[0.09, 0.07, 0.04, 0.01],
                      [0.14, 0.11, 0.06, 0.02],
                      [0.10, 0.08, 0.05, 0.02],
                      [0.05, 0.04, 0.03, 0.01]], dtype=float)
        return P / P.sum()

    def test_lift_is_valid_positive_finite(self) -> None:
        jd = jd_from_matrix(self._pmf(), n_sims=60_000, seed=99)
        r = price_parlay(jd, [leg_side_win(0, 1, "a"), leg_over_total(0, 1, 1.5)])
        assert r["lift"] > 0 and math.isfinite(r["lift"])
        assert r["correlation_sign"] in ("positive", "negative", "~independent")

    def test_positive_lift_pricing_consistency(self) -> None:
        """lift>1 => fair_joint < fair_indep (correlated parlay more accurate)."""
        jd = jd_from_matrix(self._pmf(), n_sims=60_000, seed=100)
        r = price_parlay(jd, [leg_side_win(0, 1, "a"), leg_over_total(0, 1, 1.5)])
        if r["lift"] > 1.02:
            assert r["fair_decimal_joint"] < r["fair_decimal_independent"]
        elif r["lift"] < 0.98:
            assert r["fair_decimal_joint"] > r["fair_decimal_independent"]
