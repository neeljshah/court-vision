"""Per-file unit test for joint_dist.joint -- synthetic data, no GPU-scale run
(the real 412-entity OOS run lives in data/omni/live_edge/joint_dist/
JOINT_REPORT.md, produced by run_joint.main()). Fast smoke checks on the
math primitives only."""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.joint_dist import joint as jt

STAT_COLS = ["pts", "reb", "ast"]


def _fake_box(n_per_player=30, n_players=8, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(n_players):
        base = rng.uniform(5, 20)
        z = rng.normal(size=(n_per_player, 3))
        z[:, 1] += 0.6 * z[:, 0]  # correlate reb with pts
        z[:, 2] += 0.4 * z[:, 0]  # correlate ast with pts
        for i in range(n_per_player):
            rows.append({"player_id": pid, "pts": max(0.0, base + 5 * z[i, 0]),
                         "reb": max(0.0, base / 2 + 2 * z[i, 1]),
                         "ast": max(0.0, base / 3 + 1.5 * z[i, 2])})
    return pd.DataFrame(rows)


def test_fit_marginals_covers_all_stats():
    df = _fake_box()
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    assert set(m.keys()) == set(STAT_COLS)
    for s in STAT_COLS:
        assert 0 in m[s]  # player_id 0 present
        assert m[s][0]["insufficient"] is False


def test_fit_dependence_shape_and_signal():
    df = _fake_box()
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    dep, pooled = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    assert pooled.shape == (3, 3)
    assert np.allclose(np.diag(pooled), 1.0)
    # construction correlates pts-reb and pts-ast positively -- pooled fit should see it
    assert pooled[0, 1] > 0.1
    assert pooled[0, 2] > 0.1
    assert 0 in dep


def test_sample_cloud_dependent_more_correlated_than_independent():
    df = _fake_box()
    m = jt.fit_marginals(df, "player_id", STAT_COLS)
    dep, _ = jt.fit_dependence(df, "player_id", STAT_COLS, m, "cpu")
    dep_cloud = jt.sample_cloud(0, dep, m, STAT_COLS, 2000, "cpu", seed=1, independence=False)
    ind_cloud = jt.sample_cloud(0, dep, m, STAT_COLS, 2000, "cpu", seed=1, independence=True)
    assert dep_cloud.shape == (2000, 3)
    dep_corr = np.corrcoef(dep_cloud[:, 0], dep_cloud[:, 1])[0, 1]
    ind_corr = np.corrcoef(ind_cloud[:, 0], ind_cloud[:, 1])[0, 1]
    assert dep_corr > ind_corr + 0.05


def test_energy_scores_lower_for_closer_actual():
    samples = np.tile(np.array([10.0, 5.0, 3.0]), (500, 1)) + np.random.default_rng(0).normal(scale=1.0, size=(500, 3))
    close_actual = np.array([[10.0, 5.0, 3.0]])
    far_actual = np.array([[50.0, 30.0, 20.0]])
    es_close = jt.energy_scores(samples, close_actual, "cpu")[0]
    es_far = jt.energy_scores(samples, far_actual, "cpu")[0]
    assert es_close < es_far


def test_independence_event_prob_formula():
    assert abs(jt.independence_event_prob(0.75, 3) - 0.25 ** 3) < 1e-9
    assert abs(jt.independence_event_prob(0.90, 3) - 0.10 ** 3) < 1e-9


def test_copula_event_prob_bounds():
    samples = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    p_low = jt.copula_event_prob(samples, np.array([0.0, 0.0]))
    p_high = jt.copula_event_prob(samples, np.array([10.0, 10.0]))
    assert p_low == 1.0
    assert p_high == 0.0


def test_device_string_reports_something():
    s = jt.device_string()
    assert isinstance(s, str) and len(s) > 0
