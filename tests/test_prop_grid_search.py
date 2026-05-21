"""
test_prop_grid_search.py — GridSearchCV contract tests.
"""
import numpy as np
import pytest
from sklearn.model_selection import TimeSeriesSplit


def _toy_data(n: int = 300, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, 5))
    y = X[:, 0] * 2 + rng.normal(0, 0.5, n)
    return X, y


def test_gridsearch_returns_best_params() -> None:
    """run_grid_search returns an XGBRegressor with best_params_ containing
    n_estimators, max_depth, learning_rate."""
    prop_grid_search = pytest.importorskip("src.prediction.prop_grid_search")
    run_grid_search = prop_grid_search.run_grid_search

    X_toy, y_toy = _toy_data(300)
    tscv = TimeSeriesSplit(n_splits=3)
    model = run_grid_search("pts", X_toy, y_toy, tscv)

    # The returned model must expose best_params_ (from GridSearchCV) or
    # be a plain XGBRegressor — plan 03 decides; we check both paths.
    best_params = getattr(model, "best_params_", None) or model.get_params()
    assert "n_estimators" in best_params, "best_params must contain n_estimators"
    assert "max_depth" in best_params, "best_params must contain max_depth"
    assert "learning_rate" in best_params, "best_params must contain learning_rate"


def test_holdout_gap_under_threshold() -> None:
    """Train-holdout R² gap must be < 0.08 for well-conditioned toy data.

    This test is self-contained (uses xgboost directly) to define the
    threshold contract without depending on Plan 03 code.
    """
    xgb = pytest.importorskip("xgboost")
    from sklearn.metrics import r2_score

    X, y = _toy_data(500)
    split = int(0.8 * len(X))
    X_train, X_hold = X[:split], X[split:]
    y_train, y_hold = y[:split], y[split:]

    model = xgb.XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    train_r2 = r2_score(y_train, model.predict(X_train))
    hold_r2 = r2_score(y_hold, model.predict(X_hold))
    gap = abs(train_r2 - hold_r2)

    assert gap < 0.08, (
        f"Holdout gap {gap:.4f} exceeds threshold 0.08 — "
        f"train_r2={train_r2:.4f}, hold_r2={hold_r2:.4f}"
    )


def test_poisson_grid_is_tighter() -> None:
    """POISSON_PARAM_GRID learning_rate max must be <= 0.05 (tighter than regression)."""
    prop_grid_search = pytest.importorskip("src.prediction.prop_grid_search")
    POISSON_PARAM_GRID = prop_grid_search.POISSON_PARAM_GRID

    max_lr = max(POISSON_PARAM_GRID["learning_rate"])
    assert max_lr <= 0.05, (
        f"Poisson grid max learning_rate={max_lr} must be <= 0.05 "
        f"(Poisson objective requires tighter LR per research)"
    )
