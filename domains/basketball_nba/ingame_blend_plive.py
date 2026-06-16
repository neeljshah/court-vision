"""N3 in-game blend -- P_live builder (realized-state win-prob head).

build_state_features turns one normalized live snapshot into the minimal feature
row; fit_plive trains a logistic on the FIT season ONLY; predict_plive scores a
single state. Minimal-feature discipline from the in-game brief: (score_diff,
sec_remaining) explain >90% of variance; foul_diff + bonus are the only adds
justified by this project's own replay validation (foul-out is the one in-game
modifier that survived). NO PBP sequence embeddings.

Every feature is observable AT state time (leak-safe). The model emits a
probability from REALIZED state -- not a re-pricing of priced pregame facts.
ASCII only. sklearn LogisticRegression (NFL evidence: a small logit beats deeper
nets in-game); numpy for the feature vector.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

EDGE_CLAIMED = False

PLIVE_FEATS = ["score_diff", "sec_remaining", "foul_diff", "bonus", "time_pressure"]

# NBA regulation length in seconds (4 x 12 min). Used only for sec_remaining.
_REG_SEC = 2880.0
_PERIOD_SEC = 720.0


def sec_remaining(period: int, clock_s: float) -> float:
    """Seconds left in regulation. period is 1-based; clock_s = seconds left in
    the current period. OT (period > 4) returns clock_s only. 0 at final buzzer."""
    period = int(period)
    clock_s = float(clock_s)
    if period >= 4:
        return max(0.0, clock_s)
    return max(0.0, _PERIOD_SEC * (4 - period) + clock_s)


def _team_trouble(players: dict, team, thresh: float = 4.0) -> int:
    return sum(1 for p in players.values()
               if p.get("team") == team and float(p.get("pf") or 0.0) >= thresh)


def build_state_features(st: dict, home, away) -> Dict[str, float]:
    """One normalized live snapshot -> the P_live feature row (home perspective).

    st keys: period, clock_s, home_score, away_score, players (pid -> {team, pf}),
    optional home_bonus / away_bonus flags. All fields observable at state time.
    """
    sr = sec_remaining(st["period"], st["clock_s"])
    score_diff = float(st["home_score"]) - float(st["away_score"])
    players = st.get("players") or {}
    home_trouble = _team_trouble(players, home)
    away_trouble = _team_trouble(players, away)
    foul_diff = float(away_trouble - home_trouble)  # +ve favors home
    bonus = float(int(bool(st.get("home_bonus"))) - int(bool(st.get("away_bonus"))))
    time_pressure = score_diff * (1.0 / max(sr, 30.0))
    return {
        "score_diff": score_diff,
        "sec_remaining": sr,
        "foul_diff": foul_diff,
        "bonus": bonus,
        "margin_abs": abs(score_diff),
        "time_pressure": time_pressure,
    }


def _matrix(rows: Sequence[Dict[str, float]]) -> np.ndarray:
    return np.array([[float(r[k]) for k in PLIVE_FEATS] for r in rows], dtype=float)


def fit_plive(rows: List[Dict[str, float]], labels: Sequence[float]):
    """Fit logistic on FIT-season rows ONLY.

    rows: feature dicts (PLIVE_FEATS); labels: home_won in {0,1}. Returns a
    fitted sklearn estimator. Degenerate single-class labels fall back to a
    constant predictor so the harness never crashes on a sparse fit slice.
    """
    from sklearn.linear_model import LogisticRegression

    X = _matrix(rows)
    y = np.asarray(labels, dtype=float)
    if len(np.unique(y)) < 2:
        return _ConstModel(float(y.mean()) if len(y) else 0.5)
    return LogisticRegression(max_iter=1000, C=1.0).fit(X, y)


def predict_plive(model, feats: Dict[str, float]) -> float:
    """Score one feature row -> P_live in [0, 1]."""
    if isinstance(model, _ConstModel):
        return model.p
    x = np.array([[float(feats[k]) for k in PLIVE_FEATS]], dtype=float)
    p = float(model.predict_proba(x)[0, 1])
    return min(1.0, max(0.0, p))


class _ConstModel:
    """Constant-probability fallback for single-class / empty fit slices."""

    def __init__(self, p: float):
        self.p = min(1.0, max(0.0, float(p)))
