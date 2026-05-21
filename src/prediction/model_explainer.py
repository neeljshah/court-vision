"""Model explainability via SHAP (if available) or permutation/coefficient fallback."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

_SHAP_AVAILABLE: bool = False
try:
    import shap  # type: ignore
    _SHAP_AVAILABLE = True
except ImportError:
    pass

_REPORT_DIR = os.path.join("data", "models")
_PRUNE_THRESHOLD = 0.001


def _importance_via_shap(model: Any, X: np.ndarray) -> np.ndarray:
    """Return mean absolute SHAP values per feature."""
    try:
        explainer = shap.Explainer(model, X)
        shap_values = explainer(X)
        vals = shap_values.values
        if vals.ndim == 3:          # multi-class: (n_samples, n_features, n_classes)
            vals = np.abs(vals).mean(axis=(0, 2))
        else:                        # regression / binary: (n_samples, n_features)
            vals = np.abs(vals).mean(axis=0)
        return vals
    except Exception as exc:        # noqa: BLE001
        logger.warning("SHAP Explainer failed (%s); falling back to permutation.", exc)
        return None  # type: ignore[return-value]


def _importance_via_coefficients(model: Any, n_features: int) -> Optional[np.ndarray]:
    """Return absolute coefficient magnitudes for linear models."""
    for attr in ("coef_",):
        coef = getattr(model, attr, None)
        if coef is not None:
            arr = np.abs(np.asarray(coef))
            if arr.ndim > 1:
                arr = arr.mean(axis=0)
            if arr.shape[0] == n_features:
                return arr / (arr.sum() + 1e-12)
    return None


def _importance_via_tree(model: Any, n_features: int) -> Optional[np.ndarray]:
    """Return normalised feature_importances_ from tree-based models."""
    fi = getattr(model, "feature_importances_", None)
    if fi is not None and np.asarray(fi).shape[0] == n_features:
        arr = np.asarray(fi, dtype=float)
        total = arr.sum()
        return arr / (total + 1e-12)
    return None


def _importance_via_permutation(
    model: Any,
    X: np.ndarray,
    n_repeats: int = 5,
    random_state: int = 42,
) -> np.ndarray:
    """Permutation importance: normalised mean drop in model score."""
    rng = np.random.default_rng(random_state)
    n_features = X.shape[1]

    def _score(Xm: np.ndarray) -> float:
        try:
            proba = getattr(model, "predict_proba", None)
            if proba is not None:
                p = proba(Xm)
                # use mean max-probability as a proxy for "confidence"
                return float(np.mean(np.max(p, axis=1)))
            return float(np.mean(model.predict(Xm)))
        except Exception:  # noqa: BLE001
            return 0.0

    baseline = _score(X)
    importances = np.zeros(n_features, dtype=float)
    for col in range(n_features):
        drops: List[float] = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            X_perm[:, col] = rng.permutation(X_perm[:, col])
            drops.append(baseline - _score(X_perm))
        importances[col] = float(np.mean(drops))

    # clip negatives (permuting a useless feature can yield tiny positive score)
    importances = np.clip(importances, 0.0, None)
    total = importances.sum()
    if total > 0:
        importances /= total
    return importances


def explain_model(
    model: Any,
    X: np.ndarray,
    feature_names: Sequence[str],
    model_name: str,
    prune_threshold: float = _PRUNE_THRESHOLD,
) -> Dict[str, Any]:
    """Compute per-feature importance for *model* and persist a JSON report.

    Priority: SHAP → tree importances → coefficient magnitude → permutation.

    Parameters
    ----------
    model:
        A fitted sklearn-compatible estimator.
    X:
        Feature matrix (n_samples, n_features) as a numpy array.
    feature_names:
        Ordered list of feature names matching X columns.
    model_name:
        Base name used for the output file
        ``data/models/{model_name}_shap_report.json``.
    prune_threshold:
        Features whose normalised importance is below this value are
        flagged as ``prune_candidates``.

    Returns
    -------
    dict
        ``importances``: {feature: float}, ``prune_candidates``: [str],
        ``method``: str, ``model_name``: str.
    """
    X_arr = np.asarray(X, dtype=float)
    n_features = X_arr.shape[1]
    names: List[str] = list(feature_names)

    if len(names) != n_features:
        raise ValueError(
            f"feature_names length {len(names)} != X columns {n_features}"
        )

    method = "unknown"
    importances: Optional[np.ndarray] = None

    # 1. SHAP
    if _SHAP_AVAILABLE:
        importances = _importance_via_shap(model, X_arr)
        if importances is not None:
            method = "shap"

    # 2. Tree importances
    if importances is None:
        importances = _importance_via_tree(model, n_features)
        if importances is not None:
            method = "tree_importances"

    # 3. Coefficient magnitude
    if importances is None:
        importances = _importance_via_coefficients(model, n_features)
        if importances is not None:
            method = "coefficient_magnitude"

    # 4. Permutation (final fallback)
    if importances is None:
        importances = _importance_via_permutation(model, X_arr)
        method = "permutation"

    importance_map: Dict[str, float] = {
        name: float(importances[i]) for i, name in enumerate(names)
    }
    prune_candidates: List[str] = [
        name for name, val in importance_map.items() if val < prune_threshold
    ]

    report: Dict[str, Any] = {
        "model_name": model_name,
        "method": method,
        "shap_available": _SHAP_AVAILABLE,
        "importances": importance_map,
        "prune_candidates": prune_candidates,
        "prune_threshold": prune_threshold,
    }

    os.makedirs(_REPORT_DIR, exist_ok=True)
    out_path = os.path.join(_REPORT_DIR, f"{model_name}_shap_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    logger.info("Explainability report written to %s (method=%s)", out_path, method)

    return report
