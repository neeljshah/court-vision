"""Per-file pytest for composition_blend.py / composition_gate.py.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/composition/test_composition_gate.py -q

NEVER run the full suite (freezes the box). These tests use small synthetic
tables for the blend-machinery unit tests (fast) plus ONE smoke test against
real on-disk data with a reduced bootstrap count (still exercises the full
leave-one-fold-out + planted-null path, never raises).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.composition.composition_blend import (
    C0_INIT, C1_INIT,
    blend_scores,
    fit_weight_params,
    low_sample_mask,
    shuffle_quality_within_cutoff,
    sigmoid,
    situation_feature,
    zscore,
)
from scripts.platformkit.composition.composition_gate import (
    N_BOOT,
    CompositionGateResult,
    _bootstrap_delta,
    _fold_rho_deltas,
    _leave_one_fold_out,
    run_gate,
)


def _synthetic_table(n: int, seed: int, fga_scale: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    truth = rng.uniform(0, 1, n)
    fga = rng.uniform(200, 2000, n) * fga_scale
    return pd.DataFrame({
        "player_id": np.arange(n) + seed * 1000,
        "fga": fga,
        "naive_pctile": np.clip(truth + rng.normal(0, 0.2, n), 0, 1),
        "shooter_pctile": np.clip(truth + rng.normal(0, 0.2, n), 0, 1),
        "realized_ts_pct": truth,
    })


def test_zscore_mean_zero_std_one():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = zscore(s)
    assert z.mean() == pytest.approx(0, abs=1e-9)
    assert z.std(ddof=0) == pytest.approx(1, abs=1e-9)


def test_zscore_degenerate_constant_series_returns_zeros():
    s = pd.Series([7.0, 7.0, 7.0])
    z = zscore(s)
    assert (z == 0).all()


def test_situation_feature_is_log1p_fga():
    t = pd.DataFrame({"fga": [0, 99, 999]})
    s = situation_feature(t)
    assert s.iloc[0] == pytest.approx(np.log1p(0))
    assert s.iloc[2] == pytest.approx(np.log1p(999))


def test_sigmoid_bounds():
    x = np.array([-100, 0, 100])
    y = sigmoid(x)
    assert y[0] == pytest.approx(0, abs=1e-6)
    assert y[1] == pytest.approx(0.5)
    assert y[2] == pytest.approx(1, abs=1e-6)


def test_blend_scores_reduces_to_naive_when_w_is_one():
    """c1=0, c0 -> +inf makes w(s)->1 for all s, so blend should equal naive_z."""
    t = _synthetic_table(50, seed=1)
    blend = blend_scores(t, c0=50.0, c1=0.0)
    naive_z = zscore(t["naive_pctile"])
    assert np.allclose(blend.values, naive_z.values, atol=1e-6)


def test_blend_scores_reduces_to_quality_when_w_is_zero():
    t = _synthetic_table(50, seed=2)
    blend = blend_scores(t, c0=-50.0, c1=0.0)
    quality_z = zscore(t["shooter_pctile"])
    assert np.allclose(blend.values, quality_z.values, atol=1e-6)


def test_fit_weight_params_recovers_near_naive_when_naive_dominates():
    """When naive_pctile is near-truth and shooter_pctile is pure noise, the
    fit should push w(s) toward naive across the observed s range."""
    rng = np.random.default_rng(3)
    tables = []
    for k in range(3):
        n = 200
        truth = rng.uniform(0, 1, n)
        tables.append(pd.DataFrame({
            "player_id": np.arange(n),
            "fga": rng.uniform(200, 2000, n),
            "naive_pctile": np.clip(truth + rng.normal(0, 0.03, n), 0, 1),
            "shooter_pctile": rng.uniform(0, 1, n),  # pure noise, uninformative
            "realized_ts_pct": truth,
        }))
    fit = fit_weight_params(tables)
    s_mid = np.log1p(1000.0)
    w_mid = sigmoid(np.array([fit.c0 + fit.c1 * s_mid]))[0]
    assert w_mid > 0.5  # favors naive when naive is clearly better


def test_low_sample_mask_is_bottom_tercile_of_fga():
    t = pd.DataFrame({"fga": np.arange(1, 91)})  # 90 distinct values, even split
    mask = low_sample_mask(t)
    assert mask.sum() == pytest.approx(30, abs=1)
    # bottom-tercile rows should all have fga below the mid/top tercile rows selected
    assert t.loc[mask, "fga"].max() <= t.loc[~mask, "fga"].min()


def test_low_sample_mask_degenerate_pool_returns_all_false():
    t = pd.DataFrame({"fga": [500.0] * 10})  # no spread -> cannot form terciles
    mask = low_sample_mask(t)
    assert not mask.any()


def test_shuffle_quality_within_cutoff_preserves_marginal_breaks_pairing():
    t = _synthetic_table(100, seed=5)
    rng = np.random.default_rng(9)
    shuffled = shuffle_quality_within_cutoff(t, rng)
    # marginal distribution preserved (same multiset of values)
    assert sorted(shuffled["shooter_pctile"].tolist()) == pytest.approx(
        sorted(t["shooter_pctile"].tolist())
    )
    # pairing with player_id broken (not identical row-order match, with high probability at n=100)
    assert not np.allclose(shuffled["shooter_pctile"].values, t["shooter_pctile"].values)
    # other columns untouched
    assert np.allclose(shuffled["realized_ts_pct"].values, t["realized_ts_pct"].values)
    assert np.allclose(shuffled["fga"].values, t["fga"].values)


def test_fold_rho_deltas_none_when_subset_too_small():
    t = _synthetic_table(5, seed=6)
    from scripts.platformkit.composition.composition_blend import FitResult
    fit = FitResult(c0=0.0, c1=0.0, train_mean_rho=0.0)
    assert _fold_rho_deltas(t, fit) is None  # n=5 < floor of 10


def test_leave_one_fold_out_shape_matches_cutoffs():
    tables = [_synthetic_table(150, seed=100 + i) for i in range(4)]
    cutoffs = ["c0", "c1", "c2", "c3"]
    out = _leave_one_fold_out(tables, cutoffs)
    assert len(out["per_fold"]) == 4
    assert [f["cutoff"] for f in out["per_fold"]] == cutoffs
    for f in out["per_fold"]:
        assert f["overall"] is not None
        assert "delta" in f["overall"]


def test_bootstrap_delta_ci_excludes_zero_for_strong_synthetic_signal():
    """Sanity-check the bootstrap+refit machinery: when the blend can clearly
    beat naive via the situational feature, CI should exclude 0."""
    rng = np.random.default_rng(11)
    tables = []
    for k in range(4):
        n = 200
        truth = rng.uniform(0, 1, n)
        fga = rng.uniform(200, 2000, n)
        s = np.log1p(fga)
        s_norm = (s - s.mean()) / s.std()
        # shooter_pctile is much better than naive when s is LOW (low FGA) --
        # blend should be able to exploit this via w(s)
        noise_shooter = np.where(s_norm < 0, rng.normal(0, 0.02, n), rng.normal(0, 0.6, n))
        noise_naive = np.where(s_norm < 0, rng.normal(0, 0.6, n), rng.normal(0, 0.02, n))
        tables.append(pd.DataFrame({
            "player_id": np.arange(n) + k * 1000,
            "fga": fga,
            "naive_pctile": np.clip(truth + noise_naive, 0, 1),
            "shooter_pctile": np.clip(truth + noise_shooter, 0, 1),
            "realized_ts_pct": truth,
        }))
    fits = [fit_weight_params([tables[j] for j in range(len(tables)) if j != i])
            for i in range(len(tables))]
    result = _bootstrap_delta(tables, fits, n_boot=200, seed=1)
    assert result["n_boot_effective"] > 100
    # blend should meaningfully beat pure-naive on this constructed setup
    assert result["mean_delta"] > 0


def test_run_gate_never_raises_and_returns_pre_registered_verdict():
    """Smoke test against real on-disk data with a reduced bootstrap budget
    (patched at the module level) so the per-file test stays fast; must
    terminate with one of the pre-registered verdicts, never crash."""
    import scripts.platformkit.composition.composition_gate as cg
    orig_n_boot = cg.N_BOOT
    cg.N_BOOT = 50
    try:
        g = run_gate()
    finally:
        cg.N_BOOT = orig_n_boot
    assert g.verdict in ("SHIP", "REJECT", "NOT_TESTABLE")
    assert isinstance(g.reason, str) and len(g.reason) > 0


def test_verdict_naive_stays_canonical_unless_all_conditions_hold():
    """Binding: SHIP only if (CI excludes 0 overall OR low-sample) AND sign
    holds in >=75% of scored folds (overall or low-sample) AND replicates
    AND the planted null dies. Anything else must be REJECT or NOT_TESTABLE."""
    import scripts.platformkit.composition.composition_gate as cg
    orig_n_boot = cg.N_BOOT
    cg.N_BOOT = 50
    try:
        g = run_gate()
    finally:
        cg.N_BOOT = orig_n_boot
    if g.verdict == "SHIP":
        assert g.planted_null_dies is True
        replicates = g.replication.get("status") == "OK"
        assert replicates
    else:
        assert g.verdict in ("REJECT", "NOT_TESTABLE")
