"""4-way bitwise-equivalence pin: kernel.validation.proof_metrics vs the 3 sport copies.

valid PRE-swap (copies-vs-kernel bitwise equality) AND POST-swap (shims re-export the
kernel objects → identity ⇒ equality); permanent drift-regression guard.

This test passing PRE-swap is what authorizes the later shim conversion.
Any mismatch = a real divergence to report — do NOT adjust the kernel to match
a copy without escalating; the copies are supposed to be byte-identical.

Name mapping note:
  The sport copies expose ``_devig2`` (underscore-private API).
  The kernel exposes ``devig2`` (public API, no underscore).
  Comparison: ``K.devig2(...) == T._devig2(...)`` etc.
  All other functions share names across K / T / S / M.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kernel.validation import proof_metrics as K
from scripts.platformkit.proof_tennis import proof_metrics as T
from scripts.platformkit.proof_soccer import proof_metrics as S
from scripts.platformkit.proof_mlb import proof_metrics as M


# ---------------------------------------------------------------------------
# Shared seeded test vectors (built once, reused across all function tests)
# ---------------------------------------------------------------------------

RNG = np.random.RandomState(0)
N = 500

# General probability + outcome vectors
_PROBS = RNG.uniform(0.0, 1.0, N)
_OUTCOMES = RNG.randint(0, 2, N).astype(float)

# Seeded monotone-ish train/eval for isotonic_calibrate
_RNG_ISO = np.random.RandomState(0)
_TRAIN_P = np.sort(_RNG_ISO.uniform(0.1, 0.9, 300))
_TRAIN_Y = (_TRAIN_P > 0.5).astype(float)
_EVAL_P = _RNG_ISO.uniform(0.1, 0.9, 100)

# Seeded decimal-odds arrays for CLV invariants (some open==close pairs)
_RNG_CLV = np.random.RandomState(0)
_OPEN_A = _RNG_CLV.uniform(1.5, 3.0, N)
_OPEN_B = _RNG_CLV.uniform(1.5, 3.0, N)
# close: sometimes equal to open, sometimes shifted
_SHIFT_A = _RNG_CLV.uniform(-0.3, 0.3, N)
_SHIFT_B = _RNG_CLV.uniform(-0.3, 0.3, N)
_CLOSE_A = np.clip(_OPEN_A + _SHIFT_A, 1.01, None)
_CLOSE_B = np.clip(_OPEN_B + _SHIFT_B, 1.01, None)
# Force some rows to open==close
for _i in range(0, N, 7):
    _CLOSE_A[_i] = _OPEN_A[_i]
    _CLOSE_B[_i] = _OPEN_B[_i]

# Edge-case scalars for devig2
_DEVIG_CASES = [
    (2.0, 2.0),        # equal odds
    (1.8, 2.1),        # asymmetric
    (1.01, 50.0),      # very lopsided
    (1.0, 2.0),        # price_a <= 1.0 → fallback
    (0.9, 2.0),        # price_a < 1.0 → fallback
    (2.0, 1.0),        # price_b <= 1.0 → fallback
    (1.5, 3.0),        # standard
]

# Edge-case probability/outcome arrays
_EDGE_PROBS_PERFECT = np.array([1.0, 0.0, 1.0, 0.0])
_EDGE_OUTCOMES_PERFECT = np.array([1.0, 0.0, 1.0, 0.0])
_EDGE_PROBS_EMPTY = np.array([], dtype=float)
_EDGE_OUTCOMES_EMPTY = np.array([], dtype=float)
_EDGE_PROBS_SINGLE = np.array([0.7])
_EDGE_OUTCOMES_SINGLE = np.array([1.0])

# open==close scenario for invariant (a)
_SAME_PRICES_A = np.full(20, 2.0)
_SAME_PRICES_B = np.full(20, 2.0)


# ---------------------------------------------------------------------------
# Helper: assert exact float equality on a scalar result
# ---------------------------------------------------------------------------

def _assert_exact(k_val: float, sport_val: float, label: str) -> None:
    assert k_val == sport_val, (
        f"EXACT FLOAT MISMATCH [{label}]: kernel={k_val!r}  sport={sport_val!r}"
    )


def _assert_exact_array(k_arr: np.ndarray, s_arr: np.ndarray, label: str) -> None:
    assert k_arr.shape == s_arr.shape, (
        f"SHAPE MISMATCH [{label}]: kernel={k_arr.shape}  sport={s_arr.shape}"
    )
    mismatches = np.where(k_arr != s_arr)[0]
    assert len(mismatches) == 0, (
        f"EXACT ARRAY MISMATCH [{label}]: {len(mismatches)} differing element(s); "
        f"first at index {mismatches[0]}: kernel={k_arr[mismatches[0]]!r}  sport={s_arr[mismatches[0]]!r}"
    )


# ---------------------------------------------------------------------------
# brier — 4-way exact equality
# ---------------------------------------------------------------------------


class TestBrierEquivalence:
    """K.brier == T.brier == S.brier == M.brier on every input."""

    def _check(self, probs: np.ndarray, outcomes: np.ndarray, tag: str) -> None:
        k = K.brier(probs, outcomes)
        _assert_exact(k, T.brier(probs, outcomes), f"brier/tennis/{tag}")
        _assert_exact(k, S.brier(probs, outcomes), f"brier/soccer/{tag}")
        _assert_exact(k, M.brier(probs, outcomes), f"brier/mlb/{tag}")

    def test_seeded_random(self) -> None:
        self._check(_PROBS, _OUTCOMES, "seeded_n500")

    def test_perfect_forecast(self) -> None:
        self._check(_EDGE_PROBS_PERFECT, _EDGE_OUTCOMES_PERFECT, "perfect")

    def test_single_row(self) -> None:
        self._check(_EDGE_PROBS_SINGLE, _EDGE_OUTCOMES_SINGLE, "single_row")


# ---------------------------------------------------------------------------
# ece — 4-way exact equality
# ---------------------------------------------------------------------------


class TestEceEquivalence:
    """K.ece == T.ece == S.ece == M.ece on every input."""

    def _check(self, probs: np.ndarray, outcomes: np.ndarray, tag: str) -> None:
        k = K.ece(probs, outcomes)
        _assert_exact(k, T.ece(probs, outcomes), f"ece/tennis/{tag}")
        _assert_exact(k, S.ece(probs, outcomes), f"ece/soccer/{tag}")
        _assert_exact(k, M.ece(probs, outcomes), f"ece/mlb/{tag}")

    def test_seeded_random(self) -> None:
        self._check(_PROBS, _OUTCOMES, "seeded_n500")

    def test_perfect_forecast(self) -> None:
        self._check(_EDGE_PROBS_PERFECT, _EDGE_OUTCOMES_PERFECT, "perfect")

    def test_empty_array(self) -> None:
        self._check(_EDGE_PROBS_EMPTY, _EDGE_OUTCOMES_EMPTY, "empty")

    def test_single_row(self) -> None:
        self._check(_EDGE_PROBS_SINGLE, _EDGE_OUTCOMES_SINGLE, "single_row")


# ---------------------------------------------------------------------------
# reliability_slope — 4-way exact equality
# ---------------------------------------------------------------------------


class TestReliabilitySlopeEquivalence:
    """K.reliability_slope == T.reliability_slope == S.reliability_slope == M.reliability_slope."""

    def _check(self, probs: np.ndarray, outcomes: np.ndarray, tag: str) -> None:
        k = K.reliability_slope(probs, outcomes)
        kt = T.reliability_slope(probs, outcomes)
        ks = S.reliability_slope(probs, outcomes)
        km = M.reliability_slope(probs, outcomes)
        # nan == nan is False in Python; handle NaN specially
        if math.isnan(k):
            assert math.isnan(kt), f"reliability_slope/tennis/{tag}: kernel=nan but sport={kt!r}"
            assert math.isnan(ks), f"reliability_slope/soccer/{tag}: kernel=nan but sport={ks!r}"
            assert math.isnan(km), f"reliability_slope/mlb/{tag}: kernel=nan but sport={km!r}"
        else:
            _assert_exact(k, kt, f"reliability_slope/tennis/{tag}")
            _assert_exact(k, ks, f"reliability_slope/soccer/{tag}")
            _assert_exact(k, km, f"reliability_slope/mlb/{tag}")

    def test_seeded_random(self) -> None:
        self._check(_PROBS, _OUTCOMES, "seeded_n500")

    def test_single_value_returns_nan(self) -> None:
        # All same prob → 1 bin populated → nan
        p = np.full(50, 0.5)
        y = np.array([1.0, 0.0] * 25)
        self._check(p, y, "single_bin_nan")

    def test_perfect_forecast(self) -> None:
        self._check(_EDGE_PROBS_PERFECT, _EDGE_OUTCOMES_PERFECT, "perfect")


# ---------------------------------------------------------------------------
# isotonic_calibrate — 4-way exact array equality
# ---------------------------------------------------------------------------


class TestIsotonicCalibrateEquivalence:
    """K.isotonic_calibrate == T.isotonic_calibrate == S.isotonic_calibrate == M.isotonic_calibrate."""

    def _check(
        self,
        train_p: np.ndarray,
        train_y: np.ndarray,
        eval_p: np.ndarray,
        tag: str,
    ) -> None:
        k = K.isotonic_calibrate(train_p, train_y, eval_p)
        _assert_exact_array(k, T.isotonic_calibrate(train_p, train_y, eval_p), f"isotonic/tennis/{tag}")
        _assert_exact_array(k, S.isotonic_calibrate(train_p, train_y, eval_p), f"isotonic/soccer/{tag}")
        _assert_exact_array(k, M.isotonic_calibrate(train_p, train_y, eval_p), f"isotonic/mlb/{tag}")

    def test_seeded_monotone(self) -> None:
        self._check(_TRAIN_P, _TRAIN_Y, _EVAL_P, "seeded_monotone")

    def test_single_eval_row(self) -> None:
        self._check(_TRAIN_P, _TRAIN_Y, np.array([0.5]), "single_eval")

    def test_nan_bearing_eval(self) -> None:
        # eval_p with out-of-bounds value — clip handles it
        eval_with_nan = np.array([0.0, 0.5, 1.0])
        self._check(_TRAIN_P, _TRAIN_Y, eval_with_nan, "oob_eval")


# ---------------------------------------------------------------------------
# devig2 — 4-way exact equality (K.devig2 vs T/S/M._devig2)
# ---------------------------------------------------------------------------


class TestDevig2Equivalence:
    """K.devig2 == T._devig2 == S._devig2 == M._devig2 on every input."""

    def _check(self, price_a: float, price_b: float) -> None:
        k_pa, k_pb = K.devig2(price_a, price_b)
        t_pa, t_pb = T._devig2(price_a, price_b)
        s_pa, s_pb = S._devig2(price_a, price_b)
        m_pa, m_pb = M._devig2(price_a, price_b)
        tag = f"devig2({price_a},{price_b})"
        assert k_pa == t_pa and k_pb == t_pb, f"MISMATCH tennis {tag}: K={k_pa,k_pb}  T={t_pa,t_pb}"
        assert k_pa == s_pa and k_pb == s_pb, f"MISMATCH soccer {tag}: K={k_pa,k_pb}  S={s_pa,s_pb}"
        assert k_pa == m_pa and k_pb == m_pb, f"MISMATCH mlb   {tag}: K={k_pa,k_pb}  M={m_pa,m_pb}"

    @pytest.mark.parametrize("price_a,price_b", _DEVIG_CASES)
    def test_edge_cases(self, price_a: float, price_b: float) -> None:
        self._check(price_a, price_b)

    def test_seeded_random_batch(self) -> None:
        rng = np.random.RandomState(0)
        for _ in range(200):
            pa = float(rng.uniform(1.01, 5.0))
            pb = float(rng.uniform(1.01, 5.0))
            self._check(pa, pb)


# ---------------------------------------------------------------------------
# clv_sign_invariants — 4-way exact equality on all dict values
# ---------------------------------------------------------------------------


class TestClvSignInvariantsEquivalence:
    """K.clv_sign_invariants == T/S/M.clv_sign_invariants on every input."""

    _KEYS = ["inv_a_ok", "inv_b_ok", "max_close_vs_itself",
              "mean_clv_a", "mean_clv_b", "anti_sym_gap"]

    def _check(
        self,
        open_a: np.ndarray,
        open_b: np.ndarray,
        close_a: np.ndarray,
        close_b: np.ndarray,
        tag: str,
    ) -> None:
        k_res = K.clv_sign_invariants(open_a, open_b, close_a, close_b)
        t_res = T.clv_sign_invariants(open_a, open_b, close_a, close_b)
        s_res = S.clv_sign_invariants(open_a, open_b, close_a, close_b)
        m_res = M.clv_sign_invariants(open_a, open_b, close_a, close_b)

        for key in self._KEYS:
            k_v = k_res[key]
            for sport_label, sport_res in [("tennis", t_res), ("soccer", s_res), ("mlb", m_res)]:
                sv = sport_res[key]
                assert k_v == sv, (
                    f"clv_sign_invariants[{key}] MISMATCH [{sport_label}/{tag}]: "
                    f"kernel={k_v!r}  sport={sv!r}"
                )

    def test_seeded_random(self) -> None:
        self._check(_OPEN_A, _OPEN_B, _CLOSE_A, _CLOSE_B, "seeded_n500")

    def test_open_equals_close(self) -> None:
        self._check(_SAME_PRICES_A, _SAME_PRICES_B, _SAME_PRICES_A, _SAME_PRICES_B, "open_eq_close")

    def test_single_row(self) -> None:
        oa = np.array([2.0])
        ob = np.array([1.8])
        ca = np.array([2.1])
        cb = np.array([1.75])
        self._check(oa, ob, ca, cb, "single_row")

    def test_all_prices_below_one(self) -> None:
        # All prices <= 1.0 → devig2 returns 0.5 → no movement → all zeros
        oa = np.array([0.9, 1.0, 0.5])
        ob = np.array([0.8, 1.0, 0.6])
        ca = np.array([0.9, 1.0, 0.5])
        cb = np.array([0.8, 1.0, 0.6])
        self._check(oa, ob, ca, cb, "below_one_prices")
