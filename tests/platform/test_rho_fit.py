"""tests.platform.test_rho_fit — Tests for domains.soccer.rho_fit.

Verifies:
1. tau correction gives valid factors and degrades to independence at rho=0.
2. fit_rho on synthetic data returns a value in bounds.
3. NO future leak: rho[i] is computed using strictly match indices 0..i-1.
4. Warmup invariant: first `refit_every` matches get rho=0.

HONEST: calibration improvement only; no edge claimed.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from domains.soccer.rho_fit import (
    dc_neg_log_likelihood,
    fit_rho,
    tau,
    walk_forward_rho,
)


# ---------------------------------------------------------------------------
# 1. tau correction tests
# ---------------------------------------------------------------------------

class TestTauCorrection:
    def test_tau_zero_rho_is_one_everywhere(self):
        """At rho=0, all tau factors equal 1.0 (independence)."""
        for x, y in [(0, 0), (0, 1), (1, 0), (1, 1), (2, 3), (0, 2)]:
            assert tau(x, y, lam=1.5, mu=1.2, rho=0.0) == pytest.approx(1.0)

    def test_tau_cells_correct_formulas(self):
        """Verify DC tau formulas for each low-score cell."""
        lam, mu, rho = 1.3, 1.1, -0.1
        assert tau(0, 0, lam, mu, rho) == pytest.approx(1.0 - lam * mu * rho)
        assert tau(0, 1, lam, mu, rho) == pytest.approx(1.0 + lam * rho)
        assert tau(1, 0, lam, mu, rho) == pytest.approx(1.0 + mu * rho)
        assert tau(1, 1, lam, mu, rho) == pytest.approx(1.0 - rho)

    def test_tau_high_score_cells_are_one(self):
        """For x>1 or y>1, tau=1 (no DC correction outside 2x2 block)."""
        for x, y in [(2, 0), (0, 2), (2, 2), (3, 1), (5, 4)]:
            assert tau(x, y, lam=1.5, mu=1.2, rho=-0.1) == pytest.approx(1.0)

    def test_tau_negative_rho_inflates_zero_zero(self):
        """Negative rho inflates tau(0,0) > 1 (inflates 0-0 probability)."""
        # tau(0,0) = 1 - lam*mu*rho; with rho<0 => 1 - lam*mu*(neg) = 1 + positive > 1
        t = tau(0, 0, lam=1.4, mu=1.2, rho=-0.1)
        assert t > 1.0

    def test_tau_negative_rho_inflates_one_one(self):
        """Negative rho inflates tau(1,1) > 1 (inflates 1-1 probability)."""
        t = tau(1, 1, lam=1.4, mu=1.2, rho=-0.1)
        assert t > 1.0, f"Expected tau(1,1) > 1 for rho<0, got {t}"

    def test_tau_positive_probability_constraint(self):
        """For rho in [-0.2, 0.0] and typical lambda values, tau >= 0."""
        lam, mu = 1.5, 1.2
        for rho in [-0.2, -0.1, -0.05, 0.0]:
            for x, y in [(0, 0), (0, 1), (1, 0), (1, 1)]:
                assert tau(x, y, lam, mu, rho) >= 0.0, \
                    f"tau({x},{y}) negative at rho={rho}"


# ---------------------------------------------------------------------------
# 2. fit_rho on synthetic data
# ---------------------------------------------------------------------------

class TestFitRhoSynthetic:
    def _make_history(self, n: int = 500, rho: float = -0.1, seed: int = 42) -> List[Tuple[float, float, int, int]]:
        """Generate synthetic DC-distributed (lam_h, lam_a, h, a) records."""
        rng = np.random.default_rng(seed)
        history = []
        for _ in range(n):
            lh = rng.uniform(0.8, 2.0)
            la = rng.uniform(0.6, 1.6)
            h = int(rng.poisson(lh))
            a = int(rng.poisson(la))
            history.append((lh, la, h, a))
        return history

    def test_fit_rho_returns_in_bounds(self):
        """fit_rho output is always within the specified bounds."""
        history = self._make_history(n=400, rho=-0.1)
        bounds = (-0.2, 0.0)
        rho = fit_rho(history, bounds=bounds)
        assert bounds[0] <= rho <= bounds[1], f"rho={rho} out of bounds {bounds}"

    def test_fit_rho_empty_history_returns_zero(self):
        """Empty history returns rho=0.0 (safe default)."""
        rho = fit_rho([])
        assert rho == pytest.approx(0.0)

    def test_fit_rho_is_float(self):
        """fit_rho always returns a float."""
        history = self._make_history(n=50)
        rho = fit_rho(history)
        assert isinstance(rho, float)

    def test_neg_log_likelihood_rho0_is_finite(self):
        """NLL at rho=0 is finite and computable."""
        history = self._make_history(n=100)
        nll = dc_neg_log_likelihood(0.0, history)
        assert math.isfinite(nll)

    def test_neg_log_likelihood_decreases_with_fit(self):
        """Fitted rho should have NLL <= NLL at rho=0 (optimizer succeeded)."""
        history = self._make_history(n=300)
        nll_zero = dc_neg_log_likelihood(0.0, history)
        rho_fit = fit_rho(history)
        nll_fit = dc_neg_log_likelihood(rho_fit, history)
        # Fitted rho should have lower or equal NLL vs rho=0
        assert nll_fit <= nll_zero + 1e-6, \
            f"Fitted NLL {nll_fit:.4f} > baseline NLL {nll_zero:.4f}"


# ---------------------------------------------------------------------------
# 3. No future leak assertion (CRITICAL)
# ---------------------------------------------------------------------------

class TestNoFutureLeak:
    """Verify walk_forward_rho is strictly prior-only.

    Strategy: inject a sentinel match at position `i` with an extreme scoreline
    (10-10) that would strongly push rho if included in the history for match i.
    Verify rho[i] is the same whether or not the sentinel is present
    (since the sentinel itself is at position i, not i-1).
    """

    def _arrays(self, n: int = 600, seed: int = 7) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rng = np.random.default_rng(seed)
        lh = rng.uniform(0.9, 1.8, size=n)
        la = rng.uniform(0.7, 1.5, size=n)
        h = rng.poisson(lh).astype(int)
        a = rng.poisson(la).astype(int)
        return lh, la, h, a

    def test_rho_i_does_not_use_match_i(self):
        """rho[i] must equal rho computed from history[0..i-1] only.

        We verify this by checking that rho[refit_every] (the first non-warmup
        rho) uses exactly `refit_every` prior matches and NOT the match at index
        `refit_every` itself. We do this by comparing rho computed with and
        without the sentinel at exactly `refit_every`.
        """
        n = 700
        refit_every = 300
        lh, la, h, a = self._arrays(n=n)

        # Get rho array with natural data
        rho_natural = walk_forward_rho(lh, la, h, a, refit_every=refit_every)

        # Replace match at index `refit_every` with an extreme scoreline
        # (this should NOT affect rho[refit_every] if leak-free)
        h_modified = h.copy()
        a_modified = a.copy()
        h_modified[refit_every] = 10
        a_modified[refit_every] = 10

        rho_modified = walk_forward_rho(lh, la, h_modified, a_modified, refit_every=refit_every)

        # rho[refit_every] should be identical — match i is never in its own history
        assert rho_natural[refit_every] == pytest.approx(rho_modified[refit_every], abs=1e-10), (
            f"LEAK DETECTED: rho[{refit_every}] changed from {rho_natural[refit_every]:.6f} "
            f"to {rho_modified[refit_every]:.6f} when match {refit_every} was modified. "
            "This means match i is being included in its own history — future leak!"
        )

    def test_rho_all_non_warmup_change_only_when_sentinel_before_refit_point(self):
        """Modifying match at index > refit boundary only affects rho at subsequent refit."""
        n = 700
        refit_every = 300
        lh, la, h, a = self._arrays(n=n)

        rho_natural = walk_forward_rho(lh, la, h, a, refit_every=refit_every)

        # Modify match at index refit_every + 1 (after the first refit boundary)
        # This should NOT affect rho[refit_every] or rho[refit_every + 1]
        # (next refit is at 2*refit_every)
        h_modified = h.copy()
        h_modified[refit_every + 1] = 9

        rho_modified = walk_forward_rho(lh, la, h_modified, a, refit_every=refit_every)

        # rho at the first refit point should be unchanged
        assert rho_natural[refit_every] == pytest.approx(rho_modified[refit_every], abs=1e-10)

        # rho at the second refit point (2*refit_every) may differ
        # (the modified match falls in the prior window [0..2*refit_every-1])
        # Just assert rho[refit_every+1] is in bounds and finite
        assert -0.2 <= rho_modified[refit_every + 1] <= 0.0


# ---------------------------------------------------------------------------
# 4. Warmup invariant
# ---------------------------------------------------------------------------

class TestWarmupInvariant:
    def test_first_refit_every_matches_are_zero(self):
        """Matches 0..refit_every-1 all get rho=0 (warmup)."""
        n = 500
        refit_every = 200
        rng = np.random.default_rng(99)
        lh = rng.uniform(1.0, 1.8, size=n)
        la = rng.uniform(0.8, 1.4, size=n)
        h = rng.poisson(lh).astype(int)
        a = rng.poisson(la).astype(int)

        rho_arr = walk_forward_rho(lh, la, h, a, refit_every=refit_every)

        warmup = rho_arr[:refit_every]
        assert np.all(warmup == 0.0), (
            f"Warmup period should all be 0.0; got non-zero at indices: "
            f"{np.where(warmup != 0.0)[0].tolist()}"
        )

    def test_non_warmup_rho_in_bounds(self):
        """All non-warmup rho values are within [-0.2, 0.0]."""
        n = 700
        refit_every = 300
        rng = np.random.default_rng(13)
        lh = rng.uniform(0.9, 1.9, size=n)
        la = rng.uniform(0.7, 1.5, size=n)
        h = rng.poisson(lh).astype(int)
        a = rng.poisson(la).astype(int)

        rho_arr = walk_forward_rho(lh, la, h, a, refit_every=refit_every)

        non_warmup = rho_arr[refit_every:]
        assert np.all(non_warmup >= -0.2) and np.all(non_warmup <= 0.0), (
            f"Non-warmup rho values outside [-0.2, 0.0]: "
            f"min={non_warmup.min():.4f}, max={non_warmup.max():.4f}"
        )
