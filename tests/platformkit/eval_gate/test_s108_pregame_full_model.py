"""S108: the offset must be exact, the folds must be leak-free, the bar must not move."""
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s108_pregame_full_model as s108


def _toy(n=600, p=4, seed=7):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, p))
    offset = rng.normal(scale=0.5, size=n)
    eta = offset + 1.2 * X[:, 0] - 0.8 * X[:, 1]
    y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-eta))).astype(int)
    return X, y, offset


def test_bar_not_moved():
    assert s108.IMPROVEMENT_BAR == 0.004


def test_huge_penalty_collapses_to_the_offset():
    """A penalty large enough to zero every coefficient must return the incumbent itself."""
    X, y, offset = _toy()
    beta, alpha = s108.enet_logistic(X, y, offset, lam=50.0)
    assert np.count_nonzero(beta) == 0
    p = s108.enet_predict(X, offset, (beta, alpha))
    incumbent = s108._sigmoid(offset + alpha)
    assert np.allclose(p, incumbent)


def test_enet_recovers_the_signal_and_shrinks_with_lambda():
    X, y, offset = _toy()
    loose, _ = s108.enet_logistic(X, y, offset, lam=1e-4)
    tight, _ = s108.enet_logistic(X, y, offset, lam=0.05)
    assert loose[0] > 0.5 and loose[1] < -0.3          # signs of the planted coefficients
    assert abs(tight[0]) < abs(loose[0])               # the penalty grid actually shrinks
    assert np.count_nonzero(tight) <= np.count_nonzero(loose)


def test_hgb_offset_beats_the_bare_offset_in_sample():
    X, y, offset = _toy()
    p = s108.hgb_offset(X, y, offset, X, offset, {"max_depth": 2, "l2_regularization": 1.0})
    assert np.mean((p - y) ** 2) < np.mean((s108._sigmoid(offset) - y) ** 2)


def test_folds_are_expanding_disjoint_and_gapped():
    dates = np.array([np.datetime64("2024-01-01") + np.timedelta64(i, "D") for i in range(700)])
    split = s108.folds(dates, 6)
    assert len(split) >= 5
    for train, test in split:
        assert set(train).isdisjoint(set(test))
        assert train.max() < test.min()
        gap = (dates[test[0]] - dates[train[-1]]) / np.timedelta64(1, "D")
        assert gap >= s108.GAP_DAYS
    assert all(len(split[i][0]) < len(split[i + 1][0]) for i in range(len(split) - 1))


def test_score_reports_a_single_cluster_instead_of_raising():
    out = s108._score(np.zeros(10) + 0.01, np.array(["only"] * 10))
    assert out["clusters"] == 1 and out["ci95"] is None


def test_grid_oof_never_looks_ahead():
    """The predictions of every fold come from a train window strictly before its test window."""
    n = 900
    rng = np.random.default_rng(3)
    frame = pd.DataFrame(rng.normal(size=(n, 3)), columns=list("abc"))
    bundle = {"sport": "toy", "X": frame, "y": rng.integers(0, 2, n),
              "p_inc": np.full(n, 0.5),
              "dates": np.array([np.datetime64("2024-01-01") + np.timedelta64(i, "D")
                                 for i in range(n)])}
    grid = s108._grid_oof(bundle, k=5)
    assert len(grid["picks"]) >= 5
    for pick in grid["picks"]:
        assert np.datetime64(pick["train_end"]) <= np.datetime64(pick["test_start"]) - np.timedelta64(
            s108.GAP_DAYS, "D")
        assert pick["lambda"] in s108.LAMBDAS
    assert len({r["row"] for r in grid["rows"]}) == len(grid["rows"])


def test_grid_oof_refuses_fewer_than_five_folds():
    bundle = {"sport": "toy", "X": pd.DataFrame(np.zeros((130, 2))), "y": np.zeros(130, dtype=int),
              "p_inc": np.full(130, 0.5),
              "dates": np.array([np.datetime64("2024-01-01") + np.timedelta64(i, "D")
                                 for i in range(130)])}
    with pytest.raises(ValueError, match="outer folds"):
        s108._grid_oof(bundle, k=6)
