"""
test_mlflow_logger.py — Integration tests for src/prediction/mlflow_logger.py.

Coverage
--------
1. Module imports cleanly.
2. log_training_run() is a no-op (no crash) when mlflow is absent.
3. When mlflow IS available, a run is created, tagged with the correct stat,
   and metrics are logged with the expected values.
4. Multiple calls create independent runs (no state leak between stats).
5. train_all_meta() in prop_model_stack calls log_training_run for every stat.
"""
from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _reload_logger():
    """Force a fresh import of mlflow_logger (resets module-level cache)."""
    mod_name = "src.prediction.mlflow_logger"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


# ── Test 1: importable ────────────────────────────────────────────────────────

def test_mlflow_logger_importable() -> None:
    """mlflow_logger imports cleanly regardless of mlflow availability."""
    from src.prediction import mlflow_logger  # noqa: F401
    assert hasattr(mlflow_logger, "log_training_run")


# ── Test 2: graceful no-op when mlflow absent ─────────────────────────────────

def test_log_training_run_noop_when_mlflow_absent() -> None:
    """log_training_run() does not raise when mlflow is not installed."""
    with patch.dict(sys.modules, {"mlflow": None}):
        logger_mod = _reload_logger()
        # Should not raise
        logger_mod.log_training_run(
            stat="pts",
            coef=1.05,
            intercept=-0.3,
            r2=0.85,
            n=120,
        )


# ── Test 3: run created with correct stat tag when mlflow present ─────────────

def test_log_training_run_creates_run_with_stat_tag() -> None:
    """When mlflow is available, a run is started and stat tag is set."""
    mock_mlflow = MagicMock()
    run_ctx = MagicMock()
    mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=run_ctx)
    mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

    with patch.dict(sys.modules, {"mlflow": mock_mlflow}):
        logger_mod = _reload_logger()
        logger_mod.log_training_run(
            stat="reb",
            coef=0.98,
            intercept=0.15,
            r2=0.72,
            n=200,
        )

    mock_mlflow.start_run.assert_called_once_with(run_name="prop_meta_reb")
    mock_mlflow.set_tag.assert_called_once_with("stat", "reb")
    mock_mlflow.log_params.assert_called_once_with({"stat": "reb"})
    mock_mlflow.log_metrics.assert_called_once_with(
        {
            "coef": 0.98,
            "intercept": 0.15,
            "r2": 0.72,
            "n_samples": 200.0,
        }
    )


# ── Test 4: multiple calls are independent ────────────────────────────────────

def test_log_training_run_multiple_stats_independent() -> None:
    """Each call to log_training_run creates its own run with the correct stat."""
    mock_mlflow = MagicMock()
    ctx = MagicMock()
    mock_mlflow.start_run.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_mlflow.start_run.return_value.__exit__ = MagicMock(return_value=False)

    with patch.dict(sys.modules, {"mlflow": mock_mlflow}):
        logger_mod = _reload_logger()
        for stat in ("pts", "ast", "blk"):
            logger_mod.log_training_run(
                stat=stat, coef=1.0, intercept=0.0, r2=0.5, n=50
            )

    assert mock_mlflow.start_run.call_count == 3
    run_names = [c.kwargs.get("run_name") or c.args[0] if c.args else c.kwargs["run_name"]
                 for c in mock_mlflow.start_run.call_args_list]
    # start_run called with keyword arg run_name
    run_names = [c[1]["run_name"] if c[1] else c[0][0]
                 for c in mock_mlflow.start_run.call_args_list]
    assert "prop_meta_pts" in run_names
    assert "prop_meta_ast" in run_names
    assert "prop_meta_blk" in run_names


# ── Test 5: train_all_meta calls log_training_run for each stat ───────────────

def test_train_all_meta_calls_log_for_each_stat(tmp_path, monkeypatch) -> None:
    """train_all_meta() invokes log_training_run once per stat (7 calls total)."""
    import src.prediction.prop_model_stack as stack_mod
    import src.prediction.mlflow_logger as logger_mod

    # Patch train_meta to avoid needing residuals data
    def _fake_train_meta(stat, residuals=None):
        return {"stat": stat, "coef": 1.0, "intercept": 0.0, "n": 50, "r2": 0.5}

    monkeypatch.setattr(stack_mod, "train_meta", _fake_train_meta)

    logged: list = []

    def _fake_log(stat, coef, intercept, r2, n):
        logged.append(stat)

    monkeypatch.setattr(logger_mod, "log_training_run", _fake_log)

    results = stack_mod.train_all_meta()

    assert len(results) == 7
    assert set(logged) == set(stack_mod.STATS), (
        f"Expected all 7 stats logged, got: {logged}"
    )
