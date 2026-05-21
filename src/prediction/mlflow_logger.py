"""
mlflow_logger.py — Lightweight MLflow wrapper for NBA prop model training.

Logs one run per stat-model training: params (stat name) and metrics
(coef, intercept, r2, n_samples).  If mlflow is not installed, all calls
are no-ops and a warning is emitted once.

Public API
----------
    log_training_run(stat, coef, intercept, r2, n)  -> None
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy import — resolved once, then cached.
_mlflow: Optional[object] = None
_mlflow_checked: bool = False
_MLFLOW_MISSING_WARNED: bool = False


def _get_mlflow() -> Optional[object]:
    """Return the mlflow module if available, else None (warns once)."""
    global _mlflow, _mlflow_checked, _MLFLOW_MISSING_WARNED
    if _mlflow_checked:
        return _mlflow
    _mlflow_checked = True
    try:
        import mlflow as _mlf
        _mlflow = _mlf
    except ImportError:
        if not _MLFLOW_MISSING_WARNED:
            logger.warning(
                "mlflow is not installed — training-run logging is disabled. "
                "Install with: pip install mlflow"
            )
            _MLFLOW_MISSING_WARNED = True
        _mlflow = None
    return _mlflow


def log_training_run(
    stat: str,
    coef: float,
    intercept: float,
    r2: float,
    n: int,
) -> None:
    """Log a single prop-model training run to MLflow.

    Creates a new MLflow run tagged with the stat name and records the
    Ridge regression output as params/metrics.  If mlflow is unavailable,
    the function is a silent no-op (warning emitted once at module load).

    Args:
        stat:       Stat identifier, e.g. 'pts', 'reb', 'ast'.
        coef:       Ridge regression coefficient.
        intercept:  Ridge regression intercept.
        r2:         Coefficient of determination on training data.
        n:          Number of training samples used.
    """
    mlf = _get_mlflow()
    if mlf is None:
        return

    try:
        with mlf.start_run(run_name=f"prop_meta_{stat}"):  # type: ignore[union-attr]
            mlf.set_tag("stat", stat)  # type: ignore[union-attr]
            mlf.log_params({"stat": stat})  # type: ignore[union-attr]
            mlf.log_metrics(  # type: ignore[union-attr]
                {
                    "coef": float(coef),
                    "intercept": float(intercept),
                    "r2": float(r2),
                    "n_samples": float(n),
                }
            )
    except Exception as exc:  # never crash the caller
        logger.warning("mlflow log_training_run(%s) failed: %s", stat, exc)
