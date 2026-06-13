"""drift_report_compute.py — Rolling-window aggregators for drift_report.

Extracted from drift_report.py (N-OBS-003).  Contains the three higher-level
compute functions that aggregate over DataFrames / log dicts:

    * _compute_point_metrics    — per-stat Brier/MSE/bias/PIT from calibration_frame
    * _compute_coverage_metrics — per-stat interval coverage from cal_history
    * _compute_drift_summary    — feature-importance drift detection from drift_log

These functions depend on the primitive scorers in drift_report_metrics.py.
Python 3.9 compatible.  No torch / GPU imports.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from drift_report_metrics import (
    _brier_binary,
    _brier_raw,
    _pit_uniformity,
)

log = logging.getLogger(__name__)

# Thresholds — keep in sync with drift_report.py
COVERAGE_TOLERANCE: float = 0.03
ROLLING_WINDOW_DAYS: int = 30


# ---------------------------------------------------------------------------
# Point-metric rolling window computations from calibration_frame
# ---------------------------------------------------------------------------


def _compute_point_metrics(
    df: Any,
    window_days: int = ROLLING_WINDOW_DAYS,
) -> Dict[str, Any]:
    """Compute per-stat rolling-window Brier, MSE, bias, and PIT from calibration_frame.

    Args:
        df:          calibration_frame DataFrame (cols: date, stat, pred, actual).
        window_days: Rolling lookback in days from the most-recent date in df.

    Returns:
        Dict with keys: window_days, n_total, as_of_date, per_stat, flags.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        df["_date"] = pd.to_datetime(df["date"], errors="coerce")
        latest_date = df["_date"].max()
        cutoff = latest_date - pd.Timedelta(days=window_days)
        sub = df[df["_date"] >= cutoff].copy()

        per_stat: Dict[str, Any] = {}
        flags: List[str] = []

        for stat, grp in sub.groupby("stat"):
            pred = grp["pred"].values
            actual = grp["actual"].values
            mask = np.isfinite(pred) & np.isfinite(actual)
            n = int(mask.sum())
            if n == 0:
                continue

            mse = _brier_raw(pred[mask], actual[mask])
            rmse = float(mse ** 0.5) if mse == mse else float("nan")
            bias = float(np.mean(pred[mask] - actual[mask]))
            # PIT: normalise residuals by sigma if available
            if "sigma" in grp.columns and grp["sigma"].notna().sum() > n * 0.5:
                sigma = grp["sigma"].values[mask]
                sigma_safe = np.where(sigma > 0, sigma, float("nan"))
                residuals = (actual[mask] - pred[mask]) / sigma_safe
            else:
                # Fall back to dividing by per-stat MAE as proxy sigma
                mae = float(np.mean(np.abs(pred[mask] - actual[mask])))
                sigma_proxy = mae if mae > 0 else 1.0
                residuals = (actual[mask] - pred[mask]) / sigma_proxy

            pit = _pit_uniformity(residuals)
            brier_bin = _brier_binary(pred[mask], actual[mask])

            per_stat[str(stat)] = {
                "n": n,
                "rmse": round(rmse, 4),
                "bias": round(bias, 4),
                "mse": round(mse, 4),
                "brier_binary": round(brier_bin, 4) if brier_bin == brier_bin else None,
                "pit": pit,
            }

            if pit.get("flag") == "non_uniform":
                flags.append(f"{stat}: PIT non-uniform (p={pit.get('p_value'):.3f})")
            if abs(bias) > 0.5:
                flags.append(f"{stat}: bias={bias:.3f} (|bias|>0.5)")

        return {
            "window_days": window_days,
            "n_total": int(len(sub)),
            "as_of_date": str(latest_date.date()) if pd.notna(latest_date) else "unknown",
            "per_stat": per_stat,
            "flags": flags,
        }
    except Exception as exc:
        log.warning("_compute_point_metrics failed: %s", exc)
        return {"window_days": window_days, "n_total": 0, "per_stat": {}, "flags": [],
                "error": str(exc)}


# ---------------------------------------------------------------------------
# Interval coverage from prop_calibration_history
# ---------------------------------------------------------------------------


def _compute_coverage_metrics(df: Any) -> Dict[str, Any]:
    """Compute per-stat interval coverage from prop_calibration_history.

    Args:
        df: prop_calibration_history DataFrame with cols:
            stat, n_interval, interval_coverage, interval_nominal.

    Returns:
        Dict with per_stat coverage info and overall flags.
    """
    try:
        import numpy as np  # noqa: PLC0415

        required = {"stat", "n_interval", "interval_coverage", "interval_nominal"}
        missing = required - set(df.columns)
        if missing:
            return {"per_stat": {}, "flags": [f"missing cols: {missing}"]}

        per_stat: Dict[str, Any] = {}
        flags: List[str] = []

        for stat, grp in df.groupby("stat"):
            # Weight by n_interval if multiple player rows
            n_total = int(grp["n_interval"].sum())
            if n_total == 0:
                continue
            weighted_cov = float(
                (grp["interval_coverage"] * grp["n_interval"]).sum() / n_total
            )
            # Use the first nominal value (should be uniform per stat)
            nominal = float(grp["interval_nominal"].iloc[0])
            gap = weighted_cov - nominal

            status = "ok"
            if abs(gap) > COVERAGE_TOLERANCE:
                status = "too_tight" if gap < 0 else "too_wide"
                flags.append(
                    f"{stat}: coverage={weighted_cov:.3f} vs nominal={nominal:.2f} "
                    f"(gap={gap:+.3f}, {status})"
                )

            per_stat[str(stat)] = {
                "n": n_total,
                "coverage": round(weighted_cov, 4),
                "nominal": round(nominal, 4),
                "gap": round(gap, 4),
                "status": status,
            }

        return {"per_stat": per_stat, "flags": flags}
    except Exception as exc:
        log.warning("_compute_coverage_metrics failed: %s", exc)
        return {"per_stat": {}, "flags": [], "error": str(exc)}


# ---------------------------------------------------------------------------
# Feature drift summary from existing DriftDetector log
# ---------------------------------------------------------------------------


def _compute_drift_summary(drift_log: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap DriftDetector.check_drift() for all models in the log.

    Reads the log file directly to avoid any heavy imports; mirrors the
    logic in src/prediction/drift_detector.DriftDetector.check_drift().

    Args:
        drift_log: Raw dict loaded from feature_drift_log.json.

    Returns:
        Dict with model_count, flagged_models, flags list.
    """
    try:
        import numpy as np  # noqa: PLC0415

        flagged_models: List[str] = []
        flags: List[str] = []
        model_count = len(drift_log)

        for model_id, history in drift_log.items():
            if not isinstance(history, list) or len(history) < 2:
                continue
            snapshots = [h.get("importances", {}) for h in history]
            all_features: set = set()
            for s in snapshots:
                all_features.update(s.keys())

            drifted = []
            for feat in all_features:
                vals = [float(s.get(feat, 0.0)) for s in snapshots[:-1]]
                current = float(snapshots[-1].get(feat, 0.0))
                if len(vals) >= 2:
                    mean_v = float(np.mean(vals))
                    std_v = float(np.std(vals))
                    if std_v > 0 and abs(current - mean_v) / std_v > 2.0:
                        drifted.append(feat)
                elif vals:
                    baseline = float(vals[0])
                    if baseline > 0.001 and (baseline - current) / baseline > 0.30:
                        drifted.append(feat)

            if drifted:
                flagged_models.append(model_id)
                flags.append(
                    f"model '{model_id}': {len(drifted)} drifted features "
                    f"({', '.join(drifted[:3])}{'…' if len(drifted) > 3 else ''})"
                )

        return {
            "model_count": model_count,
            "flagged_models": flagged_models,
            "n_flagged": len(flagged_models),
            "flags": flags,
        }
    except Exception as exc:
        log.warning("_compute_drift_summary failed: %s", exc)
        return {"model_count": 0, "flagged_models": [], "n_flagged": 0, "flags": [],
                "error": str(exc)}
