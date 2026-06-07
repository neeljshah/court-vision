"""prop_quantiles.py — quantile heads for per-stat prediction intervals.

Trains 3 XGB quantile regressors per stat (q=0.1, 0.5, 0.9) on the same
prop_pergame dataset, using each stat's tailored target transform (sqrt
for PTS, log1p for the 6 log1p stats). Outputs back-transformed to the
raw-count scale. Persisted alongside the cycle-23 production model so
betting downstream (Kelly sizing, EV vs prop lines) can consume them.

Public API:
    train_quantile_models(...)           -> dict (q-MAE per stat per quantile)
    predict_pergame_quantiles(stat, row) -> {q10, q50, q90} dict (raw scale)
    load_quantile_models(stat)           -> {q: XGBRegressor}

This module does NOT change the cycle-23 point-prediction stack — that
continues to drive predict_pergame. The quantile models are a new
parallel artifact for confidence intervals only.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    build_pergame_dataset, feature_columns,
)


_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_QUANTILE_LEVELS = (0.1, 0.5, 0.9)


def _transform(stat: str, y: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.sqrt(y)
    if stat in _LOG_TRANSFORM_STATS:
        return np.log1p(y)
    return y


def _inverse(stat: str, v: np.ndarray) -> np.ndarray:
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return np.clip(v, 0.0, None)


def _per_stat_xgb_params(stat: str) -> dict:
    """Match the same per-stat HPs train_pergame_models uses, so quantile
    models share the same regularisation regime as the point models."""
    base = dict(n_estimators=600, max_depth=4, learning_rate=0.04,
                subsample=0.8, colsample_bytree=0.8,
                min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5,
                gamma=0.2, random_state=42)
    overrides = {
        "pts":  dict(max_depth=6, min_child_weight=20, reg_lambda=4.0,
                     learning_rate=0.025, colsample_bytree=0.9, reg_alpha=2.0,
                     n_estimators=800),
        "reb":  dict(max_depth=3, min_child_weight=30, reg_lambda=4.0,
                     gamma=0.3, learning_rate=0.025, subsample=0.7,
                     colsample_bytree=0.9, n_estimators=800),
        "ast":  dict(max_depth=5, min_child_weight=20, reg_lambda=5.0,
                     learning_rate=0.025, subsample=0.7, n_estimators=800),
        "fg3m": dict(max_depth=4, min_child_weight=15, reg_lambda=8.0,
                     gamma=0.0, learning_rate=0.025, subsample=0.7,
                     n_estimators=600),
        "stl":  dict(max_depth=2, min_child_weight=40, reg_lambda=6.0,
                     gamma=0.6, learning_rate=0.06, subsample=0.9,
                     reg_alpha=0.25, n_estimators=400),
        "blk":  dict(max_depth=3, min_child_weight=25, reg_lambda=4.0,
                     gamma=0.4, learning_rate=0.06, colsample_bytree=1.0,
                     n_estimators=800),
        "tov":  dict(max_depth=3, min_child_weight=30, reg_lambda=6.0,
                     gamma=0.4, learning_rate=0.025, n_estimators=700),
    }
    base.update(overrides.get(stat, {}))
    return base


def train_quantile_models(
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    *,
    stats: Optional[List[str]] = None,
    holdout_frac: float = 0.2,
    val_frac: float = 0.15,
    quantiles=_QUANTILE_LEVELS,
) -> dict:
    """Train XGB quantile regressors per stat per quantile level.

    Returns per-stat per-quantile validation pinball loss + holdout MAE
    (point-comparison via q=0.5). Writes one model file per (stat, q).
    """
    import xgboost as xgb
    import lightgbm as lgb
    import joblib
    from sklearn.metrics import mean_absolute_error

    model_dir = model_dir or _MODEL_DIR
    os.makedirs(model_dir, exist_ok=True)
    rows, fcols = build_pergame_dataset(gamelog_dir or None)
    if len(rows) < 200:
        return {"status": "insufficient_data", "n_rows": len(rows)}

    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    X_all = np.array([[r[c] for c in fcols] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]

    from datetime import datetime as _dt
    train_dates = [_dt.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    stats_to_train = list(stats) if stats else list(STATS)
    metrics: dict = {"n_rows": n, "stats": {}}

    for stat in stats_to_train:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
        yt_tr, yt_val = _transform(stat, y_tr), _transform(stat, y_val)
        params = _per_stat_xgb_params(stat)
        per_q = {}
        for q in quantiles:
            # XGB quantile (always trained)
            m = xgb.XGBRegressor(
                **{k: v for k, v in params.items() if k != "random_state"},
                random_state=42,
                objective="reg:quantileerror",
                quantile_alpha=q,
                early_stopping_rounds=40,
                eval_metric="mae",
            )
            m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
                  sample_weight=sw, verbose=False)
            preds_ho = _inverse(stat, m.predict(X_ho))
            mae_q = float(mean_absolute_error(y_ho, preds_ho))
            pred_val = _inverse(stat, m.predict(X_val))
            err = y_val - pred_val
            pinball = float(np.mean(np.maximum(q * err, (q - 1) * err)))
            per_q[str(q)] = {"mae_q": mae_q, "pinball_val": pinball}
            m.save_model(os.path.join(model_dir, f"quantile_pergame_{stat}_q{int(q*100):02d}.json"))

            # LGB quantile (cycle 29 — REB ships off the LGB-q50 variant
            # which wins 4/4 WF folds where XGB-q50 was 3/4). Cheap to train
            # for every stat in case future cycles need them.
            lgb_m = lgb.LGBMRegressor(
                n_estimators=params["n_estimators"], max_depth=params["max_depth"],
                learning_rate=params["learning_rate"],
                subsample=params["subsample"], subsample_freq=1,
                colsample_bytree=params["colsample_bytree"],
                min_child_samples=max(20, params["min_child_weight"] * 2),
                reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
                random_state=42, objective="quantile", alpha=q,
                n_jobs=-1, verbosity=-1,
            )
            lgb_m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)],
                      sample_weight=sw,
                      callbacks=[lgb.early_stopping(40, verbose=False)])
            joblib.dump(lgb_m, os.path.join(model_dir, f"quantile_pergame_lgb_{stat}_q{int(q*100):02d}.pkl"))
            preds_ho_lgb = _inverse(stat, lgb_m.predict(X_ho))
            per_q[str(q)]["mae_q_lgb"] = float(mean_absolute_error(y_ho, preds_ho_lgb))
        # Coverage check: fraction of holdout y in [q10, q90] should be ~0.8
        m10 = xgb.XGBRegressor(); m10.load_model(os.path.join(model_dir, f"quantile_pergame_{stat}_q10.json"))
        m90 = xgb.XGBRegressor(); m90.load_model(os.path.join(model_dir, f"quantile_pergame_{stat}_q90.json"))
        q10 = _inverse(stat, m10.predict(X_ho))
        q90 = _inverse(stat, m90.predict(X_ho))
        covered = float(((y_ho >= q10) & (y_ho <= q90)).mean())
        avg_width = float(np.mean(q90 - q10))
        per_q["coverage_80"] = covered
        per_q["avg_interval_width"] = avg_width
        metrics["stats"][stat] = per_q
        print(f"  [quantile] {stat.upper():4s} "
              f"q50_mae={per_q['0.5']['mae_q']:.4f} "
              f"coverage_80={covered:.3f} "
              f"avg_width={avg_width:.3f}", flush=True)

    out_path = os.path.join(model_dir, "quantile_pergame_metrics.json")
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)
    return metrics


def load_quantile_models(stat: str, model_dir: Optional[str] = None) -> Dict[float, "xgb.XGBRegressor"]:
    """Load all quantile models for a stat. Returns {q: model}; empty when none on disk."""
    import xgboost as xgb
    model_dir = model_dir or _MODEL_DIR
    out: Dict[float, "xgb.XGBRegressor"] = {}
    for q in _QUANTILE_LEVELS:
        path = os.path.join(model_dir, f"quantile_pergame_{stat}_q{int(q*100):02d}.json")
        if not os.path.exists(path):
            continue
        m = xgb.XGBRegressor()
        try:
            m.load_model(path)
            out[q] = m
        except Exception:
            continue
    return out


def predict_pergame_quantiles(stat: str, feature_row: Dict[str, float],
                              model_dir: Optional[str] = None,
                              *,
                              player_id: Optional[int] = None,
                              player_name: Optional[str] = None) -> Optional[dict]:
    """Predict q10/q50/q90 for one game. Returns dict or None on no model.

    R15_W1: when ``player_id`` (or ``player_name``) is supplied, the
    returned q10/q50/q90 are multiplied by the live availability_factor
    (OUT → 0, AVAILABLE → 1, …). The band collapses to (0, 0, 0) for
    OUT/NWT players — preserves coverage on the day they don't play.
    """
    models = load_quantile_models(stat, model_dir)
    if not models:
        return None
    # PREDICTION_FIDELITY plumbing fix (2026-06-04): consult the frozen
    # per-stat column list in data/models/_meta.json via feature_columns_for so
    # the QUANTILE path gets the bbref-aligned order independent of the
    # CV_BBREF_REORDER_FIX env var (prior bug: bare feature_columns() made this
    # path's slot order flag-dependent — the audit's load-bearing-env-var risk).
    # Falls back to feature_columns(stat) when _meta.json is absent, preserving
    # legacy behaviour on a fresh checkout. The module default for the flag is
    # now ON, so the fallback is also aligned.
    from src.prediction.prop_pergame import feature_columns_for  # noqa: PLC0415
    cols = feature_columns_for(stat, model_dir or _MODEL_DIR)
    # Wave-3 / Iter-7 schema versioning: mirror predict_pergame's alignment.
    # Quantile artifacts trained before the Wave-2b schema bump expect 85
    # features while feature_columns() now returns 129. Rather than bail with
    # None (which silently nulled all 7 stats' bands), slice cols to the
    # smallest n_features_in_ across the loaded q-models (first N cols), exactly
    # as predict_pergame does for its q50/blend artifacts.
    _min_n: Optional[int] = None
    for m in models.values():
        n_feats = getattr(m, "n_features_in_", None)
        if n_feats is not None:
            if _min_n is None or n_feats < _min_n:
                _min_n = n_feats
    if _min_n is not None and _min_n != len(cols):
        cols = cols[:_min_n]
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
    out = {}
    for q, m in models.items():
        pred_t = float(m.predict(X)[0])
        out[f"q{int(q*100):02d}"] = float(_inverse(stat, np.array([pred_t]))[0])

    # R15_W1 — inference-time availability dampener. No-op when neither
    # player_id nor player_name is provided (legacy callers).
    if player_id is not None or player_name is not None:
        try:
            from src.prediction.injury_availability import (  # noqa: PLC0415
                get_availability_factor,
            )
            factor = get_availability_factor(
                player_id=int(player_id) if player_id is not None else None,
                player_name=player_name,
            )
            for k in list(out.keys()):
                out[k] = float(out[k]) * float(factor)
        except Exception as exc:
            print(f"[predict_pergame_quantiles] injury-wire skipped: {exc}")
    return out


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    train_quantile_models()
