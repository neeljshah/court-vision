"""Per-file test for domains/mlb/negbinom_sim.py — the NegBinom production-path wiring.

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platform/test_negbinom_sim.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.mlb.negbinom_sim import (
    MLBNegBinomSimModel,
    MLBPoissonSimModel,
    build_mlb_jd,
)
from scripts.platformkit.sim_framework import JointDistribution


def test_sample_shape_and_dtype():
    m = MLBNegBinomSimModel(4.5, 4.2, 4.0, 3.4)
    s = m.sample(5000, rng_seed=1)
    assert s.shape == (5000, 2)
    assert s.dtype == np.float64
    assert (s >= 0).all()


def test_mean_preserving():
    """NegBinom marginals keep the Poisson mean (lambda) within MC tolerance."""
    m = MLBNegBinomSimModel(4.6, 4.1, 4.2, 3.4)
    s = m.sample(120_000, rng_seed=2)
    assert abs(s[:, 0].mean() - 4.6) < 0.08
    assert abs(s[:, 1].mean() - 4.1) < 0.08


def test_overdispersion_present():
    """NegBinom variance must exceed Poisson variance at the SAME mean."""
    lam = 4.5
    nb = MLBNegBinomSimModel(lam, lam, 3.5, 3.5).sample(120_000, rng_seed=3)
    po = MLBPoissonSimModel(lam, lam).sample(120_000, rng_seed=3)
    assert nb[:, 0].var() > po[:, 0].var() + 0.5  # var = lam + lam^2/r > lam
    # Poisson var ~ mean
    assert abs(po[:, 0].var() - lam) < 0.3


def test_collapses_to_poisson_large_r():
    """As r -> large, NegBinom variance approaches Poisson (mean)."""
    lam = 4.5
    nb = MLBNegBinomSimModel(lam, lam, 5_000.0, 5_000.0).sample(120_000, rng_seed=4)
    assert abs(nb[:, 0].var() - lam) < 0.4


def test_build_jd_round_trip_matches_analytic_pmf():
    """Sampled O/U prob must match the analytic NegBinom PMF O/U prob (MC tol)."""
    from domains.mlb.negbinom_engine import runs_matrix_nb, markets_from_matrix_nb

    lam_h, lam_a, r_h, r_a = 4.7, 4.0, 4.2, 3.4
    P = runs_matrix_nb(lam_h, lam_a, r_h, r_a)
    analytic = markets_from_matrix_nb(P)
    jd = build_mlb_jd(lam_h, lam_a, r_h, r_a, n_sims=80_000, seed=5, dispersion="negbinom")
    for ln in (7.5, 8.5, 9.5):
        assert abs(jd.prob_over(0, 1, ln) - analytic[f"over_{ln:g}"]) < 0.012
    ph, _, pt = jd.prob_side_win(0, 1)
    assert abs((ph + 0.5 * pt) - analytic["ml_home"]) < 0.012


def test_build_jd_is_jointdistribution_independent_label():
    jd = build_mlb_jd(4.5, 4.2, 4.0, 3.4, n_sims=2000, seed=6)
    assert isinstance(jd, JointDistribution)
    assert jd.joint_quality == "independent"
    # honest: independent marginals -> joint_prob refused
    with pytest.raises(ValueError):
        jd.joint_prob([lambda s: s[:, 0] > 4, lambda s: s[:, 1] > 4])


def test_seed_stability():
    a = build_mlb_jd(4.5, 4.2, 4.0, 3.4, n_sims=3000, seed=11)
    b = build_mlb_jd(4.5, 4.2, 4.0, 3.4, n_sims=3000, seed=11)
    assert a.prob_over(0, 1, 8.5) == b.prob_over(0, 1, 8.5)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        MLBNegBinomSimModel(0.0, 4.0, 4.0, 4.0)
    with pytest.raises(ValueError):
        MLBNegBinomSimModel(4.0, 4.0, -1.0, 4.0)
    with pytest.raises(ValueError):
        build_mlb_jd(4.5, 4.2, 4.0, 3.4, dispersion="weird")
