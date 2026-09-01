"""Synthetic evidence for the runtime-safe teacher/student distillation contract."""
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.teacher_student_distill import evaluate_distillation


def _frame(signal: bool, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 180
    proxy = rng.normal(size=n)
    tracking = proxy + rng.normal(scale=0.18, size=n) if signal else rng.normal(size=n)
    target = 3.0 * tracking + rng.normal(scale=2.5, size=n) if signal else np.full(n, 3.0)
    return pd.DataFrame({"gameDate": pd.date_range("2025-01-01", periods=n, freq="D"),
                         "prior_proxy": proxy, "tracking_signal": tracking, "target": target})


def test_distillation_preserves_proxyable_tracking_signal():
    report = evaluate_distillation(_frame(True), "target", ["prior_proxy"], ["tracking_signal"], folds=4)
    assert report["pooled"]["mae_student"] < report["pooled"]["mae_runtime_baseline"]
    assert report["pooled"]["verdict"] == "DISTILLATION HELPS"


def test_unrelated_teacher_signal_is_neutral_or_worse_not_claimed_as_help():
    report = evaluate_distillation(_frame(False), "target", ["prior_proxy"], ["tracking_signal"], folds=4)
    assert report["pooled"]["verdict"] in {"DISTILLATION NEUTRAL", "DISTILLATION HURTS"}


def test_training_only_student_column_aborts_loudly():
    with pytest.raises((AssertionError, ValueError), match="unsafe|runtime|Runtime"):
        evaluate_distillation(_frame(True), "target", ["prior_proxy", "tracking_signal"], ["tracking_signal"], folds=4)
