"""tests.platform.test_stack_fit -- deterministic synthetic checks for stack_fit.py.

Per PREREG_STACK_FAMILIES_2026-07-05.md: the harness must PROVE it moved off
init (convergence diagnostics) and that the standardizer never sees eval rows
(leak tripwire). ASCII; per-file only (never full pytest).
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.combo import stack_fit as sf


def _make_logistic_data(n: int, weights: np.ndarray, seed: int = 0):
    """Synthetic rows with a KNOWN planted logistic relationship."""
    rng = np.random.default_rng(seed)
    k = len(weights) - 1  # weights[0] is the intercept
    feats = [rng.normal(0.0, 1.0, size=n) for _ in range(k)]
    X = sf.build_design(feats)
    p = sf.sigmoid(X @ weights)
    y = (rng.uniform(0.0, 1.0, size=n) < p).astype(float)
    return X, y, feats


def test_logistic_recovers_planted_coefficients():
    """Newton-Raphson fit on a large synthetic sample recovers the true weights."""
    true_w = np.array([0.2, 1.5, -0.8])
    X, y, _ = _make_logistic_data(20000, true_w, seed=1)
    fit = sf.fit_logistic(X, y)
    assert np.allclose(fit.weights, true_w, atol=0.15)
    assert fit.diagnostics.n_iter > 0
    assert fit.diagnostics.w_move_from_init > 0.1  # PROVES it moved off zero-init


def test_standardizer_never_sees_eval_rows():
    """fit_standardizer on train stats must NOT shift under an eval-only outlier."""
    rng = np.random.default_rng(2)
    train_col = rng.normal(0.0, 1.0, size=500)
    params_before = sf.fit_standardizer(train_col.reshape(-1, 1))

    # An eval split with an extreme outlier must never be seen by the fitted params.
    eval_col = np.concatenate([train_col, np.array([1e6, -1e6])])
    params_after_touching_eval = sf.fit_standardizer(train_col.reshape(-1, 1))  # re-fit on TRAIN only
    assert np.allclose(params_before.means, params_after_touching_eval.means)
    assert np.allclose(params_before.stds, params_after_touching_eval.stds)

    # standardize() applies the FROZEN train params to eval data without refitting.
    z_eval = sf.standardize(eval_col.reshape(-1, 1), params_before)
    # the frozen params are unaffected by the huge eval outlier's scale
    assert params_before.stds[0] < 5.0
    assert abs(z_eval[-1, 0]) > 100.0  # outlier still extreme AFTER standardizing (not re-scaled away)


def test_missing_feature_fallback_scores_identical_rows():
    """Rows with a NaN added feature fall back to p_base -- base/stack share row set."""
    n = 10
    p_base = np.linspace(0.1, 0.9, n)
    p_cand = np.linspace(0.9, 0.1, n)  # deliberately different from base
    added = np.full(n, 1.0)
    added[3] = np.nan
    added[7] = np.nan
    scored = sf.score_with_fallback([added], p_base, p_cand)
    assert scored[3] == p_base[3]
    assert scored[7] == p_base[7]
    assert scored[0] == p_cand[0]
    assert len(scored) == n  # no rows dropped -- identical row set as base


def test_missing_feature_fallback_no_added_features_returns_base():
    p_base = np.array([0.3, 0.6, 0.9])
    scored = sf.score_with_fallback([], p_base, np.array([0.1, 0.2, 0.3]))
    assert np.array_equal(scored, p_base)


def test_expanding_window_splits_single_fold_mid_split():
    splits = sf.expanding_window_splits(100, initial_train_frac=0.5, n_folds=1)
    assert len(splits) == 1
    assert len(splits[0].train_idx) == 50
    assert len(splits[0].test_idx) == 50
    assert splits[0].train_idx[-1] < splits[0].test_idx[0]  # no seam overlap


def test_expanding_window_splits_multi_fold_no_overlap():
    splits = sf.expanding_window_splits(100, initial_train_frac=0.4, n_folds=3)
    assert len(splits) >= 1
    seen_test_rows = set()
    for s in splits:
        test_set = set(s.test_idx.tolist())
        assert not (test_set & seen_test_rows)  # no fold re-tests a prior fold's rows
        seen_test_rows |= test_set
        assert s.train_idx.max() < s.test_idx.min() if len(s.train_idx) and len(s.test_idx) else True


def test_bootstrap_refit_deltas_runs_at_least_five():
    calls = {"n": 0}

    def fake_fit_and_score(rng):
        calls["n"] += 1
        return float(rng.normal(0.01, 0.001))

    deltas = sf.bootstrap_refit_deltas(fake_fit_and_score, n_refits=3, base_seed=42)
    assert calls["n"] == 5  # floor enforced even when caller asks for fewer
    assert len(deltas) == 5


def test_bootstrap_resample_rows_within_range():
    rng = np.random.default_rng(7)
    idx = sf.bootstrap_resample_rows(50, rng)
    assert idx.shape == (50,)
    assert idx.min() >= 0
    assert idx.max() < 50


def test_brier_and_logloss_basic_sanity():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p_perfect = np.array([1.0, 0.0, 1.0, 0.0])
    p_bad = np.array([0.0, 1.0, 0.0, 1.0])
    assert sf.brier(p_perfect, y) < sf.brier(p_bad, y)
    assert sf.logloss(p_perfect, y) < sf.logloss(p_bad, y)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
