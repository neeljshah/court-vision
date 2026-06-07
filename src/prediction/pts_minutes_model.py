"""pts_minutes_model.py — Two-stage PTS pregame model (gated, default-OFF).

Gated by env flag CV_PREGAME_PTS_MINMODEL (default OFF = byte-identical to
the baseline for any caller that never touches this module).

Decomposes PTS volume into:
    pred_pts = mu_min(row) * r_pts(row)

where:
  mu_min  = E[MIN  | minutes/context features]   — minutes head
  r_pts   = E[PTS/MIN | rate features]            — scoring-rate head

Both heads are LGBM regressors trained only on the training slice of each
walk-forward fold (no look-ahead). The rate head trains on rows with MIN>=8
to avoid noisy rate estimates for DNP-adjacent games.

Public API
----------
    is_enabled()                            -> bool
    train_pts_minmodel(rows_train) -> artifact (opaque dict)
    predict_pts_minmodel(artifact, row) -> float
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    """Return True when CV_PREGAME_PTS_MINMODEL=1 is set in the environment."""
    return os.environ.get("CV_PREGAME_PTS_MINMODEL", "").strip() in ("1", "true", "True", "yes", "YES")


# ---------------------------------------------------------------------------
# Feature sets
# ---------------------------------------------------------------------------

# Minutes head: context features that correlate with how long a player will play.
# All are lag-based (computed from prior games) or structural context — no leak.
_MIN_FEATURES: List[str] = [
    "l5_min", "l10_min", "std_min", "ewma_min", "prev_min",
    "rest_days", "is_b2b", "is_b3b",
    "days_since_last_game", "games_since_long_absence",
    "games_played", "is_home",
]

# Rate head: minutes-invariant usage/efficiency features.
# Raw per-minute ratios are computed in _safe_rate() below.
_RATE_BASE_FEATURES: List[str] = [
    "bbref_usg_pct", "bbref_ts_pct", "bbref_three_par", "bbref_ftr",
    "pts_share_3pt",
    "opp_def_pts",
]

# Computed rate-ratio feature names (built at training time from row dict).
_RATE_RATIO_NAMES: List[str] = [
    "l5_pts_per_min",
    "l10_pts_per_min",
    "ewma_pts_per_min",
    "prev_pts_per_min",
]

_ALL_RATE_FEATURES: List[str] = _RATE_BASE_FEATURES + _RATE_RATIO_NAMES

# Minimum minutes threshold for rate head training rows.
_MIN_RATE_THRESHOLD: float = 8.0

# Minimum minutes for a minutes-head training row (player actually played).
_MIN_PLAYED_THRESHOLD: float = 1.0

# Prediction clamp bounds.
_PRED_MIN: float = 0.0
_PRED_MAX: float = 70.0

# LGBM default hyperparameters — more regularised than the baseline stack to
# denoise the rate estimate (which is noisy for low-minute players).
_LGB_MIN_PARAMS: Dict[str, Any] = {
    "n_estimators": 400,
    "max_depth": 4,
    "num_leaves": 31,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "reg_lambda": 4.0,    # heavier than baseline (2.0) to reduce rate noise
    "reg_alpha": 1.0,
    "objective": "regression",
    "n_jobs": -1,
    "verbosity": -1,
    "random_state": 42,
}

_LGB_RATE_PARAMS: Dict[str, Any] = {
    "n_estimators": 400,
    "max_depth": 3,       # shallower for rate head — avoids overfitting
    "num_leaves": 16,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "min_child_samples": 30,  # higher threshold — rate unstable in small samples
    "reg_lambda": 6.0,    # heavier regularisation for rate denoising
    "reg_alpha": 1.5,
    "objective": "regression",
    "n_jobs": -1,
    "verbosity": -1,
    "random_state": 42,
}


# ---------------------------------------------------------------------------
# Feature extraction helpers
# ---------------------------------------------------------------------------

def _safe_rate(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide numerator by denominator, returning default when denominator < 1."""
    if denominator < 1.0:
        return default
    return numerator / denominator


def _extract_min_features(row: dict) -> np.ndarray:
    """Extract minutes-head feature vector from a row dict."""
    return np.array(
        [float(row.get(k, 0.0) or 0.0) for k in _MIN_FEATURES],
        dtype=float,
    )


def _rate_ratios(row: dict) -> Dict[str, float]:
    """Compute per-minute rate ratios from the row dict (guard divide-by-zero)."""
    l5_min  = float(row.get("l5_min",  0.0) or 0.0)
    l10_min = float(row.get("l10_min", 0.0) or 0.0)
    ewma_min = float(row.get("ewma_min", 0.0) or 0.0)
    prev_min = float(row.get("prev_min", 0.0) or 0.0)

    return {
        "l5_pts_per_min":   _safe_rate(float(row.get("l5_pts",   0.0) or 0.0), l5_min),
        "l10_pts_per_min":  _safe_rate(float(row.get("l10_pts",  0.0) or 0.0), l10_min),
        "ewma_pts_per_min": _safe_rate(float(row.get("ewma_pts", 0.0) or 0.0), ewma_min),
        "prev_pts_per_min": _safe_rate(float(row.get("prev_pts", 0.0) or 0.0), prev_min),
    }


def _extract_rate_features(row: dict) -> np.ndarray:
    """Extract rate-head feature vector from a row dict (base + computed ratios)."""
    base = [float(row.get(k, 0.0) or 0.0) for k in _RATE_BASE_FEATURES]
    ratios = _rate_ratios(row)
    ratio_vec = [ratios[k] for k in _RATE_RATIO_NAMES]
    return np.array(base + ratio_vec, dtype=float)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_pts_minmodel(rows_train: List[dict]) -> Dict[str, Any]:
    """Train both heads on rows_train (training-fold rows only — no look-ahead).

    Parameters
    ----------
    rows_train:
        List of row dicts from build_pergame_dataset. Must contain target_min,
        target_pts, and all feature keys referenced above.

    Returns
    -------
    artifact : dict
        Opaque dict containing the trained models; pass to predict_pts_minmodel.
        Keys: 'min_head', 'rate_head', 'isotonic' (or None).
    """
    try:
        import lightgbm as lgb  # noqa: PLC0415
        from sklearn.isotonic import IsotonicRegression  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(f"lightgbm / sklearn required for pts_minutes_model: {exc}") from exc

    # ── Minutes head ────────────────────────────────────────────────────────
    min_rows = [r for r in rows_train
                if float(r.get("target_min", 0.0) or 0.0) >= _MIN_PLAYED_THRESHOLD]

    if len(min_rows) < 50:
        raise ValueError(f"Not enough rows for minutes head: {len(min_rows)} (need >=50)")

    X_min = np.array([_extract_min_features(r) for r in min_rows], dtype=float)
    y_min = np.array([float(r["target_min"]) for r in min_rows], dtype=float)

    # Recency sample weights: exponential decay by age (mirrors cache_pergame_oof.py)
    from datetime import datetime  # noqa: PLC0415
    tr_dates = [r["date"][:10] for r in min_rows]
    max_d = max(datetime.fromisoformat(d) for d in tr_dates)
    age_min = np.array(
        [(max_d - datetime.fromisoformat(d)).days / 365.0 for d in tr_dates],
        dtype=float,
    )
    sw_min = np.exp(-0.5 * age_min)

    min_head = lgb.LGBMRegressor(**_LGB_MIN_PARAMS)
    min_head.fit(X_min, y_min, sample_weight=sw_min)

    # ── Per-minute rate head ─────────────────────────────────────────────────
    rate_rows = [r for r in rows_train
                 if float(r.get("target_min", 0.0) or 0.0) >= _MIN_RATE_THRESHOLD]

    if len(rate_rows) < 50:
        raise ValueError(f"Not enough rows for rate head: {len(rate_rows)} (need >=50)")

    X_rate = np.array([_extract_rate_features(r) for r in rate_rows], dtype=float)
    y_rate = np.array(
        [
            float(r["target_pts"]) / float(r["target_min"])
            for r in rate_rows
        ],
        dtype=float,
    )

    # Recency weights for rate head
    tr_dates_r = [r["date"][:10] for r in rate_rows]
    max_d_r = max(datetime.fromisoformat(d) for d in tr_dates_r)
    age_r = np.array(
        [(max_d_r - datetime.fromisoformat(d)).days / 365.0 for d in tr_dates_r],
        dtype=float,
    )
    sw_r = np.exp(-0.5 * age_r)

    rate_head = lgb.LGBMRegressor(**_LGB_RATE_PARAMS)
    rate_head.fit(X_rate, y_rate, sample_weight=sw_r)

    # ── Composed predictions on training rows for isotonic probe ────────────
    # We fit isotonic on the full training set predictions vs actuals.
    # This is NOT leaky because it is applied within the same training slice
    # that trained both heads — the isotonic wrapper will be evaluated OOF.
    composed_train: List[float] = []
    actuals_train: List[float] = []
    for r in rows_train:
        if float(r.get("target_pts", 0.0) or 0.0) < 0.0:
            continue
        pred_raw = _compose(min_head, rate_head, r)
        composed_train.append(pred_raw)
        actuals_train.append(float(r.get("target_pts", 0.0) or 0.0))

    iso_model = None
    if len(composed_train) >= 100:
        iso_model = IsotonicRegression(out_of_bounds="clip")
        iso_model.fit(composed_train, actuals_train)

    return {
        "min_head":  min_head,
        "rate_head": rate_head,
        "isotonic":  iso_model,
    }


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def _compose(min_head: Any, rate_head: Any, row: dict) -> float:
    """Raw composed prediction: mu_min * r_pts, clamped to [0, 70]."""
    x_min  = _extract_min_features(row).reshape(1, -1)
    x_rate = _extract_rate_features(row).reshape(1, -1)

    mu_min  = float(min_head.predict(x_min)[0])
    r_pts   = float(rate_head.predict(x_rate)[0])

    # Guard degenerate outputs
    mu_min = max(mu_min, 0.0)
    r_pts  = max(r_pts,  0.0)

    raw = mu_min * r_pts
    return float(np.clip(raw, _PRED_MIN, _PRED_MAX))


def predict_pts_minmodel(artifact: Dict[str, Any], row: dict) -> float:
    """Predict PTS for a single row using the trained two-stage model.

    Parameters
    ----------
    artifact:
        Dict returned by train_pts_minmodel.
    row:
        A single row dict from build_pergame_dataset.

    Returns
    -------
    float
        Predicted PTS, in [0, 70]. Always finite.
    """
    min_head  = artifact["min_head"]
    rate_head = artifact["rate_head"]
    iso       = artifact.get("isotonic")

    raw = _compose(min_head, rate_head, row)

    if iso is not None:
        raw = float(iso.predict([raw])[0])

    # Final clamp and NaN guard
    if not np.isfinite(raw):
        raw = 0.0
    return float(np.clip(raw, _PRED_MIN, _PRED_MAX))
