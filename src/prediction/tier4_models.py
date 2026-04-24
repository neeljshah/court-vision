"""tier4_models.py — Tier 4 CV/ML models (~50-game dataset).

Trains on player-frame data from data/tracking/*/features.csv.
Safe defaults returned when _trained=False (insufficient data).
"""
from __future__ import annotations

import glob
import os
from typing import Any

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
_MIN  = 20  # minimum samples to attempt training


# ── shared helpers ────────────────────────────────────────────────────────────

def _load_tracking() -> pd.DataFrame:
    """Load features.csv from all game subdirs under data/tracking/."""
    frames = []
    for p in sorted(glob.glob(os.path.join(_TDIR, "*/features.csv"))):
        try:
            df = pd.read_csv(p, low_memory=False)
            df["_game"] = os.path.basename(os.path.dirname(p))
            frames.append(df)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _col(df: pd.DataFrame, c: str, fill: float = 0.0) -> pd.Series:
    if c not in df.columns:
        return pd.Series(fill, index=df.index, dtype=float)
    return pd.to_numeric(df[c], errors="coerce").fillna(fill)


def _pipe_lr(**kw: Any) -> Pipeline:
    return Pipeline([("sc", StandardScaler()), ("m", LogisticRegression(max_iter=300, **kw))])


def _pipe_ridge(**kw: Any) -> Pipeline:
    return Pipeline([("sc", StandardScaler()), ("m", Ridge(**kw))])


def _save(obj: Any, name: str) -> None:
    if not _JL:
        return
    os.makedirs(_MDIR, exist_ok=True)
    joblib.dump(obj, os.path.join(_MDIR, name))
    print(f"[{name}] saved -> {_MDIR}/{name}")


def _load(name: str) -> Any:
    if not _JL:
        return None
    p = os.path.join(_MDIR, name)
    return joblib.load(p) if os.path.exists(p) else None


def _build_X(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    return pd.DataFrame({f: _col(df, f) for f in feats})


# ── ReboundPositioningModel ───────────────────────────────────────────────────

class ReboundPositioningModel:
    """P(oreb) from crash speed and proximity at shot."""

    _FILE  = "tier4_rebound.pkl"
    _FEATS = ["vel_toward_basket", "distance_to_ball", "distance_to_basket", "team_spacing"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        vtb  = _col(df, "vel_toward_basket").reindex(X.index, fill_value=0)
        zone = df.get("court_zone", pd.Series("", index=df.index))
        zone = zone.reindex(X.index, fill_value="").astype(str)
        y = ((vtb > 0.5) & (zone == "paint")).astype(int)
        self._pipe = _pipe_lr(C=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[rebound] trained n={len(X)}")

    def predict(self, vel_toward_basket: float = 0.0, distance_to_ball: float = 5.0,
                distance_to_basket: float = 10.0, team_spacing: float = 200.0) -> float:
        if not self._trained:
            return 0.25
        X = pd.DataFrame([[vel_toward_basket, distance_to_ball, distance_to_basket, team_spacing]],
                         columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── FatigueCurveModel ─────────────────────────────────────────────────────────

class FatigueCurveModel:
    """dist_per100 + minutes + games_in_last_14 → efficiency_multiplier [0.85, 1.05].

    Saved to data/models/fatigue_curve.pkl — path read by sim_models.FatigueModel.
    """

    _FILE  = "fatigue_curve.pkl"
    _FEATS = ["dist_per100", "minutes", "games_in_last_14"]

    def __init__(self) -> None:
        self._trained = False
        b = _load(self._FILE)
        if b:
            self._pipe, self._trained = b["pipe"], True

    def _player_game_agg(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["_pid"]    = df.get("player_id", pd.Series("", index=df.index)).astype(str)
        df["_game"]   = df.get("_game", pd.Series("g0", index=df.index)).astype(str)
        df["_vel"]    = _col(df, "velocity")
        df["_vtb"]    = _col(df, "vel_toward_basket")
        df["_frm"]    = _col(df, "frame")
        df["_period"] = _col(df, "scoreboard_period", fill=2.0)

        key = ["_pid", "_game"]
        base = df.groupby(key).agg(
            dist_per100=("_vel",  lambda x: float(x.mean()) * 100),
            minutes    =("_frm",  lambda x: float(x.max()) / (30 * 60)),
        )
        early_mask = df["_period"] <= 2
        late_mask  = df["_period"] >= 4
        vtb_early  = df[early_mask].groupby(key)["_vtb"].mean().rename("vtb_early")
        vtb_late   = df[late_mask ].groupby(key)["_vtb"].mean().rename("vtb_late")

        agg = base.join(vtb_early).join(vtb_late).reset_index()
        agg = agg.dropna(subset=["vtb_early", "vtb_late"])
        agg["games_in_last_14"] = 7.0  # placeholder — no schedule data in tracking
        agg["efficiency_multiplier"] = (
            agg["vtb_late"] / (agg["vtb_early"].abs() + 1e-6)
        ).clip(0.85, 1.05)
        return agg

    def train(self, df: pd.DataFrame | None = None) -> None:
        if df is None:
            df = _load_tracking()
        if df.empty:
            return
        agg = self._player_game_agg(df)
        agg = agg.dropna(subset=self._FEATS + ["efficiency_multiplier"])
        if len(agg) < _MIN:
            print(f"[fatigue] {len(agg)} player-game rows — need {_MIN}")
            return
        X = agg[self._FEATS].values
        y = agg["efficiency_multiplier"].values
        self._pipe = _pipe_ridge(alpha=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[fatigue] trained n={len(agg)}")

    def predict(self, dist_per100: float = 0.0, minutes: float = 36.0,
                games_in_last_14: int = 7) -> float:
        if not self._trained:
            penalty  = max(0.0, games_in_last_14 - 8) * 0.01
            penalty += max(0.0, dist_per100 - 4.0) * 0.005
            return float(max(0.85, 1.0 - penalty))
        X = np.array([[dist_per100, minutes, float(games_in_last_14)]])
        return float(np.clip(self._pipe.predict(X)[0], 0.85, 1.05))


# ── LateGameEfficiencyModel ───────────────────────────────────────────────────

class LateGameEfficiencyModel:
    """P(player shoots above season avg efficiency in Q4)."""

    _FILE  = "tier4_late_game.pkl"
    _FEATS = ["scoreboard_period", "scoreboard_score_diff", "possession_duration_sec"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        vtb = _col(df, "vel_toward_basket").reindex(X.index, fill_value=0)
        y = (vtb > vtb.median()).astype(int)
        self._pipe = _pipe_lr(C=0.5)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[late_game] trained n={len(X)}")

    def predict(self, period: int = 4, score_diff: float = 0.0,
                minutes_played: float = 30.0) -> float:
        if not self._trained:
            return 0.50
        X = pd.DataFrame([[float(period), score_diff, minutes_played]], columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── CloseoutQualityModel ──────────────────────────────────────────────────────

class CloseoutQualityModel:
    """xFG boost for shooter based on defender closeout speed and shot clock."""

    _FILE  = "tier4_closeout.pkl"
    _FEATS = ["vel_toward_basket", "shot_clock_est"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        # target: inverse of defender proximity — farther defender → shooter xFG boost
        opp = _col(df, "nearest_opponent").reindex(X.index, fill_value=5.0)
        y = (5.0 - opp.clip(upper=5.0))  # 0 = well-guarded, 5 = wide open
        self._pipe = _pipe_ridge(alpha=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[closeout] trained n={len(X)}")

    def predict(self, closeout_speed: float = 2.0, shot_clock: float = 10.0) -> float:
        """Return xFG boost in [-0.10, +0.10]. Positive = less contest."""
        if not self._trained:
            return 0.0
        X = pd.DataFrame([[closeout_speed, shot_clock]], columns=self._FEATS)
        raw = float(self._pipe.predict(X)[0])
        return float(np.clip(raw * 0.02, -0.10, 0.10))


# ── HelpDefenseModel ─────────────────────────────────────────────────────────

class HelpDefenseModel:
    """P(help defense triggered) from avg pressure and team spacing."""

    _FILE  = "tier4_help_def.pkl"
    _FEATS = ["nearest_opponent", "team_spacing"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        paint_opp = _col(df, "paint_count_opp").reindex(X.index, fill_value=0)
        y = (paint_opp > 1).astype(int)
        self._pipe = _pipe_lr(C=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[help_def] trained n={len(X)}")

    def predict(self, avg_defensive_pressure: float = 5.0,
                spacing: float = 200.0) -> float:
        if not self._trained:
            return 0.30
        X = pd.DataFrame([[avg_defensive_pressure, spacing]], columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── BallStagnationModel ───────────────────────────────────────────────────────

class BallStagnationModel:
    """Stagnation score (0-1): P(possession > 14s given dynamics)."""

    _FILE  = "tier4_stagnation.pkl"
    _FEATS = ["possession_duration_sec", "drive_flag", "fast_break_flag"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        dur = _col(df, "possession_duration_sec").reindex(X.index, fill_value=0)
        y = (dur > 14).astype(int)
        self._pipe = _pipe_lr(C=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[stagnation] trained n={len(X)}")

    def predict(self, pass_count: float = 3.0, drive_count: float = 1.0,
                screen_count: float = 1.0) -> float:
        if not self._trained:
            return float(np.clip((pass_count - drive_count * 2) / 10.0, 0.0, 1.0))
        # map to tracked features: long duration proxy from pass/drive counts
        dur_proxy = max(0.0, pass_count * 1.5 - drive_count * 2.0)
        X = pd.DataFrame([[dur_proxy, int(drive_count > 0), 0]], columns=self._FEATS)
        return float(np.clip(self._pipe.predict_proba(X)[0][1], 0.0, 1.0))


# ── ScreenEffectivenessModel ──────────────────────────────────────────────────

class ScreenEffectivenessModel:
    """Pts created per screen from spacing and possession context."""

    _FILE  = "tier4_screen.pkl"
    _FEATS = ["team_spacing", "possession_duration_sec"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        # target: vel_toward_basket as proxy for shot quality created
        y = _col(df, "vel_toward_basket").reindex(X.index, fill_value=0)
        self._pipe = _pipe_ridge(alpha=1.0)
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[screen] trained n={len(X)}")

    def predict(self, screen_count: float = 1.0, spacing: float = 200.0) -> float:
        """Return estimated pts_created_per_screen."""
        if not self._trained:
            return 0.15
        dur_proxy = screen_count * 3.0
        X = pd.DataFrame([[spacing, dur_proxy]], columns=self._FEATS)
        return float(np.clip(self._pipe.predict(X)[0] * 0.5, 0.0, 1.0))


# ── TurnoverPressureModel ─────────────────────────────────────────────────────

class TurnoverPressureModel:
    """P(turnover) given defensive pressure and play type."""

    _FILE  = "tier4_tov.pkl"
    _FEATS = ["nearest_opponent", "handler_isolation", "vel_toward_basket"]

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
        X = _build_X(df, self._FEATS).dropna()
        if len(X) < _MIN:
            return
        evts = df.get("event", pd.Series("", index=df.index))
        evts = evts.reindex(X.index, fill_value="").astype(str).str.lower()
        y = (evts == "turnover").astype(int)
        if y.sum() < 5:
            # proxy: high pressure + low vel → probable tov risk frame
            opp = _col(df, "nearest_opponent").reindex(X.index, fill_value=10)
            vtb = _col(df, "vel_toward_basket").reindex(X.index, fill_value=0)
            y = ((opp < 2.0) & (vtb < 0.3)).astype(int)
        self._pipe = _pipe_lr(C=0.5, class_weight="balanced")
        self._pipe.fit(X, y)
        self._trained = True
        _save({"pipe": self._pipe}, self._FILE)
        print(f"[tov_pressure] trained n={len(X)}")

    def predict(self, avg_pressure_score: float = 5.0,
                play_type: str = "drive") -> float:
        if not self._trained:
            return 0.12
        isolation = max(0.0, 10.0 - avg_pressure_score)
        vel = 1.0 if play_type in ("drive", "transition") else 0.3
        X = pd.DataFrame([[avg_pressure_score, isolation, vel]], columns=self._FEATS)
        return float(self._pipe.predict_proba(X)[0][1])


# ── convenience ───────────────────────────────────────────────────────────────

_ALL_TIER4 = [
    ReboundPositioningModel, FatigueCurveModel, LateGameEfficiencyModel,
    CloseoutQualityModel, HelpDefenseModel, BallStagnationModel,
    ScreenEffectivenessModel, TurnoverPressureModel,
]


def train_all_tier4(df: pd.DataFrame | None = None) -> dict[str, bool]:
    """Train all Tier 4 models. Returns {model_name: trained_bool}."""
    if df is None:
        df = _load_tracking()
    results = {}
    for cls in _ALL_TIER4:
        m = cls()
        try:
            m.train(df)
        except Exception as e:
            print(f"[{cls.__name__}] train error: {e}")
        results[cls.__name__] = m._trained
    return results
