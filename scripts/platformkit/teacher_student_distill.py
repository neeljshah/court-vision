"""Distil tracking-aware forecasts into a video-free runtime student.

If ``runtime_contract`` has not landed yet, a deliberately small fallback
rejects columns whose names describe training-only or tracking inputs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from scripts.platformkit.teacher_student_ab import (
    BASE_FEATURES, LOAD_FEATURES, build_features, diagnose, expanding_folds,
    _matrix as ab_matrix,
)

try:
    from scripts.platformkit.runtime_contract import assert_runtime_safe
    RUNTIME_CONTRACT_SOURCE = "runtime_contract"
except ImportError:  # The contract is being introduced alongside this module.
    RUNTIME_CONTRACT_SOURCE = "local minimal allowlist"

    def assert_runtime_safe(columns: Sequence[str]) -> None:
        """Reject obvious non-runtime inputs until runtime_contract is present."""
        banned = ("tracking", "video", "embedding", "per36", "cum_", "speed_",
                  "training", "target", "label", "future", "teacher")
        unsafe = [name for name in columns if any(word in name.lower() for word in banned)]
        if unsafe:
            raise ValueError("Runtime student contains unsafe columns: {0}".format(unsafe))


def _impute(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return train.fillna(train.median().fillna(0.0)), test.fillna(train.median().fillna(0.0))


def _model(x: pd.DataFrame, y: pd.Series) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(max_iter=120, min_samples_leaf=8, random_state=0).fit(x, y)


def _oof_teacher(frame: pd.DataFrame, columns: Sequence[str], target: str) -> pd.Series:
    """Return chronological teacher OOF forecasts, never in-sample labels."""
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    # Three expanding predictions leave an initial warm-up block intentionally unused.
    for train_i, test_i in expanding_folds(frame, folds=3):
        train, test = _impute(ab_matrix(frame.iloc[train_i], columns), ab_matrix(frame.iloc[test_i], columns))
        result.iloc[test_i] = _model(train, frame.iloc[train_i][target]).predict(test)
    return result


def _weight(y: np.ndarray, teacher_student: np.ndarray, truth_student: np.ndarray) -> float:
    weights = np.linspace(0.0, 1.0, 21)
    return float(min(weights, key=lambda w: mean_absolute_error(y, w * teacher_student + (1.0 - w) * truth_student)))


def evaluate_distillation(frame: pd.DataFrame, target: str, runtime_columns: Sequence[str],
                          tracking_columns: Sequence[str], folds: int = 4) -> dict[str, object]:
    """Evaluate teacher, distilled student, and runtime-only baseline on shared folds."""
    assert_runtime_safe(list(runtime_columns))
    if not tracking_columns:
        raise ValueError("Teacher needs at least one tracking-derived column")
    all_teacher = [*runtime_columns, *tracking_columns]
    rows: list[dict[str, object]] = []
    teacher_errors: list[float] = []
    student_errors: list[float] = []
    baseline_errors: list[float] = []
    for number, (train_i, test_i) in enumerate(expanding_folds(frame, folds), 1):
        train_frame, test_frame = frame.iloc[train_i].reset_index(drop=True), frame.iloc[test_i].reset_index(drop=True)
        y_train, y_test = train_frame[target], test_frame[target].to_numpy()
        teacher_oof = _oof_teacher(train_frame, all_teacher, target)
        usable = teacher_oof.notna()
        if usable.sum() < 8:
            raise ValueError("Need enough chronological OOF teacher predictions for distillation")
        rt_train, rt_test = _impute(ab_matrix(train_frame, runtime_columns), ab_matrix(test_frame, runtime_columns))
        te_train, te_test = _impute(ab_matrix(train_frame, all_teacher), ab_matrix(test_frame, all_teacher))
        teacher = _model(te_train, y_train)
        baseline = _model(rt_train, y_train)
        truth_student = _model(rt_train.iloc[np.flatnonzero(usable)], y_train.iloc[np.flatnonzero(usable)])
        mimic_student = _model(rt_train.iloc[np.flatnonzero(usable)], teacher_oof.loc[usable])
        # The last OOF block is an inner, train-only blend-selection split.
        validation = np.flatnonzero(usable)[-max(4, int(usable.sum() // 4)):]
        fit = np.setdiff1d(np.flatnonzero(usable), validation)
        if len(fit) >= 8:
            blend_truth = _model(rt_train.iloc[fit], y_train.iloc[fit]).predict(rt_train.iloc[validation])
            blend_mimic = _model(rt_train.iloc[fit], teacher_oof.iloc[fit]).predict(rt_train.iloc[validation])
            weight = _weight(y_train.iloc[validation].to_numpy(), blend_mimic, blend_truth)
        else:
            weight = 0.5
        teacher_pred = teacher.predict(te_test)
        base_pred = baseline.predict(rt_test)
        student_pred = weight * mimic_student.predict(rt_test) + (1.0 - weight) * truth_student.predict(rt_test)
        teacher_errors.extend(np.abs(y_test - teacher_pred))
        baseline_errors.extend(np.abs(y_test - base_pred))
        student_errors.extend(np.abs(y_test - student_pred))
        rows.append({"fold": number, "rows": int(len(test_i)), "blend_teacher_weight": weight,
                     "mae_teacher": float(mean_absolute_error(y_test, teacher_pred)),
                     "mae_student": float(mean_absolute_error(y_test, student_pred)),
                     "mae_runtime_baseline": float(mean_absolute_error(y_test, base_pred))})
    teacher_mae, student_mae, baseline_mae = map(float, map(np.mean, (teacher_errors, student_errors, baseline_errors)))
    delta = student_mae - baseline_mae
    verdict = "DISTILLATION HELPS" if delta < -1e-6 else "DISTILLATION HURTS" if delta > 1e-6 else "DISTILLATION NEUTRAL"
    return {"runtime_contract": RUNTIME_CONTRACT_SOURCE, "runtime_columns": list(runtime_columns),
            "tracking_columns": list(tracking_columns), "folds": rows,
            "pooled": {"mae_teacher": teacher_mae, "mae_student": student_mae,
                       "mae_runtime_baseline": baseline_mae, "student_minus_baseline": delta,
                       "verdict": verdict}}


def run(data_root: Path) -> dict[str, object]:
    """Run minutes distillation and write the evidence-only JSON artifact."""
    nba = data_root / "nba"
    tracking = pd.read_parquet(nba / "player_tracking_features_asof.parquet")
    load = pd.read_parquet(nba / "player_load_state_asof.parquet")
    embeddings = pd.read_parquet(nba / "player_embeddings_asof.parquet")
    frame = build_features(tracking, load, embeddings).dropna(subset=["gameDate", "minutes"])
    # Load-state values can be made without video, unlike tracking and embeddings.
    # Keep this manifest explicit and validate it above.  Historical minutes
    # features are intentionally excluded until the live contract classifies
    # their source; ``days_rest`` is available from the schedule feed.
    runtime_columns = [name for name in ("days_rest",) if name in frame]
    tracking_columns = [name for name in frame if (name.endswith(("_per36_l5", "_per36_l10"))
                        or name.startswith("style_embedding_") or name in LOAD_FEATURES)
                        and name not in runtime_columns]
    report = evaluate_distillation(frame, "minutes", runtime_columns, tracking_columns)
    report["rows_evaluated"] = int(len(frame))
    report["tracking_coverage_pct"] = min(float(diagnose(frame, source)["pair_coverage_pct"])
                                            for source in (tracking, load, embeddings))
    output = data_root / "ab_reports" / "distillation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    report = run(Path(os.environ.get("NBA_DATA_ROOT", "./data")))
    pooled = report["pooled"]
    print("MAE_teacher={0:.3f} MAE_student={1:.3f} MAE_runtime_baseline={2:.3f} delta={3:.3f} {4}".format(
        pooled["mae_teacher"], pooled["mae_student"], pooled["mae_runtime_baseline"],
        pooled["student_minus_baseline"], pooled["verdict"]))


if __name__ == "__main__":
    main()
