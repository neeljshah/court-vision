"""reb_opportunity_model.py — Gated REB pregame model (SPEC B).

Models rebounds as opportunity × share × minutes, attacking the shrinkage
fan (+1.02 bias at <12 min → -0.89 bias at 32+ min) that the flat 132-feature
shared model cannot address through calibration alone.

Architecture
------------
  1. Minutes head  : mu_min = E[MIN | pregame features]
     — LGBM on minutes-stable pregame features
     — trained on rows with target_min >= 1
  2. Rate head     : r_reb = E[REB/MIN | reb-rate features]
     — Ridge on minutes-invariant rebounding features (rate normalised)
     — trained on rows with target_min >= 8 (stable per-minute rate)
  3. Compose       : pred_reb = r_reb(row) * mu_min(row), clamped [0, 30]

Gate
----
Set env var CV_PREGAME_REB_OPPMODEL=1 to enable.  Default OFF = no change.

Public API
----------
    is_enabled()                        -> bool
    train_reb_oppmodel(rows_train)      -> _RebArtifact
    predict_reb_oppmodel(artifact, row) -> float
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

warnings.filterwarnings("ignore")

# ── gate ─────────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Return True iff CV_PREGAME_REB_OPPMODEL=1 is set in the environment."""
    return os.environ.get("CV_PREGAME_REB_OPPMODEL", "0").strip() == "1"


# ── feature definitions ───────────────────────────────────────────────────────

# Features for the minutes head — captures workload/role signals, not counting
# stats that scale with minutes (those would create leakage into the rate head).
_MIN_HEAD_FEATURES: Tuple[str, ...] = (
    "l5_min", "l10_min", "std_min", "ewma_min", "prev_min",
    "rest_days", "is_b2b", "is_b3b", "days_since_last_game",
    "games_since_long_absence", "games_played", "is_home",
)

# Features for the per-minute rate head — must be minutes-invariant.
# Rates computed from form windows, rebounding percentages, and context.
_RATE_HEAD_BASE_FEATURES: Tuple[str, ...] = (
    "bbref_orb_pct", "bbref_drb_pct", "bbref_trb_pct",
    "opp_def_reb",
    "team_oreb_pct_l5", "opp_dreb_pct_l5", "reb_chance_l5",
)

# Computed rate features added dynamically during feature extraction:
# l5_reb_per_min, l10_reb_per_min, ewma_reb_per_min, prev_reb_per_min
_RATE_COMPUTED_FEATURES: Tuple[str, ...] = (
    "l5_reb_per_min", "l10_reb_per_min",
    "ewma_reb_per_min", "prev_reb_per_min",
)

_RATE_HEAD_FEATURES: Tuple[str, ...] = (
    _RATE_HEAD_BASE_FEATURES + _RATE_COMPUTED_FEATURES
)

# ── per-minute rate feature extractor ────────────────────────────────────────

def _extract_rate_features(
    row: Dict[str, Any],
    eps: float = 1e-3,
) -> Dict[str, float]:
    """Compute minutes-invariant rate features for a single row dict.

    Divides rolling form reb counts by the corresponding form min windows,
    guarding against divide-by-zero with eps.
    """
    def _f(k: str) -> float:
        v = row.get(k, 0.0)
        return float(v) if v is not None else 0.0

    def _rate(reb_key: str, min_key: str) -> float:
        reb = _f(reb_key)
        mins = _f(min_key)
        return reb / max(mins, eps)

    return {
        # Base rebounding attributes
        "bbref_orb_pct":    _f("bbref_orb_pct"),
        "bbref_drb_pct":    _f("bbref_drb_pct"),
        "bbref_trb_pct":    _f("bbref_trb_pct"),
        "opp_def_reb":      _f("opp_def_reb"),
        "team_oreb_pct_l5": _f("team_oreb_pct_l5"),
        "opp_dreb_pct_l5":  _f("opp_dreb_pct_l5"),
        "reb_chance_l5":    _f("reb_chance_l5"),
        # Computed per-minute rates
        "l5_reb_per_min":   _rate("l5_reb",   "l5_min"),
        "l10_reb_per_min":  _rate("l10_reb",  "l10_min"),
        "ewma_reb_per_min": _rate("ewma_reb", "ewma_min"),
        "prev_reb_per_min": _rate("prev_reb", "prev_min"),
    }


def _extract_min_features(row: Dict[str, Any]) -> Dict[str, float]:
    """Extract minutes-head features from a row dict."""
    def _f(k: str) -> float:
        v = row.get(k, 0.0)
        return float(v) if v is not None else 0.0

    return {k: _f(k) for k in _MIN_HEAD_FEATURES}


# ── artifact dataclass ────────────────────────────────────────────────────────

@dataclass
class _RebArtifact:
    """Trained artifact holding both heads."""
    min_model: Any          # fitted LGBM regressor (minutes head)
    rate_model: Any         # fitted Ridge regressor (rate head)
    rate_scaler: Any        # fitted StandardScaler for rate features
    min_features: Tuple[str, ...]
    rate_features: Tuple[str, ...]


# ── training ──────────────────────────────────────────────────────────────────

def train_reb_oppmodel(rows_train: Sequence[Dict[str, Any]]) -> _RebArtifact:
    """Train the REB opportunity model on rows_train.

    Parameters
    ----------
    rows_train : sequence of row dicts from build_pergame_dataset(), sorted
        chronologically.  Must contain keys target_min, target_reb, and all
        feature keys in _MIN_HEAD_FEATURES / _RATE_HEAD_FEATURES.

    Returns
    -------
    _RebArtifact with fitted min_model, rate_model, rate_scaler.
    """
    import lightgbm as lgb
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    # ---- minutes head -------------------------------------------------------
    # Train on all rows with ≥1 minute played (same filter as the main model).
    min_rows = [r for r in rows_train if float(r.get("target_min") or 0) >= 1.0]
    if len(min_rows) < 50:
        raise ValueError(
            f"Too few training rows for minutes head: {len(min_rows)}"
        )

    X_min = np.array(
        [[float(r.get(k) or 0.0) for k in _MIN_HEAD_FEATURES]
         for r in min_rows],
        dtype=float,
    )
    y_min = np.array([float(r.get("target_min") or 0.0) for r in min_rows], dtype=float)

    # Recency weights: exponential decay 0.5 yrs half-life (matches baseline).
    from datetime import datetime
    try:
        min_dates = [datetime.fromisoformat(str(r["date"])[:10]) for r in min_rows]
        max_d = max(min_dates)
        age = np.array([(max_d - d).days / 365.0 for d in min_dates], dtype=float)
        sw_min = np.exp(-0.5 * age)
    except Exception:
        sw_min = np.ones(len(min_rows))

    min_model = lgb.LGBMRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_lambda=3.0,
        reg_alpha=1.0,
        random_state=42,
        objective="regression",
        n_jobs=-1,
        verbosity=-1,
    )
    min_model.fit(X_min, y_min, sample_weight=sw_min)

    # ---- per-minute rate head -----------------------------------------------
    # Train on rows with ≥8 minutes (rate is unstable at tiny minutes).
    rate_rows = [r for r in rows_train if float(r.get("target_min") or 0) >= 8.0]
    if len(rate_rows) < 50:
        raise ValueError(
            f"Too few training rows for rate head: {len(rate_rows)}"
        )

    rate_feats = [_extract_rate_features(r) for r in rate_rows]
    X_rate = np.array(
        [[feat[k] for k in _RATE_HEAD_FEATURES] for feat in rate_feats],
        dtype=float,
    )
    y_rate = np.array(
        [float(r.get("target_reb") or 0.0) / max(float(r.get("target_min") or 1.0), 1e-3)
         for r in rate_rows],
        dtype=float,
    )
    # Clip extreme rates (e.g., a 20-reb game in 8 min would be noise).
    y_rate = np.clip(y_rate, 0.0, 2.5)

    # Recency weights for rate head
    try:
        rate_dates = [datetime.fromisoformat(str(r["date"])[:10]) for r in rate_rows]
        max_d = max(rate_dates)
        age = np.array([(max_d - d).days / 365.0 for d in rate_dates], dtype=float)
        sw_rate = np.exp(-0.5 * age)
    except Exception:
        sw_rate = np.ones(len(rate_rows))

    # Scale rate features (Ridge is distance-based).
    rate_scaler = StandardScaler()
    X_rate_s = rate_scaler.fit_transform(X_rate)

    # Heavier regularization than the baseline — rate is noisy.
    rate_model = Ridge(alpha=50.0, fit_intercept=True)
    rate_model.fit(X_rate_s, y_rate, sample_weight=sw_rate)

    return _RebArtifact(
        min_model=min_model,
        rate_model=rate_model,
        rate_scaler=rate_scaler,
        min_features=_MIN_HEAD_FEATURES,
        rate_features=_RATE_HEAD_FEATURES,
    )


# ── prediction ────────────────────────────────────────────────────────────────

def predict_reb_oppmodel(
    artifact: _RebArtifact,
    row: Dict[str, Any],
    *,
    min_pred_floor: float = 0.5,
    pred_ceiling: float = 30.0,
) -> float:
    """Predict REB for a single row using the trained opportunity model.

    pred_reb = rate(row) × mu_min(row), clamped to [0, pred_ceiling].

    Parameters
    ----------
    artifact    : fitted _RebArtifact from train_reb_oppmodel()
    row         : feature dict from build_pergame_dataset()
    min_pred_floor : minimum allowed minutes prediction (guards divide-by-zero
                    when the minutes head predicts near-zero for a DNP candidate).
    pred_ceiling : hard upper clamp on the raw prediction.

    Returns
    -------
    float — predicted rebounds, non-negative and finite.
    """
    # ---- minutes head -------------------------------------------------------
    x_min = np.array(
        [[float(row.get(k) or 0.0) for k in artifact.min_features]],
        dtype=float,
    )
    mu_min = float(artifact.min_model.predict(x_min)[0])
    mu_min = max(mu_min, min_pred_floor)

    # ---- rate head ----------------------------------------------------------
    rate_feat = _extract_rate_features(row)
    x_rate = np.array(
        [[rate_feat[k] for k in artifact.rate_features]],
        dtype=float,
    )
    x_rate_s = artifact.rate_scaler.transform(x_rate)
    r_reb = float(artifact.rate_model.predict(x_rate_s)[0])
    r_reb = max(r_reb, 0.0)   # rates can't be negative

    # ---- compose ------------------------------------------------------------
    pred = r_reb * mu_min
    pred = max(0.0, min(pred, pred_ceiling))

    if not np.isfinite(pred):
        pred = 0.0

    return pred
