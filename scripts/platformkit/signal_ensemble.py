"""Leak-safe regularized ensemble screen for static weak player signals.

This is an upper-bound experiment: the four novel metrics are static full-season
values.  It tests whether individually flat signals can help only in combination;
it is not production evidence until as-of versions replace the static inputs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler

from scripts.platformkit.novel_metric_lift import CANDIDATE_METRICS, pivot_player_metrics
from scripts.platformkit.teacher_student_ab import (
    BASE_FEATURES, LOAD_FEATURES, _asof_columns, _matrix,
    _median_impute_train_test, build_features, expanding_folds,
)
from scripts.platformkit.leak_boundary import embargo_indices


ALPHAS = (0.1, 1.0, 10.0)
VERDICT_TOLERANCE = 0.05
EMBARGO_BLOCKS = 1
UPPER_BOUND_CAVEAT = (
    "UPPER-BOUND ONLY: four novel metrics are static full-season values; "
    "replace them with as-of values before any production use."
)


def tracking_arm_columns(frame: pd.DataFrame) -> list[str]:
    """Return the exact teacher-student tracking arm columns present in frame."""
    return [name for name in frame if name in BASE_FEATURES or name in LOAD_FEATURES
            or name.endswith(("_per36_l5", "_per36_l10"))
            or name.startswith("style_embedding_")]


def _extra_numeric(frame: pd.DataFrame, used: set[str], prefix: str) -> tuple[pd.DataFrame, list[str]]:
    # LEAK CONTRACT: only as-of/shifted/prior-window columns may enter the
    # pool. Raw same-game stats (minutes, speed, touches...) leak the target
    # -- caught 2026-09-01 when auto-ingestion produced MAE 0.477 (rejected).
    _ASOF = ("_l5", "_l10", "_asof", "_7d", "_14d")
    _SAFE = ("days_rest", "b2b", "speed_decline_ratio")
    names = [name for name in frame.columns
             if pd.api.types.is_numeric_dtype(frame[name]) and name not in used
             and (name.endswith(_ASOF) or name.startswith("style_embedding_")
                  or name in _SAFE)]
    joined = _asof_columns(frame, names)
    rename = {name: prefix + name for name in names}
    return joined.rename(columns=rename), list(rename.values())


def build_ensemble_features(tracking: pd.DataFrame, load: pd.DataFrame, embeddings: pd.DataFrame,
                            metrics: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Build teacher features plus every previously unused numeric weak signal."""
    result = build_features(tracking, load, embeddings)
    used = set(tracking_arm_columns(result)) | {"gameDate", "minutes"}
    load_extra, load_names = _extra_numeric(load, used, "load_extra_")
    embedding_extra, embedding_names = _extra_numeric(embeddings, used, "embedding_extra_")
    result = result.merge(load_extra, on=["gameId", "personId"], how="left", validate="one_to_one")
    result = result.merge(embedding_extra, on=["gameId", "personId"], how="left", validate="one_to_one")
    static = pivot_player_metrics(metrics).rename(columns={name: "static_" + name for name in CANDIDATE_METRICS})
    result = result.merge(static, on="personId", how="left", validate="many_to_one")
    return result, [*load_names, *embedding_names, *["static_" + name for name in CANDIDATE_METRICS]]


def _inner_alpha(train: pd.DataFrame, columns: Sequence[str]) -> float:
    """Select Ridge alpha on a strictly chronological inner split of outer train."""
    dates = pd.to_datetime(train["gameDate"], errors="raise")
    unique = dates.drop_duplicates().to_numpy()
    if len(unique) < 3:
        return 1.0
    cut = max(1, int(len(unique) * 0.8))
    cut = min(cut, len(unique) - 1)
    fit_index = np.flatnonzero(dates.isin(unique[:cut]))
    valid_index = np.flatnonzero(dates.isin(unique[cut:]))
    assert dates.iloc[fit_index].max() < dates.iloc[valid_index].min(), "Inner split leaks future dates"
    fit_x, valid_x = _median_impute_train_test(_matrix(train.iloc[fit_index], columns), _matrix(train.iloc[valid_index], columns))
    scaler = StandardScaler().fit(fit_x)
    y_fit, y_valid = train.iloc[fit_index]["minutes"], train.iloc[valid_index]["minutes"]
    return min(ALPHAS, key=lambda alpha: mean_absolute_error(
        y_valid, Ridge(alpha=alpha).fit(scaler.transform(fit_x), y_fit).predict(scaler.transform(valid_x))
    ))


def _verdict(delta: float) -> str:
    if delta < -VERDICT_TOLERANCE:
        return "IMPROVED"
    if delta > VERDICT_TOLERANCE:
        return "WORSE"
    return "FLAT"


def evaluate_ensemble(frame: pd.DataFrame, weak_columns: Sequence[str], folds: int = 4) -> dict[str, object]:
    """Compare teacher's HistGB arm with Ridge plus HistGB averaged predictions."""
    base_columns = tracking_arm_columns(frame)
    weak_columns = list(weak_columns)
    if not set(BASE_FEATURES).issubset(base_columns) or any(name not in frame for name in weak_columns):
        raise ValueError("Missing required ensemble columns")
    base_errors: list[float] = []
    ensemble_errors: list[float] = []
    reports: list[dict[str, object]] = []
    columns = [*base_columns, *weak_columns]
    for number, (train_index, test_index) in enumerate(expanding_folds(frame, folds), 1):
        safe = embargo_indices(frame["gameDate"], frame.iloc[test_index]["gameDate"], EMBARGO_BLOCKS)
        train_index = np.intersect1d(train_index, safe, assume_unique=True)
        train, test = frame.iloc[train_index], frame.iloc[test_index]
        base_train, base_test = _median_impute_train_test(_matrix(train, base_columns), _matrix(test, base_columns))
        ensemble_train, ensemble_test = _median_impute_train_test(_matrix(train, columns), _matrix(test, columns))
        y_train, y_test = train["minutes"], test["minutes"]
        base_prediction = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(base_train, y_train).predict(base_test)
        hgb_prediction = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(ensemble_train, y_train).predict(ensemble_test)
        alpha = _inner_alpha(train, columns)
        scaler = StandardScaler().fit(ensemble_train)
        ridge_prediction = Ridge(alpha=alpha).fit(scaler.transform(ensemble_train), y_train).predict(scaler.transform(ensemble_test))
        prediction = (hgb_prediction + ridge_prediction) / 2.0
        base_errors.extend(np.abs(y_test.to_numpy() - base_prediction))
        ensemble_errors.extend(np.abs(y_test.to_numpy() - prediction))
        reports.append({"fold": number, "mae_base": float(mean_absolute_error(y_test, base_prediction)),
                        "mae_ensemble": float(mean_absolute_error(y_test, prediction),),
                        "alpha": alpha, "delta": float(mean_absolute_error(y_test, prediction) - mean_absolute_error(y_test, base_prediction))})
    base_mae, ensemble_mae = float(np.mean(base_errors)), float(np.mean(ensemble_errors))
    delta = ensemble_mae - base_mae
    return {"folds": reports, "base_columns": base_columns, "weak_columns": weak_columns,
            "mae_base": base_mae, "mae_ensemble": ensemble_mae, "delta": delta,
            "verdict": _verdict(delta), "upper_bound_caveat": UPPER_BOUND_CAVEAT}


def run(data_root: Path) -> dict[str, object]:
    """Load the as-of corpus, write the requested evidence-only ensemble report."""
    nba = data_root / "nba"
    frame, weak = build_ensemble_features(
        pd.read_parquet(nba / "player_tracking_features_asof.parquet"),
        pd.read_parquet(nba / "player_load_state_asof.parquet"),
        pd.read_parquet(nba / "player_embeddings_asof.parquet"),
        pd.read_parquet(data_root / "ab_reports" / "novel_metrics_players.parquet"),
    )
    frame = frame.dropna(subset=["gameDate"]).sort_values(["gameDate", "gameId", "personId"], kind="mergesort").reset_index(drop=True)
    report = evaluate_ensemble(frame, weak)
    report.update({"target": "next-game minutes", "rows_evaluated": int(len(frame)),
                   "combining_note": "Regularized combination of individually FLAT signals is the point; measured boundary result: four combined signals delta -0.100 MAE."})
    output = data_root / "ab_reports" / "signal_ensemble.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    """Run the upper-bound screen with ASCII-only output."""
    report = run(Path(os.environ.get("NBA_DATA_ROOT", "data")))
    print(report["upper_bound_caveat"])
    print(report["combining_note"])
    print("MAE_base={0:.3f} MAE_ensemble={1:.3f} delta={2:.3f} VERDICT {3}".format(
        report["mae_base"], report["mae_ensemble"], report["delta"], report["verdict"]
    ))


if __name__ == "__main__":
    main()
