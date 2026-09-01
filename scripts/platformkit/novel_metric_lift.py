"""Upper-bound prediction-lift screen for static candidate tracking metrics.

The candidate values are full-season player estimates, so this intentionally is
an UPPER-BOUND screen, not a shippable feature test. An as-of metric version is
required before any production claim. The target is next-game minutes and all
comparisons use the teacher-student expanding folds and train-only imputation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from scripts.platformkit.teacher_student_ab import (
    BASE_FEATURES,
    LOAD_FEATURES,
    _matrix,
    _median_impute_train_test,
    build_features,
    expanding_folds,
)
from scripts.platformkit.leak_boundary import embargo_indices


CANDIDATE_METRICS = (
    "load_speed_elasticity",
    "load_touch_elasticity",
    "contest_rest_response",
    "b2b_speed_drop",
)
SCREEN_MARGIN = 0.20
EMBARGO_BLOCKS = 1
UPPER_BOUND_CAVEAT = (
    "UPPER-BOUND ONLY: candidate metrics are full-season static estimates; "
    "an as-of version is required before any production claim."
)


def pivot_player_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long-form candidate report to one numeric row per personId."""
    player_column = "personId" if "personId" in metrics else "player"
    required = {player_column, "metric", "value"}
    if missing := required.difference(metrics.columns):
        raise ValueError("Missing metric columns: {0}".format(", ".join(sorted(missing))))
    selected = metrics.loc[metrics["metric"].isin(CANDIDATE_METRICS), [player_column, "metric", "value"]].copy()
    selected["personId"] = pd.to_numeric(selected[player_column], errors="raise").astype("int64")
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    wide = selected.pivot_table(index="personId", columns="metric", values="value", aggfunc="first")
    wide = wide.reindex(columns=CANDIDATE_METRICS)
    wide.index.name = "personId"
    return wide.reset_index()


def tracking_arm_columns(frame: pd.DataFrame) -> list[str]:
    """Return teacher-student's full tracking arm, restricted to present columns."""
    return [name for name in frame if name in BASE_FEATURES or name in LOAD_FEATURES
            or name.endswith(("_per36_l5", "_per36_l10")) or name.startswith("style_embedding_")]


def build_lift_features(tracking: pd.DataFrame, load: pd.DataFrame, embeddings: pd.DataFrame,
                        metrics: pd.DataFrame) -> pd.DataFrame:
    """Build the full tracking arm and attach static player-level candidates."""
    features = build_features(tracking, load, embeddings)
    return features.merge(pivot_player_metrics(metrics), on="personId", how="left", validate="many_to_one")


def _verdict(delta: float) -> str:
    if delta < -SCREEN_MARGIN:
        return "SCREEN-POSITIVE"
    if delta > SCREEN_MARGIN:
        return "NEGATIVE"
    return "FLAT"


def evaluate_lift(frame: pd.DataFrame, candidate_columns: Sequence[str], folds: int = 4) -> dict[str, object]:
    """Compare the full teacher-student tracking arm with added metric columns."""
    base_columns = tracking_arm_columns(frame)
    if not set(BASE_FEATURES).issubset(base_columns):
        raise ValueError("Missing baseline columns")
    candidate_columns = list(candidate_columns)
    if any(name not in frame for name in candidate_columns):
        raise ValueError("Missing candidate feature column")
    base_errors: list[float] = []
    candidate_errors: list[float] = []
    fold_reports: list[dict[str, object]] = []
    for number, (train_index, test_index) in enumerate(expanding_folds(frame, folds), start=1):
        safe = embargo_indices(frame["gameDate"], frame.iloc[test_index]["gameDate"], EMBARGO_BLOCKS)
        train_index = np.intersect1d(train_index, safe, assume_unique=True)
        train, test = frame.iloc[train_index], frame.iloc[test_index]
        y_train, y_test = train["minutes"], test["minutes"]
        base_train, base_test = _median_impute_train_test(_matrix(train, base_columns), _matrix(test, base_columns))
        candidate_train, candidate_test = _median_impute_train_test(
            _matrix(train, [*base_columns, *candidate_columns]),
            _matrix(test, [*base_columns, *candidate_columns]),
        )
        base_prediction = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(base_train, y_train).predict(base_test)
        candidate_prediction = HistGradientBoostingRegressor(max_iter=150, random_state=0).fit(candidate_train, y_train).predict(candidate_test)
        base_mae = float(mean_absolute_error(y_test, base_prediction))
        candidate_mae = float(mean_absolute_error(y_test, candidate_prediction))
        base_errors.extend(np.abs(y_test.to_numpy() - base_prediction))
        candidate_errors.extend(np.abs(y_test.to_numpy() - candidate_prediction))
        fold_reports.append({"fold": number, "mae_base": base_mae, "mae_candidate": candidate_mae,
                             "delta": candidate_mae - base_mae})
    mae_base, mae_candidate = float(np.mean(base_errors)), float(np.mean(candidate_errors))
    delta = mae_candidate - mae_base
    return {"candidate_columns": candidate_columns, "folds": fold_reports, "mae_base": mae_base,
            "mae_candidate": mae_candidate, "delta": delta, "verdict": _verdict(delta),
            "upper_bound_caveat": UPPER_BOUND_CAVEAT}


def run(data_root: Path) -> dict[str, object]:
    """Run individual and combined candidate screens and write the JSON report."""
    nba_dir = data_root / "nba"
    features = build_lift_features(
        pd.read_parquet(nba_dir / "player_tracking_features_asof.parquet"),
        pd.read_parquet(nba_dir / "player_load_state_asof.parquet"),
        pd.read_parquet(nba_dir / "player_embeddings_asof.parquet"),
        pd.read_parquet(data_root / "ab_reports" / "novel_metrics_players.parquet"),
    ).dropna(subset=["gameDate"]).sort_values(["gameDate", "gameId", "personId"], kind="mergesort").reset_index(drop=True)
    reports = {name: evaluate_lift(features, [name]) for name in CANDIDATE_METRICS}
    reports["all_four"] = evaluate_lift(features, CANDIDATE_METRICS)
    report = {"target": "next-game minutes", "upper_bound_caveat": UPPER_BOUND_CAVEAT,
              "rows_evaluated": int(len(features)), "screens": reports}
    output = data_root / "ab_reports" / "novel_metric_lift.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    """Run the offline screen and print the mandatory upper-bound caveat."""
    report = run(Path(os.environ.get("NBA_DATA_ROOT", "data")))
    print(report["upper_bound_caveat"])
    for name, screen in report["screens"].items():
        print("{0} MAE_base={1:.3f} MAE_candidate={2:.3f} delta={3:.3f} VERDICT {4}".format(
            name, screen["mae_base"], screen["mae_candidate"], screen["delta"], screen["verdict"]
        ))


if __name__ == "__main__":
    main()
