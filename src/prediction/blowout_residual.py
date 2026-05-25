"""blowout_residual.py -- cycle 102a (loop 5). Blowout-flip specialist.

WHY: cycle 95b's decomposition surfaced ``blowout_flip`` (close-at-Q3 ->
blown-open in Q4) as a residual failure mode, but the original 50-game probe
captured 0 rows on its tight gate (|Q3 margin|<15 AND |final margin|>20). With
the 550-game retro now available (cycle 91a parquet expanded) the stratum
populates. We mirror the SHIPPED foul_residual pattern (tier1-2 cycle cb39cbd6)
exactly -- train a SECOND specialist that REPLACES the cycle-88 heuristic
``blowout_factor`` on the blowout_flip subset, with stratified dispatch.

Stratum gate (LOOSENED from cycle 95b's failed gate so it populates n>=200):

    gate = (|Q3 margin| <= 18 AND |final margin| >= 20)
        OR (|Q3 margin| <= 12 AND |final margin| >= 18)

At INFERENCE time the final margin is unobservable. We therefore use a
LIVE-PROXY gate that operates on observed Q3 signals only -- the close-game
+ late-game-velocity signature that the trained model can extrapolate
forward from. The probe + WF eval use the FULL gate (with ground-truth final
margin) for honest stratum-membership classification; the live dispatch
uses the proxy gate. This is the same separation foul_residual uses
(`in_foul_change_stratum` at train, proxy via snap_pf at inference).

Feature schema (18 features, mirrors foul_residual structure: 14 shared +
4 blowout-specific):

    [shared 14]
    pf_through_q3, q3_pf,
    min_q1, min_q2, min_q3, min_through_q3,
    period (3), score_margin_abs (|Q3 margin|, unsigned),
    is_leading_team (at endQ3),
    pos_C, pos_F, pos_G,
    l20_min, l5_min,
    [blowout extensions]
    score_margin_signed_q3   signed Q3 margin from THIS team's POV
    score_velocity_q3        Q3 margin - Q2 margin (Q4 trend proxy)
    abs_q3_margin            duplicates score_margin_abs for clarity
    margin_class             0/1/2 bucket (close / mid / wide) at Q3

Target: actual Q4+OT minutes (= total_min - min_through_q3) -- SAME as
foul_residual. We train a SPECIALIST minute model; the dispatch picks one.

Artifact: data/models/blowout_residual.lgb (+ meta JSON).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "blowout_residual.lgb")
META_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "blowout_residual_meta.json")

# Shared global-model feature schema (must stay in sync with
# minute_trajectory.FEATURE_NAMES order).
_SHARED_FEATURES: List[str] = [
    "pf_through_q3", "q3_pf",
    "min_q1", "min_q2", "min_q3", "min_through_q3",
    "period", "score_margin_abs", "is_leading_team",
    "pos_C", "pos_F", "pos_G",
    "l20_min", "l5_min",
]

# Blowout-specific extensions appended after the shared 14.
_EXTRA_FEATURES: List[str] = [
    "score_margin_signed_q3",
    "score_velocity_q3",
    "abs_q3_margin",
    "margin_class",
]

FEATURE_NAMES: List[str] = _SHARED_FEATURES + _EXTRA_FEATURES

REG_REMAINING_MIN_AT_ENDQ3 = 12.0

# ── stratum gate thresholds (training/probe ground-truth definition) ──────────
_GATE_Q3_MARGIN_NARROW = 18.0    # |Q3 margin| <= 18 AND |final margin| >= 20
_GATE_FINAL_MARGIN_WIDE = 20.0
_GATE_Q3_MARGIN_TIGHT = 12.0     # |Q3 margin| <= 12 AND |final margin| >= 18
_GATE_FINAL_MARGIN_MID = 18.0

# ── live-proxy gate thresholds (inference-time, no final margin available) ────
# At endQ3 we can only see (|Q3 margin|, score_velocity_q3). The proxy fires
# when a close-ish Q3 (<=18) shows a Q4-prone velocity profile (positive
# velocity into a leading team -> blowout brewing, OR signed Q3 small AND
# velocity high). Empirically the |Q3| <= 18 cap captures every game that
# turns into a >= 20-pt final margin in training; velocity gives a soft
# additional filter so we don't fire on every close game.
_LIVE_PROXY_ABS_Q3_MAX = 18.0
_LIVE_PROXY_VELOCITY_MIN = 4.0   # Q3 - Q2 margin swing >= 4 pts


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

def in_blowout_flip_stratum(
    *,
    q3_margin_abs: Any,
    final_margin_abs: Any,
) -> bool:
    """Ground-truth stratum classifier (TRAINING + PROBE use).

    Requires the actual final-margin (so this is unusable at inference time;
    use ``in_blowout_flip_live_proxy`` instead for live dispatch).
    """
    q3_abs = abs(_safe_float(q3_margin_abs, default=0.0))
    final_abs = abs(_safe_float(final_margin_abs, default=0.0))
    if q3_abs <= _GATE_Q3_MARGIN_NARROW and final_abs >= _GATE_FINAL_MARGIN_WIDE:
        return True
    if q3_abs <= _GATE_Q3_MARGIN_TIGHT and final_abs >= _GATE_FINAL_MARGIN_MID:
        return True
    return False


def in_blowout_flip_live_proxy(
    *,
    q3_margin_abs: Any,
    score_velocity_q3: Any,
) -> bool:
    """Live-proxy gate (INFERENCE use). Fires when the Q3 snapshot's
    margin + velocity profile is consistent with a Q4 blowout-flip
    in training data. Approximation -- we don't have the final margin
    yet -- but it's the same compromise foul_residual makes with its
    snap_pf -> q3_pf_proxy estimate.
    """
    q3_abs = abs(_safe_float(q3_margin_abs, default=0.0))
    velocity = abs(_safe_float(score_velocity_q3, default=0.0))
    if q3_abs > _LIVE_PROXY_ABS_Q3_MAX:
        return False
    if velocity < _LIVE_PROXY_VELOCITY_MIN:
        return False
    return True


def _margin_class(q3_margin_abs: float) -> int:
    """0 = close (<=8), 1 = mid (9-15), 2 = wide (16+)."""
    a = abs(q3_margin_abs)
    if a <= 8.0:
        return 0
    if a <= 15.0:
        return 1
    return 2


def build_feature_row(
    *,
    pf_through_q3: Any,
    q3_pf: Any,
    min_q1: Any,
    min_q2: Any,
    min_q3: Any,
    period: Any = 3,
    score_margin_abs: Any = 0.0,
    score_margin_signed_q3: Any = 0.0,
    score_velocity_q3: Any = 0.0,
    is_leading_team: Any = 0,
    position_proxy: Optional[str] = None,
    l20_min: Optional[float] = None,
    l5_min: Optional[float] = None,
) -> List[float]:
    """Build a feature row matching ``FEATURE_NAMES`` (14 shared + 4 extras)."""
    pf = max(0, _safe_int(pf_through_q3, default=0))
    q3 = max(0, _safe_int(q3_pf, default=0))
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

    signed_q3 = _safe_float(score_margin_signed_q3, default=0.0)
    velocity = _safe_float(score_velocity_q3, default=0.0)
    abs_q3 = abs(signed_q3) if signed_q3 != 0.0 else margin
    mclass = float(_margin_class(abs_q3))

    return [
        # 14 shared features (must match _SHARED_FEATURES order):
        float(pf), float(q3),
        m1, m2, m3, m_through,
        float(per), margin, float(leading),
        is_c, is_f, is_g,
        l20, l5,
        # 4 blowout extensions:
        float(signed_q3),
        float(velocity),
        float(abs_q3),
        mclass,
    ]


class BlowoutResidualModel:
    """LightGBM regressor specialized for the blowout_flip stratum."""

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
            num_leaves: int = 15,
            min_data_in_leaf: int = 20,
            seed: int = 42) -> "BlowoutResidualModel":
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
                "q3_narrow": _GATE_Q3_MARGIN_NARROW,
                "final_wide": _GATE_FINAL_MARGIN_WIDE,
                "q3_tight": _GATE_Q3_MARGIN_TIGHT,
                "final_mid": _GATE_FINAL_MARGIN_MID,
                "live_proxy_q3_max": _LIVE_PROXY_ABS_Q3_MAX,
                "live_proxy_velocity_min": _LIVE_PROXY_VELOCITY_MIN,
            },
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["BlowoutResidualModel"]:
        """Load artifact. Returns None if either file is missing."""
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

def stratified_blowout_factor(
    *,
    heuristic_factor: float,
    residual_model: Optional[BlowoutResidualModel],
    pf_through_q3: Any,
    q3_pf: Any,
    min_q1: Any,
    min_q2: Any,
    min_q3: Any,
    score_margin_abs: Any = 0.0,
    score_margin_signed_q3: Any = 0.0,
    score_velocity_q3: Any = 0.0,
    is_leading_team: Any = 0,
    position_proxy: Optional[str] = None,
    l20_min: Optional[float] = None,
    l5_min: Optional[float] = None,
    reg_remaining_min: float = REG_REMAINING_MIN_AT_ENDQ3,
) -> float:
    """Dispatch to residual-or-heuristic and return the minute-ratio factor.

    Logic:
      * If live proxy gate fires AND residual_model is loaded -> residual.
      * Else -> heuristic_factor (the cycle-88 blowout_factor caller passed).

    Result clamped to [0.0, 2.0].
    """
    if reg_remaining_min <= 0:
        return float(heuristic_factor)

    fire_gate = in_blowout_flip_live_proxy(
        q3_margin_abs=score_margin_abs,
        score_velocity_q3=score_velocity_q3,
    )

    if fire_gate and residual_model is not None:
        row = build_feature_row(
            pf_through_q3=pf_through_q3,
            q3_pf=q3_pf,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            period=3,
            score_margin_abs=score_margin_abs,
            score_margin_signed_q3=score_margin_signed_q3,
            score_velocity_q3=score_velocity_q3,
            is_leading_team=is_leading_team,
            position_proxy=position_proxy,
            l20_min=l20_min, l5_min=l5_min,
        )
        pred_min = residual_model.predict_one(row)
        ratio = pred_min / reg_remaining_min
        if ratio < 0.0:
            ratio = 0.0
        if ratio > 2.0:
            ratio = 2.0
        return float(ratio)

    return float(heuristic_factor)


__all__ = [
    "FEATURE_NAMES",
    "BlowoutResidualModel",
    "build_feature_row",
    "in_blowout_flip_stratum",
    "in_blowout_flip_live_proxy",
    "stratified_blowout_factor",
    "MODEL_PATH",
    "META_PATH",
    "REG_REMAINING_MIN_AT_ENDQ3",
]
