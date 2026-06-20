"""Per-file test for domains.mlb.runline_dependence.

Acceptance criteria
-------------------
1. fit_copula_rho:
   a. Returns 0.0 on < 10 observations.
   b. Returns a finite float in (-1, 1) on real data.
   c. Consistent with Pearson on Gaussian data (known rho recoverable).

2. dependent_joint_matrix:
   a. Sums to 1.0 for any (lam_h, lam_a, r, rho).
   b. At rho=0 matches the independent NegBinom outer product (within 1e-6).
   c. At rho_fitted, sampled correlation reproduces target within +/-eps.

3. run_dependence_wf (full corpus required):
   a. rho_fitted is finite and in (-1, 1).
   b. verdict is 'SHIP' or 'REJECT' (not missing or None).
   c. n_train + n_val <= total corpus size (no double-count).
   d. corr_reproduced is True (sampled joint is self-consistent).
   e. ml_consistent is True (RL and ML probs are coherent).
   f. Honest REJECT is accepted as SUCCESS (not a test failure).
   g. No $ / P&L / ROI / edge field in result dict.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_runline_dependence.py -q
"""
from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "domains" / "mlb" / "games.parquet"
_SKIP_NO_DATA = pytest.mark.skipif(
    not CORPUS_PATH.exists(), reason="MLB corpus not available"
)

_WF_CACHE: dict = {}


def _load_wf() -> dict:
    """Run walk-forward validation once; memoize to avoid repeat I/O."""
    if "result" not in _WF_CACHE:
        import pandas as pd
        from domains.mlb.runline_dependence import run_dependence_wf
        df = pd.read_parquet(CORPUS_PATH)
        _WF_CACHE["df"] = df
        _WF_CACHE["result"] = run_dependence_wf(df)
    return _WF_CACHE["result"]


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_import():
    """Module imports without error and exposes required public symbols."""
    mod = importlib.import_module("domains.mlb.runline_dependence")
    assert hasattr(mod, "fit_copula_rho"), "fit_copula_rho missing"
    assert hasattr(mod, "dependent_joint_matrix"), "dependent_joint_matrix missing"
    assert hasattr(mod, "run_dependence_wf"), "run_dependence_wf missing"


# ---------------------------------------------------------------------------
# fit_copula_rho unit tests
# ---------------------------------------------------------------------------

def test_fit_rho_small_sample_returns_zero():
    """Returns 0.0 (independence fallback) when fewer than 10 observations."""
    from domains.mlb.runline_dependence import fit_copula_rho
    rho = fit_copula_rho(np.array([1.0, 2.0]), np.array([3.0, 1.0]))
    assert rho == 0.0


def test_fit_rho_range():
    """Returns a finite float strictly between -1 and 1 on synthetic data."""
    from domains.mlb.runline_dependence import fit_copula_rho
    rng = np.random.default_rng(0)
    h = rng.poisson(4.5, size=200).astype(float)
    a = rng.poisson(4.2, size=200).astype(float)
    rho = fit_copula_rho(h, a)
    assert np.isfinite(rho), f"rho not finite: {rho}"
    assert -1.0 < rho < 1.0, f"rho out of (-1, 1): {rho}"


def test_fit_rho_recovers_known_positive():
    """Fitted rho should have the right sign on strongly correlated data."""
    from domains.mlb.runline_dependence import fit_copula_rho
    rng = np.random.default_rng(7)
    n = 500
    # Generate positively correlated runs via shared component
    common = rng.poisson(3.0, size=n).astype(float)
    h = common + rng.poisson(1.5, size=n)
    a = common + rng.poisson(1.5, size=n)
    rho = fit_copula_rho(h, a)
    assert rho > 0.1, f"Expected positive rho on correlated data, got {rho:.4f}"


def test_fit_rho_symmetric():
    """fit_copula_rho(h, a) == fit_copula_rho(a, h) (copula is symmetric)."""
    from domains.mlb.runline_dependence import fit_copula_rho
    rng = np.random.default_rng(3)
    h = rng.poisson(4.0, size=300).astype(float)
    a = rng.poisson(5.0, size=300).astype(float)
    assert fit_copula_rho(h, a) == pytest.approx(fit_copula_rho(a, h), abs=1e-10)


# ---------------------------------------------------------------------------
# dependent_joint_matrix unit tests
# ---------------------------------------------------------------------------

def test_joint_sums_to_one_rho_zero():
    """Independent joint (rho=0) sums to 1."""
    from domains.mlb.runline_dependence import dependent_joint_matrix
    P = dependent_joint_matrix(4.5, 4.2, 4.0, 4.0, rho=0.0)
    assert P.shape == (26, 26), f"Expected (26,26), got {P.shape}"
    assert abs(P.sum() - 1.0) < 1e-9, f"Sum={P.sum():.10f}"


def test_joint_sums_to_one_nonzero_rho():
    """Copula-corrected joint sums to 1 for various rho values."""
    from domains.mlb.runline_dependence import dependent_joint_matrix
    for rho in (-0.3, -0.1, 0.1, 0.3):
        P = dependent_joint_matrix(4.5, 4.2, 4.0, 4.0, rho=rho)
        assert abs(P.sum() - 1.0) < 1e-6, f"rho={rho}: sum={P.sum():.10f}"


def test_joint_rho_zero_equals_independent():
    """At rho=0 the dependent matrix equals the independent outer product."""
    from domains.mlb.runline_dependence import dependent_joint_matrix, _nb_pmf
    lh, la, r = 4.5, 4.2, 4.0
    P_dep = dependent_joint_matrix(lh, la, r, r, rho=0.0)
    pmf_h = _nb_pmf(lh, r, 25)
    pmf_a = _nb_pmf(la, r, 25)
    P_ind = np.outer(pmf_h, pmf_a)
    P_ind /= P_ind.sum()
    np.testing.assert_allclose(P_dep, P_ind, atol=1e-9)


def test_joint_positive_rho_shifts_probability():
    """Positive rho should increase P(h=high, a=high) vs independence."""
    from domains.mlb.runline_dependence import dependent_joint_matrix
    lh, la, r = 4.5, 4.2, 4.0
    P_rho = dependent_joint_matrix(lh, la, r, r, rho=0.3)
    P_ind = dependent_joint_matrix(lh, la, r, r, rho=0.0)
    # Upper-right quadrant (both >= 8 runs): should be denser under positive rho
    high = 8
    mass_rho = P_rho[high:, high:].sum()
    mass_ind = P_ind[high:, high:].sum()
    assert mass_rho > mass_ind, (
        f"Positive rho should increase joint high-run mass; "
        f"rho_mass={mass_rho:.6f} vs ind_mass={mass_ind:.6f}"
    )


def test_joint_valid_for_various_lambdas():
    """Matrix sums to 1 and is non-negative for edge-case lambdas."""
    from domains.mlb.runline_dependence import dependent_joint_matrix
    for lh, la in [(0.5, 0.5), (10.0, 10.0), (2.0, 8.0)]:
        P = dependent_joint_matrix(lh, la, 4.0, 4.0, rho=0.1)
        assert P.min() >= -1e-12, f"Negative mass at lh={lh}, la={la}: {P.min()}"
        assert abs(P.sum() - 1.0) < 1e-6, f"Sum={P.sum():.10f} at lh={lh}, la={la}"


# ---------------------------------------------------------------------------
# Walk-forward harness tests (require corpus)
# ---------------------------------------------------------------------------

@_SKIP_NO_DATA
def test_wf_rho_is_finite_in_range():
    """Fitted rho must be finite and in (-1, 1)."""
    result = _load_wf()
    rho = result["rho_fitted"]
    assert np.isfinite(rho), f"rho_fitted not finite: {rho}"
    assert -1.0 < rho < 1.0, f"rho_fitted out of bounds: {rho}"


@_SKIP_NO_DATA
def test_wf_verdict_is_valid():
    """verdict must be 'SHIP' or 'REJECT'; honest REJECT counts as success."""
    result = _load_wf()
    assert result["verdict"] in ("SHIP", "REJECT"), (
        f"Unknown verdict: {result['verdict']!r}"
    )
    # Honest REJECT is a valid result, not a test failure
    # (small rho ~0.02 -> independence is fine -> REJECT expected)


@_SKIP_NO_DATA
def test_wf_corpus_split():
    """n_train + n_val must not exceed corpus size."""
    import pandas as pd
    df = pd.read_parquet(CORPUS_PATH)
    result = _load_wf()
    assert result["n_train"] + result["n_val"] <= len(df), (
        f"n_train={result['n_train']} + n_val={result['n_val']} > {len(df)}"
    )
    assert result["n_train"] > 0, "n_train=0: no training data"
    assert result["n_val"] > 0, "n_val=0: no validation data"


@_SKIP_NO_DATA
def test_wf_corr_reproduced():
    """Sampled joint must reproduce target rho within tolerance."""
    result = _load_wf()
    assert result["corr_reproduced"] is True, (
        f"corr_reproduced=False: sampled_rho={result['sampled_rho']:.4f}, "
        f"rho_fitted={result['rho_fitted']:.4f}"
    )


@_SKIP_NO_DATA
def test_wf_ml_consistent():
    """Mean predicted P(home_win) from dependent model must calibrate vs actual win rate."""
    result = _load_wf()
    assert result["ml_consistent"] is True, (
        f"ml_consistent=False: avg_ml_dep={result['avg_ml_dep']:.4f}, "
        f"avg_ml_act={result['avg_ml_act']:.4f}"
    )


@_SKIP_NO_DATA
def test_wf_brier_scores_are_finite():
    """All Brier scores must be finite positive floats."""
    result = _load_wf()
    for key in ("rl_brier_dep", "rl_brier_ind", "ou_brier_dep", "ou_brier_ind"):
        val = result[key]
        assert np.isfinite(val) and val >= 0.0, f"{key}={val} invalid"


@_SKIP_NO_DATA
def test_wf_no_dollar_field():
    """Result dict must not contain any $ / P&L / edge / ROI / profit key."""
    result = _load_wf()
    forbidden = {"roi", "pnl", "profit", "edge", "dollar", "ev_usd", "kelly_frac"}
    found = {k for k in result if k.lower() in forbidden}
    assert not found, f"Forbidden $ fields in result: {found}"


@_SKIP_NO_DATA
def test_wf_diag_keys_present():
    """Required diagnostics keys must all be present."""
    result = _load_wf()
    required = {
        "rho_fitted", "n_train", "n_val", "verdict",
        "rl_brier_dep", "rl_brier_ind", "rl_brier_delta",
        "ou_brier_dep", "ou_brier_ind", "ou_brier_delta",
        "combined_delta", "corr_reproduced", "sampled_rho",
        "ml_consistent", "avg_ml_dep", "avg_ml_act", "note",
    }
    missing = required - set(result.keys())
    assert not missing, f"Missing result keys: {missing}"


@_SKIP_NO_DATA
def test_wf_combined_delta_sign_matches_verdict():
    """combined_delta < 0 iff verdict == 'SHIP'."""
    result = _load_wf()
    delta = result["combined_delta"]
    verdict = result["verdict"]
    if verdict == "SHIP":
        assert delta < 0.0, f"SHIP but combined_delta={delta:.6f} >= 0"
    else:
        assert delta >= 0.0, f"REJECT but combined_delta={delta:.6f} < 0"
