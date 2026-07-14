"""Per-file tests for scripts.platformkit.omni.spine_eval (P6 standing PBP-
replay evaluator). Metric math on synthetic data + reproducibility -- does
NOT touch the real season parquets (that's the full run() path, exercised
manually via `python -m scripts.platformkit.omni.spine_eval`).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_spine_eval.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.omni import spine_eval as SE


def test_crps_ordinal_perfect_forecast_is_zero():
    # perfect certainty on the true class -> CRPS == 0
    y = np.array([0, 2, 4])
    cdf = np.array([
        [1.0, 1.0, 1.0, 1.0, 1.0],   # certain class 0
        [0.0, 0.0, 1.0, 1.0, 1.0],   # certain class 2
        [0.0, 0.0, 0.0, 0.0, 1.0],   # certain class 4
    ])
    out = SE.crps_ordinal(cdf, y)
    np.testing.assert_allclose(out, 0.0, atol=1e-12)


def test_crps_ordinal_worse_for_wrong_certainty():
    y = np.array([0])
    cdf_right = np.array([[1.0, 1.0, 1.0, 1.0, 1.0]])
    cdf_wrong = np.array([[0.0, 0.0, 0.0, 0.0, 1.0]])   # certain on class 4, true is 0
    right = SE.crps_ordinal(cdf_right, y)[0]
    wrong = SE.crps_ordinal(cdf_wrong, y)[0]
    assert wrong > right


def test_log_loss_rows_matches_hand_calc():
    proba = np.array([[0.2, 0.3, 0.5, 0.0, 0.0]])
    y = np.array([1])
    out = SE.log_loss_rows(proba, y)
    np.testing.assert_allclose(out, -np.log(0.3), rtol=1e-9)


def test_verdict_ties_within_threshold():
    assert SE._verdict(1.000, 1.005) == "TIES"     # 0.5% rel
    assert SE._verdict(0.900, 1.000) == "BEATS"     # lower is better, model < baseline
    assert SE._verdict(1.100, 1.000) == "TRAILS"


def test_cdf_from_proba_cumulative():
    proba = np.array([[0.1, 0.2, 0.3, 0.2, 0.2]])
    cdf = SE.cdf_from_proba(proba)
    np.testing.assert_allclose(cdf, [[0.1, 0.3, 0.6, 0.8, 1.0]])


def test_reliability_table_bins_sum_to_n():
    rng = np.random.default_rng(1)
    n = 500
    proba = rng.dirichlet(np.ones(5), size=n)
    y = rng.integers(0, 5, size=n)
    table = SE.reliability_table(proba, y, n_bins=10)
    assert sum(row["n"] for row in table) == n


def test_marginal_proba_matches_train_frequency():
    import pandas as pd
    from scripts.platformkit.omni import spine_nba as SP
    train_df = pd.DataFrame({"points": [0, 0, 2, 2, 2, 6]})   # class0=2,class2=3,class4("6")=1
    p = SE.marginal_proba(train_df, n_rows=3)
    assert p.shape == (3, SP.N_CLASSES)
    np.testing.assert_allclose(p[0], [2 / 6, 0, 3 / 6, 0, 1 / 6])
    np.testing.assert_allclose(p[0], p[1])  # broadcast identical rows


def test_seed_deltas_zero_when_metrics_identical():
    metrics = {"per_model": {"spine_v1": {"crps": 0.6, "log_loss": 1.1}}}
    deltas, stable = SE._seed_deltas(metrics, metrics, "spine_v1")
    assert deltas["spine_v1_crps_rel_delta"] == 0.0
    assert deltas["spine_v1_log_loss_rel_delta"] == 0.0
    assert stable is True


def test_seed_deltas_flags_unstable_over_threshold():
    a = {"per_model": {"spine_v1": {"crps": 1.0, "log_loss": 1.0}}}
    b = {"per_model": {"spine_v1": {"crps": 1.10, "log_loss": 1.0}}}   # 10% drift
    deltas, stable = SE._seed_deltas(a, b, "spine_v1")
    assert deltas["spine_v1_crps_rel_delta"] > SE.SEED_STABLE_REL
    assert stable is False


def test_feature_importance_top10_shape_and_sorted():
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingClassifier
    from scripts.platformkit.omni import spine_nba as SP
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({f: rng.uniform(0, 10, n) for f in SP.FEATURES})
    df["points"] = rng.choice([0, 1, 2, 3], size=n)
    clf = HistGradientBoostingClassifier(max_iter=20, random_state=42)
    clf.fit(df[SP.FEATURES].to_numpy(dtype=float), SP.points_to_class(df["points"].to_numpy()))
    out = SE.feature_importance_top10(clf, df, SP.FEATURES, seed=42)
    assert len(out) == len(SP.FEATURES)   # <=10, here 9 features total
    means = [row["importance_mean"] for row in out]
    assert means == sorted(means, reverse=True)
