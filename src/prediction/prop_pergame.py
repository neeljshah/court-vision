"""
prop_pergame.py — Per-game prop models trained on real game logs (PRED-13).

The legacy prop pipeline (player_props.train_props) trains on SEASON
averages: it predicts a player's season-average stat from features that are
essentially that same season average, plus simulated noise. Its reported
R²≈0.99 is therefore meaningless — a near-identity fit. The honest holdout
(predictions vs realised box scores) is only ~0.45.

This module trains the real task, the way a sharp quant would: each row is
one game, every feature is computed strictly from the player's PRIOR games
(rolling form, EWMA recency, rest, home/away), and the target is THAT game's
actual stat line. No leakage — features never see the game they predict.

Public API
----------
    build_pergame_dataset(gamelog_dir, min_prior) -> (rows, feature_cols)
    train_pergame_models(...)                     -> dict   (honest holdout R²/MAE)
    load_pergame_model(stat)                      -> model or None
    predict_pergame(stat, feature_row)            -> float
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_PLAYTYPE_PATH = os.path.join(PROJECT_DIR, "data", "playtypes.parquet")
_PLAY_TYPES = [
    "isolation", "prballhandler", "prrollman", "postup",
    "spotup", "handoff", "cut", "offscreen", "transition",
]
_PLAYTYPE_DEFAULTS: Dict[str, float] = {f"pt_{pt}_freq": 0.0 for pt in _PLAY_TYPES}

# Stats predicted, and their box-score column names in the gamelog JSON.
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# Stats where the XGB Poisson learner consistently degrades the XGB+LGB
# blend (ensemble_lift negative on holdout). For these we save only the
# LGB model and predict_pergame's load_pergame_model returns just LGB,
# making the "blend" a single-model prediction.
_LGB_ONLY_STATS: set = set()  # cycle 38: try NNLS meta-stacker for STL too

# Per-stat log1p label transform for right-skewed count stats. Walk-forward
# (4 folds) confirmed MAE wins on each stat below with 4/4 folds positive:
#   Cycle 16 — STL -0.0023, BLK -0.0072 (-1.4%), TOV -0.0057
#   Cycle 17 — FG3M -0.0079, REB -0.0160 (-0.8%), AST -0.0120 (-0.9%)
# XGB / LGB switch objective from Poisson to squared error when log1p is in
# play (Poisson assumes raw counts). The blend output is expm1'd back to
# raw-count scale before NNLS, calibration, and persistence so
# predict_pergame's contract is unchanged from the caller's perspective.
_LOG_TRANSFORM_STATS: set = {"stl", "blk", "tov", "fg3m", "reb", "ast"}

# Cycle 27 (loop 5) — Quantile-median (q50) PRIMARY predictor for stats where
# the blend's mean-optimal predictions diverge meaningfully from the
# MAE-optimal median. Walk-forward (4 folds) confirmed q50 SOLO beats the
# XGB+LGB+MLP NNLS blend with 4/4 folds positive AND large effect size:
#   BLK  -0.0864 +- 0.0039  (-16.6% MAE, biggest single-stat win of the loop)
#   STL  -0.0395 +- 0.0103  (-5.6%)
#   FG3M -0.0229 +- 0.0041  (-2.6%)
#   TOV  -0.0187 +- 0.0100  (-2.1%)
#   AST  -0.0093 +- 0.0058  (-0.7%)  — WF passed BUT production single-split
#                                       regressed +0.0157 MAE, so NOT shipped.
# REB was marginal (3/4 folds); PTS regressed (high-volume stat where mean
# and median coincide). Of the WF winners, only stats that ALSO pass the
# production single-split MAE-strictly-down gate ship. predict_pergame
# dispatches to the q50 model (persisted by prop_quantiles) for these stats,
# bypassing the cycle-23 3-way NNLS blend entirely. Note: q50 R² is much
# lower than blend R² because q50 minimises MAE (median-optimal) not MSE
# (mean-optimal); R² is the wrong metric for sportsbook prop predictions.
_USE_Q50_STATS: set = {"fg3m", "stl", "blk", "tov", "reb"}

# Cycle 29 (loop 5): per-stat q50 BACKEND override. Stats here use the LGB
# quantile model on disk (quantile_pergame_lgb_<stat>_q50.pkl) instead of
# the default XGB one. Walk-forward showed REB XGB-q50 was 3/4 folds (didn't
# pass cycle 27's dual-gate) while LGB-q50 was 4/4. Production single-split
# confirms -0.0051 MAE for REB lgb_q50. AST had the same WF-vs-single-split
# conflict regardless of backend, so AST stays on its multitask-MLP blend.
_Q50_LGB_BACKEND_STATS: set = {"reb"}

# Cycle 90d (loop 5) — T1-E REB OREB-context per-stat extra features.
# When stat == "reb", feature_columns(stat="reb") appends these 3 features:
#   team_oreb_pct_l5  — rolling-5 prior team OREB% (shift(1).rolling(5))
#   opp_dreb_pct_l5   — rolling-5 prior opp DREB% (shift(1).rolling(5))
#   reb_chance_l5     — interaction (team_oreb_pct_l5 * opp_dreb_pct_l5)
# Source: data/team_reb_context.parquet, built by scripts/build_team_reb_context.py
# from boxscore_adv_*.json. Only the REB LGB-q50 head is retrained with these
# features; other heads still use feature_columns() unchanged so existing
# model artifacts (PTS sqrt+Huber, AST multitask MLP, fg3m/stl/blk/tov XGB-q50)
# load and predict without dimension mismatch.
_REB_CONTEXT_KEYS = ("team_oreb_pct_l5", "opp_dreb_pct_l5", "reb_chance_l5")
_REB_CONTEXT_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _REB_CONTEXT_KEYS}
_REB_CONTEXT_PATH = os.path.join(PROJECT_DIR, "data", "team_reb_context.parquet")

# Cycle 19 (loop 5): per-stat Huber-on-log1p infrastructure. Tested with the
# six log1p stats — only FG3M showed a clean WF 4/4-folds MAE win
# (-0.0024 +- 0.0013), but on the production single-split MAE was a wash
# (+0.0000) and R² went -0.0006. REB regressed (+0.0009 mean), AST 3/4 folds
# (-0.0013 mean), STL/BLK/TOV essentially wash. The set is empty (no stat
# ships Huber on log1p). PTS uses sqrt+Huber via _SQRT_HUBER_STATS — that
# is the only Huber path live in production. Add stats here only after BOTH
# WF 4/4 win AND production single-split MAE strictly down.
_HUBER_LOG_STATS: set = set()

# Cycle 18 (loop 5): PTS-specific recipe — sqrt label transform + Huber loss.
# log1p was tested for PTS in cycle 17 and rejected (per-fold mae sign flips,
# range -0.0206..+0.0270). For PTS (mean ~12 per game), sqrt compresses less
# aggressively than log1p; combined with Huber (smooth L1, robust to outliers)
# it wins -0.0241 +- 0.0152 MAE and -0.0081 +- 0.0019 R² across 4 walk-forward
# folds, 4/4 folds positive. The largest single-stat MAE improvement of the
# session. XGB uses reg:pseudohubererror; LGB uses 'huber' objective.
_SQRT_HUBER_STATS: set = {"pts"}
_BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
            "stl": "STL", "blk": "BLK", "tov": "TOV", "min": "MIN"}
_FORM_STATS = STATS + ["min"]          # min drives every counting stat

_MIN_PLAYED = 1.0                      # a game counts only if the player played
_EWMA_ALPHA = 0.30                     # recency weight — recent games dominate

# Training-row recency decay: weight = exp(-_RECENCY_DECAY * age_years).
# 0.0 = no weighting; 0.5 means rows 2 years old count ~37% as much as
# the most-recent training row. Picked via single-cycle sweep, see cycle 18.
_RECENCY_DECAY = 0.5


# ── feature helpers ───────────────────────────────────────────────────────────

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse an NBA gamelog date ('Apr 13, 2025'). Returns None on failure."""
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _ewma(vals: List[float], alpha: float = _EWMA_ALPHA) -> float:
    """Exponentially-weighted mean — most recent game weighted highest."""
    if not vals:
        return 0.0
    weighted = total_w = 0.0
    for i, v in enumerate(reversed(vals)):       # i=0 is the most recent game
        w = alpha * (1.0 - alpha) ** i
        weighted += w * v
        total_w += w
    return weighted / total_w if total_w > 0 else 0.0


def feature_columns(stat: Optional[str] = None) -> List[str]:
    """Ordered feature names — form, game-context, opponent defence, rest/travel,
    playtype frequency, BBRef advanced, contracts.

    When stat is provided, additional per-stat features are appended after the
    global list. Cycle 90d adds REB-context features for stat="reb" only:
    team_oreb_pct_l5, opp_dreb_pct_l5, reb_chance_l5 (interaction). All other
    stats receive the unchanged global feature list so their persisted model
    artifacts continue to load without n_features_in_ mismatch.
    """
    cols: List[str] = []
    for s in _FORM_STATS:
        cols += [f"l5_{s}", f"l10_{s}", f"std_{s}",
                 f"ewma_{s}", f"prev_{s}"]
    cols += ["rest_days", "is_home", "games_played"]
    cols += ["days_since_last_game", "games_since_long_absence"]
    cols += [f"opp_def_{s}" for s in STATS]      # opponent-defence factors
    cols += ["is_b2b", "is_b3b", "miles_traveled", "altitude_ft"]
    cols += [f"pt_{pt}_freq" for pt in _PLAY_TYPES]
    cols += [f"bbref_{k}" for k in _BBREF_KEYS]
    cols += [f"contract_{k}" for k in _CONTRACT_KEYS]
    cols += list(_RATIO_KEYS)
    # Per-game officials crew tendency features (avg fouls/fta/home_win_pct
    # averaged across 3-ref crew using PRIOR-season ref stats) infrastructure
    # lives in _OfficialsCrew + data/officials_features.parquet. Cycle 15
    # (loop 5) tested wire-in: single-split looked mixed (MAE down on 5/7
    # but R² down on all 7), and walk-forward showed all 7 stats regress on
    # MAE (PTS +0.0111 WF MAE). The single-split MAE wins were noise from
    # a specific holdout slice. Disabled.
    # cols += list(_OFFICIALS_KEYS)  # cycle 15 regressed on walk-forward
    # Per-player prior-season tracking (Drives + Passing + CatchShoot) lives in
    # data/player_tracking.parquet — _PlayerTracking wraps it. Cycle 14 (loop 5)
    # tested the wire-in and regressed 5 of 7 stats (PTS R² -0.0023, AST -0.0064)
    # because year-over-year role changes mean prior-season tracking is a noisy
    # proxy for THIS season's role. Form features (l5/l10/ewma) capture the same
    # signal more accurately. Infrastructure stays for a future angle (e.g.,
    # in-season per-month tracking, or transfer-weighted prior).
    # cols += list(_TRACKING_KEYS)  # disabled — see cycle 14 notes
    # Per-player advanced-stat L5/L10/EWMA/prev features are infrastructure-
    # ready (_AdvancedStats + data/player_adv_stats.parquet, 77k player-game
    # rows across 3 seasons), but disabled here. Cycle 8 (loop 5) verified
    # that even with full coverage, adding the 20 adv columns regresses 5
    # of 7 stats (PTS R² -0.0054, TOV R² -0.0089 worst) — gamelog form
    # features already span the same signal. Future angles: season-to-date
    # aggregation, per-opponent split, or use raw values without rolling.
    # cols += list(_ADV_FEATURE_COLS)  # disabled — see _AdvancedStats docstring

    # Cycle 90d (loop 5) — T1-E: REB-only OREB-context features.
    # ONLY appended when stat == "reb"; other stats keep the global list to
    # preserve compatibility with existing model artifacts.
    if stat == "reb":
        cols += list(_REB_CONTEXT_KEYS)
    return cols


# ── per-player advanced-stat L5/L10/EWMA features (cycle 6, loop 5) ────────────
#
# Sourced from data/player_adv_stats.parquet — built by
# scripts/aggregate_player_advanced_stats.py from cached
# data/nba/boxscore_adv_*.json (boxscoreadvancedv3 per-game). Each row carries
# one player's per-game advanced metrics: USG%, TS%, AST%, REB%, PIE. We
# expose them to the trainer as point-in-time rolling features (L5/L10/EWMA/
# prev) computed strictly from games before the row's game_date — identical
# leakage discipline as the existing per-game form features.
_ADV_STAT_KEYS = ("usg", "ts", "ast_pct", "reb_pct", "pie")
_ADV_RAW_COL = {
    "usg":     "usagepercentage",
    "ts":      "trueshootingpercentage",
    "ast_pct": "assistpercentage",
    "reb_pct": "reboundpercentage",
    "pie":     "pie",
}
_ADV_FEATURE_COLS: tuple = tuple(
    f"{prefix}_adv_{stat}"
    for stat in _ADV_STAT_KEYS
    for prefix in ("l5", "l10", "ewma", "prev")
)
_ADV_DEFAULTS: Dict[str, float] = {c: 0.0 for c in _ADV_FEATURE_COLS}
_ADV_STATS_PATH = os.path.join(PROJECT_DIR, "data", "player_adv_stats.parquet")


# ── per-player tracking features (cycle 14 loop 5) ─────────────────────────────
# Source: data/player_tracking.parquet — built by scripts/fetch_player_tracking.py
# from leaguedashptstats (Drives + Passing + CatchShoot) per season per player.
# Lookup is PRIOR-SEASON keyed: for a 2024-25 game we use the player's 2023-24
# tracking stats. That's point-in-time at season start (prior season is fully
# complete before this season begins), so no leak. Rookies and players missing
# prior-season data get neutral defaults.
_TRACKING_KEYS = (
    "trk_drv_count", "trk_drv_pts", "trk_drv_fg_pct",
    "trk_drv_passes", "trk_drv_ast", "trk_drv_tov_pct",
    "trk_pas_passes_made", "trk_pas_passes_received",
    "trk_pas_potential_ast", "trk_pas_ast_points_created",
    "trk_pas_secondary_ast", "trk_pas_ft_ast",
    "trk_cs_fga", "trk_cs_fg_pct", "trk_cs_efg_pct", "trk_cs_pts",
)
_TRACKING_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _TRACKING_KEYS}
_TRACKING_PATH = os.path.join(PROJECT_DIR, "data", "player_tracking.parquet")


def _prior_season(season: str) -> str:
    """Return '2023-24' for '2024-25', etc. Empty string on parse failure."""
    try:
        start, end = season.split("-")
        return f"{int(start)-1}-{int(end)-1:02d}"
    except (ValueError, IndexError, AttributeError):
        return ""


class _PlayerTracking:
    """Per-(player_id, season) lookup of PRIOR-season tracking features."""

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup  # keyed by (player_id, season_of_the_tracking_data)

    def features(self, player_id, season: str) -> Dict[str, float]:
        """Return tracking features for the player as of season-1.

        For a 2024-25 game (season='2024-25') we look up the player's
        2023-24 tracking row — strictly point-in-time at the start of this
        season. Rookies (no prior-season row) get neutral defaults.
        """
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_TRACKING_DEFAULTS)
        prior = _prior_season(str(season))
        if not prior:
            return dict(_TRACKING_DEFAULTS)
        row = self._lookup.get((pid, prior))
        if not row:
            return dict(_TRACKING_DEFAULTS)
        return {k: float(row.get(k, 0.0) or 0.0) for k in _TRACKING_KEYS}


def build_player_tracking(parquet_path: Optional[str] = None) -> _PlayerTracking:
    """Load data/player_tracking.parquet into a _PlayerTracking wrapper.

    Falls back to an empty wrapper when the parquet is absent or pandas is
    unavailable. Never raises.
    """
    path = parquet_path or _TRACKING_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import math  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _PlayerTracking(lookup)
        df = pd.read_parquet(path)

        def _coerce(v):
            # NaN appears for stats with zero attempts (e.g. catch_shoot_fg_pct
            # when a player took 0 catch-and-shoot threes) — collapse to 0.0
            # so downstream learners (MLP especially) don't reject the row.
            try:
                f = float(v)
                return 0.0 if (f != f) else f
            except (TypeError, ValueError):
                return 0.0

        for _, r in df.iterrows():
            key = (int(r["player_id"]), str(r["season"]))
            lookup[key] = {k: _coerce(r.get(k, 0.0)) for k in _TRACKING_KEYS}
    except Exception:
        return _PlayerTracking(lookup)
    return _PlayerTracking(lookup)


# ── MLP seed ensemble (cycle 11 loop 5) ────────────────────────────────────────
# Single-seed MLPs vary by ~0.005-0.007 R² across seeds {1,7,42,100,2024} for
# the PTS target — within the +/-0.005 ship-gate width. Averaging the 5 trained
# models stabilises the prediction AND improves it (PTS solo MLP R² 0.5107 ->
# 0.5134 = +0.0027 from averaging alone). Per the seed-stability spec rule.
_MLP_SEEDS = (1, 7, 42, 100, 2024)


class _MLPSeedEnsemble:
    """5-seed MLPRegressor wrapper — predict averages across all trained models."""

    def __init__(self, hidden_layer_sizes=(128, 64), seeds=_MLP_SEEDS):
        from sklearn.neural_network import MLPRegressor  # noqa: PLC0415
        self.models = [
            MLPRegressor(
                hidden_layer_sizes=hidden_layer_sizes, activation="relu",
                solver="adam", learning_rate_init=1e-3, alpha=1e-4,
                batch_size=512, max_iter=80, random_state=int(s),
                early_stopping=True, validation_fraction=0.15,
                n_iter_no_change=10,
            )
            for s in seeds
        ]
        # n_features_in_ is set after the first .fit — predict_pergame's stale-
        # model guard reads it on the wrapper.
        self.n_features_in_ = None

    def fit(self, X, y):
        for m in self.models:
            m.fit(X, y)
        self.n_features_in_ = int(getattr(self.models[0], "n_features_in_", X.shape[1]))
        return self

    def predict(self, X):
        import numpy as np  # noqa: PLC0415
        return np.mean([m.predict(X) for m in self.models], axis=0)


# Cycle 23 (loop 5) — Multitask MLP. One 5-seed multi-output MLPRegressor
# trained on a (n_samples, len(STATS)) target matrix with per-stat transforms
# applied (sqrt for PTS, log1p for the log1p stats, identity for any non-
# transformed stat). Shared (128, 64) hidden layers capture cross-stat
# correlations. The walk-forward probe shipped this ONLY for AST and STL
# (4/4 folds positive MAE: AST -0.0022, STL -0.0014); PTS/REB/FG3M/BLK/TOV
# either washed or regressed on WF and kept their independent _MLPSeedEnsemble.
_USE_MULTITASK_MLP_STATS: set = {"ast", "stl"}


class _MultitaskMLPEnsemble:
    """5-seed multi-output MLP wrapper. .predict(X) returns (n_samples, n_outputs)."""

    def __init__(self, hidden_layer_sizes=(128, 64), seeds=_MLP_SEEDS):
        from sklearn.neural_network import MLPRegressor  # noqa: PLC0415
        self.models = [
            MLPRegressor(
                hidden_layer_sizes=hidden_layer_sizes, activation="relu",
                solver="adam", learning_rate_init=1e-3, alpha=1e-4,
                batch_size=512, max_iter=80, random_state=int(s),
                early_stopping=True, validation_fraction=0.15,
                n_iter_no_change=10,
            )
            for s in seeds
        ]
        self.n_features_in_ = None
        self.n_outputs_ = None

    def fit(self, X, Y):
        for m in self.models:
            m.fit(X, Y)
        self.n_features_in_ = int(getattr(self.models[0], "n_features_in_", X.shape[1]))
        self.n_outputs_ = Y.shape[1] if Y.ndim > 1 else 1
        return self

    def predict(self, X):
        import numpy as np  # noqa: PLC0415
        return np.mean([m.predict(X) for m in self.models], axis=0)


class _MultitaskMLPProxy:
    """Thin wrapper exposing a single-stat .predict() over a multitask ensemble.

    load_pergame_model + predict_pergame already expect (scaler, model) tuples
    with a 1D .predict() output; this proxy provides exactly that interface
    by selecting one column from the multitask ensemble's output.
    """

    def __init__(self, ensemble: "_MultitaskMLPEnsemble", stat_idx: int):
        self.ensemble = ensemble
        self.stat_idx = int(stat_idx)
        self.n_features_in_ = getattr(ensemble, "n_features_in_", None)

    def predict(self, X):
        out = self.ensemble.predict(X)
        if out.ndim == 1:
            return out
        return out[:, self.stat_idx]


# ── REB OREB-context features (cycle 90d loop 5, T1-E) ────────────────────────
# Per-team time-series of per-game OREB% and DREB% (sourced from
# data/team_reb_context.parquet — built from boxscore_adv_*.json team entries).
# For row (team_abbrev, opp_abbrev, date), exposes 3 rolling features computed
# STRICTLY from prior games (shift(1).rolling(5)):
#   team_oreb_pct_l5  — team's last-5 OREB% average
#   opp_dreb_pct_l5   — opponent's last-5 DREB% average
#   reb_chance_l5     — interaction product (rebound-OPPORTUNITY proxy)
# Outlier/Action-Network's "Rebound Chances" framework: rebound rate ≠
# rebound volume — the ratio captures opportunity. REB-only because team-
# rebound context is dominated by player skill+pace signal for other stats.


class _TeamRebContext:
    """Per-team time series of OREB%/DREB% with point-in-time rolling-5 features.

    Keyed on team_tricode → sorted list of (date, oreb_pct, dreb_pct). For a
    row dated D, returns the mean of the team's last 5 games STRICTLY before D
    (shift(1).rolling(5) discipline). Returns neutral 0.0 defaults when the
    parquet is absent or the team has no prior games.
    """

    def __init__(self, by_team: Dict[str, list]):
        self._by_team = by_team

    def _l5(self, team_tricode: str, current_date) -> Optional[Tuple[float, float]]:
        history = self._by_team.get(str(team_tricode))
        if not history:
            return None
        priors = []
        for d, oreb, dreb in history:
            if d < current_date:
                priors.append((oreb, dreb))
            else:
                break
        if not priors:
            return None
        last5 = priors[-5:]
        o = sum(x[0] for x in last5) / len(last5)
        d = sum(x[1] for x in last5) / len(last5)
        return (o, d)

    def features(self, team_tricode: str, opp_tricode: str,
                 current_date) -> Dict[str, float]:
        out: Dict[str, float] = dict(_REB_CONTEXT_DEFAULTS)
        team_l5 = self._l5(team_tricode, current_date)
        opp_l5 = self._l5(opp_tricode, current_date)
        if team_l5 is not None:
            out["team_oreb_pct_l5"] = round(team_l5[0], 5)
        if opp_l5 is not None:
            out["opp_dreb_pct_l5"] = round(opp_l5[1], 5)
        out["reb_chance_l5"] = round(out["team_oreb_pct_l5"] * out["opp_dreb_pct_l5"], 6)
        return out


_TEAM_REB_CONTEXT_CACHE: Optional["_TeamRebContext"] = None


def _get_team_reb_context() -> "_TeamRebContext":
    """Process-cached _TeamRebContext for live prediction paths."""
    global _TEAM_REB_CONTEXT_CACHE
    if _TEAM_REB_CONTEXT_CACHE is None:
        _TEAM_REB_CONTEXT_CACHE = build_team_reb_context()
    return _TEAM_REB_CONTEXT_CACHE


def build_team_reb_context(parquet_path: Optional[str] = None) -> _TeamRebContext:
    """Load team_reb_context.parquet into a _TeamRebContext wrapper. Never raises."""
    path = parquet_path or _REB_CONTEXT_PATH
    by_team: Dict[str, list] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _TeamRebContext(by_team)
        df = pd.read_parquet(path)
        for tcode, grp in df.groupby("team_tricode"):
            grp_sorted = grp.sort_values("game_date")
            hist = []
            for _, r in grp_sorted.iterrows():
                d = _parse_date_iso(str(r["game_date"]))
                if d is None:
                    continue
                hist.append((d, float(r.get("oreb_pct", 0.0) or 0.0),
                             float(r.get("dreb_pct", 0.0) or 0.0)))
            by_team[str(tcode)] = hist
    except Exception:
        return _TeamRebContext(by_team)
    return _TeamRebContext(by_team)


# ── rest / travel features ────────────────────────────────────────────────────

# ── player positions (cycle 90e loop 5) ───────────────────────────────────────
# Source: data/player_positions.parquet — built by scripts/fetch_player_positions.py
# from commonplayerinfo cache. Per-player static metadata (not point-in-time):
# position, height_inches, weight_lbs, birth_date, draft_year. The parquet may
# not exist on a fresh checkout — _PlayerPositions.from_parquet returns a
# defaults-only wrapper in that case so build_pergame_dataset stays backward
# compatible (no crash, no behaviour change). Position is NOT yet appended to
# feature_columns() — that requires a separate retrain cycle. For now we only
# expose it via the per-row dict so probes (cycle 89c) can re-run.
_PLAYER_POSITIONS_PATH = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")


class _PlayerPositions:
    """Per-player static position / physical lookup.

    Keyed on player_id → {position, height_inches, weight_lbs, birth_date,
    draft_year}. Unknown pids return None for position (probes treat this
    as the no-position bucket).
    """

    def __init__(self, lookup: Dict[int, Dict[str, object]]):
        self._lookup = lookup

    def __contains__(self, pid) -> bool:
        try:
            return int(pid) in self._lookup
        except (TypeError, ValueError):
            return False

    def __len__(self) -> int:
        return len(self._lookup)

    def position(self, player_id) -> Optional[str]:
        """Return the player's POSITION string (e.g. 'Guard', 'Forward-Center'),
        or None when the pid is missing from the parquet."""
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        row = self._lookup.get(pid)
        if not row:
            return None
        v = row.get("position")
        if v in (None, ""):
            return None
        return str(v)

    def row(self, player_id) -> Optional[Dict[str, object]]:
        """Return the full per-player dict (position, height_inches, ...) or None."""
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        return self._lookup.get(pid)


def build_player_positions(parquet_path: Optional[str] = None) -> _PlayerPositions:
    """Load data/player_positions.parquet into a _PlayerPositions wrapper.

    GATED on file existence: when the parquet is absent (a fresh checkout
    or a machine that hasn't run fetch_player_positions.py yet), returns
    an empty wrapper so callers get position=None for every pid. Never
    raises — pandas/pyarrow import failures collapse to the empty wrapper.
    """
    path = parquet_path or _PLAYER_POSITIONS_PATH
    lookup: Dict[int, Dict[str, object]] = {}
    if not os.path.exists(path):
        return _PlayerPositions(lookup)
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError, KeyError):
                continue
            lookup[pid] = {
                "position":      r.get("position"),
                "height_inches": r.get("height_inches"),
                "weight_lbs":    r.get("weight_lbs"),
                "birth_date":    r.get("birth_date"),
                "draft_year":    r.get("draft_year"),
            }
    except Exception:
        return _PlayerPositions(lookup)
    return _PlayerPositions(lookup)


_REST_TRAVEL_PATH = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
_REST_TRAVEL_DEFAULTS: Dict[str, float] = {
    "is_b2b": 0.0, "is_b3b": 0.0, "miles_traveled": 0.0, "altitude_ft": 0.0,
}


class _RestTravel:
    """Lookup table for rest/travel features sourced from data/rest_travel.parquet.

    Keyed by (game_date_iso, team_abbreviation) → {is_b2b, is_b3b, miles_traveled, altitude_ft}.
    Yields neutral defaults when the parquet is absent or the key is missing.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, team_abbrev: str, gdate: datetime) -> Dict[str, float]:
        """Return rest/travel feature dict for a team on a date."""
        key = (gdate.date().isoformat(), str(team_abbrev))
        return dict(self._lookup.get(key, _REST_TRAVEL_DEFAULTS))


def build_rest_travel(cache_path: Optional[str] = None) -> _RestTravel:
    """Load rest/travel parquet and build the lookup table.

    If the parquet is absent or pandas/pyarrow import fails, returns a
    _RestTravel that always yields neutral defaults. Never raises.
    """
    path = cache_path or _REST_TRAVEL_PATH
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _RestTravel(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            key = (str(row["game_date"]), str(row["team_abbreviation"]))
            lookup[key] = {
                "is_b2b":         float(row.get("is_b2b", 0.0) or 0.0),
                "is_b3b":         float(row.get("is_b3b", 0.0) or 0.0),
                "miles_traveled": float(row.get("miles_traveled", 0.0) or 0.0),
                "altitude_ft":    float(row.get("altitude_ft", 0.0) or 0.0),
            }
    except Exception:
        pass
    return _RestTravel(lookup)


# ── officials crew features (cycle 15 loop 5) ──────────────────────────────────
# Source: data/officials_features.parquet — built by
# scripts/build_officials_per_team_date.py. Each game's crew is averaged across
# its 3 refs' PRIOR-SEASON tendencies (avg_total_fouls, avg_total_fta,
# home_win_rate from ref_stats_<prior_season>.json). Strictly point-in-time:
# the prior season is complete before this season starts, no leak.

_OFFICIALS_KEYS = ("ref_crew_fouls", "ref_crew_fta", "ref_crew_home_win_pct")
_OFFICIALS_DEFAULTS: Dict[str, float] = {
    "ref_crew_fouls":        42.0,
    "ref_crew_fta":          43.5,
    "ref_crew_home_win_pct": 0.55,
}
_OFFICIALS_PATH = os.path.join(PROJECT_DIR, "data", "officials_features.parquet")


class _OfficialsCrew:
    """Per-(team_abbreviation, game_date) lookup of crew tendency features."""

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, team_abbrev: str, gdate: datetime) -> Dict[str, float]:
        key = (str(team_abbrev), gdate.date().isoformat())
        return dict(self._lookup.get(key, _OFFICIALS_DEFAULTS))


def build_officials_crew(parquet_path: Optional[str] = None) -> _OfficialsCrew:
    """Load data/officials_features.parquet into an _OfficialsCrew wrapper.

    Falls back to an empty wrapper (always-defaults) when the parquet is
    absent or pandas/pyarrow fails. Never raises.
    """
    path = parquet_path or _OFFICIALS_PATH
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _OfficialsCrew(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            key = (str(r["team_abbreviation"]), str(r["game_date"]))
            lookup[key] = {k: float(r.get(k, _OFFICIALS_DEFAULTS[k]) or _OFFICIALS_DEFAULTS[k])
                           for k in _OFFICIALS_KEYS}
    except Exception:
        return _OfficialsCrew(lookup)
    return _OfficialsCrew(lookup)


# ── play-type features ────────────────────────────────────────────────────────

class _PlayTypes:
    """Lookup table for Synergy play-type frequencies sourced from data/playtypes.parquet.

    Keyed by (player_id, season) → {pt_<playtype>_freq: float, ...}.
    Yields zero defaults when the parquet is absent or the key is missing.
    """

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, season: str) -> Dict[str, float]:
        """Return play-type feature dict for a player in a season."""
        key = (int(player_id), str(season))
        return dict(self._lookup.get(key, _PLAYTYPE_DEFAULTS))


def build_playtypes(cache_path: Optional[str] = None) -> _PlayTypes:
    """Load the play-type parquet and build the lookup table.

    If the parquet is absent or pandas/pyarrow import fails, returns a
    _PlayTypes that always yields zero defaults. Never raises.
    """
    path = cache_path or _PLAYTYPE_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _PlayTypes(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            normalized = str(row["play_type"]).lower().replace(" ", "")
            key = (int(row["player_id"]), str(row["season"]))
            lookup.setdefault(key, {})[f"pt_{normalized}_freq"] = (
                float(row.get("freq_pct", 0.0) or 0.0)
            )
        # Ensure every entry has all 9 keys so callers never get KeyError.
        for key in lookup:
            for pt in _PLAY_TYPES:
                lookup[key].setdefault(f"pt_{pt}_freq", 0.0)
    except Exception:
        pass
    return _PlayTypes(lookup)


_PLAYTYPES_CACHE: Optional[_PlayTypes] = None


def _get_playtypes() -> _PlayTypes:
    global _PLAYTYPES_CACHE
    if _PLAYTYPES_CACHE is None:
        _PLAYTYPES_CACHE = build_playtypes()
    return _PLAYTYPES_CACHE


# ── BBRef advanced features (per-player-season efficiency + rate metrics) ────

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
# Order matters — drives feature_columns() output. Efficiency (ts), volume
# (usg), shot profile (three_par, ftr), per-100 rate stats (ast/stl/blk/tov),
# holistic impact (ws_per_48, per), and SPLIT offensive/defensive BPM (obpm,
# dbpm) — bpm itself is the sum so we keep the split for finer per-side
# weighting. per is included for its independent signal (corr 0.88 with bpm —
# enough non-redundancy to matter for trees). Defensive depth — dws, ows,
# vorp — are ~85% collinear with ws_per_48 / obpm / dbpm but the residual
# signal still helps gradient-boosted trees in practice; appended at the end
# so existing column positions stay stable. Dropped: trb/orb/drb_pct
# (handled implicitly by opp_def_reb + form), bpm (sum of obpm+dbpm).
_BBREF_KEYS = ("usg_pct", "ts_pct", "three_par", "ftr",
               "ast_pct", "stl_pct", "blk_pct", "tov_pct",
               "ws_per_48", "per", "obpm", "dbpm",
               "dws", "ows", "vorp")
_BBREF_DEFAULTS: Dict[str, float] = {f"bbref_{k}": 0.0 for k in _BBREF_KEYS}


class _BBRefAdvanced:
    """Per-(player_name, season) lookup of BBRef advanced metrics.

    Source: data/external/bbref_advanced_<season>.json (already cached).
    Keys: player_name (NBA full_name) and season (e.g. '2024-25').
    Yields zero defaults when the season file is absent or the player isn't
    listed (rookies, two-way contracts, missing scrape). Never raises.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]],
                 id_to_name: Dict[int, str]):
        self._lookup = lookup
        self._id_to_name = id_to_name

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            name = self._id_to_name.get(int(player_id))
        except (TypeError, ValueError):
            name = None
        if not name:
            return dict(_BBREF_DEFAULTS)
        return dict(self._lookup.get((name, str(season)), _BBREF_DEFAULTS))


def _bbref_id_to_name() -> Dict[int, str]:
    """Build {player_id: full_name} from nba_api's static player list.
    Never raises — returns {} if the static cache is unavailable."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
        return {int(p["id"]): str(p["full_name"]) for p in players.get_players()}
    except Exception:
        return {}


def _unmangle_utf8(s: str) -> str:
    """The cached BBRef JSON was written with mangled encoding — every UTF-8
    byte sequence got re-stored as if it were Latin-1, so 'Nikola Jokić'
    became 'Nikola JokiÄ\\x87'. Reverse the round-trip when possible; fall
    back to the original string. No-op for ASCII names."""
    try:
        if s.isascii():
            return s
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def build_bbref_advanced(bbref_dir: Optional[str] = None) -> _BBRefAdvanced:
    """Load every bbref_advanced_<season>.json under bbref_dir into a lookup
    keyed by (player_name, season). Never raises. Reverses the mojibake on
    non-ASCII names so accented players (Jokić, Vučević, Šengün, ...) match
    the nba_api full_name canonical form."""
    bbref_dir = bbref_dir or _BBREF_DIR
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        if not os.path.isdir(bbref_dir):
            return _BBRefAdvanced(lookup, _bbref_id_to_name())
        for fname in os.listdir(bbref_dir):
            if not fname.startswith("bbref_advanced_") or not fname.endswith(".json"):
                continue
            season = fname.removeprefix("bbref_advanced_").removesuffix(".json")
            try:
                rows = json.load(open(os.path.join(bbref_dir, fname), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                name = _unmangle_utf8(str(row.get("player_name", "")).strip())
                if not name:
                    continue
                lookup[(name, season)] = {
                    f"bbref_{k}": float(row.get(k, 0.0) or 0.0)
                    for k in _BBREF_KEYS
                }
    except Exception:
        pass
    return _BBRefAdvanced(lookup, _bbref_id_to_name())


_BBREF_CACHE: Optional[_BBRefAdvanced] = None


def _get_bbref() -> _BBRefAdvanced:
    global _BBREF_CACHE
    if _BBREF_CACHE is None:
        _BBREF_CACHE = build_bbref_advanced()
    return _BBREF_CACHE


# ── contract features (salary, contract-year, role stability) ────────────────

# Per-(player_name, season) features sourced from data/external/contracts_<season>.json.
# Schema: player_name, team, current_salary, years_remaining, cap_hit, cap_hit_pct,
# contract_type, contract_year. current_salary is log-scaled (raw range $22K..$60M
# blows up tree splits); contract_type is dropped because every cached row is
# "guaranteed" (zero-variance constant). Only 2024-25 / 2025-26 are cached, so
# ~50% of training rows currently get neutral defaults.
_CONTRACTS_DIR = os.path.join(PROJECT_DIR, "data", "external")
_CONTRACT_KEYS = ("salary_log", "cap_hit_pct", "year", "years_remaining")
_CONTRACT_DEFAULTS: Dict[str, float] = {f"contract_{k}": 0.0 for k in _CONTRACT_KEYS}


class _Contracts:
    """Per-(player_name, season) contract feature lookup.

    Yields zero defaults when the season file is absent or the player isn't
    listed (rookies on two-ways, mid-season signings, missing scrape).
    Never raises.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]],
                 id_to_name: Dict[int, str]):
        self._lookup = lookup
        self._id_to_name = id_to_name

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            name = self._id_to_name.get(int(player_id))
        except (TypeError, ValueError):
            name = None
        if not name:
            return dict(_CONTRACT_DEFAULTS)
        return dict(self._lookup.get((name, str(season)), _CONTRACT_DEFAULTS))


def build_contracts(contracts_dir: Optional[str] = None) -> _Contracts:
    """Load every contracts_<season>.json into a (player_name, season) lookup.

    Salary is converted to log10(salary+1) so heavy-tail values (Curry $60M
    vs. min $22K) don't dominate tree split selection. cap_hit_pct stays as
    its native 0-1 fraction. contract_year and years_remaining are passed
    through (0/1 and small int respectively). Never raises — missing files
    yield an empty lookup."""
    import math

    contracts_dir = contracts_dir or _CONTRACTS_DIR
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        if not os.path.isdir(contracts_dir):
            return _Contracts(lookup, _bbref_id_to_name())
        for fname in os.listdir(contracts_dir):
            if not fname.startswith("contracts_") or not fname.endswith(".json"):
                continue
            season = fname.removeprefix("contracts_").removesuffix(".json")
            try:
                rows = json.load(open(os.path.join(contracts_dir, fname), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                name = _unmangle_utf8(str(row.get("player_name", "")).strip())
                if not name:
                    continue
                salary = row.get("current_salary")
                salary_log = math.log10(float(salary) + 1.0) if salary else 0.0
                cap_pct = row.get("cap_hit_pct")
                lookup[(name, season)] = {
                    "contract_salary_log":      float(salary_log),
                    "contract_cap_hit_pct":     float(cap_pct or 0.0),
                    "contract_year":            1.0 if row.get("contract_year") else 0.0,
                    "contract_years_remaining": float(row.get("years_remaining") or 0),
                }
    except Exception:
        pass
    return _Contracts(lookup, _bbref_id_to_name())


_CONTRACTS_CACHE: Optional[_Contracts] = None


def _get_contracts() -> _Contracts:
    global _CONTRACTS_CACHE
    if _CONTRACTS_CACHE is None:
        _CONTRACTS_CACHE = build_contracts()
    return _CONTRACTS_CACHE


# ── opponent defence (leakage-free to-date factors) ──────────────────────────

class _OpponentDefense:
    """Per-team opponent-defence factors computed strictly to-date.

    For a game on date D against team O, the factor for a stat is O's mean
    allowed value for that stat over O's games BEFORE D, divided by the
    league mean to D. >1 means O is an easier-than-average matchup. Using
    only games before D keeps the feature leakage-free.
    """

    def __init__(self, allowed: Dict[str, list], league: list):
        self._team = {t: self._index(rows) for t, rows in allowed.items()}
        self._league = self._index(league)

    @staticmethod
    def _index(rows: list) -> dict:
        rows = sorted(rows, key=lambda r: r[0])
        dates = [r[0] for r in rows]
        prefix = {s: [0.0] for s in STATS}
        for _d, line in rows:
            for s in STATS:
                prefix[s].append(prefix[s][-1] + line[s])
        return {"dates": dates, "prefix": prefix}

    @staticmethod
    def _todate_mean(idx: dict, date, stat: str) -> Optional[float]:
        i = bisect.bisect_left(idx["dates"], date)
        return idx["prefix"][stat][i] / i if i > 0 else None

    def factors(self, opponent: str, date) -> Dict[str, float]:
        """Return {opp_def_{stat}: factor} for an opponent on a date.

        Falls back to a neutral 1.0 when there is no prior history."""
        out: Dict[str, float] = {}
        team_idx = self._team.get(opponent)
        for stat in STATS:
            league_mean = self._todate_mean(self._league, date, stat)
            team_mean = self._todate_mean(team_idx, date, stat) if team_idx else None
            if team_mean and league_mean and league_mean > 0:
                out[f"opp_def_{stat}"] = round(team_mean / league_mean, 4)
            else:
                out[f"opp_def_{stat}"] = 1.0
        return out


def _opponent_from_matchup(matchup: str) -> str:
    """Opponent abbreviation — the last token of 'TEAM vs. OPP' / 'TEAM @ OPP'."""
    parts = str(matchup).split()
    return parts[-1] if parts else ""


class _AdvancedStats:
    """Per-player advanced-stat time series with point-in-time L5/L10/EWMA.

    Built from data/player_adv_stats.parquet — keyed on player_id with a
    chronologically-sorted list of (date, {raw_stat: value}). For a row with
    date D, returns rolling features computed strictly from the player's games
    BEFORE D, mirroring the leakage discipline of the standard form features.
    """

    def __init__(self, by_player: Dict[int, list]):
        self._by_player = by_player

    def features(self, player_id, current_date) -> Dict[str, float]:
        """Return adv-stat rolling features for one player on one date."""
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_ADV_DEFAULTS)
        history = self._by_player.get(pid)
        if not history:
            return dict(_ADV_DEFAULTS)
        # Strictly-prior games — bisect for O(log n) lookup
        priors = []
        for d, stats in history:
            if d < current_date:
                priors.append((d, stats))
            else:
                break
        if not priors:
            return dict(_ADV_DEFAULTS)
        out: Dict[str, float] = {}
        for key, raw in _ADV_RAW_COL.items():
            recent = [s[raw] for (_d, s) in priors[-10:]]
            l5 = sum(recent[-5:]) / max(1, len(recent[-5:]))
            l10 = sum(recent) / len(recent)
            # Exponentially-weighted mean over last 10 — most recent dominates.
            w_sum = total_w = 0.0
            for i, v in enumerate(reversed(recent)):
                w = 0.30 * (0.70 ** i)
                w_sum += w * v
                total_w += w
            ewma = w_sum / total_w if total_w > 0 else 0.0
            prev = priors[-1][1][raw]
            out[f"l5_adv_{key}"]   = round(l5, 4)
            out[f"l10_adv_{key}"]  = round(l10, 4)
            out[f"ewma_adv_{key}"] = round(ewma, 4)
            out[f"prev_adv_{key}"] = round(prev, 4)
        return out


def build_advanced_stats(parquet_path: Optional[str] = None) -> _AdvancedStats:
    """Load data/player_adv_stats.parquet into an _AdvancedStats wrapper.

    Falls back to an empty (defaults-only) wrapper if the file is absent or
    pandas/pyarrow is unavailable. Never raises — the trainer gracefully gets
    all-zero advanced features and proceeds with the original feature set.
    """
    path = parquet_path or _ADV_STATS_PATH
    by_player: Dict[int, list] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _AdvancedStats(by_player)
        df = pd.read_parquet(path)
        for pid, grp in df.groupby("player_id"):
            grp_sorted = grp.sort_values("game_date")
            history = []
            for _, r in grp_sorted.iterrows():
                d = _parse_date_iso(str(r["game_date"]))
                if d is None:
                    continue
                stats = {raw: float(r.get(raw, 0.0) or 0.0)
                         for raw in _ADV_RAW_COL.values()}
                history.append((d, stats))
            by_player[int(pid)] = history
    except Exception:
        return _AdvancedStats(by_player)
    return _AdvancedStats(by_player)


def _parse_date_iso(raw: str) -> Optional[datetime]:
    """Parse an ISO date ('2024-10-22') — adv_stats parquet column format."""
    try:
        return datetime.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        return None


def build_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Pass over every gamelog to build the to-date opponent-defence model.

    Each played game is a stat line the *opponent* allowed — aggregated per
    opponent and league-wide, sorted chronologically.
    """
    allowed: Dict[str, list] = {}
    league: list = []
    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            if _num(g.get("MIN")) < _MIN_PLAYED:
                continue
            gdate = _parse_date(g.get("GAME_DATE"))
            opp = _opponent_from_matchup(g.get("MATCHUP", ""))
            if gdate is None or not opp:
                continue
            line = {s: _num(g.get(_BOX_COL[s])) for s in STATS}
            allowed.setdefault(opp, []).append((gdate, line))
            league.append((gdate, line))
    return _OpponentDefense(allowed, league)


# Cross-stat ratio features. The 6 per-minute rates (pm_pts, pm_ast, ...)
# added in cycle 4 turned out to be ~95% collinear with the existing l5_*
# form features (l5_min varies less than the counting stats it normalises)
# and added a small net MAE drift; gradient-boosted trees can derive
# per-minute behaviour from interactions of l5_pts and l5_min directly.
# pts_share_3pt is the one ratio that carries genuinely new signal (3pt
# specialists vs balanced scorers), so it stays.
_RATIO_KEYS = (
    "pts_share_3pt",  # fraction of points from threes (3 * fg3m / pts)
)


_LONG_ABSENCE_DAYS = 7      # threshold for "returning from injury / extended absence"
_GAMES_SINCE_CAP   = 10     # cap the games-since-return counter so trees don't grow
                            # spurious splits on values that exist only on a few rows
_DAYS_SINCE_CAP    = 100.0  # cap days_since_last_game (offseason gaps blow up otherwise)


def _games_since_long_absence(prior_played: List[dict], current_gap_days: float) -> float:
    """Return the games-since-return-from-7+day-absence count for the upcoming game.

    Returns:
        0.0  — no long absence in the last _GAMES_SINCE_CAP prior games
        1.0  — the upcoming game IS the first game back (current_gap_days >= 7)
        N+1  — the upcoming game is N games past the last long absence found
               in prior_played (capped at _GAMES_SINCE_CAP).

    Scans only the most-recent _GAMES_SINCE_CAP prior games for efficiency
    and to avoid splitting on stale absences from earlier in the season.
    """
    if current_gap_days >= _LONG_ABSENCE_DAYS:
        return 1.0
    # Look back through prior_played for the last 7+ day gap between consecutive games.
    recent = prior_played[-_GAMES_SINCE_CAP:]
    if len(recent) < 2:
        return 0.0
    prev_date = None
    last_absence_idx = -1
    for i, g in enumerate(recent):
        gdate = _parse_date(g.get("GAME_DATE"))
        if prev_date is not None and gdate is not None:
            if (gdate - prev_date).days >= _LONG_ABSENCE_DAYS:
                last_absence_idx = i
        prev_date = gdate if gdate is not None else prev_date
    if last_absence_idx < 0:
        return 0.0
    # +2: the absence was BEFORE recent[last_absence_idx], so recent[last_absence_idx]
    # was game-1-back. The upcoming game is (len(recent) - last_absence_idx) games past
    # that, plus 1 because we count from 1.
    games_back = (len(recent) - last_absence_idx) + 1
    return float(min(games_back, _GAMES_SINCE_CAP))


def _row_features(prior_played: List[dict], rest_days: float,
                  is_home: int, games_played: int,
                  days_since_last_game: Optional[float] = None) -> Dict[str, float]:
    """Build the leakage-free feature row from a player's prior played games.

    `days_since_last_game` is the unclamped gap (in days) from the player's
    previous played game to the upcoming game. When omitted we fall back to
    `rest_days` (clamped 0-10), which loses long-absence signal — callers
    that have the real date delta should pass it.
    """
    feats: Dict[str, float] = {}
    for stat in _FORM_STATS:
        col = _BOX_COL[stat]
        vals = [_num(g.get(col)) for g in prior_played]
        feats[f"l5_{stat}"]   = _mean(vals[-5:])
        feats[f"l10_{stat}"]  = _mean(vals[-10:])
        feats[f"std_{stat}"]  = _mean(vals)              # season-to-date
        feats[f"ewma_{stat}"] = _ewma(vals)
        feats[f"prev_{stat}"] = vals[-1] if vals else 0.0
    feats["rest_days"]     = rest_days
    feats["is_home"]       = float(is_home)
    feats["games_played"]  = float(games_played)
    # Injury rampup signal — unclamped days-since-last-game lets trees
    # distinguish "1-day rest" (back-to-back) from "14-day rest" (back from
    # extended injury). games_since_long_absence captures which rampup
    # phase the player is in (1 = first game back, 2 = second, etc).
    raw_gap = float(rest_days) if days_since_last_game is None else float(days_since_last_game)
    feats["days_since_last_game"]      = min(raw_gap, _DAYS_SINCE_CAP)
    feats["games_since_long_absence"]  = _games_since_long_absence(prior_played, raw_gap)
    # 3-point share — fraction of recent points coming from threes (3 * fg3m / pts).
    # Denominator clipped at 5 so low-volume rows don't blow up the ratio.
    l5_pts_safe = max(feats["l5_pts"], 5.0)
    feats["pts_share_3pt"] = (3.0 * feats["l5_fg3m"]) / l5_pts_safe
    return feats


# ── dataset construction ──────────────────────────────────────────────────────

def build_pergame_dataset(
    gamelog_dir: Optional[str] = None,
    min_prior: int = 0,
) -> Tuple[List[dict], List[str]]:
    """Build the per-game training set from every player gamelog.

    Each emitted row holds leakage-free pre-game features and the realised
    target_{stat} values for one game.  A game is used as a row only when the
    player actually played (>= _MIN_PLAYED minutes) and has at least
    ``min_prior`` prior played games for stable rolling features.

    Returns:
        (rows, feature_cols) — rows are dicts with the feature columns,
        target_{stat} columns, and a 'date' key for the temporal split.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    feature_cols = feature_columns()
    rows: List[dict] = []

    # Leakage-free opponent-defence model, built from all gamelogs first.
    oppdef = build_opponent_defense(gamelog_dir)
    resttravel = build_rest_travel()
    playtypes = build_playtypes()
    bbref = build_bbref_advanced()
    contracts = build_contracts()
    adv_stats = build_advanced_stats()
    tracking  = build_player_tracking()
    officials = build_officials_crew()
    # Cycle 90d (loop 5) — REB OREB-context per-team prior rolling-5.
    reb_ctx = build_team_reb_context()
    # Cycle 90e (loop 5) — per-player position lookup. GATED on file
    # existence: empty wrapper when data/player_positions.parquet is
    # absent, so the join is a no-op on fresh checkouts. position is
    # added to each row dict (NOT to feature_columns yet — that requires
    # a separate retrain cycle). Probes (cycle 89c) can re-run once the
    # parquet is populated.
    positions = build_player_positions()

    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue

        # Sort chronologically; keep games with a parseable date.
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        # Parse player_id and season from filename: gamelog_<pid>_<season>.json
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            # parts[0]="gamelog", parts[1]=pid, parts[-1]="<season>.json"
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            file_player_id = 0
            file_season = ""

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED

            if played and len(prior_played) >= min_prior:
                rest = 3.0
                if idx > 0:
                    delta = (gdate - dated[idx - 1][0]).days
                    rest = float(min(max(delta, 0), 10))
                # Rampup gap: distance to last *played* game (DNPs that just sit
                # in the gamelog shouldn't reset the rampup counter). prior_played
                # is built only from games with MIN >= _MIN_PLAYED so [-1] is the
                # most recent real appearance — except when min_prior=0 and this
                # is the very first row for a player, in which case fall back to
                # the neutral 3-day gap.
                raw_gap_days = 3.0
                if prior_played:
                    last_played_date = _parse_date(prior_played[-1].get("GAME_DATE"))
                    if last_played_date is not None:
                        raw_gap_days = float(max((gdate - last_played_date).days, 0))
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                feats = _row_features(prior_played, rest, is_home, len(prior_played),
                                      days_since_last_game=raw_gap_days)
                feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
                feats.update(resttravel.features(team_abbrev, gdate))
                feats.update(playtypes.features(file_player_id, file_season))
                feats.update(bbref.features(file_player_id, file_season))
                feats.update(contracts.features(file_player_id, file_season))
                # Cycle 90d (loop 5) — REB OREB-context (team + opp rolling-5).
                # Stored on every row but only sliced into the REB head's feature
                # set via feature_columns(stat="reb"); other heads ignore them.
                feats.update(reb_ctx.features(
                    team_abbrev, _opponent_from_matchup(matchup), gdate))
                # officials.features + tracking.features + adv_stats.features
                # available but not appended to feature_cols — see comments above.
                row = {c: feats[c] for c in feature_cols}
                # Carry REB-context cols on every row even though they aren't in
                # the default feature_cols — the REB-only retraining path reads
                # them via feature_columns(stat="reb").
                for k in _REB_CONTEXT_KEYS:
                    row[k] = feats.get(k, 0.0)
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                # Cycle 90e (loop 5) — per-row position (additive only; not in
                # feature_cols). None when the parquet is absent or the pid
                # is uncached. Probes consume row["position"] directly.
                row["position"] = positions.position(file_player_id)
                rows.append(row)

            if played:
                prior_played.append(game)

    return rows, feature_cols


# ── training ──────────────────────────────────────────────────────────────────

def train_pergame_models(
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    *,
    min_prior: int = 0,
    holdout_frac: float = 0.2,
    val_frac: float = 0.15,
    stats: Optional[List[str]] = None,
    stat_params_override: Optional[Dict[str, dict]] = None,
    recency_decay: Optional[float] = None,
) -> dict:
    """Train one XGBoost regressor per stat on the per-game dataset.

    Three-way temporal split — train / validation / holdout, in chronological
    order. The validation slice drives early stopping (the model adds trees
    only while validation error keeps falling), which curbs overfitting
    without ever touching the holdout. The most recent ``holdout_frac`` of
    games is the honest out-of-sample test.

    Returns a metrics dict ``{stat: {train_r2, holdout_r2, train_mae,
    holdout_mae, gap, best_iteration}}`` and writes props_pg_{stat}.json.
    """
    import joblib
    import lightgbm as lgb
    import numpy as np
    import xgboost as xgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    model_dir = model_dir or _MODEL_DIR
    rows, feature_cols = build_pergame_dataset(gamelog_dir, min_prior=min_prior)
    if len(rows) < 200:
        return {"status": "insufficient_data", "n_rows": len(rows)}

    rows.sort(key=lambda r: r["date"])           # temporal order
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    X_all = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]

    # Recency-decay sample weights — older training rows count less.
    # Player skill distributions drift season-to-season (rule changes,
    # pace shifts, role changes); rows from 2022-23 are less representative
    # of 2025-26 prop distributions than rows from 2024-25. Weight is
    # exp(-_RECENCY_DECAY * age_years) where age_years is the gap between
    # the most recent training row's date and the row's own date. Holdout
    # and val are NOT weighted (they're frozen ground truth).
    decay = _RECENCY_DECAY if recency_decay is None else float(recency_decay)
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_train_date = max(train_dates)
    age_years = np.array([(max_train_date - d).days / 365.0 for d in train_dates], dtype=float)
    sample_w_tr = np.exp(-decay * age_years) if decay > 0 else None

    os.makedirs(model_dir, exist_ok=True)
    metrics: dict = {"n_rows": n, "n_train": train_end,
                     "n_val": val_end - train_end, "n_holdout": n - val_end,
                     "recency_decay": decay,
                     "stats": {}}

    # Per-stat regularisation overrides — the walk-forward report (PRED-02)
    # flagged STL with a train/holdout gap of 0.18 (> the 0.15 gate). STL is
    # the noisiest counting stat — mean ~0.7, no strong player-form signal —
    # so it needs tighter regularisation than the other counts. _STAT_PARAMS
    # below is the central knob: each key overrides the default for one stat.
    _DEFAULT_COUNT = {"max_depth": 3, "min_child_weight": 10, "reg_lambda": 2.0,
                      "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.04,
                      "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.5}
    _DEFAULT_REG   = {"max_depth": 4, "min_child_weight": 10, "reg_lambda": 2.0,
                      "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.04,
                      "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.5}
    _STAT_PARAMS: Dict[str, dict] = {
        # STL — high noise, low signal; aggressive regularisation, gap 0.058 → 0.011.
        # Cycle 25: lr 0.04 → 0.06. Cycle 26: subsample 0.8 → 0.9. Cycle 28:
        # reg_alpha 0.5 → 0.25 (small L1 prune helps the noisiest stat).
        "stl": {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
                "gamma": 0.6, "n_estimators": 400, "learning_rate": 0.06,
                "subsample": 0.9, "reg_alpha": 0.25},
        # BLK — low base rate (~0.5/game), bimodal across positions; tighten
        # depth + child weight to prevent splits on rare combinations.
        # Cycle 25: lr 0.04 → 0.06. Cycle 27: colsample_bytree 0.8 → 1.0.
        # Cycle 35: max_depth 2 → 3. Cycle 36: n_estimators 500 → 800
        # (depth-3 BLK was hitting the n_est cap before early stopping).
        "blk": {"max_depth": 3, "min_child_weight": 25, "reg_lambda": 4.0,
                "gamma": 0.4, "n_estimators": 800, "learning_rate": 0.06,
                "colsample_bytree": 1.0},
        # FG3M — re-tuned cycle 20: less regularisation now that we have
        # 93k rows. Cycle 25: lr 0.04 → 0.025. Cycle 26: subsample 0.8 → 0.7.
        # Cycle 29: gamma 0.3 → 0.0. Cycle 31: reg_lambda 2.0 → 8.0
        # (stronger L2 compensates for the gamma drop; FG3M now leans on
        # leaf-weight smoothing instead of split-loss thresholding).
        "fg3m": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 8.0,
                 "gamma": 0.0, "n_estimators": 600, "learning_rate": 0.025,
                 "subsample": 0.7},
        # PTS — re-tuned cycle 20 (93k rows, recency decay): one more depth
        # level + slightly tighter mcw/lambda. Cycle 25: lr 0.04 → 0.025.
        # Cycle 27: colsample_bytree 0.8 → 0.9. Cycle 28: reg_alpha 0.5 → 2.0
        # (deeper PTS trees overfit; stronger L1 prunes noisy splits).
        "pts": {"max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
                "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
                "colsample_bytree": 0.9, "reg_alpha": 2.0},
        # AST — re-tuned cycle 20 (93k rows, recency-decay active):
        # bumped depth 4 -> 5. Cycle 25: lr 0.04 → 0.025. Cycle 26:
        # subsample 0.8 → 0.7 (biggest MAE win of the subsample sweep, -0.15%).
        "ast": {"max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
                "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
                "subsample": 0.7},
        # REB — re-tuned cycle 12: tighter min_child_weight + more reg.
        # Cycle 25: lr 0.04 → 0.025. Cycle 26: subsample 0.8 → 0.7.
        # Cycle 27: colsample_bytree 0.8 → 0.9.
        "reb": {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 4.0,
                "gamma": 0.3, "n_estimators": 800, "learning_rate": 0.025,
                "subsample": 0.7, "colsample_bytree": 0.9},
        # TOV — count-ish (mean ~1.3/game); responds to count-style reg.
        # Cycle 25: lr 0.04 → 0.025.
        "tov": {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
                "gamma": 0.4, "n_estimators": 700, "learning_rate": 0.025},
    }

    # Allow callers (e.g. tuning sweeps) to restrict which stats are trained
    # and to override the per-stat hyperparameters without editing _STAT_PARAMS.
    stats_to_train = list(stats) if stats else list(STATS)
    effective_params = dict(_STAT_PARAMS)
    if stat_params_override:
        effective_params.update(stat_params_override)

    # Cycle 23 (loop 5) — train the multitask MLP ONCE on a (n_samples, len(STATS))
    # target matrix when any stat in stats_to_train belongs to _USE_MULTITASK_MLP_STATS.
    # Per-stat columns apply the same per-stat transform used downstream (sqrt for
    # PTS, log1p for the log1p stats, identity for the rest). The proxy that gets
    # persisted per multitask-stat holds the full ensemble + a stat_idx so
    # predict_pergame's single-column output is sliced correctly.
    multitask_proxy_for_stat: Dict[str, "_MultitaskMLPProxy"] = {}
    multitask_scaler = None
    if any(s in _USE_MULTITASK_MLP_STATS for s in stats_to_train):
        # Build the full target matrix for ALL stats (not just stats_to_train),
        # so cross-stat structure is preserved.
        Y_tr_mt = np.zeros((len(y_tr_check := np.array([r["target_pts"] for r in rows[:train_end]], dtype=float)),
                            len(STATS)), dtype=float)
        for i, s in enumerate(STATS):
            ys = np.array([r[f"target_{s}"] for r in rows[:train_end]], dtype=float)
            if s in _SQRT_HUBER_STATS:
                Y_tr_mt[:, i] = np.sqrt(ys)
            elif s in _LOG_TRANSFORM_STATS:
                Y_tr_mt[:, i] = np.log1p(ys)
            else:
                Y_tr_mt[:, i] = ys
        multitask_scaler = StandardScaler()
        Xs_tr_mt = multitask_scaler.fit_transform(X_tr)
        multitask_ensemble = _MultitaskMLPEnsemble().fit(Xs_tr_mt, Y_tr_mt)
        for s in stats_to_train:
            if s in _USE_MULTITASK_MLP_STATS:
                multitask_proxy_for_stat[s] = _MultitaskMLPProxy(
                    multitask_ensemble, STATS.index(s)
                )

    for stat in stats_to_train:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
        is_count = stat in ("stl", "blk")
        use_log   = stat in _LOG_TRANSFORM_STATS
        use_sqrt_huber = stat in _SQRT_HUBER_STATS

        # When log1p is on, all three learners train on log1p(y) and the
        # base-learner predictions are expm1'd before the NNLS stacker fits.
        # When sqrt+Huber is on (PTS only), the learners train on sqrt(y),
        # predictions are squared back, and XGB/LGB use Huber loss instead
        # of squared error. NNLS / calibration / persistence all sit on the
        # raw-count scale, identical to log1p stats.
        if use_log:
            y_tr_t, y_val_t = np.log1p(y_tr), np.log1p(y_val)
        elif use_sqrt_huber:
            y_tr_t, y_val_t = np.sqrt(y_tr), np.sqrt(y_val)
        else:
            y_tr_t, y_val_t = y_tr, y_val

        params = {**(_DEFAULT_COUNT if is_count else _DEFAULT_REG),
                  **effective_params.get(stat, {})}

        # Base learner 1 — XGBoost, regularised, early-stopped on the val slice.
        # Poisson objective only makes sense on raw counts; log1p / sqrt targets
        # use squared-error or Huber. The _HUBER_LOG_STATS set carries log1p
        # stats that want Huber instead of squared error on the log target.
        if use_sqrt_huber:
            xgb_obj = "reg:pseudohubererror"
        elif use_log:
            xgb_obj = ("reg:pseudohubererror"
                       if stat in _HUBER_LOG_STATS else "reg:squarederror")
        elif is_count:
            xgb_obj = "count:poisson"
        else:
            xgb_obj = "reg:squarederror"
        xgb_model = xgb.XGBRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=params.get("learning_rate", 0.04),
            subsample=params.get("subsample", 0.8),
            colsample_bytree=params.get("colsample_bytree", 0.8),
            min_child_weight=params["min_child_weight"], reg_lambda=params["reg_lambda"],
            reg_alpha=params.get("reg_alpha", 0.5),
            gamma=params["gamma"], random_state=42,
            objective=xgb_obj,
            early_stopping_rounds=40, eval_metric="mae",
        )
        xgb_model.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
                      sample_weight=sample_w_tr, verbose=False)

        # Base learner 2 — LightGBM, a different bias-variance tradeoff.
        if use_sqrt_huber:
            lgb_obj = "huber"
        elif use_log:
            lgb_obj = ("huber" if stat in _HUBER_LOG_STATS else "regression")
        elif is_count:
            lgb_obj = "poisson"
        else:
            lgb_obj = "regression"
        lgb_model = lgb.LGBMRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=params.get("learning_rate", 0.04),
            subsample=params.get("subsample", 0.8),
            subsample_freq=1,
            colsample_bytree=params.get("colsample_bytree", 0.8),
            min_child_samples=max(20, params["min_child_weight"] * 2),
            reg_lambda=params["reg_lambda"],
            reg_alpha=params.get("reg_alpha", 0.5), random_state=42,
            objective=lgb_obj,
            n_jobs=-1, verbosity=-1,
        )
        lgb_model.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
                      sample_weight=sample_w_tr,
                      callbacks=[lgb.early_stopping(40, verbose=False)])

        # Base learner 3 — MLP on standardised features. Different bias
        # (smooth function approximator) than the trees. Single-seed MLPs
        # vary by ~0.005-0.007 R² across seeds; cycle-11 (loop 5) verified
        # 5-seed averaging buys PTS solo R² 0.5107 -> 0.5134 (+0.0027) and
        # 3-way blend MAE -0.0033 vs the single seed. The wrapper persists
        # all 5 fitted models via joblib.
        #
        # Cycle 23: for stats in _USE_MULTITASK_MLP_STATS (currently {ast, stl})
        # we re-use the pre-trained multitask MLP via a thin proxy that selects
        # this stat's output column. The same scaler is shared (it was fit on
        # X_tr above in the multitask block). Independent MLP stays for every
        # other stat.
        if stat in _USE_MULTITASK_MLP_STATS and stat in multitask_proxy_for_stat:
            mlp_scaler = multitask_scaler
            X_tr_s  = mlp_scaler.transform(X_tr)
            X_val_s = mlp_scaler.transform(X_val)
            X_ho_s  = mlp_scaler.transform(X_ho)
            mlp_model = multitask_proxy_for_stat[stat]
        else:
            mlp_scaler = StandardScaler()
            X_tr_s  = mlp_scaler.fit_transform(X_tr)
            X_val_s = mlp_scaler.transform(X_val)
            X_ho_s  = mlp_scaler.transform(X_ho)
            mlp_model = _MLPSeedEnsemble().fit(X_tr_s, y_tr_t)

        # Blend = LGB only for stats in _LGB_ONLY_STATS, otherwise a
        # 3-way weighted combo of XGB + LGB + MLP fit per-stat on the val
        # slice via non-negative least squares. Falls back to the fixed
        # equal-mean when the val fit gives wildly skewed weights (sum
        # outside [0.5, 1.5]) — that usually means val and holdout
        # disagree and the fit doesn't generalise.
        lgb_only = stat in _LGB_ONLY_STATS

        # When log1p / sqrt is on, base learners output transformed-space
        # predictions; invert them back to raw-count scale before NNLS fits on
        # raw-y target. Also fixes calibration + persistence so
        # predict_pergame's saved models still need the inverse at inference
        # (see load_pergame_model / predict_pergame).
        def _inv(v):
            if use_log:
                return np.clip(np.expm1(v), 0.0, None)
            if use_sqrt_huber:
                return np.clip(v, 0.0, None) ** 2
            return v

        xgb_ho = _inv(xgb_model.predict(X_ho))
        lgb_ho = _inv(lgb_model.predict(X_ho))
        mlp_ho = _inv(mlp_model.predict(X_ho_s))

        if lgb_only:
            w_xgb, w_lgb, w_mlp = 0.0, 1.0, 0.0
            meta_fit_source = "lgb_only"
        else:
            xgb_val = _inv(xgb_model.predict(X_val))
            lgb_val = _inv(lgb_model.predict(X_val))
            mlp_val = _inv(mlp_model.predict(X_val_s))
            from sklearn.linear_model import LinearRegression
            stacker = LinearRegression(positive=True, fit_intercept=False)
            stacker.fit(np.column_stack([xgb_val, lgb_val, mlp_val]), y_val)
            w_xgb, w_lgb, w_mlp = (float(stacker.coef_[0]),
                                   float(stacker.coef_[1]),
                                   float(stacker.coef_[2]))
            w_sum = w_xgb + w_lgb + w_mlp
            if not (0.5 <= w_sum <= 1.5):
                w_xgb, w_lgb, w_mlp = 1/3, 1/3, 1/3
                meta_fit_source = "fallback_third"
            else:
                meta_fit_source = "val_nnls_3way"

        def _blend(X, Xs):
            if lgb_only:
                return _inv(lgb_model.predict(X))
            return (w_xgb * _inv(xgb_model.predict(X))
                    + w_lgb * _inv(lgb_model.predict(X))
                    + w_mlp * _inv(mlp_model.predict(Xs)))

        blend_ho = (lgb_ho if lgb_only
                    else w_xgb * xgb_ho + w_lgb * lgb_ho + w_mlp * mlp_ho)
        blend_tr = _blend(X_tr, X_tr_s)

        # Isotonic calibration — k-fold cross-fitted on the holdout.
        #
        # We can't fit on val because val is what early-stopping used (the
        # base learners are already slightly optimistic there), and we can't
        # fit-and-evaluate on holdout directly (self-leak). 5-fold CV gives
        # honest cross-fitted predictions for the lift measurement, and we
        # then refit on the full holdout for the deployed calibrator. This
        # is opt-in per stat: if the cross-fitted lift on MAE is not strictly
        # positive, we delete any prior calibrator so predict_pergame falls
        # back to the raw blend (calibration helps low-rate stats like BLK
        # but is noise on already-unbiased high-volume stats like PTS).
        n_ho = len(blend_ho)
        k = 5
        cal_blend_ho = np.empty(n_ho, dtype=float)
        rng = np.random.default_rng(42)
        perm = rng.permutation(n_ho)
        fold_size = n_ho // k
        for fold in range(k):
            lo = fold * fold_size
            hi = n_ho if fold == k - 1 else (fold + 1) * fold_size
            test_idx = perm[lo:hi]
            train_idx = np.concatenate([perm[:lo], perm[hi:]])
            fold_cal = IsotonicRegression(out_of_bounds="clip")
            fold_cal.fit(blend_ho[train_idx], y_ho[train_idx])
            cal_blend_ho[test_idx] = fold_cal.predict(blend_ho[test_idx])
        cal_blend_ho = np.clip(cal_blend_ho, 0.0, None)

        uncal_r2  = float(r2_score(y_ho, blend_ho))
        uncal_mae = float(mean_absolute_error(y_ho, blend_ho))
        cal_r2    = float(r2_score(y_ho, cal_blend_ho))
        cal_mae   = float(mean_absolute_error(y_ho, cal_blend_ho))

        # Opt-in: only deploy the calibrator if it strictly improves MAE on
        # the cross-fitted holdout predictions. Otherwise remove any stale
        # file so predict_pergame falls back to the raw blend.
        cal_path = os.path.join(model_dir, f"calibration_pergame_{stat}.joblib")
        if cal_mae < uncal_mae:
            full_cal = IsotonicRegression(out_of_bounds="clip")
            full_cal.fit(blend_ho, y_ho)
            joblib.dump(full_cal, cal_path)
            served_r2, served_mae = cal_r2, cal_mae
            cal_used = True
        else:
            if os.path.exists(cal_path):
                os.remove(cal_path)
            served_r2, served_mae = uncal_r2, uncal_mae
            cal_used = False

        m = {
            # Production-served metrics — match what predict_pergame returns.
            "holdout_r2":      round(served_r2, 4),
            "holdout_mae":     round(served_mae, 4),
            "train_r2":        round(float(r2_score(y_tr, blend_tr)), 4),
            "xgb_holdout_r2":  round(float(r2_score(y_ho, xgb_ho)), 4),
            "lgb_holdout_r2":  round(float(r2_score(y_ho, lgb_ho)), 4),
            "mlp_holdout_r2":  round(float(r2_score(y_ho, mlp_ho)), 4),
            # Diagnostics — pre-calibration blend and the cross-fitted lift.
            "uncal_holdout_r2":  round(uncal_r2, 4),
            "uncal_holdout_mae": round(uncal_mae, 4),
            "calibration_lift_r2":  round(cal_r2 - uncal_r2, 4),
            "calibration_lift_mae": round(uncal_mae - cal_mae, 4),
            "calibration_used":  cal_used,
            # Meta-stacker weights — what predict_pergame applies to the
            # XGB + LGB + MLP base learner outputs before calibration.
            "meta_w_xgb":     round(w_xgb, 4),
            "meta_w_lgb":     round(w_lgb, 4),
            "meta_w_mlp":     round(w_mlp, 4),
            "meta_fit_source": meta_fit_source,
        }
        m["gap"] = round(m["train_r2"] - m["holdout_r2"], 4)
        m["ensemble_lift"] = round(m["holdout_r2"] - max(m["xgb_holdout_r2"],
                                                         m["lgb_holdout_r2"],
                                                         m["mlp_holdout_r2"]), 4)
        metrics["stats"][stat] = m
        # For stats listed in _LGB_ONLY_STATS the XGB Poisson learner drags
        # the blend (ensemble_lift is negative). Save only LGB so that
        # predict_pergame's load_pergame_model picks up just the LGB model
        # and the "blend" becomes a single-model prediction.
        xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
        if stat in _LGB_ONLY_STATS:
            if os.path.exists(xgb_path):
                os.remove(xgb_path)
        else:
            xgb_model.save_model(xgb_path)
        joblib.dump(lgb_model, os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl"))
        # Persist MLP + its scaler. Skip when NNLS picks ~0 weight for MLP
        # (no point keeping a learner the meta-stacker ignores).
        mlp_path = os.path.join(model_dir, f"props_pg_mlp_{stat}.pkl")
        mlp_scaler_path = os.path.join(model_dir, f"props_pg_mlp_scaler_{stat}.pkl")
        if w_mlp >= 0.05 and not lgb_only:
            joblib.dump(mlp_model, mlp_path)
            joblib.dump(mlp_scaler, mlp_scaler_path)
        else:
            for p in (mlp_path, mlp_scaler_path):
                if os.path.exists(p):
                    os.remove(p)
        cal_tag = "cal" if cal_used else "raw"
        print(f"  [prop_pergame] {stat.upper():4s} {cal_tag} R²={m['holdout_r2']:.3f} "
              f"MAE={m['holdout_mae']:.2f}  (xgb={m['xgb_holdout_r2']:.3f}, "
              f"lgb={m['lgb_holdout_r2']:.3f}, mlp={m['mlp_holdout_r2']:.3f}, "
              f"lift={m['ensemble_lift']:+.3f}, "
              f"w=[{w_xgb:.2f}/{w_lgb:.2f}/{w_mlp:.2f}], "
              f"cal_lift_mae={m['calibration_lift_mae']:+.3f})")

    metrics["feature_cols"] = feature_cols
    # Only persist metrics when this was a full train — partial trains (e.g.
    # tuning sweeps) would clobber the per-stat metrics for stats they didn't
    # touch.
    if set(stats_to_train) == set(STATS):
        with open(os.path.join(model_dir, "props_pergame_metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    # Meta-stacker weights sidecar — written even on partial trains so the
    # weights for the trained stats stay in sync with their on-disk models.
    _persist_meta_weights(model_dir, metrics)
    return metrics


_META_WEIGHTS_FILENAME = "meta_weights_pergame.json"


def _persist_meta_weights(model_dir: str, metrics: dict) -> None:
    """Merge this train run's meta-stacker weights into the sidecar JSON.

    The sidecar keeps a single weights dict keyed by stat so predict_pergame
    can apply them without parsing the full metrics report each call."""
    path = os.path.join(model_dir, _META_WEIGHTS_FILENAME)
    existing: Dict[str, dict] = {}
    if os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8"))
        except Exception:
            existing = {}
    for stat, m in metrics.get("stats", {}).items():
        if "meta_w_xgb" in m and "meta_w_lgb" in m:
            entry = {
                "w_xgb": float(m["meta_w_xgb"]),
                "w_lgb": float(m["meta_w_lgb"]),
                "source": m.get("meta_fit_source", "unknown"),
            }
            if "meta_w_mlp" in m:
                entry["w_mlp"] = float(m["meta_w_mlp"])
            existing[stat] = entry
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


# ── inference ─────────────────────────────────────────────────────────────────

def load_pergame_model(stat: str, model_dir: Optional[str] = None) -> list:
    """Load the per-game base learners (XGBoost + LightGBM + MLP) for a stat.

    Returns a list of fitted models — empty when none are trained. The MLP
    entry, when present, is a tuple (scaler, model) since the MLP needs
    standardised input — the rest receive raw X. predict_pergame disambiguates
    by class name / tuple shape.
    """
    model_dir = model_dir or _MODEL_DIR
    models: list = []
    xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
    if os.path.exists(xgb_path):
        try:
            import xgboost as xgb
            m = xgb.XGBRegressor()
            m.load_model(xgb_path)
            models.append(m)
        except Exception:
            pass
    lgb_path = os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl")
    if os.path.exists(lgb_path):
        try:
            import joblib
            models.append(joblib.load(lgb_path))
        except Exception:
            pass
    mlp_path = os.path.join(model_dir, f"props_pg_mlp_{stat}.pkl")
    mlp_scaler_path = os.path.join(model_dir, f"props_pg_mlp_scaler_{stat}.pkl")
    if os.path.exists(mlp_path) and os.path.exists(mlp_scaler_path):
        try:
            import joblib
            models.append((joblib.load(mlp_scaler_path), joblib.load(mlp_path)))
        except Exception:
            pass
    return models


def _load_pergame_calibrator(stat: str, model_dir: str):
    """Load the per-game isotonic calibrator for a stat, or None if absent."""
    path = os.path.join(model_dir, f"calibration_pergame_{stat}.joblib")
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        return None


_META_WEIGHTS_CACHE: Optional[Dict[str, dict]] = None


def _load_q50_model(stat: str, model_dir: str):
    """Load the cycle-27 q=0.5 quantile model for `stat`, or None on miss.

    Persisted by src.prediction.prop_quantiles.train_quantile_models at
    data/models/quantile_pergame_<stat>_q50.json (XGB) and
    quantile_pergame_lgb_<stat>_q50.pkl (LGB). Same per-stat target
    transform as the rest of the prop_pergame stack.

    Stats in _Q50_LGB_BACKEND_STATS use the LGB variant (cycle 29: REB
    only). All others use XGB (cycle 27: fg3m, stl, blk, tov).
    """
    if stat in _Q50_LGB_BACKEND_STATS:
        path = os.path.join(model_dir, f"quantile_pergame_lgb_{stat}_q50.pkl")
        if not os.path.exists(path):
            return None
        try:
            import joblib  # noqa: PLC0415
            return joblib.load(path)
        except Exception:
            return None
    # Default: XGB backend.
    path = os.path.join(model_dir, f"quantile_pergame_{stat}_q50.json")
    if not os.path.exists(path):
        return None
    try:
        import xgboost as xgb  # noqa: PLC0415
        m = xgb.XGBRegressor()
        m.load_model(path)
        return m
    except Exception:
        return None


def _get_pergame_meta_weights(model_dir: str) -> Dict[str, dict]:
    """Return the per-stat meta-stacker weights dict (process-cached)."""
    global _META_WEIGHTS_CACHE
    if _META_WEIGHTS_CACHE is not None:
        return _META_WEIGHTS_CACHE
    path = os.path.join(model_dir, _META_WEIGHTS_FILENAME)
    if not os.path.exists(path):
        _META_WEIGHTS_CACHE = {}
        return _META_WEIGHTS_CACHE
    try:
        _META_WEIGHTS_CACHE = json.load(open(path, encoding="utf-8"))
    except Exception:
        _META_WEIGHTS_CACHE = {}
    return _META_WEIGHTS_CACHE


def predict_pergame(stat: str, feature_row: Dict[str, float],
                    model_dir: Optional[str] = None) -> Optional[float]:
    """Predict one stat for one game — q50 dispatch or calibrated meta-blend.

    Cycle 27: for stats in _USE_Q50_STATS the quantile-median model is the
    sole predictor (walk-forward 4/4 folds positive, MAE wins -0.7% on AST
    up to -16.6% on BLK). For all other stats this returns the per-stat
    meta-stacker weighted blend (cycle 23 multitask MLP for AST/STL keys
    are no-ops since AST/STL are in _USE_Q50_STATS now — kept around for
    rollback safety). The isotonic calibrator
    (calibration_pergame_<stat>.joblib) is applied at the end when present
    AND when the stat uses the blend (not q50)."""
    import numpy as np

    model_dir = model_dir or _MODEL_DIR

    # Cycle 27 q50 dispatch — bypasses the entire 3-way blend.
    if stat in _USE_Q50_STATS:
        q50 = _load_q50_model(stat, model_dir)
        if q50 is not None:
            # Cycle 90d (REJECTED): REB OREB-context probe rejected (single
            # +0.0013, WF 1/4 positive). REB stays on the 85-col cycle-29
            # LGB-q50 artifact, so we dispatch with the global feature_columns()
            # for all q50 stats. If a future cycle ships a wider REB head,
            # switch this line to `feature_columns(stat=stat)`.
            cols = feature_columns()
            if getattr(q50, "n_features_in_", None) not in (None, len(cols)):
                return None
            X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
            pred_t = float(q50.predict(X)[0])
            # Inverse-transform back to raw-count scale (same as training inv).
            if stat in _SQRT_HUBER_STATS:
                return round(max(0.0, pred_t) ** 2, 2)
            if stat in _LOG_TRANSFORM_STATS:
                return round(max(0.0, float(np.expm1(pred_t))), 2)
            return round(max(0.0, pred_t), 2)
        # q50 model missing on disk — fall through to the legacy blend so
        # predict_pergame still returns SOMETHING.

    models = load_pergame_model(stat, model_dir)
    if not models:
        return None
    cols = feature_columns()
    expected_n = len(cols)
    # Guard: stale model trained on a different feature set — refuse to predict.
    for m in models:
        target = m[1] if isinstance(m, tuple) else m  # MLP entries are (scaler, model)
        n_feats = getattr(target, "n_features_in_", None)
        if n_feats is not None and n_feats != expected_n:
            return None
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)

    # When the stat was trained with log1p or sqrt target, each base learner
    # outputs transformed-space predictions; invert them back to raw-count
    # scale before NNLS weighting (matches training-time inversion).
    use_log = stat in _LOG_TRANSFORM_STATS
    use_sqrt_huber = stat in _SQRT_HUBER_STATS
    def _inv_pred(v: float) -> float:
        if use_log:
            return max(0.0, float(np.expm1(v)))
        if use_sqrt_huber:
            return max(0.0, float(v)) ** 2
        return v

    # load_pergame_model returns [XGB, LGB, (scaler, MLP)] when all are present,
    # or a subset (e.g. [LGB] for _LGB_ONLY_STATS, [XGB, LGB] when MLP weight
    # was below the keep threshold). Disambiguate by class/tuple shape.
    weights = _get_pergame_meta_weights(model_dir).get(stat)
    blend = 0.0
    if weights:
        xgb_pred = lgb_pred = mlp_pred = None
        for m in models:
            if isinstance(m, tuple):
                scaler, mlp_model = m
                if mlp_pred is None:
                    mlp_pred = _inv_pred(float(mlp_model.predict(scaler.transform(X))[0]))
                continue
            cls = type(m).__name__.lower()
            if "xgb" in cls and xgb_pred is None:
                xgb_pred = _inv_pred(float(m.predict(X)[0]))
            elif "lgb" in cls and lgb_pred is None:
                lgb_pred = _inv_pred(float(m.predict(X)[0]))
        w_xgb = float(weights.get("w_xgb", 0.0))
        w_lgb = float(weights.get("w_lgb", 0.0))
        w_mlp = float(weights.get("w_mlp", 0.0))
        parts: List[float] = []
        if xgb_pred is not None: parts.append(w_xgb * xgb_pred)
        if lgb_pred is not None: parts.append(w_lgb * lgb_pred)
        if mlp_pred is not None: parts.append(w_mlp * mlp_pred)
        if parts:
            blend = sum(parts)
        else:
            blend = 0.0
    else:
        # No weights file — mean of whatever predict surfaces (MLP entries
        # need scaling first).
        preds = []
        for m in models:
            if isinstance(m, tuple):
                scaler, mlp_model = m
                preds.append(_inv_pred(float(mlp_model.predict(scaler.transform(X))[0])))
            else:
                preds.append(_inv_pred(float(m.predict(X)[0])))
        blend = sum(preds) / len(preds) if preds else 0.0

    calibrator = _load_pergame_calibrator(stat, model_dir)
    if calibrator is not None:
        try:
            blend = float(calibrator.predict([blend])[0])
        except Exception:
            pass
    return round(max(blend, 0.0), 2)


# ── live prediction ───────────────────────────────────────────────────────────

# Process-level cache — building the opponent-defence model globs every
# gamelog, so it must not be rebuilt on every predict_props() call.
_OPP_DEF_CACHE: Dict[str, _OpponentDefense] = {}


def _get_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Return the (process-cached) opponent-defence model for a gamelog dir."""
    if gamelog_dir not in _OPP_DEF_CACHE:
        _OPP_DEF_CACHE[gamelog_dir] = build_opponent_defense(gamelog_dir)
    return _OPP_DEF_CACHE[gamelog_dir]


def build_prediction_row(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    min_prior: int = 0,
) -> Optional[Dict[str, float]]:
    """Build the per-game feature row for a player's UPCOMING game.

    Reads the player's season gamelog, treats every played game as prior
    form, and assembles the same feature row the models were trained on.
    Returns None when the gamelog is missing or the player has too little
    history — the caller then falls back to the legacy models.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(games, list):
        return None

    dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
    dated.sort(key=lambda x: x[0])
    prior_played = [g for _d, g in dated if _num(g.get("MIN")) >= _MIN_PLAYED]
    if len(prior_played) < min_prior:
        return None

    feats = _row_features(prior_played, float(rest_days), int(is_home),
                          len(prior_played))
    factor_date = dated[-1][0] if dated else datetime.now()
    feats.update(_get_opponent_defense(gamelog_dir).factors(opp_team, factor_date))
    # Rest/travel: use neutral defaults for future games (no parquet row yet).
    feats.update(_REST_TRAVEL_DEFAULTS)
    # Play-type frequencies: process-cached, zero defaults when parquet absent.
    try:
        feats.update(_get_playtypes().features(int(player_id), season))
    except Exception:
        feats.update(_PLAYTYPE_DEFAULTS)
    # BBRef advanced efficiency / rate stats: process-cached.
    try:
        feats.update(_get_bbref().features(int(player_id), season))
    except Exception:
        feats.update(_BBREF_DEFAULTS)
    # Contract features (salary, contract-year, role stability) — process-cached.
    try:
        feats.update(_get_contracts().features(int(player_id), season))
    except Exception:
        feats.update(_CONTRACT_DEFAULTS)
    # Cycle 90d — REB OREB-context. Derive team_abbrev from the player's most
    # recent game; opp_team is the caller-provided opponent. Neutral defaults
    # if the parquet/lookup misses.
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        team_abbrev = last_matchup.split()[0] if last_matchup.split() else ""
        feats.update(_get_team_reb_context().features(
            team_abbrev, opp_team, factor_date))
    except Exception:
        feats.update(_REB_CONTEXT_DEFAULTS)
    return feats


def predict_player_pergame(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Predict all 7 prop stats for a player's upcoming game.

    Returns ``{stat: value}`` from the honest per-game models, or None when
    the per-game models or the player's gamelog are unavailable.
    """
    row = build_prediction_row(player_id, opp_team, season, is_home=is_home,
                               rest_days=rest_days, gamelog_dir=gamelog_dir)
    if row is None:
        return None
    out: Dict[str, float] = {}
    for stat in STATS:
        val = predict_pergame(stat, row, model_dir)
        if val is None:
            return None
        out[stat] = val
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Per-game prop models")
    ap.add_argument("--train", action="store_true", help="Build dataset + train all stats")
    args = ap.parse_args()
    if args.train:
        print(json.dumps(train_pergame_models(), indent=2))
    else:
        ap.print_help()
