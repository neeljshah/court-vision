"""sim_models.py — Sub-models for possession-level Monte Carlo simulation (Phase 8).

Contains: PlayTypeSelector, FatigueModel, SubstitutionModel, and shared constants.
Imported by possession_simulator.py (orchestrator).
"""

from __future__ import annotations

import os
import random
import warnings
from typing import Any

import numpy as np
import pandas as pd

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_DIR   = os.path.join(_PROJECT_DIR, "data", "models")
_MODEL_PATH  = os.path.join(_MODEL_DIR, "play_type_selector.joblib")

# ── Play-type feature names ───────────────────────────────────────────────────
FEATURES = [
    "avg_spacing", "avg_defensive_pressure", "avg_vel_toward_basket",
    "pass_count", "screen_count", "drive_count", "score_diff",
    "fast_break", "min_shot_clock_est",
]

# ── Play-type → zone distributions ───────────────────────────────────────────
PLAY_TYPE_ZONES: dict[str, list[tuple[str, float]]] = {
    "transition":  [("fast_break_layup", 0.50), ("paint", 0.30), ("3pt_arc", 0.15), ("mid_range", 0.05)],
    "drive":       [("paint", 0.65), ("mid_range", 0.15), ("3pt_arc", 0.20)],
    "cut":         [("paint", 0.85), ("fast_break_layup", 0.10), ("mid_range", 0.05)],
    "post":        [("paint", 0.60), ("mid_range", 0.35), ("3pt_arc", 0.05)],
    "catch_shoot": [("3pt_arc", 0.60), ("mid_range", 0.30), ("paint", 0.10)],
    "spot_up":     [("3pt_arc", 0.55), ("mid_range", 0.30), ("paint", 0.15)],
    "pullup":      [("mid_range", 0.45), ("3pt_arc", 0.35), ("paint", 0.20)],
}
DEFAULT_ZONES = [("paint", 0.35), ("mid_range", 0.15), ("3pt_arc", 0.40), ("fast_break_layup", 0.10)]
ZONE_XFG = {"paint": 0.58, "mid_range": 0.40, "3pt_arc": 0.36, "fast_break_layup": 0.64}
ZONE_PTS = {"paint": 2, "mid_range": 2, "3pt_arc": 3, "fast_break_layup": 2}

# Precomputed (zones, cumulative_weights) — avoids alloc in hot loop
PLAY_TYPE_ZONE_DATA: dict[str, tuple[list[str], list[float]]] = {
    k: ([p[0] for p in v], [sum(x[1] for x in v[:i+1]) for i in range(len(v))])
    for k, v in PLAY_TYPE_ZONES.items()
}
DEFAULT_ZONE_DATA: tuple[list[str], list[float]] = (
    [p[0] for p in DEFAULT_ZONES],
    [sum(x[1] for x in DEFAULT_ZONES[:i+1]) for i in range(len(DEFAULT_ZONES))],
)
XFG_FEATS: dict[str, dict] = {
    "paint":            {"shot_zone_basic": "Restricted Area",   "shot_zone_area": "Center(C)", "shot_zone_range": "Less Than 8 ft.", "shot_distance": 4,  "is_3pt": 0, "action_type": "Layup Shot"},
    "fast_break_layup": {"shot_zone_basic": "Restricted Area",   "shot_zone_area": "Center(C)", "shot_zone_range": "Less Than 8 ft.", "shot_distance": 3,  "is_3pt": 0, "action_type": "Running Layup Shot"},
    "mid_range":        {"shot_zone_basic": "Mid-Range",         "shot_zone_area": "Center(C)", "shot_zone_range": "16-24 ft.",       "shot_distance": 18, "is_3pt": 0, "action_type": "Jump Shot"},
    "3pt_arc":          {"shot_zone_basic": "Above the Break 3", "shot_zone_area": "Center(C)", "shot_zone_range": "24+ ft.",         "shot_distance": 25, "is_3pt": 1, "action_type": "Jump Shot"},
}


# ── PlayTypeSelector ──────────────────────────────────────────────────────────

class PlayTypeSelector:
    """XGBoost play-type classifier. Falls back to uniform if untrained."""

    def __init__(self) -> None:
        self._model: Any = None
        self._classes: list[str] = []
        if os.path.exists(_MODEL_PATH):
            self._load()

    def _load(self) -> None:
        import joblib
        bundle = joblib.load(_MODEL_PATH)
        self._model  = bundle["model"]
        self._classes = bundle["classes"]

    def is_trained(self) -> bool:
        return self._model is not None

    def sample(self, features: dict) -> str:
        probs = self.predict_proba(features)
        if not probs:
            return "cut"
        keys = list(probs)
        return random.choices(keys, [probs[c] for c in keys])[0]

    def predict_proba(self, features: dict) -> dict[str, float]:
        if not self.is_trained():
            return {c: 1.0 / max(len(self._classes), 1) for c in (self._classes or ["cut"])}
        X = pd.DataFrame([{f: features.get(f, 0.0) for f in FEATURES}])[FEATURES].fillna(0.0)
        proba = self._model.predict_proba(X)[0]
        return {c: float(p) for c, p in zip(self._classes, proba)}

    def sample_batch_np(self, X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Fast numpy-native batch prediction. Returns class-index array."""
        n = len(X)
        if not self.is_trained():
            return np.zeros(n, dtype=np.int32)
        proba = self._model.predict_proba(X)
        cum   = np.cumsum(proba, axis=1)
        rand  = rng.random((n, 1))
        return np.clip((rand > cum).sum(axis=1), 0, len(self._classes) - 1).astype(np.int32)


# ── FatigueModel ──────────────────────────────────────────────────────────────

class FatigueModel:
    """Efficiency multiplier from player fatigue indicators.

    Delegates to FatigueCurveModel (tier4_models) when trained; falls back to
    heuristic otherwise. FatigueCurveModel saves to data/models/fatigue_curve.pkl.
    """

    def __init__(self) -> None:
        self._curve: object | None = None
        try:
            from src.prediction.tier4_models import FatigueCurveModel
            c = FatigueCurveModel()
            self._curve = c if c._trained else None
        except Exception:
            pass

    def predict(self, dist_per100: float = 0.0, minutes: float = 36.0,
                games_in_last_14: int = 7) -> float:
        """Return xFG multiplier in [0.85, 1.05]."""
        if self._curve is not None:
            return self._curve.predict(dist_per100, minutes, games_in_last_14)  # type: ignore[union-attr]
        penalty  = max(0.0, games_in_last_14 - 8) * 0.01
        penalty += max(0.0, dist_per100 - 4.0) * 0.005
        return float(max(0.85, 1.0 - penalty))

    def batch_predict(self, n: int,
                      minutes: "Optional[np.ndarray]" = None) -> "np.ndarray":
        """Return fatigue multiplier array.

        If *minutes* is provided (shape (n,)), calls predict() per player with
        their observed CV minutes.  Otherwise returns 1.0 (neutral) for all.
        """
        import numpy as _np
        if minutes is not None and len(minutes) == n:
            return _np.array(
                [self.predict(minutes=float(m)) for m in minutes],
                dtype=_np.float32,
            )
        return _np.ones(n, dtype=_np.float32)


# ── SubstitutionModel ─────────────────────────────────────────────────────────

class SubstitutionModel:
    """Predicts when/who subs based on foul trouble, fatigue, score margin.

    Stub: implements foul-threshold logic; full ML retrain after lineup data
    is available from Phase G CV registry.
    """

    def should_sub(self, player_fouls: int, player_minutes: float,
                   score_diff: float, period: int) -> bool:
        """Return True if player should be subbed out."""
        if player_fouls >= 5:
            return True
        # Foul trouble in early periods: sit with 4 fouls before Q4
        if player_fouls >= 4 and period < 4:
            return True
        return False

    def apply(self, roster: list[str], fouls: dict[str, int],
              minutes: dict[str, float], score_diff: float, period: int) -> list[str]:
        """Return active roster after applying sub logic. Never empties roster."""
        active = [p for p in roster
                  if not self.should_sub(fouls.get(p, 0), minutes.get(p, 0.0),
                                         score_diff, period)]
        return active if active else roster


# ── Training helper ───────────────────────────────────────────────────────────

def train_play_type_selector(csv_path: str) -> None:
    """Train PlayTypeSelector on labelled possession CSV and save joblib."""
    import joblib
    import xgboost as xgb
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    df = pd.read_csv(csv_path, low_memory=False)
    df = df[df["play_type"].notna() & (df["play_type"].str.lower() != "unknown")].reset_index(drop=True)
    if len(df) < 10:
        print(f"[play_type] Not enough labelled rows ({len(df)}). Aborting.")
        return

    X = df[[f for f in FEATURES if f in df.columns]].fillna(0.0)
    for f in FEATURES:
        if f not in X.columns:
            X[f] = 0.0
    X = X[FEATURES]

    counts = df["play_type"].value_counts()
    mask   = df["play_type"].isin(counts[counts >= 2].index)
    df, X  = df[mask].reset_index(drop=True), X[mask].reset_index(drop=True)
    if len(df) < 10:
        print(f"[play_type] Not enough rows after filtering ({len(df)}). Aborting.")
        return

    le      = LabelEncoder()
    y       = le.fit_transform(df["play_type"].astype(str))
    classes = list(le.classes_)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, use_label_encoder=False,
        eval_metric="mlogloss", random_state=42, verbosity=0,
    )
    model.fit(X_tr, y_tr)
    acc = accuracy_score(y_te, model.predict(X_te))
    print(f"[play_type] accuracy={acc:.3f}  classes={classes}  n_train={len(X_tr)}")

    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump({"model": model, "classes": classes}, _MODEL_PATH)
    print(f"[play_type] saved -> {_MODEL_PATH}")
