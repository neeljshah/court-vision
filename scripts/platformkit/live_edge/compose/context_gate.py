"""scripts.platformkit.live_edge.compose.context_gate -- COMPOSE-2 model
layer: regularized composition + context gating over compose.py's design
matrix. Two valid ways per the program rails, both built here:

(a) GBM over [baseline + raw context axis dummies] -- trees natively learn
    context-conditional splits (a claim's effect showing up only inside
    certain axis combinations), no feature-selection needed.
(b) ElasticNet with explicit baseline x context INTERACTION terms, added by
    GREEDY FORWARD SELECTION on a discovery-internal validation holdout
    (never the reserve -- exactly C1's discipline), correlation-checked at
    each add (skip |rho|>0.9 with baseline or any already-included column).

Loss = pinball @ median (same metric as C1's minutes_combiner, the spec's
CRPS-or-pinball alternative). Seeds pinned x2 (0, 42) for every fitted model.
Final gate = ONE evaluation of both tracks on the untouched reserve slice;
best of the two vs baseline-only on reserve decides the verdict.

INVARIANTS: pandas/numpy/sklearn only. <=300 LOC. ASCII stdout.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import ElasticNet

SEEDS = (0, 42)
CORR_SKIP_THRESHOLD = 0.9
MAX_GREEDY_FEATURES = 8
VAL_FRACTION = 0.2
MIN_IMPROVEMENT = 1e-4
PERM_SAMPLE_CAP = 50_000


def _pinball_median(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.where(diff >= 0, 0.5 * diff, 0.5 * -diff)))


def _fit_predict(model_name: str, X_train, y_train, X_test, seed: int):
    if model_name == "elastic_net":
        model = ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=seed, max_iter=5000)
    else:
        model = HistGradientBoostingRegressor(loss="quantile", quantile=0.5, random_state=seed, max_iter=150)
    model.fit(X_train, y_train)
    return model, model.predict(X_test)


def _internal_val_split(discovery: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Last VAL_FRACTION of discovery by game_date -- used ONLY to score
    greedy-selection candidates, never the reserve slice."""
    d = discovery.sort_values("game_date")
    cutoff_idx = int(len(d) * (1 - VAL_FRACTION))
    return d.iloc[:cutoff_idx], d.iloc[cutoff_idx:]


def greedy_select_en(discovery: pd.DataFrame, baseline_col: str, candidate_cols: list[str],
                      target_col: str, seed: int = SEEDS[0]) -> list[str]:
    """Greedy forward selection: at each step, add the candidate that most
    improves ElasticNet pinball on the internal validation holdout, subject
    to the correlation gate. Stops when no candidate improves by
    MIN_IMPROVEMENT or MAX_GREEDY_FEATURES is reached."""
    train, val = _internal_val_split(discovery)
    selected: list[str] = []
    corr_base = train[[baseline_col] + candidate_cols].corr()
    y_train, y_val = train[target_col].to_numpy(), val[target_col].to_numpy()

    def _score(cols: list[str]) -> float:
        X_train, X_val = train[[baseline_col] + cols].to_numpy(), val[[baseline_col] + cols].to_numpy()
        _, pred = _fit_predict("elastic_net", X_train, y_train, X_val, seed)
        return _pinball_median(y_val, pred)

    current_score = _score([])
    remaining = list(candidate_cols)
    while remaining and len(selected) < MAX_GREEDY_FEATURES:
        best_col, best_score = None, current_score
        for col in remaining:
            if any(abs(corr_base.loc[col, s]) > CORR_SKIP_THRESHOLD for s in selected):
                continue
            if abs(corr_base.loc[col, baseline_col]) > CORR_SKIP_THRESHOLD:
                continue
            score = _score(selected + [col])
            if score < best_score - MIN_IMPROVEMENT:
                best_col, best_score = col, score
        if best_col is None:
            break
        selected.append(best_col)
        remaining.remove(best_col)
        current_score = best_score
    return selected


def evaluate_track(discovery: pd.DataFrame, reserve: pd.DataFrame, feature_cols: list[str],
                    target_col: str, model_name: str) -> dict[str, Any]:
    """Fit on FULL discovery, evaluate once on reserve, both pinned seeds."""
    y_train, y_test = discovery[target_col].to_numpy(), reserve[target_col].to_numpy()
    per_seed = {}
    for seed in SEEDS:
        X_train, X_test = discovery[feature_cols].to_numpy(), reserve[feature_cols].to_numpy()
        _, pred = _fit_predict(model_name, X_train, y_train, X_test, seed)
        per_seed[f"seed{seed}"] = _pinball_median(y_test, pred)
    return {"features": feature_cols, "model": model_name, "per_seed_pinball": per_seed,
            "avg_pinball": float(np.mean(list(per_seed.values())))}


def permutation_attribution(discovery: pd.DataFrame, reserve: pd.DataFrame, feature_cols: list[str],
                             target_col: str, model_name: str, seed: int = SEEDS[0]) -> dict[str, float]:
    """Which claim-context features matter, via permutation importance on a
    (capped, for speed) sample of the reserve slice -- same method C1 uses,
    no new dependency."""
    X_train, y_train = discovery[feature_cols].to_numpy(), discovery[target_col].to_numpy()
    sample = reserve if len(reserve) <= PERM_SAMPLE_CAP else reserve.sample(PERM_SAMPLE_CAP, random_state=seed)
    X_test, y_test = sample[feature_cols].to_numpy(), sample[target_col].to_numpy()
    model, _ = _fit_predict(model_name, X_train, y_train, X_test, seed)
    perm = permutation_importance(model, X_test, y_test, n_repeats=5, random_state=seed,
                                   scoring="neg_mean_absolute_error")
    return dict(zip(feature_cols, (float(v) for v in perm.importances_mean)))


__all__ = ["SEEDS", "CORR_SKIP_THRESHOLD", "MAX_GREEDY_FEATURES", "greedy_select_en",
           "evaluate_track", "permutation_attribution", "_pinball_median", "_fit_predict",
           "_internal_val_split"]
