"""play_probability.py — cycle 104a (loop 5).

Per-row P(play) head. Binary classifier producing the calibrated
probability a player suits up for a given game given pre-game features
(b2b flag, age, days_since_last_game, recent minutes, rolling DNP rate,
position one-hots, opp pace).

The tier3-11b probe (b2b veteran v3) confirmed the SELECTION BIAS
hypothesis — DNP rates in the (age>=33, b2b) cohort are ~50%+ — and
recommended the right wire-in is `pred *= P(play)`, NOT a flat shrink
factor. This module produces that probability; `apply_play_prob_blend`
is the post-prediction hook that multiplies it into a base prediction.

The model artifact is gated on existence: when missing the blend
function is a no-op (back-compat with the cycle-48 baseline and
fresh checkouts without the DNP infrastructure).

Public API
----------
    PLAY_PROB_FEATURES        — feature column order used at train/inference
    train_play_probability    — fit LGBClassifier + Platt calibration
    save_play_probability     — persist artifact dict
    load_play_probability     — load artifact (None if missing)
    predict_play_probability  — calibrated P(play) ∈ [0.01, 1.0]
    apply_play_prob_blend     — pred *= P(play) hook (no-op if missing)
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_ARTIFACT_NAME = "play_probability_v1.joblib"

# Module flag — default OFF. Set to True only when the artifact exists AND
# the DNP infrastructure (data/dnp_rows.parquet) is present.
_APPLY_PLAY_PROB = False

# Feature ordering is canonical — changes here must be reflected in
# train_play_probability AND any caller that builds a feature vector.
_POSITIONS = ("G", "F", "C")
PLAY_PROB_FEATURES: List[str] = [
    "is_b2b",
    "age",
    "days_since_last_game",
    "l5_min",
    "l10_min",
    "dnp_l20_rate",
    "opp_team_pace_l5",
] + [f"pos_{p}" for p in _POSITIONS]

# Probability clip — never zero a prediction on a certainty mistake.
_PLAY_PROB_MIN = 0.01
_PLAY_PROB_MAX = 1.0


def _vectorize(feature_row: Dict[str, float]):
    import numpy as np  # noqa: PLC0415
    return np.array(
        [[float(feature_row.get(c, 0.0) or 0.0) for c in PLAY_PROB_FEATURES]],
        dtype=float,
    )


def train_play_probability(
    X, y,
    *,
    val_frac: float = 0.2,
    random_state: int = 42,
) -> dict:
    """Train LGBM binary classifier + Platt scaling on a held-out tail.

    Parameters
    ----------
    X : (n, len(PLAY_PROB_FEATURES)) float array
    y : (n,) {0, 1} array — 1 if played (MIN > 0), 0 if DNP
    val_frac : tail fraction reserved for Platt calibration (chronological
        order assumed — caller sorts).

    Returns
    -------
    artifact : dict with keys {model, platt_a, platt_b, n_train, n_val,
        val_mean_pred, val_played_frac, val_brier, features}.
    """
    import numpy as np  # noqa: PLC0415
    try:
        import lightgbm as lgb  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("lightgbm required for play_probability") from exc
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415

    n = len(X)
    if n < 50:
        raise ValueError(f"need >= 50 rows, got {n}")
    n_val = max(10, int(n * val_frac))
    n_tr = n - n_val
    X_tr, X_val = X[:n_tr], X[n_tr:]
    y_tr, y_val = y[:n_tr], y[n_tr:]

    clf = lgb.LGBMClassifier(
        n_estimators=300, learning_rate=0.05, max_depth=5,
        num_leaves=31, min_child_samples=30, subsample=0.85,
        colsample_bytree=0.85, reg_lambda=1.0, random_state=random_state,
        verbose=-1,
    )
    clf.fit(X_tr, y_tr)

    raw_val = clf.predict_proba(X_val)[:, 1]
    # Platt scaling: logistic regression on the raw scores.
    platt = LogisticRegression(C=1e6, solver="lbfgs")
    raw_val_2d = raw_val.reshape(-1, 1)
    platt.fit(raw_val_2d, y_val)
    cal_val = platt.predict_proba(raw_val_2d)[:, 1]

    artifact = {
        "model": clf,
        "platt_a": float(platt.coef_[0, 0]),
        "platt_b": float(platt.intercept_[0]),
        "n_train": int(n_tr),
        "n_val": int(n_val),
        "val_mean_pred": float(cal_val.mean()),
        "val_played_frac": float(y_val.mean()),
        "val_brier": float(((cal_val - y_val) ** 2).mean()),
        "features": list(PLAY_PROB_FEATURES),
    }
    return artifact


def save_play_probability(artifact: dict,
                          model_dir: Optional[str] = None) -> str:
    import joblib  # noqa: PLC0415
    model_dir = model_dir or _MODEL_DIR
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, _ARTIFACT_NAME)
    joblib.dump(artifact, path)
    return path


def load_play_probability(model_dir: Optional[str] = None) -> Optional[dict]:
    import joblib  # noqa: PLC0415
    model_dir = model_dir or _MODEL_DIR
    path = os.path.join(model_dir, _ARTIFACT_NAME)
    if not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("play_probability: failed to load %s: %s", path, exc)
        return None


def _calibrate(raw: float, a: float, b: float) -> float:
    import math  # noqa: PLC0415
    z = a * raw + b
    # Numerically stable sigmoid.
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def predict_play_probability(feature_row: Dict[str, float],
                             artifact: Optional[dict] = None,
                             model_dir: Optional[str] = None) -> Optional[float]:
    """Return calibrated P(play) ∈ [0.01, 1.0] or None when artifact missing."""
    artifact = artifact or load_play_probability(model_dir)
    if artifact is None:
        return None
    X = _vectorize(feature_row)
    try:
        raw = float(artifact["model"].predict_proba(X)[0, 1])
    except Exception as exc:
        logger.warning("play_probability.predict raw failure: %s", exc)
        return None
    cal = _calibrate(raw, artifact["platt_a"], artifact["platt_b"])
    if cal < _PLAY_PROB_MIN:
        cal = _PLAY_PROB_MIN
    elif cal > _PLAY_PROB_MAX:
        cal = _PLAY_PROB_MAX
    return cal


def apply_play_prob_blend(pred: float, feature_row: Dict[str, float],
                          artifact: Optional[dict] = None,
                          model_dir: Optional[str] = None) -> float:
    """Post-prediction hook: `pred * P(play)`. No-op if artifact missing
    or flag disabled, so existing callers see no behaviour change on
    fresh checkouts."""
    if not _APPLY_PLAY_PROB:
        return pred
    p = predict_play_probability(feature_row, artifact=artifact,
                                 model_dir=model_dir)
    if p is None:
        return pred
    return float(pred) * p
