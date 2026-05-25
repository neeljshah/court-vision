"""minute_trajectory.py -- tier3-10 (loop 5). Learned remaining-minutes model.

WHY: cycle 95b's endQ3 decomposition surfaced FOUL_CHANGE as the dominant
residual failure mode (+0.50 PTS MAE, bias -1.25 -> under-projection).
Cycles 96c, 97e, 98a iterated three heuristic foul_factor refinements
(NNLS + round-up integer band + fractional blend); each was rejected
because the heuristic table is a coarse step function of (pf, period).

This module replaces the heuristic with a LEARNED model: predict each
player's remaining-game minutes directly from (Q1-Q3 minute trajectory,
foul state, score margin, position, season form). The learned rate then
substitutes for ``foul_trouble_factor * remaining_min_share`` in
``predict_in_game.project_snapshot`` via an opt-in helper.

Feature schema (12 features, computed at endQ3 snapshot):
    pf_through_q3      cumulative PF at endQ3
    q3_pf              PF picked up in Q3 alone (foul-burst signal)
    min_q1, min_q2, min_q3, min_through_q3
    period             always 3 for endQ3 snapshot
    score_margin_abs   |home_score - away_score|
    is_leading_team    1 if player's team is ahead, else 0
    pos_C, pos_F, pos_G   one-hot position
    l20_min            L20 avg minutes (player baseline)
    l5_min             L5 avg minutes (recent form)

Target: actual remaining-game minutes (= total_min - min_through_q3),
from the per-quarter parquet by summing Q4 + OT minutes per player.

Artifact: data/models/minute_trajectory.lgb (LightGBM Booster + meta JSON).
The model is OPT-IN -- ``predict_in_game`` keeps the heuristic by default;
``_USE_LEARNED_MINUTES=True`` plus a successful load swaps it in.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory.lgb")
META_PATH = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory_meta.json")

FEATURE_NAMES: List[str] = [
    "pf_through_q3", "q3_pf",
    "min_q1", "min_q2", "min_q3", "min_through_q3",
    "period", "score_margin_abs", "is_leading_team",
    "pos_C", "pos_F", "pos_G",
    "l20_min", "l5_min",
]

# Regulation remaining min at endQ3 = 12.0 (one Q remaining).
REG_REMAINING_MIN_AT_ENDQ3 = 12.0


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
    """Map free-text position to one of 'C', 'F', 'G' (or '' unknown)."""
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
) -> List[float]:
    """Build one feature row matching ``FEATURE_NAMES`` order.

    Missing inputs default to safe values (0 for counts, NaN for player
    baselines so LightGBM handles them natively).
    """
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
    # LightGBM handles NaN natively as a missing-value branch.
    l20 = float("nan") if l20_min is None else _safe_float(l20_min, default=float("nan"))
    l5 = float("nan") if l5_min is None else _safe_float(l5_min, default=float("nan"))
    return [
        float(pf), float(q3),
        m1, m2, m3, m_through,
        float(per), margin, float(leading),
        is_c, is_f, is_g,
        l20, l5,
    ]


class MinuteTrajectoryModel:
    """Thin wrapper around a LightGBM regressor for remaining-min prediction.

    Train via :meth:`fit`, save with :meth:`save`, load with :meth:`load`.
    Predict via :meth:`predict_one` (single feature row) or :meth:`predict`
    (batch). Returns predicted REMAINING-MINUTES (Q4 + OT), clamped to
    [0, 24] (sanity bound: no player has played 24 min in Q4+OT in our corpus).
    """

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 7.5) -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(fallback_mean)
        self.feature_names = list(FEATURE_NAMES)

    # ── training ────────────────────────────────────────────────────────────

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 400,
            learning_rate: float = 0.05,
            num_leaves: int = 31,
            min_data_in_leaf: int = 30,
            seed: int = 42) -> "MinuteTrajectoryModel":
        """Fit the LightGBM regressor on training rows.

        Uses L2 (regression) objective with MAE eval. Early stops on the
        validation set if provided.
        """
        import lightgbm as lgb
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.size == 0:
            raise ValueError("fit called with empty training set")
        # Update global mean as fallback.
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
        # Clip to physically plausible Q4+OT range.
        return np.clip(np.asarray(preds, dtype=np.float64), 0.0, 24.0)

    def predict_one(self, row: Sequence[float]) -> float:
        """Predict one feature row -> scalar minutes."""
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
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, model_path: str = MODEL_PATH,
             meta_path: str = META_PATH) -> Optional["MinuteTrajectoryModel"]:
        """Load model artifact. Returns None if either file is missing
        (back-compat for callers that opt in but artifact hasn't trained yet).
        """
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 7.5))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# ── substitution helper (project_snapshot integration) ──────────────────────

def learned_minute_factor(
    model: Optional[MinuteTrajectoryModel],
    *,
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
    reg_remaining_min: float = REG_REMAINING_MIN_AT_ENDQ3,
) -> float:
    """Compute the LEARNED replacement for ``foul_trouble_factor``.

    Returns ``learned_remaining_min / reg_remaining_min``, the ratio that
    substitutes for the heuristic foul_factor in the project_snapshot
    pace formula. Result is clamped to [0.0, 2.0] -- values > 1.0 mean the
    player is projected to play MORE Q4 minutes than the 12.0-min regulation
    cap (rare but possible if OT is anticipated).

    If ``model`` is None, returns 1.0 (no adjustment -- back-compat with
    callers that opt in but haven't loaded the artifact yet).
    """
    if model is None:
        return 1.0
    if reg_remaining_min <= 0:
        return 1.0
    row = build_feature_row(
        pf_through_q3=pf_through_q3,
        q3_pf=q3_pf,
        min_q1=min_q1,
        min_q2=min_q2,
        min_q3=min_q3,
        period=3,
        score_margin_abs=score_margin_abs,
        is_leading_team=is_leading_team,
        position_proxy=position_proxy,
        l20_min=l20_min,
        l5_min=l5_min,
    )
    pred_min = model.predict_one(row)
    ratio = pred_min / reg_remaining_min
    if ratio < 0.0:
        ratio = 0.0
    if ratio > 2.0:
        ratio = 2.0
    return float(ratio)


__all__ = [
    "FEATURE_NAMES",
    "MinuteTrajectoryModel",
    "build_feature_row",
    "learned_minute_factor",
    "MODEL_PATH",
    "META_PATH",
    "REG_REMAINING_MIN_AT_ENDQ3",
]
