"""src/prediction/inplay_winprob.py — R10_M5 in-play win probability (cycle R10_M5).

Wraps the LightGBM boosters trained by ``scripts/train_inplay_winprob_endq3.py``
for snapshot-conditional home-team win probability. Three artifacts:

    data/models/inplay_winprob_endq1.lgb
    data/models/inplay_winprob_endq2.lgb
    data/models/inplay_winprob_endq3.lgb

The endQ3 model is the SHIP (probe R10_M5: Brier 0.1350 vs pregame baseline
0.2653, accuracy 81.33%, AUC 0.901). endQ1/endQ2 are below the 0.183 Brier
ship gate but still useful as informative priors over the naive home-rate
baseline (0.523).

Feature schema (matches scripts/probe_R10_M5_inplay_winprob.py exactly):

    score_margin       home_cum_pts - away_cum_pts at snapshot
    total_pts          home_cum_pts + away_cum_pts at snapshot
    pace_so_far        total_pts / minutes_played
    q1_delta           home_q1 - away_q1
    q2_delta           home_q2 - away_q2   (endQ2 + endQ3 only)
    q3_delta           home_q3 - away_q3   (endQ3 only)
    last_q_margin     home_qN - away_qN where N is most-recent observed quarter
    pregame_win_prob   pre-game home win probability (0.55 fallback if absent)
    home_team_id       categorical
    season             categorical (e.g. "2024-25")

Inference contract: ``predict_home_win_prob(features: dict, snapshot: str)``
returns a single float in [0, 1]. Missing-artifact policy: return ``None`` so
the caller can fall back to the pregame WP (preserves back-compat with the
pre-R10_M5 live_engine path which carried no in-play WP at all).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")

SNAPSHOTS = ("endQ1", "endQ2", "endQ3")

# Mirror scripts/train_inplay_winprob_endq3.SNAP_FEATURES exactly. Kept in
# sync so any drift surfaces as a load-time failure rather than silent
# mis-prediction.
_SNAP_FEATURES: Dict[str, list] = {
    "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
}
_CAT_COLS = ("home_team_id", "season")

# Module-scope booster cache. Keyed by snapshot name. False sentinel means
# we tried to load and the artifact was missing (so callers stop retrying).
_BOOSTER_CACHE: Dict[str, Any] = {}
_META_CACHE: Dict[str, Any] = {}


def _artifact_path(snapshot: str) -> str:
    return os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}.lgb")


def _meta_path(snapshot: str) -> str:
    return os.path.join(_MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")


def load_booster(snapshot: str):
    """Cached lightgbm.Booster loader. Returns None if artifact missing."""
    if snapshot not in SNAPSHOTS:
        return None
    if snapshot in _BOOSTER_CACHE:
        b = _BOOSTER_CACHE[snapshot]
        return b if b is not False else None
    path = _artifact_path(snapshot)
    if not os.path.exists(path):
        _BOOSTER_CACHE[snapshot] = False
        return None
    try:
        import lightgbm as lgb
        booster = lgb.Booster(model_file=path)
    except Exception:
        _BOOSTER_CACHE[snapshot] = False
        return None
    _BOOSTER_CACHE[snapshot] = booster

    mp = _meta_path(snapshot)
    if os.path.exists(mp):
        try:
            with open(mp) as f:
                _META_CACHE[snapshot] = json.load(f)
        except (OSError, json.JSONDecodeError):
            _META_CACHE[snapshot] = {}
    else:
        _META_CACHE[snapshot] = {}
    return booster


def _feature_frame(features: Dict[str, Any], snapshot: str) -> pd.DataFrame:
    """Build a single-row DataFrame in the column order the booster expects."""
    cols = _SNAP_FEATURES[snapshot]
    row = {}
    for c in cols:
        v = features.get(c)
        if c in _CAT_COLS:
            row[c] = v
        else:
            # numeric coercion -- LightGBM rejects pandas Object dtype for
            # leaf features. Use NaN for None so missing-value handling
            # falls through to LightGBM's built-in path.
            try:
                row[c] = float(v) if v is not None else np.nan
            except (TypeError, ValueError):
                row[c] = np.nan
    df = pd.DataFrame([row], columns=cols)
    for c in _CAT_COLS:
        if c in df.columns:
            df[c] = df[c].astype("category")
    return df


def predict_home_win_prob(features: Dict[str, Any],
                          snapshot: str = "endQ3") -> Optional[float]:
    """Predict P(home team wins) from a snapshot feature dict.

    Parameters
    ----------
    features : dict
        Must contain the keys listed in ``_SNAP_FEATURES[snapshot]``. Missing
        keys are tolerated as NaN; the booster's built-in missing-value
        handling kicks in.
    snapshot : str
        One of {"endQ1", "endQ2", "endQ3"}.

    Returns
    -------
    float in [0, 1], or None if the artifact is missing.
    """
    booster = load_booster(snapshot)
    if booster is None:
        return None
    X = _feature_frame(features, snapshot)
    try:
        # Booster.predict returns a 1-D ndarray of class-1 probabilities for
        # binary classifiers saved via LGBMClassifier.booster_.save_model.
        raw = booster.predict(X)
    except Exception:
        return None
    if raw is None or len(raw) == 0:
        return None
    p = float(np.clip(raw[0], 0.0, 1.0))
    return p


def features_from_snapshot(snap: Dict[str, Any]) -> Dict[str, Any]:
    """Build the inplay_winprob feature dict from a canonical live-engine snap.

    Expected keys on ``snap`` (canonical live.py schema PLUS the optional
    quarter-score arrays needed for this model):

        period, clock, home_score, away_score, home_team_id, season,
        home_q1..home_q3, away_q1..away_q3, pregame_win_prob (optional).

    For mid-quarter snapshots without per-quarter splits, callers should
    skip this routine and fall back to pregame WP -- this function does
    not invent missing quarter totals.
    """
    period = snap.get("period")
    point = _period_to_snapshot(period, snap.get("clock"))
    if point is None:
        return {}

    h_q = [snap.get(f"home_q{q}") for q in (1, 2, 3)]
    a_q = [snap.get(f"away_q{q}") for q in (1, 2, 3)]

    # n_qtrs observed at this snapshot
    n_qtrs = {"endQ1": 1, "endQ2": 2, "endQ3": 3}[point]
    h_obs = h_q[:n_qtrs]
    a_obs = a_q[:n_qtrs]
    if any(x is None for x in h_obs + a_obs):
        return {}

    h_cum = sum(h_obs)
    a_cum = sum(a_obs)
    total_pts = h_cum + a_cum
    minutes_played = n_qtrs * 12.0

    feats: Dict[str, Any] = {
        "score_margin": h_cum - a_cum,
        "total_pts": total_pts,
        "pace_so_far": (total_pts / minutes_played) if minutes_played > 0 else 0.0,
        "q1_delta": h_q[0] - a_q[0],
        "last_q_margin": h_obs[-1] - a_obs[-1],
        "pregame_win_prob": float(snap.get("pregame_win_prob", 0.55) or 0.55),
        "home_team_id": snap.get("home_team_id"),
        "season": snap.get("season"),
    }
    if n_qtrs >= 2:
        feats["q2_delta"] = h_q[1] - a_q[1]
    if n_qtrs >= 3:
        feats["q3_delta"] = h_q[2] - a_q[2]
    return feats


def _period_to_snapshot(period: Any, clock: Any) -> Optional[str]:
    """Conservative period->snapshot mapping.

    R10_M5 was probed at end-of-quarter boundaries (clock >= 11.95 in the
    NEW period). We mirror that gate exactly so model behavior matches
    walk-forward validation.
    """
    try:
        p = int(period)
    except (TypeError, ValueError):
        return None
    # period N+1 with clock near 12:00 means the snapshot is taken at the
    # END of period N. period 2 boundary -> endQ1, period 3 -> endQ2,
    # period 4 -> endQ3.
    if p not in (2, 3, 4):
        return None
    rem: float
    if isinstance(clock, (int, float)):
        rem = float(clock)
    else:
        s = str(clock or "").strip()
        if not s:
            return None
        if ":" in s:
            h, _, t = s.partition(":")
            try:
                rem = float(h) + (float(t) / 60.0 if t else 0.0)
            except ValueError:
                return None
        else:
            try:
                rem = float(s)
            except ValueError:
                return None
    if rem < 11.95:
        return None
    return {2: "endQ1", 3: "endQ2", 4: "endQ3"}[p]


def reset_cache() -> None:
    """Drop cached boosters (test helper)."""
    _BOOSTER_CACHE.clear()
    _META_CACHE.clear()


__all__ = [
    "SNAPSHOTS",
    "load_booster",
    "predict_home_win_prob",
    "features_from_snapshot",
    "reset_cache",
]
