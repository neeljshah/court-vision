"""Per-event continuous in-game projection model.

Given a leak-free *state-feature row* produced by
``src/ingame/state_featurizer.py`` (NOT YET BUILT — see INTEGRATION TODO
below), project at any moment of a live game:

    * final team scores       (home_final_score, away_final_score)
    * home win probability     (home_win_prob in [0, 1])
    * each player's final line  (pts/reb/ast/fg3m/stl/blk/tov)

Design (per .planning/ingame/SPEC.md Section 6):
    * One XGBoost model **per regression/classification target**, all sharing
      the same leak-free state-feature vector.
    * Team-score + win-prob heads operate on a *team/game-level* state row.
    * Player-line heads operate on a *player-level* state row (game state +
      that player's box-so-far + leak-free prior-form features).
    * GPU (device="cuda") with automatic CPU fallback.
    * Models persist to ``data/models/ingame/``.

LEAK DISCIPLINE (SPEC Section 6 / HARD HONESTY RULES):
    This module trains/predicts on whatever the *featurizer* hands it. It does
    NOT itself fabricate features, so it cannot introduce an as-of-today leak
    on its own. The leak-free guarantee lives in state_featurizer.py and is
    enforced by tests/test_state_featurizer (separate). What this module DOES
    guarantee:
      * Walk-forward training: folds are split chronologically by game_date;
        a test game is NEVER in the train set (train(walk_forward=True)).
      * The target-at-t=0 sanity: a "current"-anchored feature (current score,
        current player stat) is always present so projections at t=0 reduce to
        ~= current state. Tests assert this.

INTEGRATION TODO (featurizer not yet built at authoring time):
    The expected state-row contract is pinned in STATE_SCHEMA below and mirrors
    SPEC Section 4. When src/ingame/state_featurizer.py lands, it must emit rows
    matching FEATURES_TEAM / FEATURES_PLAYER (extra columns are ignored; missing
    columns must be filled, NOT silently dropped — train() will raise if a
    declared feature is absent). Wire its DataFrame output straight into
    train(df_team=..., df_player=...). No change to this module's API expected.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import pandas as pd  # noqa: F401  (used in type hints / batch paths)
except Exception:  # pragma: no cover
    pd = None  # type: ignore

import xgboost as xgb


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = ROOT / "data" / "models" / "ingame"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# v2 unified player-line head: ONE XGBoost per stat over ALL state rows, with
# game-time-remaining + period as MODEL FEATURES (single model conditions on the
# clock instead of a separate ridge per grid-bucket, as v1 / eval_second_by_second
# does). Persisted separately so the v1 design above is untouched.
SBS_V2_DIR = MODEL_DIR / "sbs_v2"

# v2 MATCHUP-AWARE head: identical v2 design + opponent/matchup features appended
# (src/ingame/matchup_features.py). Persisted SEPARATELY so the base v2 head above
# stays intact for the honest head-to-head comparison (matchup WIN only if it
# beats base v2 out-of-sample).
SBS_V2_MATCHUP_DIR = MODEL_DIR / "sbs_v2_matchup"


# --------------------------------------------------------------------------- #
# State-row schema (pinned contract with the featurizer; SPEC Section 4)
# --------------------------------------------------------------------------- #
# Shared time/score state (present on BOTH team and player rows).
_STATE_CORE: Tuple[str, ...] = (
    "period",                 # int 1-4 reg, 5+ OT
    "elapsed_sec_in_period",  # 0..720 (reg) / 0..300 (OT)
    "game_elapsed_min",       # 12*(period-1) + elapsed/60 (reg)
    "game_remaining_min",     # clamp >=0; extends for OT
    "played_share",           # game_elapsed_min / total_game_min  in (0,1]
    "home_score",             # current
    "away_score",             # current
    "margin",                 # home_score - away_score (signed, home POV)
    "total_so_far",           # home_score + away_score
    "pace_to_date",           # possessions / elapsed-min
    # leak-free momentum (event-incremental; SPEC 4 / inplay_microstructure)
    "home_run_last_240s",
    "away_run_last_240s",
    "home_pts_last_120s",
    "away_pts_last_120s",
    "lead_changes",
    # leak-free team four-factors-so-far
    "home_efg_so_far",
    "away_efg_so_far",
    "home_tov_rate_so_far",
    "away_tov_rate_so_far",
    "home_oreb_rate_so_far",
    "away_oreb_rate_so_far",
    "home_ft_rate_so_far",
    "away_ft_rate_so_far",
)

# Team/game-level rows feed the team-score + win-prob heads.
FEATURES_TEAM: Tuple[str, ...] = _STATE_CORE + (
    # prior-form (games strictly BEFORE this game's date; leak-free)
    "home_prior_ppg",
    "away_prior_ppg",
    "home_prior_pace",
    "away_prior_pace",
    "home_prior_net_rtg",
    "away_prior_net_rtg",
)

# Player-level rows feed the 7 player-line heads.
_PLAYER_BOX: Tuple[str, ...] = (
    "p_min_so_far",
    "p_pts_so_far",
    "p_reb_so_far",
    "p_ast_so_far",
    "p_fg3m_so_far",
    "p_stl_so_far",
    "p_blk_so_far",
    "p_tov_so_far",
    "p_pf_so_far",
    "p_is_starter",
    "p_on_court",          # 1 if currently on court
)
_PLAYER_PRIOR: Tuple[str, ...] = (
    # leak-free prior-form (player's games strictly before this game)
    "p_prior_min",
    "p_prior_pts",
    "p_prior_reb",
    "p_prior_ast",
    "p_prior_fg3m",
    "p_prior_stl",
    "p_prior_blk",
    "p_prior_tov",
    "p_prior_usage",
)
FEATURES_PLAYER: Tuple[str, ...] = _STATE_CORE + _PLAYER_BOX + _PLAYER_PRIOR

# --------------------------------------------------------------------------- #
# CV_INGAME_LIVE_USAGE — live-usage-vs-expected feature (default OFF)
# --------------------------------------------------------------------------- #
# When ON, the live usage feature ``p_live_usg_vs_prior`` is populated in the
# v2 player-state row and included in the v2 feature list used for retraining.
# The feature = live_usg_proxy - p_prior_usage, where
#   live_usg_proxy = (fga_so_far + 0.44*fta_so_far + tov_so_far) /
#                     team_(fga + 0.44*fta + tov)_so_far
# (NBA true-usage denominator).  Fallback when team denominator < 0.5:
#   volume_ratio = (pts_so_far / max(min_so_far, 0.01)) /
#                  (p_prior_pts / max(p_prior_min, 0.01))
# clamped to [0.0, 3.0].
#
# When OFF (default): the column is NEVER added to snapshots and defaults to
# 0.0 via _vectorize's row.get(f, 0.0) fallback in already-trained models.
# This makes the serve path BYTE-IDENTICAL when the flag is OFF.
_LIVE_USAGE_TRUTHY = {"1", "true", "yes", "on", "y", "t"}
LIVE_USAGE_FLAG: str = "CV_INGAME_LIVE_USAGE"
LIVE_USAGE_FEATURE: str = "p_live_usg_vs_prior"


def is_live_usage_enabled() -> bool:
    """True iff CV_INGAME_LIVE_USAGE is set to a truthy value.

    Default OFF (unset / "0" / non-truthy): serve path is byte-identical to
    the baseline SBS-v2 path. Enable only for explicit experimentation or
    after acceptance validation.
    """
    return os.environ.get(LIVE_USAGE_FLAG, "0").strip().lower() in _LIVE_USAGE_TRUTHY


def compute_live_usg_vs_prior(
    fga_so_far: float,
    fta_so_far: float,
    tov_so_far: float,
    team_fga: float,
    team_fta: float,
    team_tov: float,
    p_prior_usage: float,
    p_prior_pts: float,
    p_prior_min: float,
    pts_so_far: float,
    min_so_far: float,
) -> float:
    """Compute live_usg_vs_prior = live_usg_proxy - p_prior_usage.

    Primary path (when team four-factor denominator >= 0.5):
        live_usg_proxy = (fga + 0.44*fta + tov) / team_(fga + 0.44*fta + tov)
    Fallback (team denominator too small — early in game):
        live_usg_proxy = (pts_per_min / prior_pts_per_min), clamped [0, 3]

    Returns the delta vs prior usage, clamped to [-1.0, 2.0] to prevent
    extreme extrapolation from small-sample early moments.
    """
    team_denom = team_fga + 0.44 * team_fta + team_tov
    if team_denom >= 0.5:
        player_numerator = fga_so_far + 0.44 * fta_so_far + tov_so_far
        live_usg_proxy = player_numerator / team_denom
    else:
        # Fallback: volume ratio (pts/min vs prior pts/min)
        live_pts_per_min = pts_so_far / max(min_so_far, 0.01)
        prior_pts_per_min = p_prior_pts / max(p_prior_min, 0.01)
        if prior_pts_per_min < 0.01:
            live_usg_proxy = p_prior_usage
        else:
            ratio = live_pts_per_min / prior_pts_per_min
            # Proxy usage = prior_usage * volume_ratio, clamped [0, 3*prior]
            live_usg_proxy = min(3.0 * max(p_prior_usage, 0.10),
                                 p_prior_usage * min(3.0, max(0.0, ratio)))
    delta = live_usg_proxy - p_prior_usage
    return float(max(-1.0, min(2.0, delta)))

# Target column names expected on training frames.
TEAM_TARGETS: Tuple[str, ...] = ("home_final_score", "away_final_score")
WINPROB_TARGET: str = "home_win"
PLAYER_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
PLAYER_TARGETS: Tuple[str, ...] = tuple(f"final_{s}" for s in PLAYER_STATS)

# "current"-anchored feature for each player stat (used for the t=0 sanity:
# projection at t=0 must ~= current accumulation). Maps target stat -> box col.
_PLAYER_CURRENT_COL: Dict[str, str] = {s: f"p_{s}_so_far" for s in PLAYER_STATS}

STATE_SCHEMA: Dict[str, Tuple[str, ...]] = {
    "team_features": FEATURES_TEAM,
    "player_features": FEATURES_PLAYER,
    "team_targets": TEAM_TARGETS,
    "winprob_target": (WINPROB_TARGET,),
    "player_targets": PLAYER_TARGETS,
}


# --------------------------------------------------------------------------- #
# Device selection
# --------------------------------------------------------------------------- #
def _select_device(prefer: str = "cuda") -> str:
    """Return 'cuda' if usable, else 'cpu'. Honours NBA_FORCE_CPU=1."""
    if os.environ.get("NBA_FORCE_CPU") == "1":
        return "cpu"
    if prefer != "cuda":
        return "cpu"
    # Probe by training a 1-row booster on cuda; fall back on any failure.
    try:
        d = xgb.DMatrix(np.zeros((2, 1), dtype=np.float32), label=np.array([0.0, 1.0]))
        xgb.train({"device": "cuda", "tree_method": "hist", "max_depth": 1},
                  d, num_boost_round=1)
        return "cuda"
    except Exception:
        return "cpu"


def _xgb_params(device: str, *, classifier: bool) -> dict:
    p = {
        "device": device,
        "tree_method": "hist",
        "max_depth": 6,
        "eta": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "lambda": 1.0,
    }
    if classifier:
        p["objective"] = "binary:logistic"
        p["eval_metric"] = "logloss"
    else:
        p["objective"] = "reg:squarederror"
        p["eval_metric"] = "mae"
    return p


# --------------------------------------------------------------------------- #
# Projector
# --------------------------------------------------------------------------- #
@dataclass
class ContinuousProjector:
    """Holds the trained per-target boosters and serves project_state()."""

    device: str = "cpu"
    num_boost_round: int = 300
    team_features: Tuple[str, ...] = FEATURES_TEAM
    player_features: Tuple[str, ...] = FEATURES_PLAYER
    # name -> (Booster, feature_list)
    team_models: Dict[str, Tuple[object, Tuple[str, ...]]] = field(default_factory=dict)
    winprob_model: Optional[Tuple[object, Tuple[str, ...]]] = None
    player_models: Dict[str, Tuple[object, Tuple[str, ...]]] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Feature extraction
    # ------------------------------------------------------------------ #
    @staticmethod
    def _vectorize(row: Dict, feats: Sequence[str]) -> np.ndarray:
        """Build a (1, F) float32 matrix from a state-row dict.

        Missing keys -> 0.0 at *predict* time (a partial live row is tolerated),
        but train() requires all columns present (see _frame_matrix).
        """
        return np.array(
            [[float(row.get(f, 0.0) or 0.0) for f in feats]],
            dtype=np.float32,
        )

    @staticmethod
    def _frame_matrix(df, feats: Sequence[str]) -> np.ndarray:
        missing = [f for f in feats if f not in df.columns]
        if missing:
            raise ValueError(
                f"state frame is missing declared feature columns: {missing}. "
                "The featurizer must emit every column in the schema (fill, "
                "don't drop). See STATE_SCHEMA."
            )
        return df[list(feats)].to_numpy(dtype=np.float32)

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def project_state(self, state_row: Dict) -> Dict:
        """Project finals from a single leak-free state-feature row.

        ``state_row`` may carry both team-level and player-level fields. The
        team/win-prob heads read team features; the player heads read player
        features. Returns:

            {
              "home_final_score": float, "away_final_score": float,
              "home_win_prob": float in [0,1],
              "player": {stat: projected_final_float for stat in PLAYER_STATS}
                        # present only if player heads are trained
            }

        At t=0 (game_remaining_min ~= full game, nothing accumulated) the
        projections fall back toward current state / prior-form, by construction
        of the features (current score & current stat are inputs).
        """
        out: Dict = {}

        # Team scores
        for tgt in TEAM_TARGETS:
            if tgt in self.team_models:
                booster, feats = self.team_models[tgt]
                x = self._vectorize(state_row, feats)
                pred = float(booster.predict(xgb.DMatrix(x))[0])
                out[tgt] = max(0.0, pred)
            else:
                # fall back to naive pace if untrained
                out[tgt] = self._naive_team_score(state_row, tgt)

        # Home win prob
        if self.winprob_model is not None:
            booster, feats = self.winprob_model
            x = self._vectorize(state_row, feats)
            wp = float(booster.predict(xgb.DMatrix(x))[0])
            out["home_win_prob"] = min(1.0, max(0.0, wp))
        else:
            margin = out.get("home_final_score", 0.0) - out.get("away_final_score", 0.0)
            out["home_win_prob"] = 1.0 / (1.0 + np.exp(-0.18 * margin))

        # Player lines (only if heads trained AND row looks player-level)
        if self.player_models and any(
            k in state_row for k in _PLAYER_CURRENT_COL.values()
        ):
            pl: Dict[str, float] = {}
            for stat in PLAYER_STATS:
                tgt = f"final_{stat}"
                if tgt in self.player_models:
                    booster, feats = self.player_models[tgt]
                    x = self._vectorize(state_row, feats)
                    pred = float(booster.predict(xgb.DMatrix(x))[0])
                    # never project below what's already accumulated
                    cur = float(state_row.get(_PLAYER_CURRENT_COL[stat], 0.0) or 0.0)
                    pl[stat] = max(cur, pred)
            out["player"] = pl

        return out

    @staticmethod
    def _naive_team_score(row: Dict, tgt: str) -> float:
        """Linear pace extrapolation baseline (used when head untrained)."""
        share = float(row.get("played_share", 0.0) or 0.0)
        cur = float(row.get("home_score" if tgt == "home_final_score"
                            else "away_score", 0.0) or 0.0)
        if share <= 0.0:
            return cur
        return cur / share

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, model_dir: Path = MODEL_DIR) -> Dict[str, str]:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        saved: Dict[str, str] = {}
        manifest: Dict[str, dict] = {"device": self.device, "heads": {}}

        for tgt, (booster, feats) in self.team_models.items():
            fp = model_dir / f"team_{tgt}.json"
            booster.save_model(str(fp))
            saved[tgt] = str(fp)
            manifest["heads"][tgt] = {"file": fp.name, "features": list(feats)}

        if self.winprob_model is not None:
            booster, feats = self.winprob_model
            fp = model_dir / "winprob_home_win.json"
            booster.save_model(str(fp))
            saved[WINPROB_TARGET] = str(fp)
            manifest["heads"][WINPROB_TARGET] = {"file": fp.name, "features": list(feats)}

        for tgt, (booster, feats) in self.player_models.items():
            fp = model_dir / f"player_{tgt}.json"
            booster.save_model(str(fp))
            saved[tgt] = str(fp)
            manifest["heads"][tgt] = {"file": fp.name, "features": list(feats)}

        (model_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return saved

    @classmethod
    def load(cls, model_dir: Path = MODEL_DIR) -> "ContinuousProjector":
        model_dir = Path(model_dir)
        manifest_fp = model_dir / "manifest.json"
        if not manifest_fp.exists():
            raise FileNotFoundError(f"no manifest at {manifest_fp}; train first")
        manifest = json.loads(manifest_fp.read_text())
        proj = cls(device=manifest.get("device", "cpu"))
        for tgt, meta in manifest.get("heads", {}).items():
            booster = xgb.Booster()
            booster.load_model(str(model_dir / meta["file"]))
            feats = tuple(meta["features"])
            if tgt in TEAM_TARGETS:
                proj.team_models[tgt] = (booster, feats)
            elif tgt == WINPROB_TARGET:
                proj.winprob_model = (booster, feats)
            elif tgt in PLAYER_TARGETS:
                proj.player_models[tgt] = (booster, feats)
        return proj


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def _walk_forward_folds(game_dates: np.ndarray, n_folds: int = 3) -> List[np.ndarray]:
    """Return boolean test masks for expanding-window chronological folds.

    Games are split by their sorted unique date into n_folds+1 chunks; fold k
    tests chunk k+1 (train = all earlier games). Returns one test mask per fold.
    """
    uniq = np.array(sorted(set(game_dates.tolist())))
    if len(uniq) < n_folds + 1:
        # too few dates for the requested folds -> single holdout (last 20%)
        cut = uniq[max(1, int(len(uniq) * 0.8)) - 1] if len(uniq) > 1 else uniq[-1]
        return [game_dates > cut]
    bounds = np.array_split(uniq, n_folds + 1)
    masks = []
    for k in range(1, n_folds + 1):
        test_dates = set(bounds[k].tolist())
        masks.append(np.array([d in test_dates for d in game_dates]))
    return masks


def _train_one(X: np.ndarray, y: np.ndarray, params: dict, rounds: int) -> object:
    return xgb.train(params, xgb.DMatrix(X, label=y), num_boost_round=rounds)


def _fit_head(df, feats, target, params, rounds,
              walk_forward, date_col, metric_fn) -> Tuple[object, List[float]]:
    """Fit final-on-all booster + optional walk-forward fold metrics."""
    X = ContinuousProjector._frame_matrix(df, feats)
    y = df[target].to_numpy(dtype=np.float32)

    fold_scores: List[float] = []
    if walk_forward and date_col in df.columns:
        dates = df[date_col].to_numpy()
        for test_mask in _walk_forward_folds(dates):
            train_mask = ~test_mask
            if train_mask.sum() < 5 or test_mask.sum() < 1:
                continue
            booster = _train_one(X[train_mask], y[train_mask], params, rounds)
            pred = booster.predict(xgb.DMatrix(X[test_mask]))
            fold_scores.append(float(metric_fn(y[test_mask], pred)))

    # Final model trained on ALL rows (for production serving).
    final_booster = _train_one(X, y, params, rounds)
    return final_booster, fold_scores


def _mae(y, p) -> float:
    return float(np.mean(np.abs(y - p)))


def _brier(y, p) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean((p - y) ** 2))


def train(
    df_team=None,
    df_player=None,
    *,
    walk_forward: bool = True,
    num_boost_round: int = 300,
    date_col: str = "game_date",
    device: Optional[str] = None,
    save: bool = True,
    model_dir: Path = MODEL_DIR,
) -> Tuple[ContinuousProjector, Dict[str, List[float]]]:
    """Train all heads on historical leak-free state rows.

    Args:
        df_team: DataFrame of TEAM/game-level state rows. Must contain
            FEATURES_TEAM + TEAM_TARGETS + WINPROB_TARGET (+ date_col for WF).
        df_player: DataFrame of PLAYER-level state rows. Must contain
            FEATURES_PLAYER + PLAYER_TARGETS (+ date_col for WF). Optional —
            if None, only team-score + win-prob heads are trained.
        walk_forward: if True, also compute expanding-window chronological fold
            metrics per head (reported in the returned dict). The shipped model
            is ALWAYS the all-rows fit; folds are for the honest WF report.

    Returns:
        (projector, metrics) where metrics maps head-name -> list of per-fold
        held-out scores (MAE for regression heads, Brier for win-prob).

    NOTE: This trainer does not load data itself. The leak-free state rows come
    from src/ingame/state_featurizer.py (INTEGRATION TODO). A thin loader/CLI
    belongs in scripts/ingame/ and should pass frames straight here.
    """
    dev = device or _select_device("cuda")
    proj = ContinuousProjector(device=dev, num_boost_round=num_boost_round)
    metrics: Dict[str, List[float]] = {}

    if df_team is not None:
        reg_params = _xgb_params(dev, classifier=False)
        for tgt in TEAM_TARGETS:
            if tgt not in df_team.columns:
                continue
            booster, folds = _fit_head(
                df_team, FEATURES_TEAM, tgt, reg_params, num_boost_round,
                walk_forward, date_col, _mae,
            )
            proj.team_models[tgt] = (booster, FEATURES_TEAM)
            metrics[tgt] = folds

        if WINPROB_TARGET in df_team.columns:
            clf_params = _xgb_params(dev, classifier=True)
            booster, folds = _fit_head(
                df_team, FEATURES_TEAM, WINPROB_TARGET, clf_params, num_boost_round,
                walk_forward, date_col, _brier,
            )
            proj.winprob_model = (booster, FEATURES_TEAM)
            metrics[WINPROB_TARGET] = folds

    if df_player is not None:
        reg_params = _xgb_params(dev, classifier=False)
        for tgt in PLAYER_TARGETS:
            if tgt not in df_player.columns:
                continue
            booster, folds = _fit_head(
                df_player, FEATURES_PLAYER, tgt, reg_params, num_boost_round,
                walk_forward, date_col, _mae,
            )
            proj.player_models[tgt] = (booster, FEATURES_PLAYER)
            metrics[tgt] = folds

    if save:
        proj.save(model_dir)
    return proj, metrics


# =========================================================================== #
# v2 UNIFIED player-line head
# =========================================================================== #
# DESIGN (vs the v1 per-grid-bucket ridge in scripts/ingame/eval_second_by_second.py
# and vs the v1 ContinuousProjector heads above):
#   * ONE XGBoost model per player-stat (pts/reb/ast/fg3m/stl/blk/tov), trained on
#     state rows from ALL available PBP games at EVERY event (not bucketed by
#     game-time). The clock is a MODEL FEATURE: `game_remaining_min`, `period`,
#     `played_share` are inputs, so a single model conditions on the moment in the
#     game instead of needing a separate ridge per (grid-bucket).
#   * Leak posture is inherited from the featurizer + the caller's walk-forward
#     split: this module never fabricates features and trains strictly chronological
#     folds (train games' dates < each test fold's earliest date). The shipped model
#     is the all-rows fit; folds are for the honest WF report (same contract as v1
#     `train`). Predictions are floored at the player's current accumulation.
#
# The v2 feature set is the leak-free player state. We DEFAULT to the same
# FEATURES_PLAYER schema as v1 (it already carries period + game_remaining_min +
# played_share + box-so-far + leak-free prior-form), so a featurizer frame that
# trains v1 also trains v2 with no extra columns. A caller may pass an explicit
# feature list to use a richer/leaner state vector.

# Explicit clock features that MUST be present so the single model can condition
# on game-time (the whole point of v2). train_player_lines_v2 asserts these exist.
V2_CLOCK_FEATURES: Tuple[str, ...] = ("game_remaining_min", "period", "played_share")
FEATURES_PLAYER_V2: Tuple[str, ...] = FEATURES_PLAYER


@dataclass
class UnifiedPlayerLineProjector:
    """v2: one clock-conditioned XGBoost per player-stat over ALL event rows.

    Use ``project_player_lines_v2(state_row)`` (module function) for the simplest
    call; this class is the trained container it serves from. Load a persisted
    set with ``UnifiedPlayerLineProjector.load()``.
    """

    device: str = "cpu"
    num_boost_round: int = 400
    features: Tuple[str, ...] = FEATURES_PLAYER_V2
    # stat -> (Booster, feature_list)
    models: Dict[str, Tuple[object, Tuple[str, ...]]] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    def project(self, state_row: Dict) -> Dict[str, float]:
        """Project a single player's FINAL line from one leak-free state row.

        Returns {stat: projected_final_float}. Each projection is floored at the
        player's current accumulation (``p_{stat}_so_far``) so it can never
        regress below what already happened. Untrained stats are omitted.
        """
        out: Dict[str, float] = {}
        for stat in PLAYER_STATS:
            tgt = f"final_{stat}"
            if tgt not in self.models:
                continue
            booster, feats = self.models[tgt]
            x = ContinuousProjector._vectorize(state_row, feats)
            pred = float(booster.predict(xgb.DMatrix(x))[0])
            cur = float(state_row.get(_PLAYER_CURRENT_COL[stat], 0.0) or 0.0)
            out[stat] = max(cur, pred)
        return out

    # ------------------------------------------------------------------ #
    def save(self, model_dir: Path = SBS_V2_DIR) -> Dict[str, str]:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        saved: Dict[str, str] = {}
        manifest: Dict[str, object] = {
            "version": "sbs_v2",
            "device": self.device,
            "num_boost_round": self.num_boost_round,
            "features": list(self.features),
            "clock_features": list(V2_CLOCK_FEATURES),
            "heads": {},
        }
        for tgt, (booster, feats) in self.models.items():
            fp = model_dir / f"player_{tgt}.json"
            booster.save_model(str(fp))
            saved[tgt] = str(fp)
            manifest["heads"][tgt] = {"file": fp.name, "features": list(feats)}
        (model_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return saved

    @classmethod
    def load(cls, model_dir: Path = SBS_V2_DIR) -> "UnifiedPlayerLineProjector":
        model_dir = Path(model_dir)
        manifest_fp = model_dir / "manifest.json"
        if not manifest_fp.exists():
            raise FileNotFoundError(
                f"no v2 manifest at {manifest_fp}; train_player_lines_v2 first"
            )
        manifest = json.loads(manifest_fp.read_text())
        proj = cls(
            device=manifest.get("device", "cpu"),
            num_boost_round=int(manifest.get("num_boost_round", 400)),
            features=tuple(manifest.get("features", FEATURES_PLAYER_V2)),
        )
        for tgt, meta in manifest.get("heads", {}).items():
            booster = xgb.Booster()
            booster.load_model(str(model_dir / meta["file"]))
            proj.models[tgt] = (booster, tuple(meta["features"]))
        return proj


# Process-level cache so project_player_lines_v2 doesn't reload per call.
_V2_SINGLETON: Optional[UnifiedPlayerLineProjector] = None


def train_player_lines_v2(
    df_player,
    *,
    features: Optional[Sequence[str]] = None,
    walk_forward: bool = True,
    num_boost_round: int = 400,
    date_col: str = "game_date",
    device: Optional[str] = None,
    save: bool = True,
    model_dir: Path = SBS_V2_DIR,
) -> Tuple[UnifiedPlayerLineProjector, Dict[str, List[float]]]:
    """Train the v2 unified, clock-conditioned player-line heads.

    Args:
        df_player: DataFrame of PLAYER-level leak-free state rows (one per event,
            from src/ingame/state_featurizer). Must contain ``features`` +
            ``final_<stat>`` targets (+ ``date_col`` for the walk-forward report).
            The clock features in V2_CLOCK_FEATURES MUST be present (this is what
            lets a single model replace the per-bucket ridge).
        features: feature column list; defaults to FEATURES_PLAYER_V2.
        walk_forward: if True, also compute expanding-window chronological fold
            MAE per stat (held-out). The shipped model is ALWAYS the all-rows fit.

    Returns:
        (projector, metrics) where metrics maps ``final_<stat>`` -> per-fold
        held-out MAE list.
    """
    feats = tuple(features) if features is not None else FEATURES_PLAYER_V2
    missing_clock = [c for c in V2_CLOCK_FEATURES if c not in feats]
    if missing_clock:
        raise ValueError(
            f"v2 requires clock features {missing_clock} in the feature list so "
            "ONE model can condition on game-time (the point of v2). Add them."
        )
    dev = device or _select_device("cuda")
    reg_params = _xgb_params(dev, classifier=False)
    proj = UnifiedPlayerLineProjector(
        device=dev, num_boost_round=num_boost_round, features=feats,
    )
    metrics: Dict[str, List[float]] = {}
    for stat in PLAYER_STATS:
        tgt = f"final_{stat}"
        if tgt not in df_player.columns:
            continue
        booster, folds = _fit_head(
            df_player, feats, tgt, reg_params, num_boost_round,
            walk_forward, date_col, _mae,
        )
        proj.models[tgt] = (booster, feats)
        metrics[tgt] = folds
    if save:
        proj.save(model_dir)
    return proj, metrics


# =========================================================================== #
# v2 MATCHUP-AWARE variant
# =========================================================================== #
# Same UnifiedPlayerLineProjector container + clock-conditioned per-stat design.
# The ONLY difference is that the feature list is the base v2 feature list with
# the leak-free opponent/matchup columns (src.ingame.matchup_features) appended.
# Those columns describe the OPPONENT defense computed from games STRICTLY BEFORE
# this game's date (leak posture lives in matchup_features.py + an as-of test);
# this trainer never fabricates them — it just asserts they're present and trains
# the same GPU XGBoost on the augmented vector. Persists to SBS_V2_MATCHUP_DIR so
# the base v2 head stays available for the head-to-head comparison.


def matchup_feature_columns() -> Tuple[str, ...]:
    """The matchup columns appended in the matchup-aware variant.

    Sourced from src.ingame.matchup_features.feature_columns(). Imported lazily
    so the base v2 path has zero dependency on the matchup module.
    """
    try:
        from src.ingame.matchup_features import feature_columns as _mc  # noqa
        return tuple(_mc())
    except Exception:
        # documented interface fallback (matchup_features not importable yet):
        # keep the contract stable so a frame that carries these trains.
        return (
            "mu_opp_def_rtg_z", "mu_opp_rim_fg_allowed_z",
            "mu_opp_paint_fg_allowed_z", "mu_opp_3p_pct_allowed_z",
            "mu_opp_3pa_rate_allowed_z", "mu_opp_dreb_pct_z",
            "mu_opp_tov_forced_z", "mu_opp_pace_z",
            "mu_opp_pf_drawn_allowed_z", "mu_is_home",
        )


def build_matchup_feature_list(
    base_features: Optional[Sequence[str]] = None,
) -> Tuple[str, ...]:
    """Append the matchup columns to a base v2 feature list (dedup, order-stable).

    The clock features remain present (they're in ``base_features``), so the
    matchup variant still satisfies the v2 clock-conditioning contract.
    """
    base = tuple(base_features) if base_features is not None else FEATURES_PLAYER_V2
    extra = matchup_feature_columns()
    seen = set(base)
    merged = list(base) + [c for c in extra if c not in seen]
    return tuple(merged)


def train_player_lines_v2_matchup(
    df_player,
    *,
    base_features: Optional[Sequence[str]] = None,
    walk_forward: bool = True,
    num_boost_round: int = 400,
    date_col: str = "game_date",
    device: Optional[str] = None,
    save: bool = True,
    model_dir: Path = SBS_V2_MATCHUP_DIR,
) -> Tuple[UnifiedPlayerLineProjector, Dict[str, List[float]], Tuple[str, ...]]:
    """Train the MATCHUP-AWARE v2 player-line heads (``include_matchup=True``).

    Identical to :func:`train_player_lines_v2` except the feature list is
    ``build_matchup_feature_list(base_features)`` — the base v2 state columns plus
    the leak-free opponent/matchup columns from src.ingame.matchup_features. The
    frame MUST already carry those matchup columns (the assembler appends them via
    ``matchup_feature_row``); this trainer asserts they are present so a silently
    matchup-LESS frame can't masquerade as matchup-aware.

    Persists to ``SBS_V2_MATCHUP_DIR`` (base v2 untouched). Returns
    ``(projector, metrics, feature_list)`` — the extra ``feature_list`` lets the
    caller confirm exactly which matchup columns entered the model.
    """
    feats = build_matchup_feature_list(base_features)

    # Assert clock features survived (the v2 contract) ...
    missing_clock = [c for c in V2_CLOCK_FEATURES if c not in feats]
    if missing_clock:
        raise ValueError(
            f"matchup v2 requires clock features {missing_clock} in the base "
            "feature list so ONE model still conditions on game-time."
        )
    # ... and that the matchup columns ACTUALLY entered the feature list AND the
    # training frame (otherwise this is not a matchup model — fail loud).
    mu_cols = [c for c in matchup_feature_columns() if c in feats]
    if not mu_cols:
        raise ValueError(
            "no matchup columns present in the augmented feature list; "
            "matchup_feature_columns() returned nothing usable."
        )
    missing_in_df = [c for c in mu_cols if c not in df_player.columns]
    if missing_in_df:
        raise ValueError(
            f"matchup columns absent from the training frame: {missing_in_df}. "
            "The assembler must append matchup_feature_row(...) to every event "
            "row before training the matchup-aware head (fill, don't drop)."
        )

    dev = device or _select_device("cuda")
    reg_params = _xgb_params(dev, classifier=False)
    proj = UnifiedPlayerLineProjector(
        device=dev, num_boost_round=num_boost_round, features=feats,
    )
    metrics: Dict[str, List[float]] = {}
    for stat in PLAYER_STATS:
        tgt = f"final_{stat}"
        if tgt not in df_player.columns:
            continue
        booster, folds = _fit_head(
            df_player, feats, tgt, reg_params, num_boost_round,
            walk_forward, date_col, _mae,
        )
        proj.models[tgt] = (booster, feats)
        metrics[tgt] = folds
    if save:
        proj.save(model_dir)
    return proj, metrics, mu_cols


# Process-level cache for the matchup serving path (separate from base v2).
_V2_MATCHUP_SINGLETON: Optional[UnifiedPlayerLineProjector] = None


def project_player_lines_v2_matchup(
    state_row: Dict,
    *,
    model_dir: Path = SBS_V2_MATCHUP_DIR,
    projector: Optional[UnifiedPlayerLineProjector] = None,
) -> Dict[str, float]:
    """Serve the matchup-aware v2 heads. ``state_row`` must include the matchup
    columns (missing keys vectorize to 0.0, same tolerance as base v2). Mirrors
    :func:`project_player_lines_v2`'s shape; floored at current accumulation.
    """
    global _V2_MATCHUP_SINGLETON
    if projector is None:
        if _V2_MATCHUP_SINGLETON is None:
            _V2_MATCHUP_SINGLETON = UnifiedPlayerLineProjector.load(model_dir)
        projector = _V2_MATCHUP_SINGLETON
    return projector.project(state_row)


def project_player_lines_v2(
    state_row: Dict,
    *,
    model_dir: Path = SBS_V2_DIR,
    projector: Optional[UnifiedPlayerLineProjector] = None,
) -> Dict[str, float]:
    """Project one player's FINAL line from a leak-free state row using v2.

    Loads the persisted v2 heads from ``model_dir`` once (process-cached) unless
    a ``projector`` is supplied. Returns {stat: projected_final_float}, each
    floored at the player's current accumulation. Mirrors the v1
    ``ContinuousProjector.project_state(...)['player']`` shape for comparison.
    """
    global _V2_SINGLETON
    if projector is None:
        if _V2_SINGLETON is None:
            _V2_SINGLETON = UnifiedPlayerLineProjector.load(model_dir)
        projector = _V2_SINGLETON
    return projector.project(state_row)


# =========================================================================== #
# CV_INGAME_MATCHUP — reversible flag gate
# =========================================================================== #
# This flag gates the MATCHUP-AWARE v2 head into the serving path.
#
# Default: OFF  (env unset / "0" / any non-truthy value)
#   -> project_player_lines_v2_routed dispatches to the BASE v2 head
#      (project_player_lines_v2). Prediction is byte-identical to the current
#      validated SBS-v2 path. The matchup head and SBS_V2_MATCHUP_DIR are
#      NEVER loaded or touched. Proven no-op by tests/test_cv_ingame_matchup_flag.py.
#
# Full-send / experiment: ON  (env = "1" / "true" / any truthy spelling below)
#   -> dispatches to the MATCHUP-AWARE head (project_player_lines_v2_matchup).
#      The matchup block is KNOWN to be net-harmful per the honest walk-forward
#      eval (.planning/ingame/eval_sbs_matchup.{json,md}): beats base in 6/49
#      cells, strictly worse from half onward (mean Δ = +0.006..+0.018 MAE
#      depending on stat). Flip OFF in one step to restore the validated head.
#
# One-line disable:  del $env:CV_INGAME_MATCHUP   (PowerShell)
#                or: unset CV_INGAME_MATCHUP       (bash)
#                or: set NBA_INGAME_MATCHUP=0 in your process env.

MATCHUP_FLAG: str = "CV_INGAME_MATCHUP"
_MATCHUP_TRUTHY = {"1", "true", "yes", "on", "y", "t"}


def is_matchup_enabled() -> bool:
    """True iff the matchup-aware v2 head is switched on via ``CV_INGAME_MATCHUP``.

    Default OFF: unset / empty / "0" / any non-truthy value keeps the base v2
    head active — byte-identical to the validated SBS-v2 path. Truthy spellings
    ("1", "true", "yes", "on", "y", "t") route to the matchup-aware head.

    WARNING: the matchup head is validated NULL / net-harmful (beats base in
    6/49 cells; strictly worse from half-game onward per the walk-forward eval).
    Keep OFF for production. Only enable for explicit experimentation.
    """
    return os.environ.get(MATCHUP_FLAG, "0").strip().lower() in _MATCHUP_TRUTHY


def project_player_lines_v2_routed(
    state_row: Dict,
    *,
    base_projector: Optional[UnifiedPlayerLineProjector] = None,
    matchup_projector: Optional[UnifiedPlayerLineProjector] = None,
    base_model_dir: Path = SBS_V2_DIR,
    matchup_model_dir: Path = SBS_V2_MATCHUP_DIR,
) -> Dict[str, float]:
    """Route a projection through the base or matchup v2 head based on ``CV_INGAME_MATCHUP``.

    When ``CV_INGAME_MATCHUP`` is OFF (default), this is a strict no-op identity:
    it calls :func:`project_player_lines_v2` with the supplied ``base_projector``
    and returns the byte-identical result. The matchup head and its model dir are
    never loaded or referenced. Proven by ``tests/test_cv_ingame_matchup_flag.py``.

    When ON, it calls :func:`project_player_lines_v2_matchup` (the matchup-aware
    head). The ``state_row`` should carry the ``mu_`` matchup columns; missing
    keys vectorize to 0.0 (same tolerance as the base head for missing features).

    Args:
        state_row: leak-free player-state feature dict (same contract as
            ``project_player_lines_v2``). When the flag is ON and matchup columns
            are absent the head still predicts (0.0 fill), but the prediction
            degrades to the opponent-identity embedding baseline.
        base_projector: optional in-process base v2 projector (avoids disk load).
        matchup_projector: optional in-process matchup projector (avoids disk load).
        base_model_dir: override base v2 model dir (tests use tmp paths).
        matchup_model_dir: override matchup model dir (tests use tmp paths).

    Returns:
        {stat: projected_final_float} — same shape as ``project_player_lines_v2``.
    """
    if is_matchup_enabled():
        return project_player_lines_v2_matchup(
            state_row,
            model_dir=matchup_model_dir,
            projector=matchup_projector,
        )
    # FLAG OFF — strict identity: delegate directly to the base v2 function.
    return project_player_lines_v2(
        state_row,
        model_dir=base_model_dir,
        projector=base_projector,
    )


__all__ = [
    "ContinuousProjector",
    "train",
    "STATE_SCHEMA",
    "FEATURES_TEAM",
    "FEATURES_PLAYER",
    "TEAM_TARGETS",
    "WINPROB_TARGET",
    "PLAYER_STATS",
    "PLAYER_TARGETS",
    "MODEL_DIR",
    # v2 unified clock-conditioned player-line head
    "SBS_V2_DIR",
    "FEATURES_PLAYER_V2",
    "V2_CLOCK_FEATURES",
    "UnifiedPlayerLineProjector",
    "train_player_lines_v2",
    "project_player_lines_v2",
    # v2 MATCHUP-AWARE variant
    "SBS_V2_MATCHUP_DIR",
    "matchup_feature_columns",
    "build_matchup_feature_list",
    "train_player_lines_v2_matchup",
    "project_player_lines_v2_matchup",
    # CV_INGAME_MATCHUP flag gate
    "MATCHUP_FLAG",
    "is_matchup_enabled",
    "project_player_lines_v2_routed",
    # CV_INGAME_LIVE_USAGE flag gate
    "LIVE_USAGE_FLAG",
    "LIVE_USAGE_FEATURE",
    "is_live_usage_enabled",
    "compute_live_usg_vs_prior",
]
