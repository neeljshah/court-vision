"""Regression test for the engine decorrelation audit (N_eff math + gated reporting byte-identity).

Covers the SS4D correlation-guard lever: the N_eff formula must be exact at the boundaries, and the
predict_ensemble CV_ENGINE_NEFF reporting must be additive-only (flag OFF -> the source has no top-level
decorrelation logic outside the env guard).
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))

import engine_decorrelation as ed  # noqa: E402


def test_n_eff_identity_is_N():
    # orthogonal engines -> N_eff == N (no redundancy)
    for N in (2, 5, 7):
        assert abs(ed.n_eff_from_corr(np.eye(N)) - N) < 1e-9


def test_n_eff_all_ones_is_one():
    # perfectly correlated engines -> N_eff == 1 (one shared view)
    for N in (2, 5, 7):
        assert abs(ed.n_eff_from_corr(np.ones((N, N))) - 1.0) < 1e-9


def test_n_eff_uniform_corr_formula():
    # uniform off-diagonal rho -> N_eff == N / (1 + (N-1)*rho); matches the measured 0.805 -> ~1.19
    N, rho = 5, 0.805
    R = np.full((N, N), rho)
    np.fill_diagonal(R, 1.0)
    expected = N / (1 + (N - 1) * rho)
    assert abs(ed.n_eff_from_corr(R) - expected) < 1e-9
    assert 1.1 < ed.n_eff_from_corr(R) < 1.3   # the audit's measured regime


def test_n_eff_monotone_in_correlation():
    # more correlation -> fewer effective views
    N = 5
    prev = None
    for rho in (0.0, 0.2, 0.5, 0.8, 0.99):
        R = np.full((N, N), rho)
        np.fill_diagonal(R, 1.0)
        v = ed.n_eff_from_corr(R)
        if prev is not None:
            assert v < prev + 1e-9
        prev = v


def test_predict_ensemble_neff_block_is_env_gated():
    # byte-identical-OFF guarantee: the new reporting is reachable ONLY under the env flag.
    src = open(os.path.join(ROOT, "scripts", "team_system", "predict_ensemble.py"), encoding="utf-8").read()
    assert 'os.environ.get("CV_ENGINE_NEFF") == "1"' in src
    # the decorrelation artifact read must sit INSIDE the guarded block (after the env check)
    guard = src.index('os.environ.get("CV_ENGINE_NEFF")')
    assert src.index("engine_decorrelation.json") > guard
