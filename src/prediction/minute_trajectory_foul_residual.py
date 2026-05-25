"""minute_trajectory_foul_residual.py -- tier1-2 (loop 5). Foul-change specialist.

WHY: cycle 9d3 (minute_trajectory) shipped a LightGBM model that is GLOBALLY
-10% PTS MAE vs the heuristic, but FAILS on the foul_change stratum (cycle 95b
decomposition; +0.16 PTS MAE inside the stratum). The opposite-direction
signal is real -- foul-trouble players are a distinct sub-population whose Q4
minutes are governed by an entirely different dynamic (coach sit decision)
than the global pace+rate signal the cycle-9d3 model averages over.

This module trains a SECOND specialized model on ONLY the foul_change stratum
and REPLACES the global minute_trajectory's prediction when foul_change
criteria are met. Strict stratified blending -- no probabilistic mixing.

Stratum gate (matches cycle 95b's `foul_change` definition expanded to the
endQ3 snapshot, where Q4 PF is unobservable):

    gate = (q3_pf >= 2)               # foul-burst already happened in Q3
        OR (pf_through_q3 >= 3)       # already in foul trouble at endQ3
        OR (q3_pf == 0 AND pf_through_q3 == 4)  # one away from foul-out edge

The expanded gate ensures n > 200 (per the assignment: "criteria must not be
too strict; n needs to be > 200 for stable training"). The first two clauses
match the empirical foul_change definition; the third widens to capture
sit-prone players who arrived at endQ3 with 4 fouls but stayed quiet in Q3.

Feature schema -- inherits ALL 14 global features then APPENDS 4 foul-rate
intensity features (so the residual model has access to the same context the
global model uses PLUS the foul-burst dynamics that distinguish the stratum):

    [global 14]
    q3_pf_extra            (alias for q3_pf to satisfy schema-vs-name)
    q2_pf                  fouls in Q2 alone (early-foul-trouble signal)
    total_pf_through_q3    duplicates pf_through_q3 (kept for clarity)
    pf_per_min_q3          q3_pf / max(min_q3, 1.0)  -- foul rate intensity

Target: actual remaining-game minutes (= total_min - min_through_q3), SAME
as the global model. We're training a SPECIALIST, not a residual on top of
the global -- the dispatch logic at inference picks one or the other.

Artifact: data/models/minute_trajectory_foul_residual.lgb (+ meta JSON).
The model is OPT-IN -- ``_USE_FOUL_RESIDUAL=True`` plus a successful load
swaps it in for the global model when the gate fires.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "minute_trajectory_foul_residual.lgb")
META_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "minute_trajectory_foul_residual_meta.json")

# Global-model feature names (must stay in sync with
# src.prediction.minute_trajectory.FEATURE_NAMES).
_GLOBAL_FEATURES: List[str] = [
    "pf_through_q3", "q3_pf",
    "min_q1", "min_q2", "min_q3", "min_through_q3",
    "period", "score_margin_abs", "is_leading_team",
    "pos_C", "pos_F", "pos_G",
    "l20_min", "l5_min",
]

# Foul-rate intensity extensions (residual-only, appended).
_EXTRA_FEATURES: List[str] = [
    "q2_pf",
    "total_pf_through_q3",
    "pf_per_min_q3",
    "q3_pf_extra",
]

FEATURE_NAMES: List[str] = _GLOBAL_FEATURES + _EXTRA_FEATURES

REG_REMAINING_MIN_AT_ENDQ3 = 12.0

# Gate thresholds (defined as module constants for testability + clarity).
_GATE_Q3_PF_MIN = 2          # picked up 2+ in Q3
_GATE_TOTAL_PF_MIN = 3       # total pf at endQ3 >= 3
_GATE_FOUL_OUT_EDGE = 4      # at 4 pf at endQ3 even if Q3 was quiet


# ── helpers (mirror minute_trajectory.py) ─────────────────────────────────────

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


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


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


# ── public API ────────────────────────────────────────────────────────────────

def in_foul_change_stratum(
    *,
    q3_pf: Any,
    pf_through_q3: Any,
) -> bool:
    """Decide whether the (player, game) endQ3 row belongs in the foul_change
    stratum -- i.e. whether the residual model should REPLACE the global
    minute_trajectory prediction.

    The gate is intentionally broad enough to keep training n > 200 (the
    assignment's stability bar) but narrow enough that the dominant signal
    inside the stratum is foul-trouble dynamics, not generic Q4 minutes.
    """
    q3 = max(0, _safe_int(q3_pf, default=0))
    total = max(0, _safe_int(pf_through_q3, default=0))
    if q3 >= _GATE_Q3_PF_MIN:
        return True
    if total >= _GATE_TOTAL_PF_MIN:
        return True
    if q3 == 0 and total == _GATE_FOUL_OUT_EDGE:
        return True
    return False


def build_feature_row(
    *,
    pf_through_q3: Any,
    q3_pf: Any,
    min_q1: Any,
    min_q2: Any,
    min_q3: Any,
    period: Any = 3,
    score_margin_abs: Any = 0.0,
    is_leading_team: Any = 0,
    position_proxy: Optional[str] = None,
    l20_min: Optional[float] = None,
    l5_min: Optional[float] = None,
    q2_pf: Any = 0,
) -> List[float]:
    """Build a feature row matching ``FEATURE_NAMES`` (14 global + 4 extra).

    Identical contract to the global model's ``build_feature_row`` for the
    first 14 fields; the 4 trailing fields are the foul-rate intensity
    extensions. ``q2_pf`` is the only NEW required-ish field (defaults to 0 if
    the caller doesn't pass it -- the model handles the absence gracefully).
    """
    pf = max(0, _safe_int(pf_through_q3, default=0))
    q3 = max(0, _safe_int(q3_pf, default=0))
    q2 = max(0, _safe_int(q2_pf, default=0))
    m1 = max(0.0, _safe_float(min_q1, default=0.0))
    m2 = max(0.0, _safe_float(min_q2, default=0.0))
    m3 = max(0.0, _safe_float(min_q3, default=0.0))
    m_through = m1 + m2 + m3
    per = max(1, _safe_int(period, default=3))
    margin = abs(_safe_float(score_margin_abs, default=0.0))
    leading = 1 if _safe_int(is_leading_team, default=0) >= 1 else 0
    pos = _normalize_position(position_proxy)
    is_c = 1.0 if pos == "C" else 0.0
    is_f = 1.0 if pos == "F" else 0.0
    is_g = 1.0 if pos == "G" else 0.0
    l20 = float("nan") if l20_min is None else _safe_float(l20_min, default=float("nan"))
    l5 = float("nan") if l5_min is None else _safe_float(l5_min, default=float("nan"))

    # Foul intensity extensions.
    pf_per_min = q3 / max(m3, 1.0)
    total = pf  # alias

    return [
        # 14 global features (must match _GLOBAL_FEATURES order):
        float(pf), float(q3),
        m1, m2, m3, m_through,
        float(per), margin, float(leading),
        is_c, is_f, is_g,
        l20, l5,
        # 4 residual extensions:
        float(q2),
        float(total),
        float(pf_per_min),
        float(q3),  # q3_pf_extra alias
    ]


class FoulChangeResidualModel:
    """LightGBM regressor specialized for the foul_change stratum.

    Smaller model than the global -- the stratum has 5-10x less data than
    the full corpus, so we restrict capacity (fewer leaves, more min-data-in-
    leaf) to prevent overfitting. The model's only job is to predict Q4+OT
    minutes for foul-trouble-prone players; outside the stratum its
    predictions are NEVER consulted.
    """

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 5.0) -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(fallback_mean)
        self.feature_names = list(FEATURE_NAMES)

    # ── training ────────────────────────────────────────────────────────────

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 300,
            learning_rate: float = 0.04,
            num_leaves: int = 15,            # smaller than global (31)
            min_data_in_leaf: int = 20,
            seed: int = 42) -> "FoulChangeResidualModel":
        """Fit on the foul_change subset only."""
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
        return np.clip(np.asarray(preds, dtype=np.float64), 0.0, 24.0)

    def predict_one(self, row: Sequence[float]) -> float:
        if self.booster is None:
            return float(self.fallback_mean)
        arr = np.asarray(row, dtype=np.float64).reshape(1, -1)
        pred = float(self.booster.predict(arr)[0])
        if pred < 0.0:
            pred = 0.0
        if pred > 24.0:
            pred = 24.0
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
                "q3_pf_min": _GATE_Q3_PF_MIN,
                "total_pf_min": _GATE_TOTAL_PF_MIN,
                "foul_out_edge": _GATE_FOUL_OUT_EDGE,
            },
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["FoulChangeResidualModel"]:
        """Load artifact. Returns None if either file is missing -- callers
        that opt in stay safe and fall back to the global model.
        """
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 5.0))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# ── stratified dispatch ───────────────────────────────────────────────────────

def stratified_minute_factor(
    *,
    global_model,                # MinuteTrajectoryModel (or None)
    residual_model: Optional[FoulChangeResidualModel],
    pf_through_q3: Any,
    q3_pf: Any,
    min_q1: Any,
    min_q2: Any,
    min_q3: Any,
    score_margin_abs: Any = 0.0,
    is_leading_team: Any = 0,
    position_proxy: Optional[str] = None,
    l20_min: Optional[float] = None,
    l5_min: Optional[float] = None,
    q2_pf: Any = 0,
    reg_remaining_min: float = REG_REMAINING_MIN_AT_ENDQ3,
) -> float:
    """Dispatch to residual-or-global model and return the minute-ratio
    suitable for plugging into ``project_final`` as ``foul_factor``.

    Logic:
      * If gate fires AND residual_model is loaded -> use residual prediction.
      * Else if global_model is loaded -> use global learned_minute_factor.
      * Else -> return 1.0 (no adjustment, identical to legacy heuristic path
        when no models are present).

    The return value is clamped to [0.0, 2.0] (ratios > 1.0 mean projected
    Q4+OT > 12 min, plausible only if OT is anticipated -- rare but allowed).
    """
    from src.prediction.minute_trajectory import learned_minute_factor

    if reg_remaining_min <= 0:
        return 1.0

    fire_gate = in_foul_change_stratum(q3_pf=q3_pf, pf_through_q3=pf_through_q3)

    if fire_gate and residual_model is not None:
        row = build_feature_row(
            pf_through_q3=pf_through_q3,
            q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            period=3,
            score_margin_abs=score_margin_abs,
            is_leading_team=is_leading_team,
            position_proxy=position_proxy,
            l20_min=l20_min, l5_min=l5_min,
            q2_pf=q2_pf,
        )
        pred_min = residual_model.predict_one(row)
        ratio = pred_min / reg_remaining_min
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 2.0:
            ratio = 2.0
        return float(ratio)

    # Fallback: global learned model (no gate fire or residual missing).
    return learned_minute_factor(
        global_model,
        pf_through_q3=pf_through_q3,
        q3_pf=q3_pf,
        min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
        score_margin_abs=score_margin_abs,
        is_leading_team=is_leading_team,
        position_proxy=position_proxy,
        l20_min=l20_min, l5_min=l5_min,
        reg_remaining_min=reg_remaining_min,
    )


__all__ = [
    "FEATURE_NAMES",
    "FoulChangeResidualModel",
    "build_feature_row",
    "in_foul_change_stratum",
    "stratified_minute_factor",
    "MODEL_PATH",
    "META_PATH",
    "REG_REMAINING_MIN_AT_ENDQ3",
]
