"""Per-file unit test for joint_dist.joint_v2 -- synthetic data, CPU, no
GPU-scale run (the real OOS run lives in
data/omni/live_edge/joint_dist/v2/JOINT_V2_REPORT.md, produced by
run_joint_v2.main()). Fast smoke checks on the t-copula math primitives."""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.joint_dist import joint as jt
from scripts.platformkit.live_edge.joint_dist import joint_v2 as jv2

STAT_COLS = ["pts", "reb", "ast"]


def _fake_box(n_per_player=40, n_players=8, seed=0, dof=4.0):
    """Same construction as test_joint_dist's fixture, but with Student-t
    (fat-tailed) shocks instead of Normal -- the case the Gaussian copula
    under-counts."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(n_players):
        base = rng.uniform(5, 20)
        z = rng.standard_t(dof, size=(n_per_player, 3))
        z[:, 1] += 0.6 * z[:, 0]
        z[:, 2] += 0.4 * z[:, 0]
        for i in range(n_per_player):
            rows.append({"player_id": pid, "pts": max(0.0, base + 5 * z[i, 0]),
                         "reb": max(0.0, base / 2 + 2 * z[i, 1]),
                         "ast": max(0.0, base / 3 + 1.5 * z[i, 2])})
    return pd.DataFrame(rows)


def test_fit_dof_prefers_low_dof_on_fat_tailed_data():
    """Data generated from a fat-tailed (dof=3) shock, enough rows to
    discriminate, should score a low-dof candidate strictly better than the
    flattest (dof=50, near-Gaussian) grid member."""
    df = _fake_box(n_per_player=200, dof=3.0)
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    _, pooled = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    U = jv2._pit_matrix(df, "player_id", STAT_COLS, m)
    assert len(U) > 0
    import torch
    corr_t = torch.tensor(pooled, dtype=torch.float32)
    ll_low = jv2._t_copula_loglik(U, corr_t, 5.0, "cpu")
    ll_high = jv2._t_copula_loglik(U, corr_t, 50.0, "cpu")
    assert ll_low > ll_high


def test_fit_dof_returns_grid_member():
    df = _fake_box(dof=4.0)
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    _, pooled = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    nu = jv2.fit_dof(df, "player_id", STAT_COLS, m, pooled, "cpu")
    assert nu in jv2.NU_GRID


def test_sample_cloud_t_shape_and_dependence():
    df = _fake_box()
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    dep, _ = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    cloud = jv2.sample_cloud_t(0, dep, m, STAT_COLS, 2000, "cpu", seed=1, nu=5.0, independence=False)
    assert cloud.shape == (2000, 3)
    dep_corr = np.corrcoef(cloud[:, 0], cloud[:, 1])[0, 1]
    ind_cloud = jv2.sample_cloud_t(0, dep, m, STAT_COLS, 2000, "cpu", seed=1, nu=5.0, independence=True)
    ind_corr = np.corrcoef(ind_cloud[:, 0], ind_cloud[:, 1])[0, 1]
    assert dep_corr > ind_corr + 0.05


def test_sample_cloud_t_fatter_tailed_than_gaussian_at_same_corr():
    """At the SAME correlation, a low-dof t-copula cloud should produce more
    extreme joint co-exceedances than the Gaussian copula -- this is the
    entire point of the lane (closing the realized-vs-predicted tail gap)."""
    df = _fake_box()
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    dep, _ = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    thr = jt.leg_thresholds(0, m, STAT_COLS, 0.9)
    gauss_cloud = jt.sample_cloud(0, dep, m, STAT_COLS, 20000, "cpu", seed=2, independence=False)
    t_cloud = jv2.sample_cloud_t(0, dep, m, STAT_COLS, 20000, "cpu", seed=2, nu=3.0, independence=False)
    p_gauss = jt.copula_event_prob(gauss_cloud, thr)
    p_t = jt.copula_event_prob(t_cloud, thr)
    assert p_t >= p_gauss
