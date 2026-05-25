"""center_blk_residual.py -- cycle 106d (loop 5).

Center-bucket BLK opp-aware SHRINKAGE / INFLATION residual.

Why this exists
---------------
Cycle 96e granular per-position stratification surfaced (Center, BLK) as the
single largest bucket-vs-global MAE gap in the holdout:

    Center            n=2075   bucket_mae 0.8115   global 0.4398  rel 1.845
    Center-Forward    n= 807   bucket_mae 0.8256   global 0.4398  rel 1.877
    Forward-Center    n=1038   bucket_mae 0.6953   global 0.4398  rel 1.581

Cycles 97b / 98b / 100b / 101b / 102d all rejected flat-or-feature-based
attempts to fix this with a global per-position scale (factor sweeps all
regressed non-Center stats or broke WF). The SHIPPED pattern proven by
cycles cb39cbd6 / dfd4ce0b / f1ae0919 (foul_residual / blowout_residual /
heat_check_shrinkage_residual) is: train a STRATIFIED RESIDUAL on the
specific stratum where the global model fails, output a SHRINKAGE FACTOR
(bounded multiplicative), and apply it ONLY when the stratum gate fires.

Stratum gate
------------
    position in {Center, Center-Forward, Forward-Center} AND stat == 'blk'

Features (rich, opp-aware)
--------------------------
    season_blk_per_36       -- player BLK tendency (proxy: l10_blk / l10_min * 36)
    l5_blk
    l10_blk
    opp_team_pace_l5        -- from _TeamAdvancedL5 (None -> 0.0)
    opp_team_oreb_pct_l5    -- from _TeamAdvancedL5 (None -> 0.0)
    opp_def_blk_l5          -- proxy: opp_def_blk (existing opp-defence factor)
    min_avg_l5              -- l5_min (allocation expectations)
    is_starter              -- proxy: 1.0 if l5_min >= 22 else 0.0
    score_margin_pregame    -- abs(home_spread); 0.0 when missing

Target
------
    ratio = actual_blk / predicted_blk
    clipped to [0.80, 1.50] (model can shrink OR inflate, bounded)

Artifact
--------
    data/models/center_blk_residual.lgb   (+ meta JSON)

Scope
-----
Applied ONLY to stat == 'blk' AND position in {Center, Center-Forward,
Forward-Center}. Every other (stat, position) combination is a strict no-op
(factor = 1.0).

See tests/test_center_blk_residual.py for the 6 regression tests.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "center_blk_residual.lgb")
META_PATH = os.path.join(PROJECT_DIR, "data", "models", "center_blk_residual_meta.json")

FEATURE_NAMES: List[str] = [
    "season_blk_per_36",
    "l5_blk",
    "l10_blk",
    "opp_team_pace_l5",
    "opp_team_oreb_pct_l5",
    "opp_def_blk_l5",
    "min_avg_l5",
    "is_starter",
    "score_margin_pregame",
]

# Bounded factor clamp -- model can shrink or inflate but bounded.
FACTOR_FLOOR = 0.80
FACTOR_CEIL = 1.50

# Center stratum (matches cycle 96e granular buckets surfaced by
# build_player_positions(); strings come from commonplayerinfo's POSITION).
CENTER_POSITIONS = frozenset({"Center", "Center-Forward", "Forward-Center"})

# This residual applies only to BLK predictions.
APPLIES_TO_STATS = frozenset({"blk"})


# -- helpers -----------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return v


def is_center_position(position: Optional[str]) -> bool:
    """True iff position string falls in the Center bucket."""
    if position is None:
        return False
    return str(position) in CENTER_POSITIONS


def in_center_blk_stratum(stat: str, position: Optional[str]) -> bool:
    """Gate for the residual. Stat must be 'blk' AND position in Center bucket."""
    if stat not in APPLIES_TO_STATS:
        return False
    return is_center_position(position)


def build_feature_row(
    *,
    l5_blk: Any,
    l10_blk: Any,
    l5_min: Any,
    l10_min: Any,
    opp_def_blk: Any,
    opp_team_pace_l5: Any = None,
    opp_team_oreb_pct_l5: Any = None,
    home_spread: Any = None,
) -> List[float]:
    """Construct a FEATURE_NAMES-aligned float row from a per-game prediction row."""
    l5b = max(0.0, _safe_float(l5_blk))
    l10b = max(0.0, _safe_float(l10_blk))
    l5m = max(0.0, _safe_float(l5_min))
    l10m = max(0.0, _safe_float(l10_min))
    # season_blk_per_36 proxy: l10_blk / l10_min * 36 (per-36 normalisation).
    season_blk_per_36 = (l10b / l10m * 36.0) if l10m > 0.0 else 0.0
    opp_def = _safe_float(opp_def_blk, default=1.0)
    pace = _safe_float(opp_team_pace_l5, default=0.0)
    oreb = _safe_float(opp_team_oreb_pct_l5, default=0.0)
    is_starter = 1.0 if l5m >= 22.0 else 0.0
    margin = abs(_safe_float(home_spread, default=0.0))
    return [
        season_blk_per_36,
        l5b,
        l10b,
        pace,
        oreb,
        opp_def,
        l5m,
        is_starter,
        margin,
    ]


# -- model class -------------------------------------------------------------

class CenterBlkResidualModel:
    """LightGBM regressor predicting actual_blk / predicted_blk for Centers.

    Output is hard-clamped to [FACTOR_FLOOR, FACTOR_CEIL] at predict time.
    """

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 1.0) -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(np.clip(fallback_mean, FACTOR_FLOOR, FACTOR_CEIL))
        self.feature_names = list(FEATURE_NAMES)

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 250,
            learning_rate: float = 0.04,
            num_leaves: int = 15,
            min_data_in_leaf: int = 15,
            seed: int = 42) -> "CenterBlkResidualModel":
        import lightgbm as lgb
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.size == 0:
            raise ValueError("fit called with empty training set")
        y_arr = np.clip(y_arr, FACTOR_FLOOR, FACTOR_CEIL)
        self.fallback_mean = float(np.mean(y_arr))

        train_set = lgb.Dataset(X_arr, label=y_arr, feature_name=self.feature_names)
        valid_sets = [train_set]
        valid_names = ["train"]
        callbacks = []
        if X_val is not None and y_val is not None and len(X_val) > 0:
            X_val_arr = np.asarray(X_val, dtype=np.float64)
            y_val_arr = np.clip(
                np.asarray(y_val, dtype=np.float64), FACTOR_FLOOR, FACTOR_CEIL)
            val_set = lgb.Dataset(X_val_arr, label=y_val_arr,
                                  feature_name=self.feature_names,
                                  reference=train_set)
            valid_sets.append(val_set)
            valid_names.append("val")
            callbacks.append(lgb.early_stopping(stopping_rounds=30, verbose=False))
        callbacks.append(lgb.log_evaluation(period=0))

        params = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "min_data_in_leaf": min_data_in_leaf,
            "feature_pre_filter": False,
            "verbose": -1,
            "seed": seed,
        }
        self.params = dict(params)
        self.booster = lgb.train(
            params, train_set,
            num_boost_round=num_boost_round,
            valid_sets=valid_sets, valid_names=valid_names,
            callbacks=callbacks,
        )
        return self

    def _clip(self, x):
        return np.clip(x, FACTOR_FLOOR, FACTOR_CEIL)

    def predict(self, X: Sequence[Sequence[float]]) -> np.ndarray:
        if self.booster is None:
            return np.full(len(X), self.fallback_mean, dtype=np.float64)
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        preds = self.booster.predict(X_arr)
        return self._clip(np.asarray(preds, dtype=np.float64))

    def predict_one(self, row: Sequence[float]) -> float:
        if self.booster is None:
            return float(self.fallback_mean)
        arr = np.asarray(row, dtype=np.float64).reshape(1, -1)
        pred = float(self.booster.predict(arr)[0])
        return float(np.clip(pred, FACTOR_FLOOR, FACTOR_CEIL))

    def save(self, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> None:
        if self.booster is None:
            raise RuntimeError("save called before fit")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        self.booster.save_model(model_path)
        meta = {
            "feature_names": self.feature_names,
            "fallback_mean": float(self.fallback_mean),
            "params": self.params,
            "stratum": {
                "stats":     sorted(APPLIES_TO_STATS),
                "positions": sorted(CENTER_POSITIONS),
            },
            "clamp": {"floor": FACTOR_FLOOR, "ceil": FACTOR_CEIL},
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["CenterBlkResidualModel"]:
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 1.0))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# -- dispatch helper ---------------------------------------------------------

def center_blk_shrinkage_factor(
    *,
    residual_model: Optional[CenterBlkResidualModel],
    stat: str,
    position: Optional[str],
    feature_row: Dict[str, Any],
) -> float:
    """Return a multiplicative factor in [FACTOR_FLOOR, FACTOR_CEIL] for the BLK
    prediction.

    Returns 1.0 (no-op) when:
      * stat is not 'blk'
      * position is not in CENTER_POSITIONS (or None)
      * residual_model is None (artifact missing -- back-compat)

    Caller multiplies the BLK point prediction by this factor.
    """
    if not in_center_blk_stratum(stat, position):
        return 1.0
    if residual_model is None:
        return 1.0
    row = build_feature_row(
        l5_blk=feature_row.get("l5_blk"),
        l10_blk=feature_row.get("l10_blk"),
        l5_min=feature_row.get("l5_min"),
        l10_min=feature_row.get("l10_min"),
        opp_def_blk=feature_row.get("opp_def_blk"),
        opp_team_pace_l5=feature_row.get("opp_team_pace_l5"),
        opp_team_oreb_pct_l5=feature_row.get("opp_team_oreb_pct_l5"),
        home_spread=feature_row.get("home_spread"),
    )
    return float(residual_model.predict_one(row))


def apply_center_blk_shrinkage(pred: float, factor: float) -> float:
    """Multiplicative apply with defensive clamp and >=0 floor."""
    f = float(np.clip(factor, FACTOR_FLOOR, FACTOR_CEIL))
    return max(0.0, float(pred) * f)


__all__ = [
    "FEATURE_NAMES",
    "FACTOR_FLOOR",
    "FACTOR_CEIL",
    "CENTER_POSITIONS",
    "APPLIES_TO_STATS",
    "CenterBlkResidualModel",
    "is_center_position",
    "in_center_blk_stratum",
    "build_feature_row",
    "center_blk_shrinkage_factor",
    "apply_center_blk_shrinkage",
    "MODEL_PATH",
    "META_PATH",
]
