"""
prop_stacker.py — Linear meta-learner that combines XGBoost + LightGBM + CatBoost
out-of-fold (OOF) predictions into a single ensemble prediction per prop stat.

Architecture
------------
    Base learners:  XGBoost (.json), LightGBM (.pkl), CatBoost (.cbm, optional)
    OOF stacking:   5-fold cross-val on synthetic/training data produces OOF preds
    Meta-learner:   Ridge regression (L2 alpha=1.0) maps base predictions -> target
    Holdout eval:   R² logged vs best single base-learner

Public API
----------
    fit_stacker(X, y, stat)          -> StackerResult
    predict_ensemble(X, stat)        -> np.ndarray
    train_stacker_all(...)           -> dict
    load_stacker(stat)               -> Ridge or None
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_STACKER_METRICS = os.path.join(_MODELS_DIR, "prop_stacker_metrics.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
_N_FOLDS = 5

# ── CatBoost availability guard ───────────────────────────────────────────────
try:
    import catboost as _catboost_mod  # noqa: F401
    _CATBOOST_AVAILABLE = True
except ImportError:
    _CATBOOST_AVAILABLE = False


@dataclass
class StackerResult:
    """Output from fit_stacker() for one stat."""
    stat: str
    meta_r2: float
    best_base_r2: float
    r2_gain: float                              # meta_r2 - best_base_r2
    base_r2s: Dict[str, float]                  # learner_name -> holdout R²
    n_train: int
    n_holdout: int
    learners_used: List[str]
    extra: Dict[str, object] = field(default_factory=dict)


# ── Base-learner OOF prediction helpers ───────────────────────────────────────

def _xgb_oof(X_train: np.ndarray, y_train: np.ndarray,
              X_holdout: np.ndarray, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (oof_preds_train, holdout_preds) for XGBoost."""
    import xgboost as xgb
    from sklearn.model_selection import KFold
    from src.prediction.prop_cv_split import _objective_for_stat

    oof = np.zeros(len(X_train))
    kf = KFold(n_splits=_N_FOLDS, shuffle=True, random_state=42)

    for train_idx, val_idx in kf.split(X_train):
        m = xgb.XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42,
            objective=_objective_for_stat(stat),
        )
        m.fit(X_train[train_idx], y_train[train_idx])
        oof[val_idx] = m.predict(X_train[val_idx])

    # Full-train model for holdout
    m_full = xgb.XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        objective=_objective_for_stat(stat),
    )
    m_full.fit(X_train, y_train)
    return oof, m_full.predict(X_holdout)


def _lgb_oof(X_train: np.ndarray, y_train: np.ndarray,
             X_holdout: np.ndarray, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (oof_preds_train, holdout_preds) for LightGBM."""
    import lightgbm as lgb
    from sklearn.model_selection import KFold

    objective = "poisson" if stat in ("stl", "blk") else "regression"
    oof = np.zeros(len(X_train))
    kf = KFold(n_splits=_N_FOLDS, shuffle=True, random_state=42)

    for train_idx, val_idx in kf.split(X_train):
        m = lgb.LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            random_state=42, objective=objective, n_jobs=1, verbosity=-1,
        )
        m.fit(X_train[train_idx], y_train[train_idx])
        oof[val_idx] = m.predict(X_train[val_idx])

    m_full = lgb.LGBMRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        random_state=42, objective=objective, n_jobs=1, verbosity=-1,
    )
    m_full.fit(X_train, y_train)
    return oof, m_full.predict(X_holdout)


def _cb_oof(X_train: np.ndarray, y_train: np.ndarray,
            X_holdout: np.ndarray, stat: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (oof_preds_train, holdout_preds) for CatBoost.

    Raises ImportError if catboost is unavailable — caller checks _CATBOOST_AVAILABLE.
    """
    import catboost as cb
    from sklearn.model_selection import KFold

    loss_fn = "Poisson" if stat in ("stl", "blk") else "RMSE"
    oof = np.zeros(len(X_train))
    kf = KFold(n_splits=_N_FOLDS, shuffle=True, random_state=42)

    for train_idx, val_idx in kf.split(X_train):
        m = cb.CatBoostRegressor(
            iterations=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, random_seed=42, loss_function=loss_fn, verbose=0,
        )
        m.fit(X_train[train_idx], y_train[train_idx])
        oof[val_idx] = m.predict(X_train[val_idx])

    m_full = cb.CatBoostRegressor(
        iterations=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, random_seed=42, loss_function=loss_fn, verbose=0,
    )
    m_full.fit(X_train, y_train)
    return oof, m_full.predict(X_holdout)


# ── Core fit / predict ─────────────────────────────────────────────────────────

def fit_stacker(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_holdout: np.ndarray,
    y_holdout: np.ndarray,
    stat: str,
    models_dir: Optional[str] = None,
) -> StackerResult:
    """Fit a Ridge meta-learner on OOF predictions from available base learners.

    Trains each available base-learner (XGB + LGB + optionally CatBoost) with
    k-fold cross-validation to generate out-of-fold (OOF) predictions.  A Ridge
    regression is then fit on the OOF feature matrix [xgb_oof, lgb_oof, ...] to
    produce the final ensemble predictor.

    Args:
        X_train:    Feature matrix for meta-learner fitting (n_train, n_feats).
        y_train:    Target labels (n_train,).
        X_holdout:  Held-out feature matrix for evaluation (n_holdout, n_feats).
        y_holdout:  Held-out labels (n_holdout,).
        stat:       Stat name (e.g. "pts").
        models_dir: Override directory for saving the meta model.

    Returns:
        StackerResult with R² metrics and improvement over best single learner.
    """
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score
    import joblib

    save_dir = models_dir or _MODELS_DIR
    os.makedirs(save_dir, exist_ok=True)

    oof_cols: List[np.ndarray] = []
    holdout_cols: List[np.ndarray] = []
    learner_names: List[str] = []
    base_r2s: Dict[str, float] = {}

    # XGBoost (required)
    try:
        xgb_oof, xgb_hold = _xgb_oof(X_train, y_train, X_holdout, stat)
        oof_cols.append(xgb_oof)
        holdout_cols.append(xgb_hold)
        learner_names.append("xgboost")
        base_r2s["xgboost"] = float(r2_score(y_holdout, xgb_hold))
    except Exception as exc:
        log.warning("[stacker] XGBoost OOF failed for %s: %s", stat, exc)

    # LightGBM (required)
    try:
        lgb_oof, lgb_hold = _lgb_oof(X_train, y_train, X_holdout, stat)
        oof_cols.append(lgb_oof)
        holdout_cols.append(lgb_hold)
        learner_names.append("lightgbm")
        base_r2s["lightgbm"] = float(r2_score(y_holdout, lgb_hold))
    except Exception as exc:
        log.warning("[stacker] LightGBM OOF failed for %s: %s", stat, exc)

    # CatBoost (optional — skip gracefully if unavailable)
    if _CATBOOST_AVAILABLE:
        try:
            cb_oof, cb_hold = _cb_oof(X_train, y_train, X_holdout, stat)
            oof_cols.append(cb_oof)
            holdout_cols.append(cb_hold)
            learner_names.append("catboost")
            base_r2s["catboost"] = float(r2_score(y_holdout, cb_hold))
        except Exception as exc:
            log.warning("[stacker] CatBoost OOF failed for %s: %s", stat, exc)

    if not oof_cols:
        raise RuntimeError(f"[stacker] No base learners produced OOF preds for {stat}")

    # Stack OOF predictions as meta-features
    Z_train = np.column_stack(oof_cols)        # (n_train, n_learners)
    Z_hold  = np.column_stack(holdout_cols)    # (n_holdout, n_learners)

    meta = Ridge(alpha=1.0, fit_intercept=True)
    meta.fit(Z_train, y_train)
    meta_preds = meta.predict(Z_hold)
    meta_r2 = float(r2_score(y_holdout, meta_preds))

    best_base_r2 = max(base_r2s.values()) if base_r2s else 0.0
    r2_gain = meta_r2 - best_base_r2

    # Persist meta model
    meta_path = os.path.join(save_dir, f"props_stacker_{stat}.pkl")
    joblib.dump({"meta": meta, "learners": learner_names}, meta_path)

    result = StackerResult(
        stat=stat,
        meta_r2=round(meta_r2, 4),
        best_base_r2=round(best_base_r2, 4),
        r2_gain=round(r2_gain, 4),
        base_r2s={k: round(v, 4) for k, v in base_r2s.items()},
        n_train=len(X_train),
        n_holdout=len(X_holdout),
        learners_used=learner_names,
    )

    log.info(
        "[stacker] %s  meta_r2=%.4f  best_base_r2=%.4f  gain=%.4f  learners=%s",
        stat, meta_r2, best_base_r2, r2_gain, learner_names,
    )
    return result


def load_stacker(stat: str, models_dir: Optional[str] = None) -> Optional[object]:
    """Load a persisted stacker bundle dict for *stat*, or None if not found."""
    try:
        import joblib
        path = os.path.join(models_dir or _MODELS_DIR, f"props_stacker_{stat}.pkl")
        if not os.path.exists(path):
            return None
        return joblib.load(path)
    except Exception as exc:
        log.warning("[stacker] load_stacker(%s) failed: %s", stat, exc)
        return None


def predict_ensemble(
    X: np.ndarray,
    stat: str,
    models_dir: Optional[str] = None,
) -> np.ndarray:
    """Generate ensemble predictions for *X* using the fitted stacker for *stat*.

    If the stacker model file is missing, falls back to the XGBoost base prediction.

    Args:
        X:          Feature matrix (n, n_feats).
        stat:       Stat name (e.g. "pts").
        models_dir: Override directory for loading models.

    Returns:
        Predicted values as np.ndarray (n,).
    """
    from src.prediction.prop_model_stack import predict_base_learner

    bundle = load_stacker(stat, models_dir)

    # Fallback: no stacker available — use XGBoost directly
    if bundle is None:
        xgb_pred = predict_base_learner("xgboost", stat, X)
        return np.full(len(X), xgb_pred if xgb_pred is not None else float("nan"))

    meta = bundle["meta"]
    learners: List[str] = bundle["learners"]

    base_preds: List[np.ndarray] = []
    for name in learners:
        col: List[float] = []
        for i in range(len(X)):
            p = predict_base_learner(name, stat, X[i:i+1])
            col.append(p if p is not None else float("nan"))
        base_preds.append(np.array(col))

    Z = np.column_stack(base_preds)
    # Replace any NaN columns with column mean to prevent propagation
    col_means = np.nanmean(Z, axis=0)
    for j in range(Z.shape[1]):
        mask = np.isnan(Z[:, j])
        Z[mask, j] = col_means[j]

    return meta.predict(Z)


# ── Train all stats ────────────────────────────────────────────────────────────

def train_stacker_all(
    seasons: Optional[List[str]] = None,
    force: bool = False,
    models_dir: Optional[str] = None,
    exclude_player_ids: Optional[List[int]] = None,
) -> Dict[str, StackerResult]:
    """Train a linear stacker for all 7 prop stats using OOF from 3 base learners.

    Calls _build_prop_training_frame() to obtain the same train/holdout split used
    by the individual base-learner trainers, then calls fit_stacker() per stat.

    Args:
        seasons:           NBA seasons to use.  Defaults to player_props default.
        force:             Re-train even if stacker files already exist.
        models_dir:        Override save directory (default data/models/).
        exclude_player_ids: Player IDs to exclude from training data.

    Returns:
        {stat: StackerResult, ...}
    """
    import datetime
    from src.prediction.player_props import _build_prop_training_frame, _PROP_STATS

    save_dir = models_dir or _MODELS_DIR
    os.makedirs(save_dir, exist_ok=True)

    if not force and all(
        os.path.exists(os.path.join(save_dir, f"props_stacker_{s}.pkl"))
        for s in STATS
    ):
        print("[stacker] All stacker models already exist. Use force=True to retrain.")
        return {}

    train_df, test_df, feat_cols = _build_prop_training_frame(
        seasons, exclude_player_ids
    )
    if train_df is None:
        print("[stacker] Not enough data for stacker training.")
        return {}

    results: Dict[str, StackerResult] = {}

    for stat in STATS:
        stat_feats = [c for c in feat_cols if c != f"season_{stat}"]

        # Fill any missing columns with 0.0
        _train = train_df.copy()
        _test  = test_df.copy()
        for col in stat_feats:
            if col not in _train.columns:
                _train[col] = 0.0
                _test[col]  = 0.0

        label_col = f"season_{stat}"
        if label_col not in _train.columns:
            print(f"  [stacker] {stat.upper()} — no label column, skipping")
            continue

        X_train = _train[stat_feats].fillna(0.0).values
        X_test  = _test[stat_feats].fillna(0.0).values
        y_train = _train[label_col].values
        y_test  = _test[label_col].values

        try:
            res = fit_stacker(X_train, y_train, X_test, y_test, stat, save_dir)
            results[stat] = res
            gain_flag = "OK" if res.r2_gain >= 0.01 else "WARN(gain<0.01)"
            print(
                f"  [stacker] {stat.upper():<4}  meta_r2={res.meta_r2:.4f}  "
                f"best_base={res.best_base_r2:.4f}  gain={res.r2_gain:+.4f}  {gain_flag}"
            )
        except Exception as exc:
            log.warning("[stacker] fit_stacker(%s) failed: %s", stat, exc)

    # Write metrics JSON
    metrics_payload = {
        "model": "linear_stacker",
        "task": "season_aggregate_circular",
        "trained_at": datetime.datetime.now().isoformat(),
        "catboost_available": _CATBOOST_AVAILABLE,
        "stats": {
            stat: {
                "meta_r2": r.meta_r2,
                "best_base_r2": r.best_base_r2,
                "r2_gain": r.r2_gain,
                "base_r2s": r.base_r2s,
                "learners_used": r.learners_used,
                "n_train": r.n_train,
                "n_holdout": r.n_holdout,
            }
            for stat, r in results.items()
        },
    }
    import logging
    logging.getLogger(__name__).warning(
        "prop_stacker metrics reflect a SEASON-AVERAGE CIRCULAR task — "
        "R² is not a real game-level holdout. The honest game-level model is prop_pergame."
    )
    with open(_STACKER_METRICS, "w") as f:
        json.dump(metrics_payload, f, indent=2)
    print(f"[stacker] Metrics -> {_STACKER_METRICS}")

    return results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Prop linear stacker trainer")
    parser.add_argument("--force", action="store_true", help="Retrain even if models exist")
    parser.add_argument("--seasons", nargs="*", help="Seasons to use for training")
    args = parser.parse_args()

    results = train_stacker_all(seasons=args.seasons, force=args.force)
    if results:
        gains = [r.r2_gain for r in results.values()]
        print(f"\n[stacker] Done. Mean R² gain: {np.mean(gains):+.4f}")
    else:
        print("[stacker] No results produced.")
