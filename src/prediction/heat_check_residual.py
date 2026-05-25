"""heat_check_residual.py -- cycle 102b (loop 5). Heat-check Q4 PPM specialist.

STATUS: REJECTED on ship gate (probe heat_check PTS delta +0.24 vs the
heuristic baseline; gate required -0.10). NOT wired into
``live_engine.project_from_snapshot``. Artifact retained for archaeology;
the loaded module is callable but no live consumer dispatches to it.
See ``scripts/_results/heat_check_blend_v1.md`` for the rejection report.

WHY: cycle 95b's endQ3 decomposition identified `heat_check` (Q3 pts/min >
1.5x Q1-Q2 avg pts/min) as the SECOND-LARGEST endQ3 failure mode (after
foul_change): +0.53 PTS MAE excess and +0.74 bias = OVERSHOOT. The cycle-88
projector linearly extrapolates Q3's inflated PPM into Q4 but the rate mean-
reverts (defense adjusts, makes regress to baseline). Cycle 96d shipped a
HEURISTIC Bayesian shrinkage which was REJECTED (-0.082 vs the -0.10 gate).
This cycle (102b) trained a LEARNED residual following the foul_residual
pattern (cb39cbd6) -- also REJECTED. The cycle-96d heuristic shrinkage
actually outperforms both the unadjusted heuristic AND this learned head
on the heat_check stratum, but neither clears the ship gate.

This module ships a LEARNED residual following the SHIPPED foul_residual
pattern (tier1-2 cb39cbd6): a small LightGBM regressor that predicts the
actual Q4 PTS-per-minute (NOT remaining minutes -- this stratum is about
SCORING RATE that reverts, not minute reduction). At inference, when the
heat_check gate fires we REPLACE the cycle-88 extrapolation with:

    projected_final = current_stat + learned_q4_ppm * remaining_minutes_est

Outside the stratum, this module is a no-op.

Stratum gate
------------
    q3_ppm > 1.5 * q12_ppm  AND  q12_ppm > 0.3

The q12_ppm > 0.3 floor avoids divide-by-near-zero on cold-Q1+Q2 players
(per assignment spec).

Feature schema (12 features, PTS-specific)
------------------------------------------
    q1_pts, q2_pts, q3_pts
    min_q1, min_q2, min_q3
    q3_ppm, q12_ppm, q3_q12_ratio
    season_pts_per_min, l5_pts_per_min
    position one-hots (C/F/G)

Target: actual Q4 pts-per-minute (= q4_pts / q4_min). Rows where the player
sits all of Q4 (q4_min < 0.5) are dropped to avoid PPM blow-up.

Artifact: ``data/models/heat_check_residual.lgb`` (+ meta JSON).

API
---
``in_heat_check_stratum(q3_ppm, q12_ppm)``           -> bool
``build_feature_row(...)``                            -> List[float]
``HeatCheckResidualModel.{fit,predict,save,load}``    -> trained head
``stratified_heat_check_projection(...)``             -> dispatch helper

See ``tests/test_heat_check_residual.py`` for 5 regression tests.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "heat_check_residual.lgb")
META_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "heat_check_residual_meta.json")

FEATURE_NAMES: List[str] = [
    "q1_pts", "q2_pts", "q3_pts",
    "min_q1", "min_q2", "min_q3",
    "q3_ppm", "q12_ppm", "q3_q12_ratio",
    "season_pts_per_min", "l5_pts_per_min",
    "pos_C", "pos_F", "pos_G",
]

# Gate thresholds.
_GATE_RATIO_TRIGGER = 1.5
_GATE_Q12_PPM_FLOOR = 0.3

# Reasonable Q4+OT remaining minutes anchor for the projector when caller
# doesn't supply a learned minute estimate.
REG_REMAINING_MIN_AT_ENDQ3 = 12.0


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
    """True iff the (player, game) endQ3 row qualifies as heat_check.

    Definition (mirrors cycle 95b decompose_endQ3_mae):
        q3_ppm > 1.5 * q12_ppm  AND  q12_ppm > 0.3

    The q12_ppm floor avoids the divide-by-near-zero pathology on cold-Q1
    players (a 0-pt Q1+Q2 followed by any Q3 score yields infinite ratio).
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
) -> List[float]:
    """Build a feature row matching ``FEATURE_NAMES`` (14 floats).

    Per-minute rates derived inline. NaN-safe: missing season / L5 priors
    propagate as NaN (LightGBM handles natively).
    """
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
    return [
        q1p, q2p, q3p,
        m1, m2, m3,
        q3_ppm, q12_ppm, ratio,
        spm, lpm,
        is_c, is_f, is_g,
    ]


# ── model class ───────────────────────────────────────────────────────────────

class HeatCheckResidualModel:
    """LightGBM regressor predicting Q4 PTS-per-minute for heat_check rows.

    Smaller than the global minute model -- the stratum is narrow, so we
    cap leaves/min_data to prevent overfitting. Outside the gate this
    model is never consulted.
    """

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 0.7) -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(fallback_mean)
        self.feature_names = list(FEATURE_NAMES)

    # ── training ────────────────────────────────────────────────────────────

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 250,
            learning_rate: float = 0.04,
            num_leaves: int = 15,
            min_data_in_leaf: int = 15,
            seed: int = 42) -> "HeatCheckResidualModel":
        import lightgbm as lgb
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.size == 0:
            raise ValueError("fit called with empty training set")
        self.fallback_mean = float(np.mean(y_arr))

        train_set = lgb.Dataset(X_arr, label=y_arr,
                                feature_name=self.feature_names)
        valid_sets = [train_set]
        valid_names = ["train"]
        callbacks = []
        if X_val is not None and y_val is not None and len(X_val) > 0:
            X_val_arr = np.asarray(X_val, dtype=np.float64)
            y_val_arr = np.asarray(y_val, dtype=np.float64)
            val_set = lgb.Dataset(X_val_arr, label=y_val_arr,
                                  feature_name=self.feature_names,
                                  reference=train_set)
            valid_sets.append(val_set)
            valid_names.append("val")
            callbacks.append(lgb.early_stopping(stopping_rounds=30,
                                                 verbose=False))
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
            params,
            train_set,
            num_boost_round=num_boost_round,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=callbacks,
        )
        return self

    # ── inference ───────────────────────────────────────────────────────────

    def predict(self, X: Sequence[Sequence[float]]) -> np.ndarray:
        if self.booster is None:
            return np.full(len(X), self.fallback_mean, dtype=np.float64)
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        preds = self.booster.predict(X_arr)
        # PPM physically bounded: 0 to ~3 (a 3-ptr every 60s = 3.0 ppm).
        return np.clip(np.asarray(preds, dtype=np.float64), 0.0, 3.0)

    def predict_one(self, row: Sequence[float]) -> float:
        if self.booster is None:
            return float(self.fallback_mean)
        arr = np.asarray(row, dtype=np.float64).reshape(1, -1)
        pred = float(self.booster.predict(arr)[0])
        if pred < 0.0:
            pred = 0.0
        if pred > 3.0:
            pred = 3.0
        return pred

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
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["HeatCheckResidualModel"]:
        """Load artifact; return None if either file missing (back-compat)."""
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 0.7))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# ── stratified dispatch (PTS projection override) ─────────────────────────────

def stratified_heat_check_projection(
    *,
    residual_model: Optional[HeatCheckResidualModel],
    current_pts: float,
    q1_pts: float,
    q2_pts: float,
    q3_pts: float,
    min_q1: float,
    min_q2: float,
    min_q3: float,
    remaining_min: float = REG_REMAINING_MIN_AT_ENDQ3,
    season_pts_per_min: Optional[float] = None,
    l5_pts_per_min: Optional[float] = None,
    position_proxy: Optional[str] = None,
    fallback_projection: Optional[float] = None,
) -> Optional[float]:
    """Return a heat-check-aware projected_final_pts, or None when the gate
    doesn't fire (caller should keep its existing projection).

    Logic:
      * Compute q3_ppm + q12_ppm + ratio gate.
      * If gate fires AND residual_model is loaded -> return
        ``current_pts + model.predict(row) * remaining_min``.
      * If gate fires AND residual missing -> return fallback_projection
        (caller's value) unchanged. The residual is OPT-IN.
      * If gate doesn't fire -> return None to signal "no override".

    The caller is responsible for substituting the returned float into the
    appropriate per-row dict only when None is not returned.
    """
    q3_min = max(0.0, _safe_float(min_q3))
    q12_min = max(0.0, _safe_float(min_q1)) + max(0.0, _safe_float(min_q2))
    if q3_min <= 0.0 or q12_min <= 0.0:
        return None
    q3p = max(0.0, _safe_float(q3_pts))
    q12p = max(0.0, _safe_float(q1_pts)) + max(0.0, _safe_float(q2_pts))
    q3_ppm = q3p / q3_min
    q12_ppm = q12p / q12_min

    if not in_heat_check_stratum(q3_ppm, q12_ppm):
        return None

    # Gate fires.
    if residual_model is None:
        return fallback_projection

    row = build_feature_row(
        q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
        min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
        season_pts_per_min=season_pts_per_min,
        l5_pts_per_min=l5_pts_per_min,
        position_proxy=position_proxy,
    )
    learned_ppm = residual_model.predict_one(row)
    rem = max(0.0, _safe_float(remaining_min, default=0.0))
    return float(current_pts) + learned_ppm * rem


__all__ = [
    "FEATURE_NAMES",
    "HeatCheckResidualModel",
    "build_feature_row",
    "in_heat_check_stratum",
    "stratified_heat_check_projection",
    "MODEL_PATH",
    "META_PATH",
    "REG_REMAINING_MIN_AT_ENDQ3",
]
