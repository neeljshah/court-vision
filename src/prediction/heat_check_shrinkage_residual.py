"""heat_check_shrinkage_residual.py -- cycle 103b (loop 5). Heat-check SHRINKAGE.

WHY: cycle 102b REJECTED a learned residual that REPLACED the cycle-88 Q4 PPM
projection (got too flat, under-projected genuine high-usage scorers; +0.24
MAE in stratum). Cycle 96d's heuristic shrinkage was directionally right
(-0.18 vs heuristic) but missed the ship gate by 0.018 MAE.

THE FIX: train a residual that outputs a SHRINKAGE FACTOR ∈ [0.70, 1.00]
applied MULTIPLICATIVELY to the cycle-88 projection. This BLENDS the
cycle-88 extrapolation (good for sustained scorers) with mean-reversion
(good for genuine hot streaks). Multiplicative, not replacement.

Stratum gate (unchanged from v1)
--------------------------------
    q3_ppm > 1.5 * q12_ppm  AND  q12_ppm > 0.3  AND  q4_min >= 0.5

Target
------
    ratio = actual_q4_ppm / naive_q4_ppm,  where naive_q4_ppm = q3_ppm
    clipped to [0.70, 1.00] (model can only shrink; can't over-extrapolate)

Feature schema (15 features)
----------------------------
    q1_pts, q2_pts, q3_pts
    min_q1, min_q2, min_q3
    q3_ppm, q12_ppm, q3_q12_ratio
    season_pts_per_min, l5_pts_per_min
    pos_C, pos_F, pos_G
    plus_minus_through_q3             -- per-player Q1+Q2+Q3 +/- as game-flow proxy

Artifact: data/models/heat_check_shrinkage_residual.lgb (+ meta JSON).

Scope
-----
Applied ONLY to scoring stats {pts, ast, fg3m} when the gate fires. NEVER
applied to STL/BLK/TOV (no heat-check dynamic on defensive counts).

See tests/test_heat_check_shrinkage_residual.py for the 6 regression tests.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "heat_check_shrinkage_residual.lgb")
META_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "heat_check_shrinkage_residual_meta.json")

FEATURE_NAMES: List[str] = [
    "q1_pts", "q2_pts", "q3_pts",
    "min_q1", "min_q2", "min_q3",
    "q3_ppm", "q12_ppm", "q3_q12_ratio",
    "season_pts_per_min", "l5_pts_per_min",
    "pos_C", "pos_F", "pos_G",
    "score_margin_abs",
]

# Stratum gate thresholds (mirror v1).
_GATE_RATIO_TRIGGER = 1.5
_GATE_Q12_PPM_FLOOR = 0.3

# Shrinkage factor clamp.
FACTOR_FLOOR = 0.70
FACTOR_CEIL = 1.00

# Stats this shrinkage applies to (scoring-burst-prone).
HEAT_CHECK_STATS = frozenset({"pts", "ast", "fg3m"})


# ── helpers ───────────────────────────────────────────────────────────────────

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


def _normalize_position(position_proxy: Optional[str]) -> str:
    if not position_proxy:
        return ""
    s = str(position_proxy).strip().lower()
    if not s:
        return ""
    if "center" in s:
        return "C"
    if "forward" in s:
        return "F"
    if "guard" in s:
        return "G"
    u = s.upper()
    if u == "C":
        return "C"
    if u in {"PF", "SF", "F"}:
        return "F"
    if u in {"PG", "SG", "G"}:
        return "G"
    return ""


# ── public gate ───────────────────────────────────────────────────────────────

def in_heat_check_stratum(q3_ppm: Any, q12_ppm: Any) -> bool:
    """True iff the (player, game) endQ3 row qualifies for heat_check shrinkage.

    Same definition as cycle 102b: q3_ppm > 1.5 * q12_ppm AND q12_ppm > 0.3.
    """
    q3 = _safe_float(q3_ppm, default=0.0)
    q12 = _safe_float(q12_ppm, default=0.0)
    if q12 <= _GATE_Q12_PPM_FLOOR:
        return False
    if q3 <= 0.0:
        return False
    return q3 > _GATE_RATIO_TRIGGER * q12


# ── feature builder ───────────────────────────────────────────────────────────

def build_feature_row(
    *,
    q1_pts: Any,
    q2_pts: Any,
    q3_pts: Any,
    min_q1: Any,
    min_q2: Any,
    min_q3: Any,
    season_pts_per_min: Optional[float] = None,
    l5_pts_per_min: Optional[float] = None,
    position_proxy: Optional[str] = None,
    score_margin_abs: Any = 0.0,
) -> List[float]:
    """Build a feature row matching FEATURE_NAMES (15 floats)."""
    q1p = max(0.0, _safe_float(q1_pts))
    q2p = max(0.0, _safe_float(q2_pts))
    q3p = max(0.0, _safe_float(q3_pts))
    m1 = max(0.0, _safe_float(min_q1))
    m2 = max(0.0, _safe_float(min_q2))
    m3 = max(0.0, _safe_float(min_q3))
    q3_ppm = q3p / m3 if m3 > 0.0 else 0.0
    q12_min = m1 + m2
    q12_ppm = (q1p + q2p) / q12_min if q12_min > 0.0 else 0.0
    ratio = q3_ppm / max(q12_ppm, 0.01)
    spm = (float("nan") if season_pts_per_min is None
           else _safe_float(season_pts_per_min, default=float("nan")))
    lpm = (float("nan") if l5_pts_per_min is None
           else _safe_float(l5_pts_per_min, default=float("nan")))
    pos = _normalize_position(position_proxy)
    is_c = 1.0 if pos == "C" else 0.0
    is_f = 1.0 if pos == "F" else 0.0
    is_g = 1.0 if pos == "G" else 0.0
    margin = abs(_safe_float(score_margin_abs, default=0.0))
    return [
        q1p, q2p, q3p,
        m1, m2, m3,
        q3_ppm, q12_ppm, ratio,
        spm, lpm,
        is_c, is_f, is_g,
        margin,
    ]


# ── model class ───────────────────────────────────────────────────────────────

class HeatCheckShrinkageResidualModel:
    """LightGBM regressor predicting Q4-PPM shrinkage RATIO for heat_check rows.

    Output is the predicted (actual_q4_ppm / q3_ppm) ratio, hard-clamped to
    [FACTOR_FLOOR, FACTOR_CEIL] at predict time so callers can multiply the
    cycle-88 projection by a guaranteed-in-band shrinkage.
    """

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 0.85) -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(np.clip(fallback_mean, FACTOR_FLOOR, FACTOR_CEIL))
        self.feature_names = list(FEATURE_NAMES)

    # ── training ────────────────────────────────────────────────────────────

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 250,
            learning_rate: float = 0.04,
            num_leaves: int = 15,
            min_data_in_leaf: int = 15,
            seed: int = 42) -> "HeatCheckShrinkageResidualModel":
        import lightgbm as lgb
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.size == 0:
            raise ValueError("fit called with empty training set")
        # Clip training targets to legal shrinkage band so the regressor's
        # output naturally lives in the right range.
        y_arr = np.clip(y_arr, FACTOR_FLOOR, FACTOR_CEIL)
        self.fallback_mean = float(np.mean(y_arr))

        train_set = lgb.Dataset(X_arr, label=y_arr,
                                feature_name=self.feature_names)
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
            "objective": "regression",        # MSE on the ratio target
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

    # ── inference ───────────────────────────────────────────────────────────

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

    # ── persistence ─────────────────────────────────────────────────────────

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
            "gate": {
                "ratio_trigger": _GATE_RATIO_TRIGGER,
                "q12_ppm_floor": _GATE_Q12_PPM_FLOOR,
            },
            "clamp": {"floor": FACTOR_FLOOR, "ceil": FACTOR_CEIL},
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["HeatCheckShrinkageResidualModel"]:
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 0.85))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# ── dispatch helper ───────────────────────────────────────────────────────────

def heat_check_shrinkage_factor(
    *,
    residual_model: Optional[HeatCheckShrinkageResidualModel],
    q1_pts: float, q2_pts: float, q3_pts: float,
    min_q1: float, min_q2: float, min_q3: float,
    season_pts_per_min: Optional[float] = None,
    l5_pts_per_min: Optional[float] = None,
    position_proxy: Optional[str] = None,
    score_margin_abs: float = 0.0,
) -> float:
    """Return a shrinkage factor ∈ [0.70, 1.00] for the cycle-88 projection.

    Returns 1.00 (no-op) when:
      * gate doesn't fire (not a heat_check row)
      * residual_model is None (artifact missing -- back-compat)
      * input ratios are degenerate (zero minutes)

    Caller multiplies the cycle-88 projected_final by this factor for
    pts/ast/fg3m only.
    """
    q3_min = max(0.0, _safe_float(min_q3))
    q12_min = max(0.0, _safe_float(min_q1)) + max(0.0, _safe_float(min_q2))
    if q3_min <= 0.0 or q12_min <= 0.0:
        return 1.0
    q3p = max(0.0, _safe_float(q3_pts))
    q12p = max(0.0, _safe_float(q1_pts)) + max(0.0, _safe_float(q2_pts))
    q3_ppm = q3p / q3_min
    q12_ppm = q12p / q12_min
    if not in_heat_check_stratum(q3_ppm, q12_ppm):
        return 1.0
    if residual_model is None:
        return 1.0
    row = build_feature_row(
        q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
        min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
        season_pts_per_min=season_pts_per_min,
        l5_pts_per_min=l5_pts_per_min,
        position_proxy=position_proxy,
        score_margin_abs=score_margin_abs,
    )
    return float(residual_model.predict_one(row))


def apply_shrinkage_to_projection(
    cycle88_projection: float,
    current_stat: float,
    shrinkage_factor: float,
) -> float:
    """Apply shrinkage to the REMAINING-stats portion of the cycle-88 projection.

    The already-locked-in current_stat is never altered; only the remaining
    projection (projected_final - current_stat) is scaled.

        out = current_stat + (cycle88_projection - current_stat) * shrinkage

    Factor is clamped defensively even if caller already clamped.
    """
    f = float(np.clip(shrinkage_factor, FACTOR_FLOOR, FACTOR_CEIL))
    cur = float(current_stat)
    rem = float(cycle88_projection) - cur
    return cur + rem * f


__all__ = [
    "FEATURE_NAMES",
    "FACTOR_FLOOR",
    "FACTOR_CEIL",
    "HEAT_CHECK_STATS",
    "HeatCheckShrinkageResidualModel",
    "in_heat_check_stratum",
    "build_feature_row",
    "heat_check_shrinkage_factor",
    "apply_shrinkage_to_projection",
    "MODEL_PATH",
    "META_PATH",
]
