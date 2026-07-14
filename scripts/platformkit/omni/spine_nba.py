"""scripts.platformkit.omni.spine_nba -- P6 next-possession spine v0.

Empirical possession stores already carry (state -> points) rows: the sim2
corpus (domains.basketball_nba.sim2.corpus / possession_model) segments PBP
into possessions with period, clock_start, off_margin, home_margin, and
points (0..6, 6="6+"). This module fits a SUPERVISED v0 upgrade to the
existing empirical-cell engine: HistGradientBoostingClassifier over
P(points-class | state), TRAINED ON 2024-25 ONLY (discovery season; 2025-26
is reserved for spine_eval.py's held-out replay).

Outcome classes (5): 0, 1, 2, 3, 4+ (points 4/5/6 pooled -- rare, 714/780166
rows league-wide per the P6 premise check).

Model choice (ponytail): HistGradientBoostingClassifier -- CPU-only sklearn,
trains in seconds on ~260k rows / 9 features. A deep net is unjustified for
a v0 tabular problem this size; rails say prefer the calibrated tabular
baseline when training doesn't need a GPU. No GPU claim made.

Features (all leak-free / pregame+in-game honest): period, clock_start,
off_margin, home_margin, time_b, margin_b, off_t, def_t, pace_t. The last
five mirror the existing sim2 cell's 5 declared state dims; period/clock/
off_margin/home_margin give the model continuous resolution the discrete
cells lack -- the actual v0 upgrade thesis.

INVARIANTS: domains/src untouched (import-only); <=300 LOC; ASCII; local
only; no $/edge claims; seed pinned (default 42), reproducible.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_spine_nba.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from domains.basketball_nba.sim2.corpus import (
    load_corpus, build_asof_terciles, attach_terciles)
from domains.basketball_nba.sim2.possession_model import add_state_buckets

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "omni" / "spine"

TRAIN_SEASON = "2024-25"           # v0 spine: discovery season ONLY
N_CLASSES = 5                      # points class 0,1,2,3,4+ (4+ pools 4/5/6)
FEATURES = ["period", "clock_start", "off_margin", "home_margin",
            "time_b", "margin_b", "off_t", "def_t", "pace_t"]
DEFAULT_SEED = 42


def points_to_class(points) -> Any:
    """points (0..6, scalar or array-like) -> outcome class (0..4, 4 == '4+')."""
    arr = np.asarray(points)
    return np.minimum(arr, 4).astype(int)


def build_state_frame(rebuild: bool = False,
                       max_games: Optional[int] = None) -> pd.DataFrame:
    """Full 3-season possession frame with state buckets + as-of terciles
    attached (off_t/def_t/pace_t are leak-free -- computed from strictly
    prior games by corpus.build_asof_terciles). One shared prep path for
    both spine_nba (train) and spine_eval (test) so features match exactly."""
    poss = add_state_buckets(load_corpus(rebuild, max_games))
    wide, _thr = build_asof_terciles(poss)
    m = attach_terciles(poss, wide)
    # ponytail: attach_terciles's merge collides poss.season with wide's own
    # season column (both real, always equal for the same game_id) -> pandas
    # emits season_x/season_y instead of erroring. corpus.py is import-only
    # here (not owned by this lane); fix up locally rather than edit it.
    if "season_x" in m.columns:
        assert (m["season_x"] == m["season_y"]).all(), "season mismatch on merge"
        m = m.drop(columns=["season_y"]).rename(columns={"season_x": "season"})
    return m


def _xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    x = df[FEATURES].to_numpy(dtype=float)
    y = points_to_class(df["points"].to_numpy())
    return x, y


def fit_spine(df: pd.DataFrame, seed: int = DEFAULT_SEED
              ) -> HistGradientBoostingClassifier:
    """Fit the v0 spine on df (caller must have already filtered to
    TRAIN_SEASON -- this function does not filter, see fit_spine_discovery)."""
    x, y = _xy(df)
    clf = HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.08, max_depth=6,
        random_state=seed, categorical_features=None)
    clf.fit(x, y)
    return clf


def fit_spine_discovery(state_df: pd.DataFrame, seed: int = DEFAULT_SEED
                        ) -> Tuple[HistGradientBoostingClassifier, pd.DataFrame]:
    """Filter state_df to TRAIN_SEASON and fit. Returns (model, train_df) so
    callers (and the leak test) can assert the train slice's season."""
    train_df = state_df[state_df["season"] == TRAIN_SEASON].reset_index(drop=True)
    if train_df.empty:
        raise ValueError(f"no rows for TRAIN_SEASON={TRAIN_SEASON!r}")
    return fit_spine(train_df, seed=seed), train_df


def predict_proba(clf: HistGradientBoostingClassifier, df: pd.DataFrame) -> np.ndarray:
    """[n, N_CLASSES] class-probability matrix for df (any season). Remaps
    onto the full 0..N_CLASSES-1 label space via clf.classes_ -- sklearn only
    emits columns for classes actually seen in training, which a thin/synthetic
    training slice can miss (unseen classes get probability 0)."""
    x = df[FEATURES].to_numpy(dtype=float)
    raw = clf.predict_proba(x)
    out = np.zeros((len(df), N_CLASSES))
    out[:, clf.classes_.astype(int)] = raw
    return out


def save_model(clf: HistGradientBoostingClassifier, path: Optional[Path] = None) -> Path:
    import joblib
    path = path or (_OUT_DIR / "models" / "spine_nba_v0.joblib")
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, path)
    return path


def load_model(path: Optional[Path] = None) -> HistGradientBoostingClassifier:
    import joblib
    path = path or (_OUT_DIR / "models" / "spine_nba_v0.joblib")
    return joblib.load(path)


def _main() -> int:
    state_df = build_state_frame()
    clf, train_df = fit_spine_discovery(state_df, seed=DEFAULT_SEED)
    path = save_model(clf)
    print("spine_nba v0: train_season=%s n_train=%d n_features=%d model=%s" % (
        TRAIN_SEASON, len(train_df), len(FEATURES), path))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
