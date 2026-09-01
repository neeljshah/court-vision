"""Combinatorial purged cross-validation (Lopez de Prado) for the harness.

Instead of one train/test verdict this produces MANY paths from combinations of
date-groups, so the output is a DISTRIBUTION of scores rather than a single
number.  Train rows sharing a date with any test group are purged, and the
first ``embargo_blocks`` distinct dates after each test group are embargoed --
same date-block embargo unit as ``signal_foundry.EMBARGO_BLOCKS``.

This is measurement tooling: it reports calibration/accuracy distributions and
an overfitting probability, never a betting-edge or profit claim.
"""
from __future__ import annotations

import itertools
from typing import Callable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error

from scripts.platformkit.signal_foundry import _design, _impute

Split = tuple[np.ndarray, np.ndarray]
ModelFactory = Callable[[], object]


def default_model() -> Ridge:
    """Return the same plain Ridge the foundry uses as its baseline learner."""
    return Ridge(alpha=1.0)


def cpcv_splits(dates: Sequence[object] | pd.Series, n_groups: int = 6, n_test_groups: int = 2,
                embargo_blocks: int = 1) -> Iterator[Split]:
    """Yield purged and embargoed (train_idx, test_idx) paths over date-groups.

    ``dates`` are positional row dates; groups are contiguous blocks of DISTINCT
    dates, so a date never straddles a group boundary.  Every combination of
    ``n_test_groups`` groups becomes one path.
    """
    if n_groups < 2:
        raise ValueError("n_groups must be at least 2")
    if not 1 <= n_test_groups < n_groups:
        raise ValueError("n_test_groups must be in [1, n_groups)")
    if embargo_blocks < 0:
        raise ValueError("embargo_blocks must be non-negative")
    stamps = pd.to_datetime(pd.Series(list(dates)), errors="raise").reset_index(drop=True)
    unique = np.sort(stamps.drop_duplicates().to_numpy())
    if len(unique) < n_groups:
        raise ValueError("Need at least {0} distinct dates for {0} groups".format(n_groups))
    blocks = np.array_split(unique, n_groups)
    positions = np.arange(len(stamps))
    yielded = 0
    for combo in itertools.combinations(range(n_groups), n_test_groups):
        test_dates = np.concatenate([blocks[group] for group in combo])
        blocked = list(test_dates)
        for group in combo:
            blocked.extend(unique[unique > blocks[group][-1]][:embargo_blocks])
        in_test = stamps.isin(test_dates).to_numpy()
        in_blocked = stamps.isin(np.asarray(blocked, dtype=unique.dtype)).to_numpy()
        train_index, test_index = positions[~in_blocked], positions[in_test]
        if train_index.size == 0 or test_index.size == 0:
            continue
        yielded += 1
        yield train_index, test_index
    if yielded == 0:
        raise ValueError("No usable CPCV path; widen the corpus or shrink the embargo")


def _fit_score(matrix: pd.DataFrame, target: str, columns: Sequence[str], train_index: np.ndarray,
               test_index: np.ndarray, model_factory: ModelFactory) -> tuple[float, float]:
    """Fit one feature set on train and return its (in-sample, out-of-sample) MAE."""
    x_train, x_test = _impute(_design(matrix.iloc[train_index], columns), _design(matrix.iloc[test_index], columns))
    y_train = pd.to_numeric(matrix.iloc[train_index][target], errors="raise").to_numpy()
    y_test = pd.to_numeric(matrix.iloc[test_index][target], errors="raise").to_numpy()
    model = model_factory().fit(x_train, y_train)
    return (float(mean_absolute_error(y_train, model.predict(x_train))),
            float(mean_absolute_error(y_test, model.predict(x_test))))


def _check(matrix: pd.DataFrame, target: str, columns: Sequence[str]) -> list[str]:
    """Validate that the target and every requested feature column exist."""
    if target not in matrix:
        raise ValueError("Missing target: {0}".format(target))
    missing = [name for name in columns if name != "__intercept__" and name not in matrix]
    if missing:
        raise ValueError("Missing feature columns: {0}".format(missing))
    return list(columns) or ["__intercept__"]


def evaluate_paths(matrix: pd.DataFrame, target: str, feature_cols: Sequence[str], splits: Sequence[Split],
                   model_factory: ModelFactory = default_model,
                   baseline_cols: Sequence[str] | None = None) -> dict[str, object]:
    """Score every CPCV path and summarise the resulting verdict DISTRIBUTION.

    ``lift`` is baseline MAE minus candidate MAE per path (positive = the
    candidate feature set predicts the target more accurately on that path).
    Scale the features inside ``model_factory`` (e.g. a Pipeline) if the learner
    needs it -- nothing is scaled here.
    """
    candidate = _check(matrix, target, feature_cols)
    baseline = _check(matrix, target, baseline_cols if baseline_cols is not None else ["__intercept__"])
    paths: list[dict[str, float]] = []
    for number, (train_index, test_index) in enumerate(splits):
        _, base_oos = _fit_score(matrix, target, baseline, train_index, test_index, model_factory)
        _, cand_oos = _fit_score(matrix, target, candidate, train_index, test_index, model_factory)
        paths.append({"path": number, "n_train": int(len(train_index)), "n_test": int(len(test_index)),
                      "mae_baseline": base_oos, "mae_candidate": cand_oos, "lift": base_oos - cand_oos})
    if not paths:
        raise ValueError("No CPCV paths to evaluate")
    lifts = np.asarray([item["lift"] for item in paths], dtype=float)
    return {"paths": paths, "n_paths": len(paths),
            "median_lift": float(np.median(lifts)),
            "p10_lift": float(np.percentile(lifts, 10)),
            "p90_lift": float(np.percentile(lifts, 90)),
            "median_mae": float(np.median([item["mae_candidate"] for item in paths])),
            "share_improving": float(np.mean(lifts > 0.0))}


def probability_of_backtest_overfitting(matrix: pd.DataFrame, target: str,
                                        feature_sets: Mapping[str, Sequence[str]], splits: Sequence[Split],
                                        model_factory: ModelFactory = default_model) -> dict[str, object]:
    """Estimate PBO: how often the in-sample-best feature set lands below the OOS median.

    Keep the candidate feature sets the same size -- a larger set wins in-sample
    almost mechanically, which biases the selection step rather than the metric.
    """
    names = list(feature_sets)
    if len(names) < 2:
        raise ValueError("PBO needs at least 2 candidate feature sets")
    columns = {name: _check(matrix, target, feature_sets[name]) for name in names}
    ranks: list[float] = []
    picks: list[str] = []
    for train_index, test_index in splits:
        scored = {name: _fit_score(matrix, target, columns[name], train_index, test_index, model_factory)
                  for name in names}
        best = min(names, key=lambda name: scored[name][0])
        oos = pd.Series({name: scored[name][1] for name in names})
        # rank 1 = lowest OOS MAE = best; map to [0, 1] where 0 is best.
        relative = (oos.rank(method="average")[best] - 1.0) / (len(names) - 1.0)
        ranks.append(float(relative))
        picks.append(best)
    if not ranks:
        raise ValueError("No CPCV paths to evaluate")
    values = np.asarray(ranks, dtype=float)
    return {"pbo": float(np.mean(values > 0.5)), "n_paths": len(ranks), "n_sets": len(names),
            "relative_ranks": ranks, "is_best_per_path": picks,
            "median_relative_rank": float(np.median(values))}
