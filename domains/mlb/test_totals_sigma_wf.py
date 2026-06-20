"""Per-file test for domains.mlb.totals_sigma_wf.

Acceptance criteria
-------------------
1. Fit r on corpus first half, score held-out second half:
   a. 50% band coverage ~50% +/- 3 pp on half2.
   b. Pinball loss (q25 + q75) on half2 <= Poisson(lam_total) baseline.
2. No future row used in fit (walk-forward lambdas; only half1 outcomes inform r).
3. Deterministic (repeated calls return identical r_fit).
4. diag['passes'] == True end-to-end.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_totals_sigma_wf.py -q
"""
from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "domains" / "mlb" / "games.parquet"

_SKIP_NO_DATA = pytest.mark.skipif(
    not CORPUS_PATH.exists(), reason="MLB corpus not available"
)


_FIT_CACHE: dict = {}


def _load_fit():
    """Load corpus and run fit(); memoized at module scope to avoid re-running."""
    if "result" not in _FIT_CACHE:
        import pandas as pd
        from domains.mlb.totals_sigma_wf import fit

        df = pd.read_parquet(CORPUS_PATH)
        _FIT_CACHE["df"] = df
        _FIT_CACHE["result"] = fit(df)
    return _FIT_CACHE["result"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_import():
    """Module and public symbols import cleanly."""
    mod = importlib.import_module("domains.mlb.totals_sigma_wf")
    assert hasattr(mod, "fit"), "fit() missing from module"
    assert hasattr(mod, "load_and_fit"), "load_and_fit() missing from module"


@_SKIP_NO_DATA
def test_r_fit_positive():
    """Fitted r must be a finite positive float."""
    r_fit, _ = _load_fit()
    assert isinstance(r_fit, float), f"r_fit type: {type(r_fit)}"
    assert np.isfinite(r_fit), f"r_fit not finite: {r_fit}"
    assert r_fit > 0.0, f"r_fit <= 0: {r_fit}"


@_SKIP_NO_DATA
def test_50pct_coverage_held_out():
    """50% predictive-interval coverage on held-out half2 must be 0.47..0.53."""
    _, diag = _load_fit()
    val_cov = diag["val_coverage"]
    assert abs(val_cov - 0.50) <= 0.03, (
        f"val_coverage={val_cov:.4f} outside [0.47, 0.53]; "
        f"r_fit={diag['r_fit']:.3f}"
    )


@_SKIP_NO_DATA
def test_pinball_not_worse_than_poisson():
    """NB pinball on held-out half2 must be <= Poisson baseline."""
    _, diag = _load_fit()
    nb_pb = diag["pinball_nb_val"]
    po_pb = diag["pinball_poisson_val"]
    assert nb_pb <= po_pb + 1e-9, (
        f"NB pinball {nb_pb:.6f} > Poisson pinball {po_pb:.6f}; "
        f"delta={diag['pinball_delta']:.6f}"
    )


@_SKIP_NO_DATA
def test_passes_flag():
    """diag['passes'] must be True (composite acceptance gate)."""
    _, diag = _load_fit()
    assert diag["passes"] is True, (
        f"diag['passes']=False; val_coverage={diag['val_coverage']:.4f}, "
        f"pinball_delta={diag['pinball_delta']:.6f}"
    )


@_SKIP_NO_DATA
def test_deterministic():
    """Two consecutive fit() calls on same data return identical r_fit."""
    from domains.mlb.totals_sigma_wf import fit

    # Use cached df to avoid an extra parquet load; call fit() twice
    df = _FIT_CACHE.get("df")
    if df is None:
        import pandas as pd
        df = pd.read_parquet(CORPUS_PATH)
    r1, _ = fit(df)
    r2, _ = fit(df)
    assert r1 == r2, f"Non-deterministic: r1={r1}, r2={r2}"


@_SKIP_NO_DATA
def test_diag_keys():
    """Diagnostics dict contains all expected keys."""
    _, diag = _load_fit()
    required = {
        "n_train", "n_val", "r_fit", "train_coverage", "val_coverage",
        "pinball_nb_val", "pinball_poisson_val", "pinball_delta", "passes", "note",
    }
    missing = required - set(diag.keys())
    assert not missing, f"Missing diag keys: {missing}"


@_SKIP_NO_DATA
def test_n_train_half():
    """Training size must be approximately half the corpus."""
    import pandas as pd
    df = pd.read_parquet(CORPUS_PATH)
    _, diag = _load_fit()
    expected_mid = len(df) // 2
    assert diag["n_train"] == expected_mid, (
        f"n_train={diag['n_train']} != expected {expected_mid}"
    )
    assert diag["n_val"] == len(df) - expected_mid
