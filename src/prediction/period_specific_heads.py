"""period_specific_heads.py -- cycle 105b (loop 5).

Per-(stat, snapshot-point) LightGBM regressors for in-play stat projection.

WHY: cycle-88 project_snapshot uses a SINGLE pace-based linear extrapolation
for every snapshot point (endQ1 / endQ2 / endQ3). But the conditional
distribution of "remaining stat | game state" varies hugely with the
snapshot point: endQ1 has only 12 min observed (high variance, regression
to the mean dominates), endQ3 has 36 min (low variance, current pace is a
strong signal). A single linear extrapolator cannot adapt to that.

This module trains 7 stats * 3 snapshot points = 21 separate LightGBM
regressors. At inference, ``predict_remaining`` dispatches by snapshot
period; missing artifacts return None so callers can cleanly fall back to
cycle-88 linear extrapolation.

Feature schema (per snapshot point, target = remaining stat sum from this
snapshot through end of regulation Q4):

    current_stat        sum of stat through snapshot (e.g. q1_pts if endQ1)
    per_min_rate        current_stat / min_through_snapshot (0.0 if min==0)
    min_through         minutes played through snapshot
    pf_through          fouls through snapshot
    score_margin_abs    |home_score - away_score| at snapshot
    is_leading_team     1 if this player's team is leading, else 0
    l5_stat             L5 rolling per-game mean of the same stat
    l20_stat            L20 rolling per-game mean
    l20_min             L20 rolling per-game minutes
    pos_C, pos_F, pos_G one-hot of player position proxy

Artifacts saved to ``data/models/period_heads/<stat>_<point>.lgb`` plus a
sibling ``.meta.json`` recording feature_names, fallback_mean, and the
LightGBM params actually used at fit time.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models", "period_heads")

STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SNAPSHOT_POINTS: Tuple[str, ...] = ("endQ1", "endQ2", "endQ3")

# Quarters that have been OBSERVED at each snapshot point.
SNAPSHOT_QUARTERS: Dict[str, Tuple[int, ...]] = {
    "endQ1": (1,),
    "endQ2": (1, 2),
    "endQ3": (1, 2, 3),
}

# Quarters that are STILL TO COME (the prediction target window).
REMAINING_QUARTERS: Dict[str, Tuple[int, ...]] = {
    "endQ1": (2, 3, 4),
    "endQ2": (3, 4),
    "endQ3": (4,),
}

# Snapshot period dispatch: at the start of period P, clock=12:00, we are
# at end of period (P-1).
PERIOD_TO_SNAPSHOT: Dict[int, str] = {2: "endQ1", 3: "endQ2", 4: "endQ3"}

FEATURE_NAMES: List[str] = [
    "current_stat", "per_min_rate", "min_through", "pf_through",
    "score_margin_abs", "is_leading_team",
    "l5_stat", "l20_stat", "l20_min",
    "pos_C", "pos_F", "pos_G",
]


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:
        return default
    return x


def _normalize_position(pos: Optional[str]) -> str:
    if not pos:
        return ""
    s = str(pos).strip().lower()
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
    current_stat: Any,
    min_through: Any,
    pf_through: Any = 0.0,
    score_margin_abs: Any = 0.0,
    is_leading_team: Any = 0,
    l5_stat: Optional[float] = None,
    l20_stat: Optional[float] = None,
    l20_min: Optional[float] = None,
    position_proxy: Optional[str] = None,
) -> List[float]:
    """Build a single feature row matching FEATURE_NAMES order."""
    cs = _safe_float(current_stat)
    mt = max(0.0, _safe_float(min_through))
    rate = (cs / mt) if mt > 1e-6 else 0.0
    pf = max(0.0, _safe_float(pf_through))
    margin = abs(_safe_float(score_margin_abs))
    lead = 1.0 if _safe_float(is_leading_team) >= 1.0 else 0.0
    pos = _normalize_position(position_proxy)
    is_c = 1.0 if pos == "C" else 0.0
    is_f = 1.0 if pos == "F" else 0.0
    is_g = 1.0 if pos == "G" else 0.0
    l5 = float("nan") if l5_stat is None else _safe_float(l5_stat, default=float("nan"))
    l20 = float("nan") if l20_stat is None else _safe_float(l20_stat, default=float("nan"))
    l20m = float("nan") if l20_min is None else _safe_float(l20_min, default=float("nan"))
    return [cs, rate, mt, pf, margin, lead, l5, l20, l20m, is_c, is_f, is_g]


def artifact_paths(stat: str, point: str, models_dir: str = MODELS_DIR) -> Tuple[str, str]:
    """Return (model_path, meta_path) for one (stat, snapshot-point) head."""
    base = os.path.join(models_dir, f"{stat}_{point}")
    return base + ".lgb", base + ".meta.json"


class PeriodHead:
    """Thin LightGBM regressor wrapper for one (stat, snapshot-point) head."""

    def __init__(self, booster=None, params: Optional[Dict[str, Any]] = None,
                 fallback_mean: float = 0.0,
                 stat: str = "", point: str = "") -> None:
        self.booster = booster
        self.params = params or {}
        self.fallback_mean = float(fallback_mean)
        self.feature_names = list(FEATURE_NAMES)
        self.stat = stat
        self.point = point

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float],
            *, X_val: Optional[Sequence[Sequence[float]]] = None,
            y_val: Optional[Sequence[float]] = None,
            num_boost_round: int = 400,
            learning_rate: float = 0.05,
            num_leaves: int = 31,
            min_data_in_leaf: int = 30,
            seed: int = 42) -> "PeriodHead":
        import lightgbm as lgb
        X_arr = np.asarray(X, dtype=np.float64)
        y_arr = np.asarray(y, dtype=np.float64)
        if X_arr.size == 0:
            raise ValueError("fit called with empty corpus")
        self.fallback_mean = float(np.mean(y_arr))

        train_set = lgb.Dataset(X_arr, label=y_arr, feature_name=self.feature_names)
        valid_sets = [train_set]
        valid_names = ["train"]
        callbacks = [lgb.log_evaluation(period=0)]
        if X_val is not None and y_val is not None and len(X_val) > 0:
            Xv = np.asarray(X_val, dtype=np.float64)
            yv = np.asarray(y_val, dtype=np.float64)
            valid_sets.append(lgb.Dataset(Xv, label=yv,
                                          feature_name=self.feature_names,
                                          reference=train_set))
            valid_names.append("val")
            callbacks.insert(0, lgb.early_stopping(stopping_rounds=30, verbose=False))

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
            params, train_set, num_boost_round=num_boost_round,
            valid_sets=valid_sets, valid_names=valid_names, callbacks=callbacks,
        )
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> np.ndarray:
        if self.booster is None:
            return np.full(len(X), self.fallback_mean, dtype=np.float64)
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        preds = self.booster.predict(X_arr)
        # Stats are non-negative counts; clip below 0.
        return np.clip(np.asarray(preds, dtype=np.float64), 0.0, None)

    def predict_one(self, row: Sequence[float]) -> float:
        if self.booster is None:
            return float(self.fallback_mean)
        arr = np.asarray(row, dtype=np.float64).reshape(1, -1)
        p = float(self.booster.predict(arr)[0])
        return max(0.0, p)

    def save(self, model_path: Optional[str] = None,
             meta_path: Optional[str] = None) -> None:
        if self.booster is None:
            raise RuntimeError("save before fit")
        if model_path is None or meta_path is None:
            model_path, meta_path = artifact_paths(self.stat, self.point)
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        self.booster.save_model(model_path)
        meta = {
            "feature_names": self.feature_names,
            "fallback_mean": float(self.fallback_mean),
            "params": self.params,
            "stat": self.stat,
            "point": self.point,
        }
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

    @classmethod
    def load(cls, stat: str, point: str,
             models_dir: str = MODELS_DIR) -> Optional["PeriodHead"]:
        model_path, meta_path = artifact_paths(stat, point, models_dir)
        if not (os.path.exists(model_path) and os.path.exists(meta_path)):
            return None
        try:
            import lightgbm as lgb
            booster = lgb.Booster(model_file=model_path)
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            inst = cls(booster=booster, params=meta.get("params", {}),
                       fallback_mean=meta.get("fallback_mean", 0.0),
                       stat=meta.get("stat", stat),
                       point=meta.get("point", point))
            inst.feature_names = list(meta.get("feature_names", FEATURE_NAMES))
            return inst
        except Exception:
            return None


# ── dispatch helpers (used by live_engine) ───────────────────────────────────

# Module-level cache so repeated project calls don't re-read artifacts.
_HEAD_CACHE: Dict[Tuple[str, str], Optional[PeriodHead]] = {}


def snapshot_point_for(period: Any, clock: Any) -> Optional[str]:
    """Map (period, clock) to snapshot point name. Returns None unless we
    are at an end-of-period boundary (clock=12:00 in the new period).

    Accepts clock as 'MM:SS' string or numeric remaining-minutes.
    """
    try:
        p = int(period)
    except (TypeError, ValueError):
        return None
    if p not in PERIOD_TO_SNAPSHOT:
        return None
    # parse clock to remaining-minutes
    rem: float
    if isinstance(clock, (int, float)):
        rem = float(clock)
    else:
        s = str(clock or "").strip()
        if not s:
            rem = 0.0
        else:
            sep = ":" if ":" in s else None
            if sep is None:
                try:
                    rem = float(s)
                except ValueError:
                    return None
            else:
                head, _, tail = s.partition(":")
                try:
                    rem = float(head) + (float(tail) / 60.0 if tail else 0.0)
                except ValueError:
                    return None
    # Treat clock >= 11.95 as boundary (matches retro reconstruction).
    if rem >= 11.95:
        return PERIOD_TO_SNAPSHOT[p]
    return None


def get_head(stat: str, point: str,
             models_dir: str = MODELS_DIR) -> Optional[PeriodHead]:
    """Cached loader. Returns None if artifact absent (caller falls back)."""
    key = (stat, point)
    if key in _HEAD_CACHE:
        return _HEAD_CACHE[key]
    head = PeriodHead.load(stat, point, models_dir=models_dir)
    _HEAD_CACHE[key] = head
    return head


def predict_remaining(
    stat: str, point: str, *,
    current_stat: float, min_through: float,
    pf_through: float = 0.0,
    score_margin_abs: float = 0.0,
    is_leading_team: int = 0,
    l5_stat: Optional[float] = None,
    l20_stat: Optional[float] = None,
    l20_min: Optional[float] = None,
    position_proxy: Optional[str] = None,
    models_dir: str = MODELS_DIR,
) -> Optional[float]:
    """Predict REMAINING stat (from snapshot through end-of-regulation).

    Returns None when no artifact is present for (stat, point) -- caller
    should fall back to cycle-88 linear extrapolation.
    """
    head = get_head(stat, point, models_dir=models_dir)
    if head is None:
        return None
    row = build_feature_row(
        current_stat=current_stat, min_through=min_through, pf_through=pf_through,
        score_margin_abs=score_margin_abs, is_leading_team=is_leading_team,
        l5_stat=l5_stat, l20_stat=l20_stat, l20_min=l20_min,
        position_proxy=position_proxy,
    )
    return head.predict_one(row)


def reset_cache() -> None:
    """Clear the module-level head cache (useful in tests)."""
    _HEAD_CACHE.clear()


__all__ = [
    "STATS", "SNAPSHOT_POINTS", "SNAPSHOT_QUARTERS", "REMAINING_QUARTERS",
    "PERIOD_TO_SNAPSHOT", "FEATURE_NAMES", "MODELS_DIR",
    "build_feature_row", "artifact_paths", "PeriodHead",
    "snapshot_point_for", "get_head", "predict_remaining", "reset_cache",
]
