"""tier5_models.py — Tier 5 models requiring ~100 games.

Stubs train on available data where possible; return safe defaults otherwise.
LineupChemistryModel and PacePerLineupModel are explicit stubs (need 100+ games).
"""
from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.prediction.sim_models import SubstitutionModel
from src.prediction.tier4_models import (
    _col, _load, _load_tracking, _MIN, _MDIR, _pipe_lr, _save,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MATCHUP_JSON = os.path.join(_ROOT, "data", "models", "matchup_model.json")
_LEAGUE_AVG_EFF = 112.0


# ── LineupChemistryModel ──────────────────────────────────────────────────────

class LineupChemistryModel:
    """5-man lineup → net_rtg delta. Stub until 100+ games available."""

    _FILE = "tier5_lineup_chemistry.pkl"

    def __init__(self) -> None:
        self._trained = False

    def train(self, df: pd.DataFrame | None = None) -> None:
        # Requires lineup-tagged net_rtg labels — needs 100+ games
        print("[lineup_chemistry] stub — needs 100+ games for reliable lineup net_rtg labels")

    def predict(self, lineup_ids: list[int] | None = None,
                team_avg_rtg: float = 0.0) -> float:
        """Return net_rtg delta. Returns 0.0 until trained."""
        return 0.0


# ── DefensiveMatchupMatrix ────────────────────────────────────────────────────

class DefensiveMatchupMatrix:
    """Player A vs Player B → efficiency_allowed.

    Loads from data/models/matchup_model.json if it is a {key: value} dict.
    Falls back to league avg (112.0) otherwise.
    """

    def __init__(self) -> None:
        self._data: dict[str, float] = {}
        self._trained = False
        if os.path.exists(_MATCHUP_JSON):
            try:
                with open(_MATCHUP_JSON) as f:
                    raw = json.load(f)
                # matchup_model.json may be an XGBoost learner bundle (has "learner" key)
                if isinstance(raw, dict) and "learner" not in raw:
                    self._data = {str(k): float(v) for k, v in raw.items()
                                  if isinstance(v, (int, float))}
                    self._trained = bool(self._data)
            except Exception:
                pass

    def train(self, df: pd.DataFrame | None = None) -> None:
        print("[matchup_matrix] stub — needs labeled offensive×defensive matchup sequences")

    def predict(self, player_a: str = "", player_b: str = "") -> float:
        """Return efficiency_allowed for player_b defending player_a."""
        return float(self._data.get(f"{player_a}:{player_b}", _LEAGUE_AVG_EFF))


# ── SubstitutionTimingModel ───────────────────────────────────────────────────

class SubstitutionTimingModel(SubstitutionModel):
    """LogisticRegression on score_diff + period augmenting foul-threshold logic."""

    _FILE  = "tier5_sub_timing.pkl"
    _FEATS = ["scoreboard_score_diff", "possession_duration_sec", "scoreboard_period"]

    def __init__(self) -> None:
        super().__init__()
        self._ml_pipe: Any = None
        self._trained = False
        b = _load(self._FILE)
        if b:
            self._ml_pipe, self._trained = b["pipe"], True

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty:
            return
        X = pd.DataFrame({f: _col(df, f) for f in self._FEATS}).dropna()
        if len(X) < _MIN:
            return
        # proxy label: late period + large score diff → high sub probability
        period = _col(df, "scoreboard_period").reindex(X.index, fill_value=2)
        diff   = _col(df, "scoreboard_score_diff").abs().reindex(X.index, fill_value=0)
        y = ((period >= 4) & (diff > 10)).astype(int)
        self._ml_pipe = Pipeline([("sc", StandardScaler()),
                                   ("m", LogisticRegression(C=1.0, max_iter=300))])
        self._ml_pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._ml_pipe}, self._FILE)
        print(f"[sub_timing] trained n={len(X)}")

    def should_sub(self, player_fouls: int, player_minutes: float,
                   score_diff: float, period: int) -> bool:
        # ML override: if model highly confident, sub regardless of foul count
        if self._trained and self._ml_pipe is not None:
            X = pd.DataFrame([[score_diff, player_minutes, float(period)]],
                             columns=self._FEATS)
            p = float(self._ml_pipe.predict_proba(X)[0][1])
            if p > 0.75:
                return True
        return super().should_sub(player_fouls, player_minutes, score_diff, period)


# ── MomentumModel ─────────────────────────────────────────────────────────────

class MomentumModel:
    """P(next possession scores) from scoring run context."""

    _FILE  = "tier5_momentum.pkl"
    _FEATS = ["possession_duration_sec", "scoreboard_score_diff", "fast_break_flag"]

    def __init__(self) -> None:
        self._trained = False
        b = _load(self._FILE)
        if b:
            self._pipe, self._trained = b["pipe"], True

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty:
            return
        X = pd.DataFrame({f: _col(df, f) for f in self._FEATS}).dropna()
        if len(X) < _MIN:
            return
        # proxy: high vel_toward_basket on next row = shot attempt (scoring play)
        vtb  = _col(df, "vel_toward_basket").shift(-1).reindex(X.index, fill_value=0)
        y = (vtb > 1.0).astype(int)
        self._pipe = _pipe_lr(C=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[momentum] trained n={len(X)}")

    def predict(self, run_length: int = 0, score_diff: float = 0.0,
                fast_break: bool = False) -> float:
        if not self._trained:
            return float(np.clip(0.50 + run_length * 0.02, 0.0, 0.75))
        X = pd.DataFrame([[float(run_length * 5), score_diff, int(fast_break)]],
                         columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── FoulDrawingModel ──────────────────────────────────────────────────────────

class FoulDrawingModel:
    """P(foul drawn) from drive tendency and contact proximity."""

    _FILE  = "tier5_foul_drawing.pkl"
    _FEATS = ["drive_flag", "vel_toward_basket", "nearest_opponent"]

    def __init__(self) -> None:
        self._trained = False
        b = _load(self._FILE)
        if b:
            self._pipe, self._trained = b["pipe"], True

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty:
            return
        X = pd.DataFrame({f: _col(df, f) for f in self._FEATS}).dropna()
        if len(X) < _MIN:
            return
        drive = _col(df, "drive_flag").reindex(X.index, fill_value=0)
        opp   = _col(df, "nearest_opponent").reindex(X.index, fill_value=10)
        y = ((drive > 0) & (opp < 2.0)).astype(int)
        self._pipe = _pipe_lr(C=1.0, class_weight="balanced")
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[foul_drawing] trained n={len(X)}")

    def predict(self, drives_per_36: float = 5.0, fta_tendency: float = 0.15,
                play_type: str = "drive") -> float:
        if not self._trained:
            return fta_tendency
        drive_flag = 1.0 if play_type in ("drive", "cut") else 0.0
        vtb = drives_per_36 / 36.0
        X = pd.DataFrame([[drive_flag, vtb, max(0.0, 3.0 - drive_flag * 2)]],
                         columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── SecondChanceModel ─────────────────────────────────────────────────────────

class SecondChanceModel:
    """E(second_chance_pts) from oreb rate and crash proximity."""

    _FILE  = "tier5_second_chance.pkl"
    _FEATS = ["vel_toward_basket", "distance_to_basket"]

    def __init__(self) -> None:
        self._trained = False
        b = _load(self._FILE)
        if b:
            self._pipe, self._trained = b["pipe"], True

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty:
            return
        X = pd.DataFrame({f: _col(df, f) for f in self._FEATS}).dropna()
        if len(X) < _MIN:
            return
        vtb  = _col(df, "vel_toward_basket").reindex(X.index, fill_value=0)
        dist = _col(df, "distance_to_basket").reindex(X.index, fill_value=15)
        y = (vtb / dist.clip(lower=0.5)).clip(0, 1)
        self._pipe = Pipeline([("sc", StandardScaler()), ("m", Ridge(alpha=1.0))])
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[second_chance] trained n={len(X)}")

    def predict(self, oreb_rate: float = 0.25, proximity: float = 5.0) -> float:
        """E(second_chance_pts) = oreb_rate × putback_fg × 2pts."""
        if not self._trained:
            return float(oreb_rate * 2.0 * 0.58)
        X = pd.DataFrame([[oreb_rate * 2, proximity]], columns=self._FEATS)
        return float(np.clip(self._pipe.predict(X)[0], 0.0, 2.0))


# ── PacePerLineupModel ────────────────────────────────────────────────────────

class PacePerLineupModel:
    """Pace adjustment (seconds/possession) for a lineup. Stub: team avg."""

    _FILE = "tier5_pace.pkl"

    def __init__(self) -> None:
        self._trained = False
        self._team_avg: dict[str, float] = {}

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty or "possession_duration_sec" not in df.columns:
            print("[pace] stub — no possession_duration_sec or no data")
            return
        team_col = df.get("team", pd.Series("UNK", index=df.index)).astype(str)
        self._team_avg = (
            df.assign(_team=team_col)
              .groupby("_team")["possession_duration_sec"]
              .mean()
              .to_dict()
        )
        print(f"[pace] team avg computed for {len(self._team_avg)} teams")

    def predict(self, lineup_id: str = "", team: str = "") -> float:
        """Return seconds-per-possession pace adjustment. Returns 14.0 until trained."""
        return float(self._team_avg.get(team, 14.0))


# ── convenience ───────────────────────────────────────────────────────────────

_ALL_TIER5 = [
    LineupChemistryModel, DefensiveMatchupMatrix, SubstitutionTimingModel,
    MomentumModel, FoulDrawingModel, SecondChanceModel, PacePerLineupModel,
]


def train_all_tier5(df: pd.DataFrame | None = None) -> dict[str, bool]:
    """Train all Tier 5 models. Returns {model_name: trained_bool}."""
    if df is None:
        df = _load_tracking()
    results = {}
    for cls in _ALL_TIER5:
        m = cls()
        try:
            m.train(df)
        except Exception as e:
            print(f"[{cls.__name__}] train error: {e}")
        results[cls.__name__] = getattr(m, "_trained", False)
    return results
