"""live_models.py — Phase 11: Live in-game models M70-M75.

All models use sklearn with safe defaults when insufficient data.
"""
from __future__ import annotations

import glob
import os
from typing import Any, Dict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import joblib
    _JL = True
except ImportError:
    _JL = False

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TDIR = os.path.join(_ROOT, "data", "tracking")
_MDIR = os.path.join(_ROOT, "data", "models")
_MIN  = 20


def _load_tracking() -> pd.DataFrame:
    frames = []
    for p in sorted(glob.glob(os.path.join(_TDIR, "*/features.csv"))):
        try:
            df = pd.read_csv(p, low_memory=False)
            df["_game"] = os.path.basename(os.path.dirname(p))
            frames.append(df)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pipe(estimator: Any) -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("model", estimator)])


def _save(model: Any, name: str) -> None:
    if _JL:
        os.makedirs(_MDIR, exist_ok=True)
        joblib.dump(model, os.path.join(_MDIR, name))


def _load(name: str) -> Any:
    path = os.path.join(_MDIR, name)
    if _JL and os.path.exists(path):
        try:
            obj = joblib.load(path)
            if hasattr(obj, "predict"):
                return obj
        except Exception:
            pass
    return None


# ── M70: LivePropUpdater ───────────────────────────────────────────────────────

class LivePropUpdater:
    """M70 — Bayesian update: pre-game sim prior + halftime box → full projection."""

    PKL = "live_prop_updater.pkl"
    FEATS = ["pre_game_proj", "halftime_actual", "minutes_played_ratio"]

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(Ridge(alpha=1.0))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["full_game_actual"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN:
            return False
        self._model.fit(df[self.FEATS].values, df["full_game_actual"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, pre_game_proj: float, halftime_actual: float,
                minutes_played_ratio: float) -> float:
        """Return projected full-game stat."""
        if not self._trained:
            remaining = max(0.0, 1.0 - minutes_played_ratio)
            return halftime_actual + pre_game_proj * remaining
        x = np.array([[pre_game_proj, halftime_actual, minutes_played_ratio]])
        return float(self._model.predict(x)[0])


# ── M71: ComebackProbabilityModel ─────────────────────────────────────────────

class ComebackProbabilityModel:
    """M71 — P(trailing team recovers) given score_diff and minutes_remaining."""

    PKL = "comeback_prob.pkl"
    FEATS = ["score_diff", "minutes_remaining", "home_flag"]

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(LogisticRegression(max_iter=500))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["came_back"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN or df["came_back"].nunique() < 2:
            return False
        self._model.fit(df[self.FEATS].values, df["came_back"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, score_diff: float, minutes_remaining: float,
                home_flag: int = 0) -> float:
        """Return P(comeback) for trailing team. score_diff < 0 means trailing."""
        if not self._trained:
            # Heuristic: ~2% per point deficit, time-discounted
            time_factor = minutes_remaining / 48.0
            return float(np.clip(0.5 + score_diff * 0.02 * time_factor, 0.02, 0.98))
        x = np.array([[score_diff, minutes_remaining, home_flag]])
        return float(self._model.predict_proba(x)[0][1])


# ── M72: GarbageTimePredictor ─────────────────────────────────────────────────

class GarbageTimePredictor:
    """M72 — P(game decided, starters pulled). Returns bool is_garbage_time."""

    PKL = "m72_garbage_time.pkl"
    FEATS = ["score_diff", "minutes_remaining", "scoreboard_period"]
    THRESHOLD = 0.65

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(LogisticRegression(max_iter=500))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["is_garbage_time"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN or df["is_garbage_time"].nunique() < 2:
            return False
        self._model.fit(df[self.FEATS].values, df["is_garbage_time"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, score_diff: float, minutes_remaining: float,
                scoreboard_period: int) -> bool:
        """Return True if game is in garbage time."""
        if not self._trained:
            return abs(score_diff) >= 20 and minutes_remaining <= 6.0
        x = np.array([[score_diff, minutes_remaining, scoreboard_period]])
        prob = float(self._model.predict_proba(x)[0][1])
        return prob >= self.THRESHOLD


# ── M73: FoulTroubleModel ─────────────────────────────────────────────────────

class FoulTroubleModel:
    """M73 — P(player fouls out given foul_count at current period)."""

    PKL = "m73_foul_trouble.pkl"
    FEATS = ["foul_count", "period", "minutes_remaining"]

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(LogisticRegression(max_iter=500))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["fouled_out"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN or df["fouled_out"].nunique() < 2:
            return False
        self._model.fit(df[self.FEATS].values, df["fouled_out"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, foul_count: int, period: int, minutes_remaining: float) -> float:
        """Return P(player fouls out). Suppress props if > 0.3."""
        if not self._trained:
            fouls_remaining = 6 - foul_count
            periods_remaining = max(0, 4 - period) + minutes_remaining / 12.0
            if fouls_remaining <= 0:
                return 1.0
            rate = 1.0 / max(fouls_remaining * periods_remaining, 0.1)
            return float(np.clip(rate * 0.15, 0.0, 0.99))
        x = np.array([[foul_count, period, minutes_remaining]])
        return float(self._model.predict_proba(x)[0][1])


# ── M74: Q4UsageModel ─────────────────────────────────────────────────────────

class Q4UsageModel:
    """M74 — Usage multiplier for players in close Q4."""

    PKL = "q4_usage.pkl"
    FEATS = ["score_diff", "player_usage_rate", "close_game_flag"]

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(Ridge(alpha=1.0))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["q4_usage_multiplier"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN:
            return False
        self._model.fit(df[self.FEATS].values, df["q4_usage_multiplier"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, score_diff: float, player_usage_rate: float,
                close_game_flag: int) -> float:
        """Return usage_multiplier clamped to [0.7, 1.5].

        In untrained mode: always boost the highest-usage player in close Q4
        (star players get usage share ≥1/roster_size = 0.1 for any roster).
        """
        if not self._trained:
            if close_game_flag:
                return 1.2
            return 1.0
        x = np.array([[score_diff, player_usage_rate, close_game_flag]])
        return float(np.clip(self._model.predict(x)[0], 0.7, 1.5))


# ── M75: MomentumRunModel ──────────────────────────────────────────────────────

class MomentumRunModel:
    """M75 — P(scoring run continues ≥5 pts) given current run length."""

    PKL = "momentum_run.pkl"
    FEATS = ["run_length", "team_fg_pct_last_10", "time_since_last_timeout"]

    def __init__(self) -> None:
        loaded = _load(self.PKL)
        if loaded is not None:
            self._model = loaded
            self._trained = True
        else:
            self._model = _pipe(LogisticRegression(max_iter=500))
            self._trained = False

    def train(self) -> bool:
        df = _load_tracking()
        cols = self.FEATS + ["run_continued"]
        present = [c for c in cols if c in df.columns]
        if len(present) < len(cols) or len(df) < _MIN:
            return False
        df = df[cols].dropna()
        if len(df) < _MIN or df["run_continued"].nunique() < 2:
            return False
        self._model.fit(df[self.FEATS].values, df["run_continued"].values)
        self._trained = True
        _save(self._model, self.PKL)
        return True

    def predict(self, run_length: int, team_fg_pct_last_10: float,
                time_since_last_timeout: float) -> float:
        """Return P(run extends ≥5 more pts)."""
        if not self._trained:
            base = 0.35 + run_length * 0.03 + team_fg_pct_last_10 * 0.2
            return float(np.clip(base, 0.05, 0.85))
        x = np.array([[run_length, team_fg_pct_last_10, time_since_last_timeout]])
        return float(self._model.predict_proba(x)[0][1])


# ── convenience ───────────────────────────────────────────────────────────────

def train_all() -> Dict[str, bool]:
    results = {}
    for cls in (LivePropUpdater, ComebackProbabilityModel, GarbageTimePredictor,
                FoulTroubleModel, Q4UsageModel, MomentumRunModel):
        m = cls()
        results[cls.__name__] = m.train()
    return results
