"""Per-file test for scripts.platformkit.calib_decomp.

Acceptance criteria (BACKLOG pa-decomp):
  - perfectly-calibrated probs -> reliability ~0
  - collapse-to-base-rate -> resolution ~0
  - REL - RES + UNC reconstructs brier_binned within 1e-6
  - under-N -> INSUFFICIENT_DATA
  - no dollar-figure key anywhere in any result

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_calib_decomp.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit import calib_decomp as cd

RNG = np.random.default_rng


def _no_dollar_keys(obj) -> None:
    """Recursively assert no banned financial keys and no bare dollar sign in keys."""
    if isinstance(obj, dict):
        for k in obj:
            kl = k.lower()
            assert not kl.startswith("$"), f"dollar-sign key: {k!r}"
            assert kl not in ("dollar", "pnl", "roi", "profit", "loss_dollar"), f"banned key: {k!r}"
            _no_dollar_keys(obj[k])
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _no_dollar_keys(item)


# ---------------------------------------------------------------------------
# Core: REL - RES + UNC == brier_binned within 1e-6 (Murphy identity)
# ---------------------------------------------------------------------------

def test_identity_random():
    p = RNG(0).uniform(0.05, 0.95, 400)
    y = (RNG(0).uniform(size=400) < p).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert r["status"] == "ok"
    assert abs(r["brier_check"] - r["brier_binned"]) < 1e-6

def test_identity_skewed():
    p = RNG(7).beta(2, 8, 500)
    y = (RNG(7).uniform(size=500) < p).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert abs(r["brier_check"] - r["brier_binned"]) < 1e-6

def test_identity_constant_probs_matches_raw_brier():
    """Constant probs -> brier == brier_binned (no within-bin variance)."""
    p = np.full(100, 0.6)
    y = RNG(99).binomial(1, 0.6, 100).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert abs(r["brier"] - r["brier_binned"]) < 1e-10
    assert abs(r["brier_check"] - r["brier_binned"]) < 1e-6


# ---------------------------------------------------------------------------
# Acceptance: perfectly-calibrated -> reliability ~0
# ---------------------------------------------------------------------------

def test_reliability_near_zero_perfect_calibration():
    """Outcomes ~ Bernoulli(p_i) with n=2000 -> REL well under 0.01."""
    p = np.linspace(0.05, 0.95, 2000)
    y = RNG(1).binomial(1, p).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert r["status"] == "ok"
    assert r["reliability"] < 0.01, f"REL={r['reliability']:.6f}"


# ---------------------------------------------------------------------------
# Acceptance: collapse-to-base-rate -> resolution ~0
# ---------------------------------------------------------------------------

def test_resolution_zero_for_constant_forecast():
    """All probs identical -> single bin, o_bar_k == o_bar -> RES = 0."""
    p = np.full(300, 0.4)
    y = RNG(2).binomial(1, 0.4, 300).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert r["status"] == "ok"
    assert r["resolution"] < 1e-12, f"RES={r['resolution']:.2e}"


# ---------------------------------------------------------------------------
# Acceptance: under-N -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_insufficient_data_below_min_n():
    n = cd.MIN_N_TOTAL - 1
    r = cd.decompose(np.linspace(0.1, 0.9, n), np.zeros(n))
    assert r["status"] == "INSUFFICIENT_DATA"
    assert r["brier"] is None and r["reliability"] is None
    assert r["resolution"] is None and r["uncertainty"] is None
    assert r["bins_detail"] == []

def test_exactly_min_n_is_ok():
    p = np.linspace(0.1, 0.9, cd.MIN_N_TOTAL)
    y = RNG(3).binomial(1, p).astype(float)
    assert cd.decompose(p, y)["status"] == "ok"

def test_empty_is_insufficient():
    assert cd.decompose([], [])["status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Acceptance: no dollar-figure keys
# ---------------------------------------------------------------------------

def test_no_dollar_keys_ok():
    p = RNG(4).uniform(0.1, 0.9, 100)
    y = (RNG(4).uniform(size=100) < p).astype(float)
    _no_dollar_keys(cd.decompose(p, y))

def test_no_dollar_keys_insufficient():
    _no_dollar_keys(cd.decompose([0.5, 0.4], [1.0, 0.0]))

def test_no_dollar_keys_batch():
    rng = RNG(5)
    recs = [
        {"sport": "nba", "market": "ml",
         "probs": rng.uniform(0.3, 0.7, 50).tolist(),
         "outcomes": rng.binomial(1, 0.5, 50).tolist()},
        {"sport": "mlb", "market": "ml",
         "probs": rng.uniform(0.4, 0.6, 40).tolist(),
         "outcomes": rng.binomial(1, 0.5, 40).tolist()},
    ]
    for r in cd.decompose_batch(recs):
        _no_dollar_keys(r)


# ---------------------------------------------------------------------------
# Structural correctness
# ---------------------------------------------------------------------------

def test_uncertainty_is_base_rate_variance():
    y = RNG(6).binomial(1, 0.35, 200).astype(float)
    r = cd.decompose(RNG(6).uniform(0.2, 0.8, 200), y)
    assert abs(r["uncertainty"] - float(y.mean() * (1 - y.mean()))) < 1e-10

def test_bin_n_sums_to_total():
    p = RNG(8).uniform(0.0, 1.0, 200)
    y = RNG(8).binomial(1, 0.5, 200).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert sum(b["n"] for b in r["bins_detail"]) == r["n"]

def test_sparse_flag_on_large_bin():
    p, y = np.full(200, 0.55), np.zeros(200)
    r = cd.decompose(p, y, bins=10)
    assert len(r["bins_detail"]) == 1
    assert r["bins_detail"][0]["sparse"] is False   # 200 >= SPARSE_N

def test_batch_propagates_sport_market():
    rng = RNG(9)
    recs = [{"sport": "tennis", "market": "ml",
             "probs": rng.uniform(0.3, 0.7, 50).tolist(),
             "outcomes": rng.binomial(1, 0.5, 50).tolist()}]
    res = cd.decompose_batch(recs)
    assert res[0]["sport"] == "tennis" and res[0]["market"] == "ml"

def test_batch_insufficient_propagated():
    recs = [{"sport": "nba", "market": "spread", "probs": [0.5, 0.4], "outcomes": [1.0, 0.0]}]
    assert cd.decompose_batch(recs)[0]["status"] == "INSUFFICIENT_DATA"

def test_resolution_matches_scoring_module():
    """RES must match scoring.py resolution()."""
    try:
        from scripts.platformkit.eval_gate.scoring import resolution as s_res
    except ImportError:
        pytest.skip("eval_gate.scoring not importable")
    p = RNG(10).uniform(0.1, 0.9, 300)
    y = RNG(10).binomial(1, 0.5, 300).astype(float)
    r = cd.decompose(p, y, bins=10)
    assert abs(r["resolution"] - s_res(p, y, bins=10)) < 1e-8


# ---------------------------------------------------------------------------
# format_summary: ASCII-only, no dollar signs, honest labels
# ---------------------------------------------------------------------------

def test_format_summary_ascii_only():
    p = RNG(11).uniform(0.2, 0.8, 100)
    y = RNG(11).binomial(1, 0.5, 100).astype(float)
    r = cd.decompose(p, y)
    r.update({"sport": "nba", "market": "moneyline"})
    cd.format_summary(r).encode("ascii")

def test_format_summary_insufficient():
    text = cd.format_summary(cd.decompose([0.5, 0.4], [1.0, 0.0]), label="thin")
    assert "INSUFFICIENT_DATA" in text

def test_format_summary_no_dollar_sign():
    p = RNG(12).uniform(0.2, 0.8, 100)
    y = RNG(12).binomial(1, 0.5, 100).astype(float)
    text = cd.format_summary(cd.decompose(p, y))
    assert "$" not in text

def test_format_summary_calibration_and_edge_mentioned():
    p = RNG(13).uniform(0.2, 0.8, 100)
    y = RNG(13).binomial(1, 0.5, 100).astype(float)
    text = cd.format_summary(cd.decompose(p, y)).lower()
    assert "calibration" in text and "edge" in text


if __name__ == "__main__":
    import sys
    import pytest as _p
    sys.exit(_p.main([__file__, "-q"]))
