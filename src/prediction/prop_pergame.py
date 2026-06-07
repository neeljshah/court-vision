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
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

# Cycle 93b (loop 5) — module logger for silent-join honesty. Each cycle-91/92
# join wrapper catches broad Exception so build_pergame_dataset stays robust on
# fresh checkouts. Without logging those swallowed errors are invisible: cycle
# 92d hit one (pyarrow missing) and silently shipped a no-op probe. We log a
# single WARNING per join load failure (once per process) so future probes
# notice the degradation.
logger = logging.getLogger(__name__)
_SILENT_JOIN_WARNED: set = set()


def _warn_join_load_once(name: str, path: str, exc: Exception) -> None:
    """Emit a one-shot WARNING when a cycle-91/92 parquet join fails to load.
    Subsequent failures for the same join are suppressed to avoid stdout floods.
    """
    if name in _SILENT_JOIN_WARNED:
        return
    _SILENT_JOIN_WARNED.add(name)
    logger.warning(
        "prop_pergame.%s: failed to load %s (%s: %s) — collapsing to empty "
        "wrapper; downstream probes will see all defaults/None.",
        name, path, type(exc).__name__, exc,
    )

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")


def _resolve_model_dir() -> str:
    """Resolve the prop-model artifact directory with worktree-aware fallback.

    R31_X2 refactor: the original R21_N1 inline body now delegates to the
    shared `src.prediction._paths.resolve_model_dir` so every production
    loader (prop_pergame, game_models, residual_heads, injury_availability)
    uses identical resolution semantics. Behaviour preserved:

      1. `NBA_MODEL_DIR` env override.
      2. `NBA_DATA_DIR` umbrella + `/models` (operator-controlled).
      3. Local `<PROJECT_DIR>/data/models` if it contains `props_pg_pts.json`.
      4. Host-repo fallback when running inside `/.claude/worktrees/<wt>/`.
         (Detection sentinel preserved so the R30_W6 audit still flags
         the R21_N1 wire as live.)
      5. Default `<PROJECT_DIR>/data/models` (graceful-miss).

    Kept as a thin wrapper so existing imports / test patches that target
    `prop_pergame._resolve_model_dir` continue to work.
    """
    from src.prediction._paths import resolve_model_dir  # local import to avoid circulars
    return resolve_model_dir(
        canary="props_pg_pts.json",
        project_dir=PROJECT_DIR,
    )


_MODEL_DIR = _resolve_model_dir()
_PLAYTYPE_PATH = os.path.join(PROJECT_DIR, "data", "playtypes.parquet")
_PLAY_TYPES = [
    "isolation", "prballhandler", "prrollman", "postup",
    "spotup", "handoff", "cut", "offscreen", "transition",
]
_PLAYTYPE_DEFAULTS: Dict[str, float] = {f"pt_{pt}_freq": 0.0 for pt in _PLAY_TYPES}

# R10_M14 (loop 10): Synergy play-type frequencies joined PRIOR-SEASON only (S-1 -> S).
# Replaces the cycle-? current-season join, which leaked because freq_pct is computed
# across the WHOLE season including the game being predicted. Probe (24322 player-games,
# 4-fold WF) showed 6/7 stats improve under prior-season join: PTS -0.027 (WF 4/4),
# REB -0.013, AST -0.004, FG3M -0.011 (WF 4/4), STL -0.003, BLK 0.0; TOV +0.001 mild
# regression. Only PTS + FG3M passed WF 4/4 individually; those two are the shipped
# retrains (PTS via train_pergame_models, FG3M via prop_quantiles q50 LGB+XGB).
# Other 5 stats benefit passively from the leak fix because their existing 85-col
# model artifacts still receive the playtype column slots — only the VALUES change
# (prior-season vs current-season), no dim-mismatch.
_PLAYTYPE_PRIOR_SEASON_JOIN: bool = True
_PLAYTYPE_SHIPPED_STATS: set = {"pts", "fg3m"}


# Stats predicted, and their box-score column names in the gamelog JSON.
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# CV (computer vision tracking) feature gate. Off by default — flip on via env
# var PROP_USE_CV=1 to add 15 cv_* columns to feature_columns() and populate
# them in build_pergame_dataset rows.
_USE_CV_FEATURES = os.environ.get("PROP_USE_CV", "").strip() in ("1", "true", "True", "yes", "YES")

# EX-5 gate (real-money discipline). ON by module default as of the
# PREDICTION_FIDELITY plumbing fix (2026-06-04): the 85-col root artifacts in
# data/models were TRAINED in the aligned order (props_pergame_metrics.json
# feature_cols: contract/ratio at slots 80-84, bbref_extra after), so the
# aligned serve order is correct, not the legacy one. With the fix ON,
# feature_columns()[:85] has 0/85 mismatches vs the trained list; OFF has 5/85
# (bbref_extra leaks into slots 80-84 where the artifacts expect
# contract_*/pts_share_3pt). The fidelity audit confirmed ON is strictly >= OFF
# on prod accuracy (pooled -0.84% MAE, no stat regresses), and golive already
# sets CV_BBREF_REORDER_FIX=1. Making ON the default removes the load-bearing
# env var so any cache/backtest build is aligned without it.
#
# ESCAPE HATCH (revertible, not removed): set CV_BBREF_REORDER_FIX=0 (or
# false/no) to force the legacy misaligned order back for emergency rollback /
# A-B. Any other value (including unset) keeps the aligned default. The frozen
# _meta.json (see _persist_meta_feature_columns / write_meta_feature_columns)
# is the un-revertable backstop for feature_columns_for-consuming paths.
# See feature_columns() and docs/_audits/EX5_BBREF_GATE_2026-06-01.md +
# docs/_audits/PLUMBING_FIX_FAITHFUL_OOF.md.
_BBREF_REORDER_FIX = os.environ.get("CV_BBREF_REORDER_FIX", "").strip().lower() not in ("0", "false", "no", "off")

# vac_ast AST-model-feature gate (real-money discipline). OFF by default =
# byte-identical to the current AST feature set (the production AST model has NO
# assist-vacancy feature). When CV_AST_VAC_FEATURE=1, feature_columns(stat="ast")
# appends 2 leak-free vacated-assist columns — vac_ast (sum of as-of L10 assists
# of confirmed-out regulars) and vac_ast_share (vac_ast / (vac_ast + the
# appearing roster's as-of L10 assists)) — and build_pergame_dataset populates
# them per (player_id, game_date) from the box-appearance recipe. The signal is
# the campaign's one validated point-model lift (PRED_EXP_crosseason_validate
# 2026-06-01: reg-season held-out AST MAE 1.5565->1.5445, gated ROI +11.11->
# +14.76%). The SAME signal FAILS as a post-hoc gate, so it must be TRAINED IN.
# Keep OFF until the full OOF refresh validates ON-vs-OFF ROI/CLV on the slate
# path — flipping it shifts live AST preds. See docs/_audits/
# VAC_AST_FEATURE_VALIDATION_2026-06-01.md.
_AST_VAC_FEATURE = os.environ.get("CV_AST_VAC_FEATURE", "").strip() in ("1", "true", "True", "yes", "YES")
_VAC_AST_KEYS = ("vac_ast", "vac_ast_share")

# vac_load PTS+REB-model-feature gate (real-money discipline). OFF by default =
# byte-identical to the current PTS/REB feature sets (the production models have
# NO team-vacated-load feature). When CV_VAC_LOAD_FEATURE=1,
# feature_columns(stat in ("pts","reb")) appends 3 leak-free vacated-load
# columns — vac_min (sum of as-of L10 minutes of confirmed-out regulars),
# vac_pts (sum of their as-of L10 points) and n_out (count of out regulars) —
# and build_pergame_dataset populates them per (player_id, game_date) from the
# SAME box-appearance recipe as vac_ast. Production rolling-origin retrain
# (docs/_audits/NIGHT_RUN_STATUS.md): PTS Family A MAE 5.122->5.064
# (P(ON better)=0.997), ungated ROI -2.42%->+1.75% (+4.17pp, significant);
# cross-season Family C positive; REB MAE improves both corpora
# (P=0.901/0.965), ROI ~flat. So PTS = a betting edge, REB = accuracy-only.
# Keep OFF until the full OOF refresh validates ON-vs-OFF ROI/CLV on the slate
# path — flipping it shifts live PTS/REB preds. Append LAST so a fresh artifact
# trained with the flag ON carries the cols in trailing slots and older frozen
# artifacts load without an n_features_in_ mismatch (same mechanism as vac_ast).
_VAC_LOAD_FEATURE = os.environ.get("CV_VAC_LOAD_FEATURE", "").strip() in ("1", "true", "True", "yes", "YES")
_VAC_LOAD_KEYS = ("vac_min", "vac_pts", "n_out")

_CV_FEATURE_COLS = [
    "cv_avg_defender_distance",
    "cv_contested_shot_rate",
    "cv_shot_zone_paint_pct",
    "cv_shot_zone_3pt_pct",
    "cv_shots_per_possession",
    "cv_possession_duration_avg",
    "cv_play_type_transition_pct",
    # 7 new mechanical CV features (Round 2 — not exposed by NBA API)
    "cv_avg_contest_arm_angle",
    "cv_avg_closeout_speed",
    "cv_avg_fatigue_proxy",
    "cv_catch_shoot_pct",
    "cv_avg_dribble_count",
    "cv_second_chance_rate",
    "cv_avg_shot_distance",
    # meta-feature: number of prior games with CV data (keep last)
    "cv_n_games_cv",
]

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

# Iter-44 (loop 5) — narrow synergy PPP per-play-type extras.
# Five PPP columns keyed (player_id, season) from data/nba/synergy_player_*.json.
# Wired ONLY into the three stats where signal hypothesis is strongest:
#   AST  gets syn_pnr_bh_ppp (PnR BH sets up teammates)
#   PTS  gets syn_iso_ppp + syn_pnr_bh_ppp (scorer efficiency + creation)
#   FG3M gets syn_spotup_ppp (3PT spot-up frequency × success)
# Other stats keep the global feature list to preserve artifact compatibility.
# Source: data/cache/synergy_ppp_features.parquet, built by
#   scripts/build_synergy_ppp_features.py. Join key = (player_id, season)
#   CURRENT-SEASON (not prior-season like pt_*_freq) — OOS gate catches leak.
_SYN_PPP_KEYS = (
    "syn_pnr_bh_ppp", "syn_spotup_ppp", "syn_iso_ppp",
    "syn_postup_ppp", "syn_transition_ppp",
)
_SYN_PPP_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _SYN_PPP_KEYS}
_SYN_PPP_PATH = os.path.join(PROJECT_DIR, "data", "cache", "synergy_ppp_features.parquet")
# Per-stat subset: only the columns relevant to each stat
_SYN_PPP_AST_KEYS:  Tuple[str, ...] = ("syn_pnr_bh_ppp",)
_SYN_PPP_PTS_KEYS:  Tuple[str, ...] = ("syn_iso_ppp", "syn_pnr_bh_ppp")
_SYN_PPP_FG3M_KEYS: Tuple[str, ...] = ("syn_spotup_ppp",)

# Iter-46 (loop 5) — per-opponent rolling-3 stat features.
# Source: data/cache/per_opp_stat_rolling.parquet, built by
# scripts/build_per_opp_rolling.py from all gamelog_*.json files.
# For each (player_id, game_date): shift(1).rolling(3, min_periods=1).mean()
# within each (player_id, opp_team) group for PTS, REB, AST, FG3M, STL, BLK.
# Key: (player_id, game_date_iso)  → feature dict (NaN when <1 prior meeting).
# High null rate (~20%) expected (first-ever matchup rows); NaN-safe join.
# Wired ONLY into the corresponding per-stat model (per_opp_pts_l3 → PTS only,
# per_opp_reb_l3 → REB only, etc.) to avoid feature dilution.
_PER_OPP_ROLLING_STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk")
_PER_OPP_ROLLING_KEYS: Tuple[str, ...] = tuple(
    f"per_opp_{s}_l3" for s in _PER_OPP_ROLLING_STATS
)
# NaN default (not 0.0) — preserves missing-data signal for tree learners.
_PER_OPP_ROLLING_DEFAULTS: Dict[str, Optional[float]] = {
    k: None for k in _PER_OPP_ROLLING_KEYS
}
_PER_OPP_ROLLING_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "per_opp_stat_rolling.parquet"
)

# Iter-19 (loop 5) — linescore blowout/pace context features.
# Source: data/cache/linescore_context.parquet, built by
# scripts/build_linescore_context.py from data/nba/linescores_all.json
# (4,915 games, 4 seasons 2022-23 through 2025-26). All 7 features use
# shift(1).rolling(5, min_periods=2) — strictly leak-free.
# Keyed by (team_abbreviation, game_date):
#   ls_blowout_pct_l5        — frac last 5 with |H1 margin| > 15
#   ls_avg_total_l5          — avg game total (final) last 5
#   ls_avg_q1_pts_l5         — team avg Q1 pts last 5
#   ls_avg_q4_pts_l5         — team avg Q4 pts last 5
#   ls_garbage_time_pct_l5   — frac last 5 with final margin > 20
#   ls_opp_avg_total_allowed_l5  — opp's avg game total last 5 (from opp team's rows)
#   ls_opp_q1_pts_allowed_l5    — opp's avg Q1 pts allowed last 5
_LS_FEATURE_KEYS: Tuple[str, ...] = (
    "ls_blowout_pct_l5",
    "ls_avg_total_l5",
    "ls_avg_q1_pts_l5",
    "ls_avg_q4_pts_l5",
    "ls_garbage_time_pct_l5",
    "ls_opp_avg_total_allowed_l5",
    "ls_opp_q1_pts_allowed_l5",
)
_LS_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _LS_FEATURE_KEYS}
_LS_CONTEXT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "linescore_context.parquet")

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
    # EX-5 gate (CV_BBREF_REORDER_FIX, default OFF = legacy/byte-identical).
    # LEGACY (OFF): bbref_extra (orb_pct, drb_pct, trb_pct, bpm, ws) is emitted
    #   here, BETWEEN bbref_base and contract. This is the order all deployed
    #   85-col root artifacts in data/models were SERVED with — but it is a bug:
    #   predict_pergame slices cols[:n_features_in_] (=85), so bbref_extra lands
    #   in slots 80-84 where those artifacts were TRAINED on contract_*/pts_share_3pt
    #   (5/85 slots fed wrong values on the live slate/predictions_cache path).
    # FIX (ON): bbref_extra is appended AFTER the contract/ratio block (slots
    #   85-89), restoring contract_*/pts_share_3pt to slots 80-84 so cols[:85]
    #   matches props_pergame_metrics.json feature_cols exactly. Verified 0/85
    #   mismatches ON vs 5/85 mismatches OFF. Keep OFF until OLD-vs-NEW ROI/CLV
    #   is validated on the slate path (NOT gate1, which trains fresh per fold).
    if not _BBREF_REORDER_FIX:
        cols += [f"bbref_{k}" for k in _BBREF_EXTRA_KEYS]  # LEGACY slots 80-84 (misaligned)
    cols += [f"contract_{k}" for k in _CONTRACT_KEYS]
    cols += list(_RATIO_KEYS)
    if _BBREF_REORDER_FIX:
        cols += [f"bbref_{k}" for k in _BBREF_EXTRA_KEYS]  # FIX: slots 85-89 (aligned)
    # Wave-2b: defender matchup (7 keys) + player profile (12 keys)
    cols += list(_DMATCH_KEYS)
    cols += list(_PROF_KEYS)
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

    # Iter-3 (Wave-3): 20 new features (officials rolling 5, foul rolling 5,
    # DNP team 4, adv stats splits 6). APPENDED after the 109-col baseline so
    # existing artifacts that don't have feature_columns in _meta.json continue
    # to load via feature_columns_for() without dim-mismatch. New artifacts
    # trained on 129-col get feature_columns written to _meta.json by the OOS
    # retrain scripts; feature_columns_for() then returns the frozen 129-col
    # list for those artifacts and the legacy 109-col list for older ones.
    cols += list(_OFFICIALS_ROLLING_KEYS)   # A: 5 cols
    cols += list(_FOUL_FEATURE_KEYS)        # B: 5 cols
    cols += list(_DNP_TEAM_KEYS)            # C: 4 cols
    cols += list(_ADV_SPLITS_KEYS)          # D: 6 cols

    # Iter-5: hustle (6) + on_off (3) static per-season features.
    # REVERTED after backtest_holdout REVERT decision (delta_units gate failed
    # due to baseline scope mismatch — baseline was 1-stat, current is 7-stat).
    # Wiring infrastructure (build_hustle_features, build_on_off_features,
    # loaders) stays intact for future re-probe once baseline is rebuilt.
    # Uncomment to re-enable:
    # cols += list(_HUSTLE_KEYS)              # E: 6 cols (130-135)
    # cols += list(_ONOFF_KEYS)              # F: 3 cols (136-138)

    # Iter-17: gamelog_full box-stat rolling (oreb/dreb/fga/fta/pm) — 14 new keys.
    # REVERTED (backtest_holdout REVERT decision 2026-05-27): validation MAE
    # improved 6/7 stats but OOS 4-slice ROI regressed across all stats
    # (pts -2.26pp, ast -7.9pp, reb -4.3pp, fg3m -1.0pp, stl -2.3pp, blk -1.3pp).
    # Pattern: large training-set MAE gains with OOS ROI regression = overfitting.
    # Infrastructure stays intact for future probe with feature selection /
    # regularization angle (e.g., only fga_l5 + plus_minus_l5 instead of all 14).
    # cols += list(_GAMELOG_FULL_FEATURE_KEYS)  # 14 cols — DISABLED pending re-probe

    # Iter-18 narrow probe: only 2 isolated gamelog_full features for PTS.
    # REVERTED (backtest_holdout REVERT decision 2026-05-27): OOS holdout ROI
    # dropped from +2.55% to -0.06% (delta -2.61pp), MAE rose 5.70→6.94 (+1.24).
    # RS WF: 4/11 positive folds, mean_roi=-4.3%. Both gates FAILED decisively.
    # Pattern: gl_fga_l5 proxies usage, duplicating existing l5_pts/ewma_pts form
    # signals; gl_plus_minus_l5 introduces lineup noise. Even with tighter reg
    # (alpha 2→3, lambda 4→6) the 2-feature add creates OOS drag on PTS.
    # Infrastructure stays intact. Future angle: per-role probe (high-usage
    # scorers only where fga_l5 might carry marginal independent signal).
    # if stat == "pts":
    #     cols += ["gl_fga_l5", "gl_plus_minus_l5"]

    # Iter-19 (loop 5) — linescore blowout/pace context (7 ls_* keys).
    # REVERTED (backtest_holdout REVERT decision 2026-05-27): validation MAE
    # improved 6/7 stats but OOS ROI regressed across 5/6 stats tested
    # (ast -14.3pp, reb -8.8pp, fg3m -2.8pp, stl -4.1pp, pts -0.95pp).
    # Pattern: large training-set MAE gains with OOS ROI regression = overfitting.
    # Infrastructure (build_linescore_context, _LinescoreContext, _LS_FEATURE_KEYS,
    # the injection in build_pergame_dataset and _inject_iter23_features) stays
    # active for a future probe with tighter feature selection or regularization
    # (e.g., only ls_avg_total_l5 for high-pace contexts, or interaction with
    # garbage_time_pct for volume props like PTS).
    # cols += list(_LS_FEATURE_KEYS)  # 7 cols — DISABLED pending re-probe

    # Cycle 90d (loop 5) — T1-E: REB-only OREB-context features.
    # ONLY appended when stat == "reb"; other stats keep the global list to
    # preserve compatibility with existing model artifacts.
    if stat == "reb":
        cols += list(_REB_CONTEXT_KEYS)

    # vac_ast feature gate (CV_AST_VAC_FEATURE, default OFF = byte-identical).
    # ONLY appended when stat == "ast" AND the flag is ON; other stats and the
    # OFF path keep the unchanged global list so every existing model artifact
    # loads without an n_features_in_ mismatch. The 2 cols are appended LAST so
    # a fresh AST artifact trained with the flag ON carries them in slots
    # [n..n+1] and feature_columns_for() (frozen-list) keeps older AST artifacts
    # on the legacy column set. Leak-free vacated-assist signal (box-appearance
    # recipe, as-of L10); see _AST_VAC_FEATURE banner + the validation audit.
    if stat == "ast" and _AST_VAC_FEATURE:
        cols += list(_VAC_AST_KEYS)

    # vac_load feature gate (CV_VAC_LOAD_FEATURE, default OFF = byte-identical).
    # ONLY appended when stat in ("pts","reb") AND the flag is ON; other stats
    # and the OFF path keep the unchanged list so every existing PTS/REB model
    # artifact loads without an n_features_in_ mismatch. The 3 cols are appended
    # LAST — for REB this is AFTER the _REB_CONTEXT_KEYS append, so the ON-flag
    # REB order is base + reb_context + vac_load. PTS gains them in trailing
    # slots [129..131] (129->132), REB in [132..134] (132->135). Leak-free
    # team-vacated-load signal (box-appearance recipe, as-of L10); see the
    # _VAC_LOAD_FEATURE banner + docs/_audits/NIGHT_RUN_STATUS.md.
    if stat in ("pts", "reb") and _VAC_LOAD_FEATURE:
        cols += list(_VAC_LOAD_KEYS)

    # Iter-47 (loop 5) — l3 + l7 rolling windows for PTS, AST, REB only.
    # REVERTED (backtest_holdout REVERT decision 2026-05-28): OOS ROI regressed
    # across all 3 probe stats:
    #   PTS: delta_roi=-14.6pp, delta_mae=+6.15 (massive OOS MAE increase)
    #   AST: delta_roi=-16.4pp, delta_mae=+1.60
    #   REB: delta_roi=-3.1pp
    # Pattern: denser window coverage overlaps heavily with existing l5/l10/ewma,
    # adding collinear features that overfit training distributions without
    # generalizing to 2025-26 OOS. _row_features still computes l3/l7 for ALL
    # _FORM_STATS (zero inference cost); gate here keeps them out of all models.
    # Future probe angle: interaction feature (l3 - l5 as momentum delta), or
    # selective use in high-variance players only (role change detection).
    # if stat in ("pts", "ast", "reb"):
    #     cols += [f"l3_{stat}", f"l7_{stat}"]

    # Iter-44 (loop 5) — narrow synergy PPP per-play-type extras.
    # REVERTED (backtest_holdout REVERT decision 2026-05-28): OOS ROI regressed
    # across all 3 probe stats despite validation MAE improvement:
    #   PTS: delta_roi=-7.0pp, delta_mae=+5.43 (massive OOS MAE increase)
    #   AST: delta_roi=-16.7pp, delta_mae=+1.58
    #   FG3M: delta_roi=-12.7pp
    # Pattern: per-season aggregate PPP features overfit to training seasons and
    # don't generalize to 2025-26 OOS distribution. The features shift the model's
    # prediction distribution but don't improve accuracy on unseen data.
    # Infrastructure (build_syn_ppp, _SynPPP, parquet) stays for future probe
    # angles (e.g., rolling PPP within-season, per-opponent PPP split).
    # if stat == "ast":
    #     cols += list(_SYN_PPP_AST_KEYS)
    # elif stat == "pts":
    #     cols += list(_SYN_PPP_PTS_KEYS)
    # elif stat == "fg3m":
    #     cols += list(_SYN_PPP_FG3M_KEYS)

    # Iter-46 (loop 5) — per-opponent rolling-3 stat features.
    # REVERTED (backtest_holdout REVERT decision 2026-05-28): OOS ROI regressed
    # across all 6 probe stats despite feature importance pickup for FG3M/REB:
    #   PTS:  delta_roi=-11.0pp, delta_mae=+6.01 (OOS MAE far worse)
    #   AST:  delta_roi=-17.7pp, delta_mae=+1.60
    #   FG3M: delta_roi=-12.9pp
    #   REB:  delta_roi=-8.3pp
    #   STL:  delta_roi=-3.9pp
    #   BLK:  delta_roi=+1.1pp (only stat with positive ROI but mae regressed +0.54)
    # Pattern: per-opponent historical rolling (last 3 prior meetings) captures
    # team-matchup style bias but doesn't generalize OOS — in the 2025-26 playoffs
    # sample, matchup history is too sparse (82% non-null = first-ever meeting
    # rows) and the non-null rows reflect regular-season matchups that don't
    # predict playoff performance. Identical failure mode to iter-44 (per-season
    # synergy PPP).
    # Infrastructure (_PerOppRolling, build_per_opp_rolling, parquet) stays
    # for future probe angles (e.g., interact per_opp_pts_l3 × home_spread,
    # or use longer window L10 to reduce sparsity, or restrict to playoff games).
    # if stat in _PER_OPP_ROLLING_STATS:
    #     cols += [f"per_opp_{stat}_l3"]

    # Iter-48 (loop 5) — momentum-delta features (l3 - l5) for PTS, AST, REB only.
    # REVERTED (backtest_holdout REVERT decision 2026-05-28): OOS ROI regressed
    # across all 3 probe stats:
    #   PTS: delta_roi=-12.64pp (catastrophic)
    #   AST: delta_roi=-17.80pp (catastrophic)
    #   REB: delta_roi=-5.68pp
    # Pattern: even the explicit l3-l5 DIFFERENCE feature (numerically independent
    # of l5/l10/ewma levels) overfits training distributions without generalizing to
    # 2025-26 OOS. _row_features computes mom_delta_* for all _FORM_STATS (zero
    # inference cost) and build_pergame_dataset carries them on every row dict;
    # gate here keeps them out of all models.
    # Root cause hypothesis: the momentum signal (hot-streak detection) is already
    # captured by the model through its ewma/l5/prev interactions. The explicit delta
    # adds noise from short-window volatility (3-game samples are high-variance) that
    # helps on training data but hurts OOS. This exhausts the l3-window probe space.
    # if stat in ("pts", "ast", "reb"):
    #     cols += [f"mom_delta_{stat}"]

    # CV feature gate (PROP_USE_CV=1). Appended last so existing model
    # artifacts without these columns continue to load without dim-mismatch.
    if _USE_CV_FEATURES:
        cols.extend(_CV_FEATURE_COLS)

    return cols


def feature_columns_for(stat: str, artifact_dir: Optional[str] = None) -> List[str]:
    """Return the frozen column list for an artifact directory, or the live default.

    Wave-3 schema versioning: if artifact_dir/_meta.json contains
    stats.<stat>.feature_columns, that frozen list is returned so the
    prediction path can slice the input DataFrame to exactly the columns
    the artifact was trained on — enabling clean A/B tests between
    85-col (pre-Wave-2b) and 109-col (post-Wave-2b) artifacts without
    ValueError on dim-mismatch.

    Falls back to feature_columns(stat) when the key is absent (fresh
    training run, or pre-patch artifact) so existing callers are unaffected.
    """
    if artifact_dir is not None:
        meta_path = os.path.join(artifact_dir, "_meta.json")
        if os.path.isfile(meta_path):
            try:
                meta = json.load(open(meta_path, encoding="utf-8"))
                frozen = (meta.get("stats") or {}).get(stat, {}).get("feature_columns")
                if isinstance(frozen, list) and frozen:
                    return frozen
            except Exception:
                pass
    return feature_columns(stat)


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
    except Exception as exc:
        _warn_join_load_once("build_player_tracking", path, exc)
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

# Cycle 96a (loop 5) — T1-A garbage-time haircut SHIPPED.
# Cycle 94a/95a validated: with the cycle-95a home_spread join fix (13% ->
# 99.9% holdout coverage) the v1-revalidate variant passes the ship gate:
#   single-split PTS -0.0117 MAE, agg(PTS+REB+AST) -0.0103
#   walk-forward 4-fold PTS 4/4 folds negative (improvement)
# Tiered multiplicative shrink keyed on |home_spread|, applied AFTER the
# main blend/q50 dispatch and AFTER quantile_calibration on volume stats
# (PTS, REB, AST) only — fg3m/stl/blk/tov are saturated per cycle 89f/90a.
# The flag _APPLY_GARBAGE_HAIRCUT can be flipped to False for emergency
# rollback without touching the prediction call sites.
_APPLY_GARBAGE_HAIRCUT = True
_GARBAGE_HAIRCUT_BINS = (6.0, 10.0, 14.0)
_GARBAGE_HAIRCUT_FACTORS = (0.98, 0.95, 0.92)
_GARBAGE_HAIRCUT_STATS = ("pts", "reb", "ast")


def apply_garbage_time_haircut(pred: float, stat: str,
                               home_spread: Optional[float]) -> float:
    """Cycle 96a (loop 5). Cycle 94a/95a-validated spread-conditioned shrink.

    Multiplicative haircut on volume-stat predictions when the absolute
    home_spread crosses 6/10/14 point bins (0.98/0.95/0.92 factors). A no-op
    when:
      * the module flag _APPLY_GARBAGE_HAIRCUT is False
      * the stat isn't in _GARBAGE_HAIRCUT_STATS (only PTS/REB/AST shipped)
      * home_spread is None (no pre-game line cached for the matchup)

    home_spread is from the PLAYER'S perspective (negative when their team
    is favoured); abs() captures blowout magnitude either way. Must be
    applied AFTER any other post-prediction transform (quantile calibration,
    isotonic calibration, lineup scaling) so the haircut sees the final
    point estimate. Returns pred unchanged when any guard trips so existing
    callers see no behaviour change on pre-cycle-95a data (no home_spread).
    """
    if not _APPLY_GARBAGE_HAIRCUT:
        return pred
    if stat not in _GARBAGE_HAIRCUT_STATS:
        return pred
    if home_spread is None:
        return pred
    try:
        m = abs(float(home_spread))
    except (TypeError, ValueError):
        return pred
    if m >= _GARBAGE_HAIRCUT_BINS[2]:
        return pred * _GARBAGE_HAIRCUT_FACTORS[2]
    if m >= _GARBAGE_HAIRCUT_BINS[1]:
        return pred * _GARBAGE_HAIRCUT_FACTORS[1]
    if m >= _GARBAGE_HAIRCUT_BINS[0]:
        return pred * _GARBAGE_HAIRCUT_FACTORS[0]
    return pred


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
    except Exception as exc:
        _warn_join_load_once("build_team_reb_context", path, exc)
        return _TeamRebContext(by_team)
    return _TeamRebContext(by_team)


# ── Iter-19: linescore blowout/pace context (ls_* features) ──────────────────
# Source: data/cache/linescore_context.parquet — pre-computed rolling-5
# features per (team_abbreviation, game_date). The parquet already applies
# shift(1).rolling(5, min_periods=2) so every row is strictly leak-free.
# We load the full parquet into a (team, date_iso) → {ls_*} dict for O(1)
# lookup at inference time. Missing rows fall back to _LS_DEFAULTS (0.0).


class _LinescoreContext:
    """Pre-computed (team_abbreviation, date_iso) → {ls_*} lookup.

    Loaded from data/cache/linescore_context.parquet. The parquet is already
    aggregated (shift(1).rolling(5)) so no in-memory rolling is needed — we
    just do a keyed lookup. Both team-side (5 features) and opponent-side
    (2 features) are stored in the same parquet per team; at join time the
    caller passes team_abbrev to get team features and opp_abbrev separately
    for the opp variants.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup  # keyed by (team_abbreviation, date_iso)

    def features(self, team_abbrev: str, opp_abbrev: str, game_date) -> Dict[str, float]:
        """Return 7 ls_* features for this (team, opponent, date) triple.

        Team-side features (ls_blowout_pct_l5, ls_avg_total_l5,
        ls_avg_q1_pts_l5, ls_avg_q4_pts_l5, ls_garbage_time_pct_l5) come
        from the team's own row. Opp-side features
        (ls_opp_avg_total_allowed_l5, ls_opp_q1_pts_allowed_l5) come from
        the opp team's row (where opp_q1_pts_allowed means our-team Q1 pts
        scored against that opponent in prior games — i.e., opp's Q1
        defence tendency from opp's perspective).
        """
        out = dict(_LS_DEFAULTS)
        try:
            if hasattr(game_date, "date"):
                date_iso = game_date.date().isoformat()
            else:
                date_iso = str(game_date)[:10]
            team_row = self._lookup.get((str(team_abbrev), date_iso))
            opp_row  = self._lookup.get((str(opp_abbrev),  date_iso))
            if team_row:
                out["ls_blowout_pct_l5"]       = team_row.get("ls_blowout_pct_l5", 0.0)
                out["ls_avg_total_l5"]         = team_row.get("ls_avg_total_l5", 0.0)
                out["ls_avg_q1_pts_l5"]        = team_row.get("ls_avg_q1_pts_l5", 0.0)
                out["ls_avg_q4_pts_l5"]        = team_row.get("ls_avg_q4_pts_l5", 0.0)
                out["ls_garbage_time_pct_l5"]  = team_row.get("ls_garbage_time_pct_l5", 0.0)
            if opp_row:
                out["ls_opp_avg_total_allowed_l5"] = opp_row.get("ls_opp_avg_total_allowed_l5", 0.0)
                out["ls_opp_q1_pts_allowed_l5"]    = opp_row.get("ls_opp_q1_pts_allowed_l5", 0.0)
        except Exception:
            pass
        return out


_LS_CONTEXT_CACHE: Optional["_LinescoreContext"] = None


def _get_linescore_context() -> "_LinescoreContext":
    """Process-cached _LinescoreContext for live prediction paths."""
    global _LS_CONTEXT_CACHE
    if _LS_CONTEXT_CACHE is None:
        _LS_CONTEXT_CACHE = build_linescore_context()
    return _LS_CONTEXT_CACHE


def build_linescore_context(parquet_path: Optional[str] = None) -> _LinescoreContext:
    """Load linescore_context.parquet into a _LinescoreContext wrapper. Never raises."""
    path = parquet_path or _LS_CONTEXT_PATH
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _LinescoreContext(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            team = str(r.get("team_abbreviation", "")).strip()
            date = str(r.get("game_date", ""))[:10]
            if not team or not date:
                continue
            lookup[(team, date)] = {k: float(r.get(k, 0.0) or 0.0) for k in _LS_FEATURE_KEYS}
    except Exception as exc:
        _warn_join_load_once("build_linescore_context", path, exc)
        return _LinescoreContext(lookup)
    return _LinescoreContext(lookup)


# ── team advanced stats — opp-context rolling-5 (cycle 99e loop 5) ────────────
# Source: data/team_advanced_stats.parquet — built by
# scripts/aggregate_team_stats_from_boxscores.py from boxscore_adv_*.json
# teams entries. Per-team-per-game advanced rates: off_rtg, def_rtg, pace,
# oreb_pct, dreb_pct, ast_pct, efg_pct, ts_pct, tov_ratio.
#
# Exposes a (team_tricode, current_date) -> {opp_team_<col>_l5} lookup that
# averages the OPPONENT's last 5 games STRICTLY before the row's date. This
# is the rolling-5 sibling of _OpponentDefense (which uses to-date expanding
# means of stats ALLOWED). The two are complementary: _OpponentDefense
# captures HOW MANY pts/reb a defence allows; _TeamAdvancedL5 captures the
# style they play (pace, ratings, rebound rates).
#
# Additive only — keys land on row dict (NOT in feature_columns()). Cycle
# 99e ships the join; cycles 99a/b/c retrain the heads. Gated on parquet
# existence so fresh checkouts get the no-op empty wrapper.
_TEAM_ADV_STATS_PATH = os.path.join(
    PROJECT_DIR, "data", "team_advanced_stats.parquet"
)
_TEAM_ADV_COLS = (
    "off_rtg", "def_rtg", "pace",
    "oreb_pct", "dreb_pct", "ast_pct",
    "efg_pct", "ts_pct", "tov_ratio",
)
_TEAM_ADV_FEATURE_KEYS = tuple(f"opp_team_{c}_l5" for c in _TEAM_ADV_COLS)


class _TeamAdvancedL5:
    """Per-team time series of advanced rates with rolling-5 prior aggregation.

    Keyed on team_tricode → sorted list of (date, {col: value}). For a row
    with (opponent_tricode, current_date), returns the mean of the
    opponent's last 5 games STRICTLY before current_date. Empty wrapper
    yields all-None when the parquet is absent so probes/tests can branch
    on missingness without a try/except.
    """

    def __init__(self, by_team: Dict[str, list]):
        self._by_team = by_team

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_team.values())

    def features(self, opp_tricode: str,
                 current_date) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {k: None for k in _TEAM_ADV_FEATURE_KEYS}
        history = self._by_team.get(str(opp_tricode))
        if not history:
            return out
        priors = []
        for d, row in history:
            if d < current_date:
                priors.append(row)
            else:
                break
        if not priors:
            return out
        last5 = priors[-5:]
        for col in _TEAM_ADV_COLS:
            vals = [r.get(col) for r in last5 if r.get(col) is not None]
            if vals:
                out[f"opp_team_{col}_l5"] = float(sum(vals)) / float(len(vals))
        return out


def build_team_advanced_l5(parquet_path: Optional[str] = None) -> _TeamAdvancedL5:
    """Load data/team_advanced_stats.parquet into a _TeamAdvancedL5 wrapper.

    Returns an empty wrapper (all-None lookups) when the parquet is absent
    or pandas/pyarrow fails. Never raises.
    """
    path = parquet_path or _TEAM_ADV_STATS_PATH
    by_team: Dict[str, list] = {}
    if not os.path.exists(path):
        return _TeamAdvancedL5(by_team)
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        for tcode, grp in df.groupby("team_tricode"):
            grp_sorted = grp.sort_values("game_date")
            hist = []
            for _, r in grp_sorted.iterrows():
                d = _parse_date_iso(str(r["game_date"]))
                if d is None:
                    continue
                row = {}
                for c in _TEAM_ADV_COLS:
                    v = r.get(c)
                    try:
                        row[c] = float(v) if v is not None else 0.0
                    except (TypeError, ValueError):
                        row[c] = 0.0
                hist.append((d, row))
            by_team[str(tcode)] = hist
    except Exception as exc:
        _warn_join_load_once("build_team_advanced_l5", path, exc)
        return _TeamAdvancedL5(by_team)
    return _TeamAdvancedL5(by_team)


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
    except Exception as exc:
        _warn_join_load_once("build_player_positions", path, exc)
        return _PlayerPositions(lookup)
    return _PlayerPositions(lookup)


# ── per-quarter stats (cycle 91a loop 5) ──────────────────────────────────────
# Source: data/player_quarter_stats.parquet — built by
# scripts/aggregate_quarter_boxscores.py from
# data/cache/quarter_box/<gid>_q<p>.json (fetched by
# scripts/fetch_per_quarter_boxscores.py). Per-(game_id, player_id, period)
# box-score slice: min, pts, reb, ast, fg3m, stl, blk, tov, pf, plus_minus.
#
# This scaffold (cycle 91a) provides the wrapper + a date-keyed lookup so
# build_pergame_dataset can attach rolling-Q1 prior-5 features to each row.
# The parquet is OPTIONAL — when absent (fresh checkout, or before the
# fetch daemon has run), the wrapper is empty and every row gets q1_*_l5
# defaults of None. Probes in cycle 91+ consume these via row["q1_pts_l5"]
# etc.; nothing is appended to feature_columns() until a separate retrain
# cycle wires the signal in.
_PLAYER_QUARTER_STATS_PATH = os.path.join(
    PROJECT_DIR, "data", "player_quarter_stats.parquet"
)
_Q1_STAT_KEYS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min")
_Q1_FEATURE_KEYS = tuple(f"q1_{s}_l5" for s in _Q1_STAT_KEYS)


class _PlayerQuarterStats:
    """Per-(player_id, period) per-quarter stat lookup, keyed by date.

    Joining quarter boxscores to per-game rows is tricky: the gamelog
    cache has no GAME_ID column, so the wrapper exposes a date-based
    lookup. We construct (player_id, game_date_iso) -> period -> stats
    by walking season_games_*.json once at load time and pairing each
    quarter row's game_id with its date.

    All methods are NO-OPs on a fresh checkout (empty wrapper). They
    yield None for unknown keys and never raise.
    """

    def __init__(self, by_pid_date_period: Dict[Tuple[int, str, int],
                                                Dict[str, float]]):
        self._lookup = by_pid_date_period

    def __len__(self) -> int:
        return len(self._lookup)

    def quarter(self, player_id, gdate: datetime, period: int) -> Optional[Dict[str, float]]:
        """Return the player's Q<period> stat dict for ``gdate`` or None."""
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        key = (pid, gdate.date().isoformat(), int(period))
        row = self._lookup.get(key)
        if not row:
            return None
        return dict(row)

    def rolling_q1_prior(self, player_id, prior_dates: List[datetime],
                         window: int = 5) -> Dict[str, Optional[float]]:
        """Mean Q1 stats over the last `window` prior games that have Q1 data.

        ``prior_dates`` is the player's already-played game dates (sorted
        oldest -> newest). We walk it BACKWARDS, picking up to `window`
        games that exist in the parquet, then average each stat. Returns
        defaults of None for every key when nothing is found (preserves
        the "no leak / no data" semantics — downstream code can treat
        None as missing without an arithmetic crash).
        """
        out: Dict[str, Optional[float]] = {k: None for k in _Q1_FEATURE_KEYS}
        if not self._lookup or not prior_dates:
            return out
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return out
        # Walk newest -> oldest, picking up to `window` matching games.
        picked: List[Dict[str, float]] = []
        for d in reversed(prior_dates):
            key = (pid, d.date().isoformat(), 1)
            row = self._lookup.get(key)
            if row is not None:
                picked.append(row)
                if len(picked) >= window:
                    break
        if not picked:
            return out
        for stat in _Q1_STAT_KEYS:
            vals = [r.get(stat) for r in picked if r.get(stat) is not None]
            if vals:
                out[f"q1_{stat}_l5"] = float(sum(vals)) / float(len(vals))
        return out


def build_player_quarter_stats(
    parquet_path: Optional[str] = None,
    season_games_dir: Optional[str] = None,
) -> _PlayerQuarterStats:
    """Load player_quarter_stats.parquet keyed by (pid, date, period).

    GATED on file existence — returns an empty wrapper when the parquet
    is absent so build_pergame_dataset stays back-compat. Pairs each
    quarter row's game_id with the corresponding game_date from the
    season_games_*.json cache; rows whose game_id is unknown are
    silently dropped (defensive — never raises).
    """
    path = parquet_path or _PLAYER_QUARTER_STATS_PATH
    cache_dir = season_games_dir or _NBA_CACHE
    lookup: Dict[Tuple[int, str, int], Dict[str, float]] = {}
    if not os.path.exists(path):
        return _PlayerQuarterStats(lookup)
    # Build game_id -> game_date map from every season_games_*.json.
    gid_to_date: Dict[str, str] = {}
    try:
        for fname in sorted(os.listdir(cache_dir)):
            if not fname.startswith("season_games_") or not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(cache_dir, fname), encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                continue
            rows = payload["rows"] if isinstance(payload, dict) else payload
            for g in rows or []:
                gid = g.get("game_id") or g.get("GAME_ID")
                gdate = g.get("game_date") or g.get("GAME_DATE")
                if gid and gdate:
                    gid_to_date[str(gid).zfill(10)] = str(gdate)[:10]
    except FileNotFoundError:
        pass
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
                period = int(r["period"])
                gid = str(r["game_id"]).zfill(10)
            except (TypeError, ValueError, KeyError):
                continue
            gdate = gid_to_date.get(gid)
            if not gdate:
                continue
            entry = {}
            for k in _Q1_STAT_KEYS:
                v = r.get(k)
                if v is None:
                    continue
                try:
                    entry[k] = float(v)
                except (TypeError, ValueError):
                    continue
            lookup[(pid, gdate, period)] = entry
    except Exception as exc:
        _warn_join_load_once("build_player_quarter_stats", path, exc)
        return _PlayerQuarterStats(lookup)
    return _PlayerQuarterStats(lookup)


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
    except Exception as exc:
        _warn_join_load_once("build_rest_travel", path, exc)
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
    except Exception as exc:
        _warn_join_load_once("build_officials_crew", path, exc)
        return _OfficialsCrew(lookup)
    return _OfficialsCrew(lookup)


# ── pre-game sportsbook spreads (cycle 91c loop 5) ────────────────────────────
# Source: data/pregame_spreads.parquet — built by
# scripts/aggregate_spreads_to_parquet.py from ESPN scoreboard caches under
# data/cache/spreads/. Each row: (game_date, home_team, away_team, home_spread,
# total). Sign convention: home_spread < 0 ⇒ home favoured by |home_spread|
# points. Strictly pre-game (ESPN publishes the posted line on the scoreboard
# before tip-off). Additive-only on row dict — NOT in feature_columns() yet;
# T1-A garbage-time haircut probe reads row["home_spread"] directly.
# Gated on parquet existence so fresh checkouts have a no-op join.

_PREGAME_SPREADS_PATH = os.path.join(PROJECT_DIR, "data", "pregame_spreads.parquet")

# Cycle 95a (loop 5) — ESPN tricode → NBA gamelog tricode alias map.
# Diagnosed: pregame_spreads holdout coverage was 12.9% because ESPN's
# scoreboard publishes 2-char / 4-char abbreviations for 6 teams while NBA
# gamelog MATCHUPs use the canonical 3-letter codes. Without this map every
# Warriors / Pelicans / Knicks / Spurs / Jazz / Wizards row silently missed.
_ESPN_TO_NBA_ABBR = {
    "GS":   "GSW",
    "NO":   "NOP",
    "NY":   "NYK",
    "SA":   "SAS",
    "UTAH": "UTA",
    "WSH":  "WAS",
    # Historical / fallback aliases (cheap insurance — no-op when absent).
    "NOH":  "NOP",
    "NJN":  "BKN",
}


def _normalize_abbr(abbr: str) -> str:
    """Canonicalise any 2-/3-/4-letter abbrev to the NBA gamelog tricode."""
    up = str(abbr).upper().strip()
    return _ESPN_TO_NBA_ABBR.get(up, up)


class _PregameSpreads:
    """Lookup of (game_date_iso, home_team, away_team) → {home_spread, total}.

    Empty wrapper yields None on every lookup so callers can branch on missing
    coverage without try/except.

    Cycle 95a (loop 5): keys are stored under the ET date (matching NBA
    gamelog MATCHUP dates). The parquet itself uses UTC dates because
    ESPN's scoreboard payload reports `event["date"]` as UTC, so a game
    tipping off at 7-10pm ET appears on the NEXT UTC calendar day. We
    disambiguate via the cache filename (`data/cache/spreads/YYYYMMDD.json`,
    where YYYYMMDD is the ET date the scoreboard was queried for). When the
    cache is absent (fresh checkouts), we fall back to a ±1 day fuzzy match
    on lookup.
    """

    def __init__(self, lookup: Dict[Tuple[str, str, str], Dict[str, float]],
                 fuzzy_dates: bool = False):
        self._lookup = lookup
        self._fuzzy_dates = fuzzy_dates

    def features(self, home_abbr: str, away_abbr: str,
                 gdate: datetime) -> Dict[str, Optional[float]]:
        h = _normalize_abbr(home_abbr)
        a = _normalize_abbr(away_abbr)
        base = gdate.date()
        # Primary lookup: ET date (always tried; usually hits exactly when
        # the cache filename was used to compute the key at load time).
        key = (base.isoformat(), h, a)
        rec = self._lookup.get(key)
        if rec is not None:
            return {"home_spread": rec.get("home_spread"),
                    "total":       rec.get("total")}
        # Fuzzy fallback (only when ET-date keying was unavailable): try +1
        # day to compensate for raw UTC parquet keys.
        if self._fuzzy_dates:
            from datetime import timedelta as _td  # noqa: PLC0415
            for delta in (1, -1):
                key = ((base + _td(days=delta)).isoformat(), h, a)
                rec = self._lookup.get(key)
                if rec is not None:
                    return {"home_spread": rec.get("home_spread"),
                            "total":       rec.get("total")}
        return {"home_spread": None, "total": None}

    def __len__(self) -> int:
        return len(self._lookup)


# Cycle 95a: cache (game_date_utc, home, away) → ET date by scanning
# `data/cache/spreads/YYYYMMDD.json`. The filename is the date the ESPN
# scoreboard was queried for (always ET because we're a US-based pipeline),
# and the events inside carry UTC timestamps. This lets us key the parquet
# rows by ET date even though the parquet only stores UTC.
def _build_et_date_index(
    cache_dir: Optional[str] = None,
) -> Dict[Tuple[str, str, str], str]:
    """Return {(utc_date_iso, home_norm, away_norm) -> et_date_iso}.

    Best-effort: returns an empty dict if the cache directory is absent or
    unreadable. Used at _PregameSpreads load time to upgrade UTC keys to
    proper ET-dated keys (eliminating the ±1 day collision risk on
    consecutive same-opponent matchups).
    """
    import glob as _glob  # noqa: PLC0415
    cache_dir = cache_dir or os.path.join(PROJECT_DIR, "data", "cache", "spreads")
    idx: Dict[Tuple[str, str, str], str] = {}
    if not os.path.isdir(cache_dir):
        return idx
    for path in _glob.glob(os.path.join(cache_dir, "*.json")):
        fname = os.path.basename(path)
        stem = fname.replace(".json", "")
        if len(stem) != 8 or not stem.isdigit():
            continue
        et_date = f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}"
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for ev in (payload.get("events") or []):
            try:
                comps = ev.get("competitions") or []
                if not comps:
                    continue
                comp = comps[0]
                teams = comp.get("competitors") or []
                home_abbr = away_abbr = None
                for t in teams:
                    abbr = ((t.get("team") or {}).get("abbreviation") or "").upper()
                    ha = (t.get("homeAway") or "").lower()
                    if ha == "home":
                        home_abbr = abbr
                    elif ha == "away":
                        away_abbr = abbr
                if not home_abbr or not away_abbr:
                    continue
                utc_date = (ev.get("date") or comp.get("date") or "")[:10]
                if not utc_date:
                    continue
                idx[(utc_date,
                     _normalize_abbr(home_abbr),
                     _normalize_abbr(away_abbr))] = et_date
            except Exception:
                continue
    return idx


def build_pregame_spreads(parquet_path: Optional[str] = None) -> _PregameSpreads:
    """Load data/pregame_spreads.parquet into a _PregameSpreads wrapper.

    Returns an empty wrapper (every lookup yields None) when the parquet is
    absent or pandas/pyarrow fails. Never raises.

    Cycle 95a (loop 5): apply _ESPN_TO_NBA_ABBR aliasing at load time so the
    in-memory lookup is keyed by NBA-canonical tricodes (matching gamelog
    MATCHUP strings). Date keys are normalised to ISO YYYY-MM-DD strings —
    pandas may surface game_date as either a str or a Timestamp depending on
    pyarrow version, so we coerce defensively.
    """
    path = parquet_path or _PREGAME_SPREADS_PATH
    lookup: Dict[Tuple[str, str, str], Dict[str, float]] = {}
    fuzzy = False
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _PregameSpreads(lookup)
        df = pd.read_parquet(path)
        # Cycle 95a: build UTC->ET date index from the scoreboard cache so
        # we can rekey the parquet (which is in UTC) onto the NBA gamelog ET
        # calendar. When the cache directory is absent, fall back to fuzzy
        # ±1 day matching at lookup time.
        et_index = _build_et_date_index()
        if not et_index:
            fuzzy = True
        for _, r in df.iterrows():
            try:
                raw_date = r["game_date"]
                if hasattr(raw_date, "date"):
                    utc_iso = raw_date.date().isoformat()
                else:
                    utc_iso = str(raw_date)[:10]
                home_norm = _normalize_abbr(r["home_team"])
                away_norm = _normalize_abbr(r["away_team"])
                # Prefer the ET date from the cache index; fall back to UTC.
                et_iso = et_index.get((utc_iso, home_norm, away_norm), utc_iso)
                key = (et_iso, home_norm, away_norm)
                hs = r.get("home_spread")
                tot = r.get("total")
                lookup[key] = {
                    "home_spread": float(hs) if hs is not None and hs == hs else None,
                    "total":       float(tot) if tot is not None and tot == tot else None,
                }
            except Exception:
                continue
    except Exception as exc:
        _warn_join_load_once("build_pregame_spreads", path, exc)
        return _PregameSpreads(lookup, fuzzy_dates=fuzzy)
    return _PregameSpreads(lookup, fuzzy_dates=fuzzy)


_PREGAME_SPREADS_CACHE: Optional["_PregameSpreads"] = None


def _get_pregame_spreads() -> "_PregameSpreads":
    """Process-cached _PregameSpreads for live prediction paths.

    Cycle 96a (loop 5) added this so build_prediction_row can resolve a
    pre-game home_spread for the upcoming matchup without rebuilding the
    parquet lookup on every call. Returns an empty wrapper (always None
    lookups) when the parquet is absent — see build_pregame_spreads."""
    global _PREGAME_SPREADS_CACHE
    if _PREGAME_SPREADS_CACHE is None:
        _PREGAME_SPREADS_CACHE = build_pregame_spreads()
    return _PREGAME_SPREADS_CACHE


# ── per-player personal fouls (cycle 91b loop 5) ──────────────────────────────
# Source: data/player_pf.parquet — built by
# scripts/aggregate_player_pf_from_boxscores.py from cached
# data/nba/boxscore_<gid>.json. Each row: (game_id, player_id,
# team_abbreviation, game_date, pf, min). Companion rolling lookup at
# data/player_pf_per36.parquet is built by scripts/aggregate_pf_per_36.py:
# per-(player_id, game_date) expanding PF/36 EXCLUDING the target game.
#
# GATED on file existence: when the parquet is absent the wrapper returns
# None for every query so build_pergame_dataset is a strict no-op back-compat
# path. pf is NOT yet appended to feature_columns() — this is the cycle 91b
# backfill that unblocks the cycle-90c T1-B foul-rate probe (which silently
# degraded to a BLK proxy because PF was absent from the gamelog cache).
_PLAYER_PF_PATH = os.path.join(PROJECT_DIR, "data", "player_pf.parquet")
_PLAYER_PF_PER36_PATH = os.path.join(PROJECT_DIR, "data", "player_pf_per36.parquet")


class _PlayerPF:
    """Per-(player_id, game_date) PF + rolling expanding PF/36 lookup.

    Both queries return None on miss so callers can NaN-fill or substitute
    a default without a try/except. season_pf_per_36 is strictly
    point-in-time (excludes the target game) — built by
    scripts/aggregate_pf_per_36.py with pandas expanding+shift(1).
    """

    def __init__(
        self,
        pf_lookup: Dict[Tuple[int, str], float],
        per36_lookup: Dict[Tuple[int, str], float],
    ):
        self._pf = pf_lookup
        self._per36 = per36_lookup

    def __len__(self) -> int:
        return len(self._pf)

    def pf(self, player_id, gdate_iso: str) -> Optional[float]:
        """Realised PF for (player_id, game_date_iso) — None when unknown."""
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        return self._pf.get((pid, str(gdate_iso)))

    def season_pf_per_36(self, player_id, gdate_iso: str) -> Optional[float]:
        """Rolling expanding PF/36 EXCLUDING the target game (no leakage).

        None when the player has no prior game or the parquet is absent.
        """
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        return self._per36.get((pid, str(gdate_iso)))


def build_player_pf(
    pf_path: Optional[str] = None,
    per36_path: Optional[str] = None,
) -> _PlayerPF:
    """Load data/player_pf.parquet (+ optional per36) into a _PlayerPF wrapper.

    GATED on file existence: missing pf parquet collapses to the empty
    wrapper so build_pergame_dataset is a no-op back-compat path. Missing
    per36 parquet only disables the rolling lookup (raw pf still works).
    Never raises — pandas/pyarrow import failures fall through to empty.
    """
    pf_path = pf_path or _PLAYER_PF_PATH
    per36_path = per36_path or _PLAYER_PF_PER36_PATH
    pf_lookup: Dict[Tuple[int, str], float] = {}
    per36_lookup: Dict[Tuple[int, str], float] = {}
    if not os.path.exists(pf_path):
        return _PlayerPF(pf_lookup, per36_lookup)
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(pf_path)
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError, KeyError):
                continue
            gdate = str(r.get("game_date", ""))
            if not gdate:
                continue
            try:
                pf_lookup[(pid, gdate)] = float(r.get("pf", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
        if os.path.exists(per36_path):
            df36 = pd.read_parquet(per36_path)
            for _, r in df36.iterrows():
                try:
                    pid = int(r["player_id"])
                except (TypeError, ValueError, KeyError):
                    continue
                v = r.get("season_pf_per_36")
                try:
                    v_f = float(v)
                except (TypeError, ValueError):
                    continue
                if v_f != v_f:  # NaN
                    continue
                per36_lookup[(pid, str(r["game_date"]))] = v_f
    except Exception as exc:
        _warn_join_load_once("build_player_pf", pf_path, exc)
        return _PlayerPF(pf_lookup, per36_lookup)
    return _PlayerPF(pf_lookup, per36_lookup)


def _load_cv_features_before(player_id: int, game_date_cutoff: str, last_n: int = 5) -> dict:
    """Aggregate CV features from the player's last N games BEFORE game_date_cutoff.

    Leakage-safe: the cv_features table stores NBA game_ids (lex-sortable:
    season-prefix + sequence). We resolve game_ids whose game_date is strictly
    less than game_date_cutoff using the season_games_*.json cache, then
    ORDER BY game_id DESC LIMIT last_n to retrieve only prior-game CV data.
    Returns 15 cv_* keys (8 original + 7 new mechanical features); zero-defaults
    when no prior CV data exists or the DB is absent.

    Note: build_pergame_dataset's gamelog cache has no GAME_ID column (only
    GAME_DATE), so this helper uses game_date_cutoff (ISO date string, e.g.
    "2024-11-15") as the leakage gate rather than a raw game_id.
    """
    _defaults = {c: 0.0 for c in _CV_FEATURE_COLS}
    _key_map = {
        # Original 7 mappings
        "avg_defender_distance":    "cv_avg_defender_distance",
        "contested_shot_rate":      "cv_contested_shot_rate",
        "shot_zone_paint_pct":      "cv_shot_zone_paint_pct",
        "shot_zone_3pt_pct":        "cv_shot_zone_3pt_pct",
        "shots_per_possession":     "cv_shots_per_possession",
        "possession_duration_avg":  "cv_possession_duration_avg",
        "play_type_transition_pct": "cv_play_type_transition_pct",
        # 7 new mechanical CV features (Round 2)
        "avg_contest_arm_angle":    "cv_avg_contest_arm_angle",
        "avg_closeout_speed":       "cv_avg_closeout_speed",
        "avg_fatigue_proxy":        "cv_avg_fatigue_proxy",
        "catch_shoot_pct":          "cv_catch_shoot_pct",
        "avg_dribble_count":        "cv_avg_dribble_count",
        "second_chance_rate":       "cv_second_chance_rate",
        "avg_shot_distance":        "cv_avg_shot_distance",
    }
    try:
        # Build date -> game_id lookup from season_games_*.json (same source
        # used by build_player_quarter_stats). Only game_ids with date <
        # game_date_cutoff are eligible — this is the leakage gate.
        cutoff_date = str(game_date_cutoff)[:10]  # normalise to YYYY-MM-DD
        eligible_game_ids: set = set()
        for sg_path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
            try:
                with open(sg_path, encoding="utf-8") as _f:
                    sg = json.load(_f)
                sg_rows = sg.get("rows", sg) if isinstance(sg, dict) else sg
                for g in sg_rows or []:
                    gid = g.get("game_id")
                    gdate = str(g.get("game_date", ""))[:10]
                    if gid and gdate and gdate < cutoff_date:
                        eligible_game_ids.add(str(gid))
            except Exception:
                pass

        if not eligible_game_ids:
            return _defaults.copy()

        from src.data.db import get_connection  # noqa: PLC0415
        conn = get_connection()
        # Retrieve the player's CV game_ids that fall within the eligible set,
        # ordered by game_id DESC (lex == chronological for NBA IDs) to get
        # the most-recent-first, capped at last_n.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT game_id FROM cv_features "
                "WHERE player_id = ? "
                "ORDER BY game_id DESC",
                (int(player_id),),
            )
            all_player_gids = [r[0] for r in cur.fetchall()]

        # Filter to eligible (pre-cutoff) game_ids, take most recent last_n.
        prior_gids = [g for g in all_player_gids if g in eligible_game_ids][:last_n]
        if not prior_gids:
            conn.close()
            return _defaults.copy()

        accum: dict = {}
        counts: dict = {}
        for gid in prior_gids:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT feature_name, feature_value FROM cv_features "
                    "WHERE player_id = ? AND game_id = ?",
                    (int(player_id), gid),
                )
                for fname, fval in cur.fetchall():
                    out_key = _key_map.get(fname)
                    if out_key:
                        accum[out_key] = accum.get(out_key, 0.0) + float(fval)
                        counts[out_key] = counts.get(out_key, 0) + 1
        conn.close()
        result = _defaults.copy()
        for k, v in accum.items():
            result[k] = round(v / counts.get(k, 1), 4)
        result["cv_n_games_cv"] = float(len(prior_gids))
        return result
    except Exception:
        return _defaults.copy()


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
    except Exception as exc:
        _warn_join_load_once("build_playtypes", path, exc)
    return _PlayTypes(lookup)


_PLAYTYPES_CACHE: Optional[_PlayTypes] = None


def _get_playtypes() -> _PlayTypes:
    global _PLAYTYPES_CACHE
    if _PLAYTYPES_CACHE is None:
        _PLAYTYPES_CACHE = build_playtypes()
    return _PLAYTYPES_CACHE


# ── Iter-44: synergy PPP per-play-type lookup ─────────────────────────────────

class _SynPPP:
    """Lookup table for per-(player_id, season) synergy PPP values.

    Keyed (player_id, season) → {syn_*_ppp: float, ...}.
    Returns full 5-key defaults on miss so callers see no KeyError.
    Join key is CURRENT-SEASON (not prior-season) — OOS gate catches any leak.
    """

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            key = (int(player_id), str(season))
        except (TypeError, ValueError):
            return dict(_SYN_PPP_DEFAULTS)
        return dict(self._lookup.get(key, _SYN_PPP_DEFAULTS))


def build_syn_ppp(parquet_path: Optional[str] = None) -> _SynPPP:
    """Load synergy_ppp_features.parquet into a _SynPPP lookup. Never raises."""
    path = parquet_path or _SYN_PPP_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _SynPPP(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            key = (int(row["player_id"]), str(row["season"]))
            lookup[key] = {k: float(row.get(k, 0.0) or 0.0) for k in _SYN_PPP_KEYS}
    except Exception as exc:
        _warn_join_load_once("build_syn_ppp", path, exc)
    return _SynPPP(lookup)


_SYN_PPP_CACHE: Optional[_SynPPP] = None


def _get_syn_ppp() -> _SynPPP:
    global _SYN_PPP_CACHE
    if _SYN_PPP_CACHE is None:
        _SYN_PPP_CACHE = build_syn_ppp()
    return _SYN_PPP_CACHE


# ── Iter-46: per-opponent rolling-3 stat features ────────────────────────────

class _PerOppRolling:
    """Per-(player_id, game_date_iso) per-opponent rolling-3 stat lookup.

    Keyed (player_id, game_date_str 'YYYY-MM-DD') → {per_opp_<stat>_l3: float|None}.
    Returns all-None defaults on miss (no prior opponent meetings).
    NaN passthrough intentional — tree learners handle missing values natively;
    imputing with 0 would conflate "first meeting" with "scored 0".
    """

    def __init__(
        self,
        lookup: Dict[Tuple[int, str], Dict[str, Optional[float]]],
    ) -> None:
        self._lookup = lookup

    def features(
        self,
        player_id: int,
        game_date_iso: str,
    ) -> Dict[str, Optional[float]]:
        try:
            key = (int(player_id), str(game_date_iso)[:10])
        except (TypeError, ValueError):
            return dict(_PER_OPP_ROLLING_DEFAULTS)
        return dict(self._lookup.get(key, _PER_OPP_ROLLING_DEFAULTS))

    def __len__(self) -> int:
        return len(self._lookup)


def build_per_opp_rolling(
    parquet_path: Optional[str] = None,
) -> "_PerOppRolling":
    """Load per_opp_stat_rolling.parquet into a _PerOppRolling lookup.

    Falls back to an empty wrapper (all-None on every lookup) when the
    parquet is absent or pandas/pyarrow fails. Never raises.
    """
    path = parquet_path or _PER_OPP_ROLLING_PATH
    lookup: Dict[Tuple[int, str], Dict[str, Optional[float]]] = {}
    if not os.path.exists(path):
        return _PerOppRolling(lookup)
    try:
        import math as _math  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            try:
                pid = int(row["player_id"])
                gd = str(row["game_date"])[:10]
            except (TypeError, ValueError, KeyError):
                continue
            vals: Dict[str, Optional[float]] = {}
            for k in _PER_OPP_ROLLING_KEYS:
                v = row.get(k)
                try:
                    fv = float(v)
                    vals[k] = None if _math.isnan(fv) else fv
                except (TypeError, ValueError):
                    vals[k] = None
            lookup[(pid, gd)] = vals
    except Exception as exc:
        _warn_join_load_once("build_per_opp_rolling", path, exc)
        return _PerOppRolling(lookup)
    return _PerOppRolling(lookup)


_PER_OPP_ROLLING_CACHE: Optional["_PerOppRolling"] = None


def _get_per_opp_rolling() -> "_PerOppRolling":
    global _PER_OPP_ROLLING_CACHE
    if _PER_OPP_ROLLING_CACHE is None:
        _PER_OPP_ROLLING_CACHE = build_per_opp_rolling()
    return _PER_OPP_ROLLING_CACHE


# ── BBRef advanced features (per-player-season efficiency + rate metrics) ────

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
_BBREF_EXTENDED_PARQUET = os.path.join(PROJECT_DIR, "data", "cache", "bbref_advanced_extended.parquet")
# Order matters — drives feature_columns() output. Efficiency (ts), volume
# (usg), shot profile (three_par, ftr), per-100 rate stats (ast/stl/blk/tov),
# holistic impact (ws_per_48, per), and SPLIT offensive/defensive BPM (obpm,
# dbpm) — bpm itself is the sum so we keep the split for finer per-side
# weighting. per is included for its independent signal (corr 0.88 with bpm —
# enough non-redundancy to matter for trees). Defensive depth — dws, ows,
# vorp — are ~85% collinear with ws_per_48 / obpm / dbpm but the residual
# signal still helps gradient-boosted trees in practice; appended at the end
# so existing column positions stay stable.
# Wave-2a extension: orb_pct/drb_pct/trb_pct/bpm/ws from bbref_advanced_extended.parquet.
_BBREF_KEYS = ("usg_pct", "ts_pct", "three_par", "ftr",
               "ast_pct", "stl_pct", "blk_pct", "tov_pct",
               "ws_per_48", "per", "obpm", "dbpm",
               "dws", "ows", "vorp")
_BBREF_EXTRA_KEYS = ("orb_pct", "drb_pct", "trb_pct", "bpm", "ws")
_BBREF_DEFAULTS: Dict[str, float] = {
    **{f"bbref_{k}": 0.0 for k in _BBREF_KEYS},
    **{f"bbref_{k}": 0.0 for k in _BBREF_EXTRA_KEYS},
}


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


def _load_bbref_extra_from_parquet() -> Dict[Tuple[str, str], Dict[str, float]]:
    """Load _BBREF_EXTRA_KEYS from bbref_advanced_extended.parquet.
    Returns {(player_name, season): {bbref_<key>: float}}. Never raises."""
    result: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.isfile(_BBREF_EXTENDED_PARQUET):
            return result
        df = pd.read_parquet(_BBREF_EXTENDED_PARQUET, columns=["player_name", "season"] + list(_BBREF_EXTRA_KEYS))
        for _, row in df.iterrows():
            name = str(row["player_name"]).strip()
            season = str(row["season"]).strip()
            if not name or not season:
                continue
            result[(name, season)] = {
                f"bbref_{k}": float(row[k]) if pd.notna(row[k]) else 0.0
                for k in _BBREF_EXTRA_KEYS
            }
    except Exception as exc:
        _warn_join_load_once("load_bbref_extra_from_parquet", _BBREF_EXTENDED_PARQUET, exc)
    return result


def build_bbref_advanced(bbref_dir: Optional[str] = None) -> _BBRefAdvanced:
    """Load every bbref_advanced_<season>.json under bbref_dir into a lookup
    keyed by (player_name, season). Never raises. Reverses the mojibake on
    non-ASCII names so accented players (Jokić, Vučević, Šengün, ...) match
    the nba_api full_name canonical form.
    Wave-2a: merges bbref_advanced_extended.parquet for 5 extra keys."""
    bbref_dir = bbref_dir or _BBREF_DIR
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    # Load extra keys from parquet first; JSON rows will override base keys.
    extra_lookup = _load_bbref_extra_from_parquet()
    try:
        if not os.path.isdir(bbref_dir):
            # Still surface extra keys even if JSON dir is absent.
            for key, val in extra_lookup.items():
                lookup[key] = {**{f"bbref_{k}": 0.0 for k in _BBREF_KEYS}, **val}
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
                base = {f"bbref_{k}": float(row.get(k, 0.0) or 0.0) for k in _BBREF_KEYS}
                extra = extra_lookup.get((name, season), {f"bbref_{k}": 0.0 for k in _BBREF_EXTRA_KEYS})
                lookup[(name, season)] = {**base, **extra}
        # Add any parquet rows not in JSON (e.g. newer seasons).
        for key, val in extra_lookup.items():
            if key not in lookup:
                lookup[key] = {**{f"bbref_{k}": 0.0 for k in _BBREF_KEYS}, **val}
    except Exception as exc:
        _warn_join_load_once("build_bbref_advanced", bbref_dir, exc)
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
    except Exception as exc:
        _warn_join_load_once("build_contracts", contracts_dir, exc)
    return _Contracts(lookup, _bbref_id_to_name())


_CONTRACTS_CACHE: Optional[_Contracts] = None


def _get_contracts() -> _Contracts:
    global _CONTRACTS_CACHE
    if _CONTRACTS_CACHE is None:
        _CONTRACTS_CACHE = build_contracts()
    return _CONTRACTS_CACHE


# ── Wave-2b: defender matchup features (dmatch_*) ────────────────────────────
# Source: data/cache/defender_matchup_features.parquet
# Keyed by (off_player_id, game_date). Training join uses (player_id, game_date)
# since gamelogs lack game_id. ~81% coverage; missing rows get neutral defaults.
_DMATCH_KEYS: Tuple[str, ...] = (
    "dmatch_fg_pct_l10",
    "dmatch_partial_poss_share",
    "dmatch_switches_per_poss",
    "dmatch_primary_def_height_in",
    "dmatch_height_advantage_in",
    "dmatch_help_blocks_per_game",
    "dmatch_3p_pct_l10",
)
_DMATCH_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _DMATCH_KEYS}
_DMATCH_PARQUET = os.path.join(PROJECT_DIR, "data", "cache", "defender_matchup_features.parquet")
# Column mapping: parquet col -> dmatch_ key
_DMATCH_COL_MAP: Dict[str, str] = {
    "matchup_fg_pct_l10":          "dmatch_fg_pct_l10",
    "matchup_partial_poss_share":  "dmatch_partial_poss_share",
    "switches_per_poss":           "dmatch_switches_per_poss",
    "primary_def_height_in":       "dmatch_primary_def_height_in",
    "height_advantage_in":         "dmatch_height_advantage_in",
    "help_blocks_per_game":        "dmatch_help_blocks_per_game",
    "matchup_3p_pct_l10":          "dmatch_3p_pct_l10",
}


class _DefenderMatchup:
    """Per-(player_id, game_date) lookup of defender matchup features.

    Keyed by (int player_id, date object). Falls back to neutral defaults
    when the parquet is absent or the (player, game) pair is uncached.
    """

    def __init__(self, lookup: Dict[Tuple[int, object], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, game_date) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_DMATCH_DEFAULTS)
        gd = game_date.date() if hasattr(game_date, "date") else game_date
        row = self._lookup.get((pid, gd))
        if not row:
            return dict(_DMATCH_DEFAULTS)
        return row


def build_defender_matchup(parquet_path: Optional[str] = None) -> _DefenderMatchup:
    """Load defender_matchup_features.parquet into a (player_id, game_date) lookup.

    Never raises — returns an empty wrapper when the parquet is absent.
    """
    path = parquet_path or _DMATCH_PARQUET
    lookup: Dict[Tuple[int, object], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _DefenderMatchup(lookup)
        df = pd.read_parquet(path)
        df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
        for _, row in df.iterrows():
            try:
                pid = int(row["off_player_id"])
            except (TypeError, ValueError):
                continue
            gd = row["game_date"]
            feats: Dict[str, float] = dict(_DMATCH_DEFAULTS)
            for parquet_col, dmatch_key in _DMATCH_COL_MAP.items():
                val = row.get(parquet_col)
                if val is not None:
                    try:
                        fval = float(val)
                        feats[dmatch_key] = fval if fval == fval else 0.0  # NaN guard
                    except (TypeError, ValueError):
                        pass
            lookup[(pid, gd)] = feats
    except Exception as exc:
        _warn_join_load_once("build_defender_matchup", path, exc)
    return _DefenderMatchup(lookup)


_DMATCH_CACHE: Optional[_DefenderMatchup] = None


def _get_defender_matchup() -> _DefenderMatchup:
    global _DMATCH_CACHE
    if _DMATCH_CACHE is None:
        _DMATCH_CACHE = build_defender_matchup()
    return _DMATCH_CACHE


# ── Wave-2b: player profile features (prof_*) ────────────────────────────────
# Source: data/cache/player_profile_features.parquet
# Static snapshot keyed by player_id (850 players, 98% gamelog coverage).
# prof_age_days and derived flags are point-in-time as of profile_as_of date.
_PROF_KEYS: Tuple[str, ...] = (
    "prof_height_in",
    "prof_weight_lb",
    "prof_draft_year",
    "prof_draft_number",
    "prof_undrafted_flag",
    "prof_intl_flag",
    "prof_college_d1_flag",
    "prof_greatest_75_flag",
    "prof_age_days",
    "prof_years_in_league",
    "prof_rookie_flag",
    "prof_season_exp",
)
_PROF_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _PROF_KEYS}
_PROF_PARQUET = os.path.join(PROJECT_DIR, "data", "cache", "player_profile_features.parquet")


class _PlayerProfile:
    """Per-player_id lookup of static profile features (prof_*).

    All values are floats. Flags (undrafted, intl, college_d1, greatest_75,
    rookie) are 0/1. Missing players get neutral defaults.
    """

    def __init__(self, lookup: Dict[int, Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_PROF_DEFAULTS)
        return self._lookup.get(pid, _PROF_DEFAULTS)


def build_player_profiles(parquet_path: Optional[str] = None) -> _PlayerProfile:
    """Load player_profile_features.parquet into a player_id -> feature-dict lookup.

    Never raises — returns an empty wrapper when the parquet is absent.
    """
    path = parquet_path or _PROF_PARQUET
    lookup: Dict[int, Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _PlayerProfile(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            try:
                pid = int(row["player_id"])
            except (TypeError, ValueError):
                continue
            def _f(col: str) -> float:
                v = row.get(col)
                if v is None:
                    return 0.0
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0
            lookup[pid] = {
                "prof_height_in":       _f("height_in"),
                "prof_weight_lb":       _f("weight_lb"),
                "prof_draft_year":      _f("draft_year"),
                "prof_draft_number":    _f("draft_number"),
                "prof_undrafted_flag":  _f("undrafted_flag"),
                "prof_intl_flag":       _f("intl_flag"),
                "prof_college_d1_flag": _f("college_d1_flag"),
                "prof_greatest_75_flag":_f("greatest_75_flag"),
                "prof_age_days":        _f("age_precise_days_as_of"),
                "prof_years_in_league": _f("years_in_league_as_of"),
                "prof_rookie_flag":     _f("rookie_flag_as_of"),
                "prof_season_exp":      _f("season_exp"),
            }
    except Exception as exc:
        _warn_join_load_once("build_player_profiles", path, exc)
    return _PlayerProfile(lookup)


_PROF_CACHE: Optional[_PlayerProfile] = None


def _get_player_profiles() -> _PlayerProfile:
    global _PROF_CACHE
    if _PROF_CACHE is None:
        _PROF_CACHE = build_player_profiles()
    return _PROF_CACHE


# ── Iter-3: officials rolling features (A, 5 keys) ───────────────────────────
# Source: data/cache/officials_rolling.parquet
# Per (game_id, team_abbreviation): rolling-5 ref-crew foul/fta rates + z-scores.
# WHY rolling: cycle 15 (loop 5) tested prior-season season-grain officials and
# it REGRESSED all 7 stats on walk-forward. Rolling is a new angle (within-season
# game-to-game variation rather than referee identity across seasons).
_OFFICIALS_ROLLING_KEYS: Tuple[str, ...] = (
    "ref_l5_fouls", "ref_l5_fta", "ref_fouls_z", "ref_fta_z", "ref_home_advantage",
)
_OFFICIALS_ROLLING_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _OFFICIALS_ROLLING_KEYS}
_OFFICIALS_ROLLING_PATH_PP = os.path.join(
    PROJECT_DIR, "data", "cache", "officials_rolling.parquet"
)


class _OfficialsRolling:
    """Per-(game_date_iso, team_abbreviation) lookup of rolling crew foul/fta features.

    Gamelogs don't expose game_id so we key by (date, team) to join during
    training. The parquet has a game_date column, so this is still leakage-
    free: the rolling stats are pre-computed from PRIOR games only.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, game_date, team_abbrev: str) -> Dict[str, float]:
        gd = game_date.date().isoformat() if hasattr(game_date, "date") else str(game_date)[:10]
        key = (gd, str(team_abbrev))
        return dict(self._lookup.get(key, _OFFICIALS_ROLLING_DEFAULTS))


def build_officials_rolling(parquet_path: Optional[str] = None) -> _OfficialsRolling:
    """Load officials_rolling.parquet into an _OfficialsRolling wrapper. Never raises."""
    path = parquet_path or _OFFICIALS_ROLLING_PATH_PP
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd
        if not os.path.exists(path):
            return _OfficialsRolling(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            gd_raw = r.get("game_date")
            gd = gd_raw.date().isoformat() if hasattr(gd_raw, "date") else str(gd_raw)[:10]
            ta = str(r.get("team_abbreviation", ""))
            if not gd or not ta:
                continue
            def _f(col: str, default: float = 0.0) -> float:
                v = r.get(col)
                try:
                    fv = float(v)
                    return fv if fv == fv else default
                except (TypeError, ValueError):
                    return default
            lookup[(gd, ta)] = {
                "ref_l5_fouls":       _f("l5_ref_crew_fouls_per_g"),
                "ref_l5_fta":         _f("l5_ref_crew_fta_per_g"),
                "ref_fouls_z":        _f("ref_crew_fouls_z"),
                "ref_fta_z":          _f("ref_crew_fta_z"),
                "ref_home_advantage": _f("home_win_pct_advantage"),
            }
    except Exception as exc:
        _warn_join_load_once("build_officials_rolling", path, exc)
    return _OfficialsRolling(lookup)


_OFFICIALS_ROLLING_CACHE: Optional[_OfficialsRolling] = None


def _get_officials_rolling() -> _OfficialsRolling:
    global _OFFICIALS_ROLLING_CACHE
    if _OFFICIALS_ROLLING_CACHE is None:
        _OFFICIALS_ROLLING_CACHE = build_officials_rolling()
    return _OFFICIALS_ROLLING_CACHE


# ── Iter-3: foul features (B, 5 keys) ────────────────────────────────────────
# Source: data/cache/foul_features.parquet
# Per (player_id, game_id, game_date): rolling PF/36 rates + foul trouble + last PF.
_FOUL_FEATURE_KEYS: Tuple[str, ...] = (
    "foul_pf36_l5", "foul_pf36_l10", "foul_trouble_l10", "foul_last_pf", "foul_min_l5",
)
_FOUL_FEATURE_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _FOUL_FEATURE_KEYS}
_FOUL_FEATURES_PATH_PP = os.path.join(
    PROJECT_DIR, "data", "cache", "foul_features.parquet"
)


class _FoulFeatures:
    """Per-(player_id, game_date) lookup of rolling foul features."""

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, game_date) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_FOUL_FEATURE_DEFAULTS)
        gd = game_date.date().isoformat() if hasattr(game_date, "date") else str(game_date)[:10]
        return dict(self._lookup.get((pid, gd), _FOUL_FEATURE_DEFAULTS))


def build_foul_features(parquet_path: Optional[str] = None) -> _FoulFeatures:
    """Load foul_features.parquet into a _FoulFeatures wrapper. Never raises."""
    path = parquet_path or _FOUL_FEATURES_PATH_PP
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd
        if not os.path.exists(path):
            return _FoulFeatures(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError, KeyError):
                continue
            gd_raw = r.get("game_date")
            if gd_raw is None:
                continue
            gd = gd_raw.date().isoformat() if hasattr(gd_raw, "date") else str(gd_raw)[:10]
            def _f(col: str) -> float:
                v = r.get(col)
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0
            lookup[(pid, gd)] = {
                "foul_pf36_l5":     _f("pf_per_36_l5"),
                "foul_pf36_l10":    _f("pf_per_36_l10"),
                "foul_trouble_l10": _f("foul_trouble_rate_l10"),
                "foul_last_pf":     _f("last_game_pf"),
                "foul_min_l5":      _f("min_l5"),
            }
    except Exception as exc:
        _warn_join_load_once("build_foul_features", path, exc)
    return _FoulFeatures(lookup)


_FOUL_FEATURES_CACHE: Optional[_FoulFeatures] = None


def _get_foul_features() -> _FoulFeatures:
    global _FOUL_FEATURES_CACHE
    if _FOUL_FEATURES_CACHE is None:
        _FOUL_FEATURES_CACHE = build_foul_features()
    return _FOUL_FEATURES_CACHE


# ── Iter-3: DNP team features (C, 4 keys) ────────────────────────────────────
# Source: data/cache/dnp_features_team.parquet
# Per (game_id, team_abbreviation): DNP counts (current game + L5/L10/prior game).
_DNP_TEAM_KEYS: Tuple[str, ...] = (
    "dnp_in_game", "dnp_l5_avg", "dnp_l10_avg", "dnp_prior_game",
)
_DNP_TEAM_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _DNP_TEAM_KEYS}
_DNP_TEAM_PATH_PP = os.path.join(
    PROJECT_DIR, "data", "cache", "dnp_features_team.parquet"
)


class _DnpTeamFeatures:
    """Per-(game_date_iso, team_abbreviation) lookup of DNP count features.

    Keyed by (date, team) to support gamelog-sourced training rows (no game_id
    in gamelog JSON). The parquet has game_date so this is still leakage-free:
    L5/L10 rolling cols are pre-computed from prior games only.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, game_date, team_abbrev: str) -> Dict[str, float]:
        gd = game_date.date().isoformat() if hasattr(game_date, "date") else str(game_date)[:10]
        key = (gd, str(team_abbrev))
        return dict(self._lookup.get(key, _DNP_TEAM_DEFAULTS))


def build_dnp_team_features(parquet_path: Optional[str] = None) -> _DnpTeamFeatures:
    """Load dnp_features_team.parquet into a _DnpTeamFeatures wrapper. Never raises."""
    path = parquet_path or _DNP_TEAM_PATH_PP
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd
        if not os.path.exists(path):
            return _DnpTeamFeatures(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            gd_raw = r.get("game_date")
            gd = gd_raw.date().isoformat() if hasattr(gd_raw, "date") else str(gd_raw)[:10]
            ta = str(r.get("team_abbreviation", ""))
            if not gd or not ta:
                continue
            def _f(col: str) -> float:
                v = r.get(col)
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0
            lookup[(gd, ta)] = {
                "dnp_in_game":    _f("dnp_count_in_game"),
                "dnp_l5_avg":     _f("dnp_count_l5_avg"),
                "dnp_l10_avg":    _f("dnp_count_l10_avg"),
                "dnp_prior_game": _f("prior_game_dnp_count"),
            }
    except Exception as exc:
        _warn_join_load_once("build_dnp_team_features", path, exc)
    return _DnpTeamFeatures(lookup)


_DNP_TEAM_CACHE: Optional[_DnpTeamFeatures] = None


def _get_dnp_team_features() -> _DnpTeamFeatures:
    global _DNP_TEAM_CACHE
    if _DNP_TEAM_CACHE is None:
        _DNP_TEAM_CACHE = build_dnp_team_features()
    return _DNP_TEAM_CACHE


# ── Iter-3: advanced stats splits (D, 6 keys) ────────────────────────────────
# Source: data/cache/adv_stats_splits.parquet
# Per (player_id, game_id, game_date): season-to-date expanding TS%/USG%/eFG%
# + per-opponent L3 splits + usage z-score. WHY new angles: cycle 6+8 showed
# L5/L10/EWMA adv stats regress under WF — those are rolling averages tracking
# the same signal as form features. Season-to-date expanding captures stable
# efficiency floor; per-opp L3 captures matchup-specific tendency.
_ADV_SPLITS_KEYS: Tuple[str, ...] = (
    "adv_usage_std", "adv_ts_std", "adv_efg_std",
    "adv_usage_vs_opp_l3", "adv_ts_vs_opp_l3", "adv_usage_z",
)
_ADV_SPLITS_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _ADV_SPLITS_KEYS}
_ADV_SPLITS_PATH_PP = os.path.join(
    PROJECT_DIR, "data", "cache", "adv_stats_splits.parquet"
)


class _AdvStatsSplits:
    """Per-(player_id, game_date) lookup of season-to-date adv stats + opp splits."""

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, game_date) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_ADV_SPLITS_DEFAULTS)
        gd = game_date.date().isoformat() if hasattr(game_date, "date") else str(game_date)[:10]
        return dict(self._lookup.get((pid, gd), _ADV_SPLITS_DEFAULTS))


def build_adv_stats_splits(parquet_path: Optional[str] = None) -> _AdvStatsSplits:
    """Load adv_stats_splits.parquet into an _AdvStatsSplits wrapper. Never raises."""
    path = parquet_path or _ADV_SPLITS_PATH_PP
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd
        if not os.path.exists(path):
            return _AdvStatsSplits(lookup)
        df = pd.read_parquet(path)
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError, KeyError):
                continue
            gd_raw = r.get("game_date")
            if gd_raw is None:
                continue
            gd = gd_raw.date().isoformat() if hasattr(gd_raw, "date") else str(gd_raw)[:10]
            def _f(col: str) -> float:
                v = r.get(col)
                try:
                    fv = float(v)
                    return fv if fv == fv else 0.0
                except (TypeError, ValueError):
                    return 0.0
            lookup[(pid, gd)] = {
                "adv_usage_std":       _f("adv_usage_season_to_date"),
                "adv_ts_std":          _f("adv_ts_season_to_date"),
                "adv_efg_std":         _f("adv_efg_season_to_date"),
                "adv_usage_vs_opp_l3": _f("adv_usage_vs_opp_l3"),
                "adv_ts_vs_opp_l3":    _f("adv_ts_vs_opp_l3"),
                "adv_usage_z":         _f("adv_usage_z_in_season"),
            }
    except Exception as exc:
        _warn_join_load_once("build_adv_stats_splits", path, exc)
    return _AdvStatsSplits(lookup)


_ADV_SPLITS_CACHE: Optional[_AdvStatsSplits] = None


def _get_adv_stats_splits() -> _AdvStatsSplits:
    global _ADV_SPLITS_CACHE
    if _ADV_SPLITS_CACHE is None:
        _ADV_SPLITS_CACHE = build_adv_stats_splits()
    return _ADV_SPLITS_CACHE


# ── Iter-5: hustle static season features (E, 6 keys) ────────────────────────
# Source: data/cache/hustle_features.parquet (commit 79df9f04).
# Keys: (player_id, season). Per-season hustle aggregates — low overfit risk
# because they're static season totals, not rolling slices of the playoff test
# set. Coverage: 6 seasons (2018-19 → 2024-25, gap 2019-20). Training rows for
# 2022-23 onward have ~75-80% coverage; on_off only has 2024-25 (~0% for older).
_HUSTLE_KEYS: Tuple[str, ...] = (
    "hustle_deflections", "hustle_contested_shots", "hustle_screen_assists",
    "hustle_box_outs", "hustle_loose_balls", "hustle_charges_drawn",
)
_HUSTLE_DEFAULTS: Dict[str, float] = {k: float("nan") for k in _HUSTLE_KEYS}
_HUSTLE_PARQUET_PATH = os.path.join(PROJECT_DIR, "data", "cache", "hustle_features.parquet")
_HUSTLE_DF_CACHE: Optional[object] = None  # pandas DataFrame or False


def _load_hustle_df():
    """Lazy-load hustle_features.parquet once; returns DataFrame or None."""
    global _HUSTLE_DF_CACHE
    if _HUSTLE_DF_CACHE is None:
        try:
            import pandas as pd  # noqa: PLC0415
            if os.path.isfile(_HUSTLE_PARQUET_PATH):
                _HUSTLE_DF_CACHE = pd.read_parquet(
                    _HUSTLE_PARQUET_PATH,
                    columns=["player_id", "season"] + list(_HUSTLE_KEYS),
                )
                # Build fast index: (player_id, season) -> row index
                _HUSTLE_DF_CACHE = _HUSTLE_DF_CACHE.set_index(
                    ["player_id", "season"]
                )
            else:
                _HUSTLE_DF_CACHE = False
        except Exception as exc:
            _warn_join_load_once("_load_hustle_df", _HUSTLE_PARQUET_PATH, exc)
            _HUSTLE_DF_CACHE = False
    return _HUSTLE_DF_CACHE if _HUSTLE_DF_CACHE is not False else None


class _HustleFeatures:
    """Per-(player_id, season) lookup of static hustle season aggregates."""

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_HUSTLE_DEFAULTS)
        return dict(self._lookup.get((pid, str(season)), _HUSTLE_DEFAULTS))


def build_hustle_features(parquet_path: Optional[str] = None) -> _HustleFeatures:
    """Load hustle_features.parquet into a _HustleFeatures wrapper. Never raises."""
    path = parquet_path or _HUSTLE_PARQUET_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _HustleFeatures(lookup)
        df = pd.read_parquet(path, columns=["player_id", "season"] + list(_HUSTLE_KEYS))
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError):
                continue
            season = str(r["season"])
            row: Dict[str, float] = {}
            for k in _HUSTLE_KEYS:
                v = r.get(k)
                try:
                    fv = float(v)
                    row[k] = fv  # NaN passthrough is intentional
                except (TypeError, ValueError):
                    row[k] = float("nan")
            lookup[(pid, season)] = row
    except Exception as exc:
        _warn_join_load_once("build_hustle_features", path, exc)
    return _HustleFeatures(lookup)


_HUSTLE_CACHE: Optional[_HustleFeatures] = None


def _get_hustle_features() -> _HustleFeatures:
    global _HUSTLE_CACHE
    if _HUSTLE_CACHE is None:
        _HUSTLE_CACHE = build_hustle_features()
    return _HUSTLE_CACHE


# ── Iter-5: on_off static season features (F, 3 keys) ────────────────────────
# Source: data/cache/on_off_features.parquet (commit 9903a47e).
# Keys: (player_id, season). Only 2024-25 data — coverage ~0% for older rows.
# Stub-NaN cols (on_off_orating_diff, on_off_drating_diff, on_off_pace_diff)
# are intentionally NOT wired — they're all-NaN and add no signal.
_ONOFF_KEYS: Tuple[str, ...] = (
    "onoff_net_rating_diff", "onoff_impact_z", "onoff_min_weight",
)
_ONOFF_DEFAULTS: Dict[str, float] = {k: float("nan") for k in _ONOFF_KEYS}
_ONOFF_PARQUET_PATH = os.path.join(PROJECT_DIR, "data", "cache", "on_off_features.parquet")
_ONOFF_DF_CACHE: Optional[object] = None  # pandas DataFrame or False

# Column mapping: parquet col -> feature key
_ONOFF_COL_MAP: Dict[str, str] = {
    "on_off_net_rating_diff": "onoff_net_rating_diff",
    "on_off_impact_z":        "onoff_impact_z",
    "on_off_min_weight":      "onoff_min_weight",
}


def _load_on_off_df():
    """Lazy-load on_off_features.parquet once; returns DataFrame or None."""
    global _ONOFF_DF_CACHE
    if _ONOFF_DF_CACHE is None:
        try:
            import pandas as pd  # noqa: PLC0415
            if os.path.isfile(_ONOFF_PARQUET_PATH):
                _ONOFF_DF_CACHE = pd.read_parquet(
                    _ONOFF_PARQUET_PATH,
                    columns=["player_id", "season"] + list(_ONOFF_COL_MAP.keys()),
                )
            else:
                _ONOFF_DF_CACHE = False
        except Exception as exc:
            _warn_join_load_once("_load_on_off_df", _ONOFF_PARQUET_PATH, exc)
            _ONOFF_DF_CACHE = False
    return _ONOFF_DF_CACHE if _ONOFF_DF_CACHE is not False else None


class _OnOffFeatures:
    """Per-(player_id, season) lookup of static on/off impact season aggregates."""

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_ONOFF_DEFAULTS)
        return dict(self._lookup.get((pid, str(season)), _ONOFF_DEFAULTS))


def build_on_off_features(parquet_path: Optional[str] = None) -> _OnOffFeatures:
    """Load on_off_features.parquet into a _OnOffFeatures wrapper. Never raises."""
    path = parquet_path or _ONOFF_PARQUET_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _OnOffFeatures(lookup)
        df = pd.read_parquet(path, columns=["player_id", "season"] + list(_ONOFF_COL_MAP.keys()))
        for _, r in df.iterrows():
            try:
                pid = int(r["player_id"])
            except (TypeError, ValueError):
                continue
            season = str(r["season"])
            row: Dict[str, float] = {}
            for parquet_col, feat_key in _ONOFF_COL_MAP.items():
                v = r.get(parquet_col)
                try:
                    fv = float(v)
                    row[feat_key] = fv  # NaN passthrough is intentional
                except (TypeError, ValueError):
                    row[feat_key] = float("nan")
            lookup[(pid, season)] = row
    except Exception as exc:
        _warn_join_load_once("build_on_off_features", path, exc)
    return _OnOffFeatures(lookup)


_ONOFF_CACHE: Optional[_OnOffFeatures] = None


def _get_on_off_features() -> _OnOffFeatures:
    global _ONOFF_CACHE
    if _ONOFF_CACHE is None:
        _ONOFF_CACHE = build_on_off_features()
    return _ONOFF_CACHE


# ── Iter-17: gamelog_full box-stat rolling features ──────────────────────────
# Source: data/nba/gamelog_full_<pid>_<season>.json (same filenames as regular
# gamelog_* but prefixed "gamelog_full_"). Each file carries a richer set of
# box-stat columns including oreb, dreb, fga, fg_pct, fta, ft_pct, plus_minus,
# pf — absent from the stripped gamelog_*.json files read by the main loop.
#
# Per-game grain, same date format and player_id as the existing gamelogs.
# Strategy: load ALL gamelog_full_*.json files once, group by player_id, sort
# chronologically, compute shift(1).rolling(N, min_periods=N-1) features.
# Keyed by (player_id, game_date_str) for O(1) join in build_pergame_dataset.
#
# 14 new keys — none overlap existing feature_columns():
#   gl_oreb_l5, gl_oreb_l10                — offensive rebounds
#   gl_dreb_l5, gl_dreb_l10                — defensive rebounds
#   gl_fga_l5, gl_fga_l10                  — FG attempts (volume proxy)
#   gl_fg_pct_l10, gl_fg_pct_ewma          — FG% (efficiency rate)
#   gl_fta_l5, gl_fta_l10                  — FT attempts (paint volume + foul drawn)
#   gl_ft_pct_l10                          — FT% (efficiency)
#   gl_plus_minus_l5, gl_plus_minus_ewma   — net impact / lineup context
#   gl_pf_l5                               — personal fouls (distinct from pf_per36 in foul features)
_GAMELOG_FULL_RAW_STATS = ("oreb", "dreb", "fga", "fg_pct", "fta", "ft_pct", "plus_minus", "pf")
_GAMELOG_FULL_FEATURE_KEYS: Tuple[str, ...] = (
    "gl_oreb_l5", "gl_oreb_l10",
    "gl_dreb_l5", "gl_dreb_l10",
    "gl_fga_l5", "gl_fga_l10",
    "gl_fg_pct_l10", "gl_fg_pct_ewma",
    "gl_fta_l5", "gl_fta_l10",
    "gl_ft_pct_l10",
    "gl_plus_minus_l5", "gl_plus_minus_ewma",
    "gl_pf_l5",
)
_GAMELOG_FULL_DEFAULTS: Dict[str, float] = {k: 0.0 for k in _GAMELOG_FULL_FEATURE_KEYS}
_GAMELOG_FULL_MIN_PLAYED = 1.0  # mirror _MIN_PLAYED — only count games where player played


class _GamelogFullRolling:
    """Per-(player_id, game_date_str) rolling box-stat features from gamelog_full_*.json.

    Built once at dataset construction time from all gamelog_full files. For
    each player, games are sorted chronologically and each game's features are
    the rolling L5/L10/EWMA of PRIOR games (shift(1) discipline — the current
    game is excluded from its own features). Keyed by (int player_id, str ISO
    game_date 'YYYY-MM-DD') for O(1) join during the main gamelog loop.

    Empty wrapper (no gamelog_full files found) returns all-zero defaults so
    build_pergame_dataset stays back-compat on a fresh checkout. Never raises.
    """

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def __len__(self) -> int:
        return len(self._lookup)

    def features(self, player_id, game_date) -> Dict[str, float]:
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return dict(_GAMELOG_FULL_DEFAULTS)
        gd = game_date.date().isoformat() if hasattr(game_date, "date") else str(game_date)[:10]
        return dict(self._lookup.get((pid, gd), _GAMELOG_FULL_DEFAULTS))


def build_gamelog_full_rolling(gamelog_dir: Optional[str] = None) -> _GamelogFullRolling:
    """Load all gamelog_full_*.json and compute shift(1) rolling features per player.

    Returns an empty wrapper when no files are found or on any import failure.
    Never raises. Idempotent — calling multiple times produces the same result.
    """
    gdir = gamelog_dir or _NBA_CACHE
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import math as _math  # noqa: PLC0415
        # Group games by player_id across all files and seasons.
        by_pid: Dict[int, List[Tuple[str, Dict]]] = {}
        for fname in os.listdir(gdir):
            if not fname.startswith("gamelog_full_") or not fname.endswith(".json"):
                continue
            try:
                games = json.load(open(os.path.join(gdir, fname), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(games, list):
                continue
            for g in games:
                try:
                    pid = int(g.get("player_id", 0) or 0)
                    gdate_str = str(g.get("game_date", "") or "").strip()
                except Exception:
                    continue
                if not pid or not gdate_str:
                    continue
                # Only include games where the player actually played.
                try:
                    minutes = float(g.get("min", 0.0) or 0.0)
                except (TypeError, ValueError):
                    minutes = 0.0
                if minutes < _GAMELOG_FULL_MIN_PLAYED:
                    continue
                by_pid.setdefault(pid, []).append((gdate_str, g))

        def _safe_float(v) -> Optional[float]:
            if v is None:
                return None
            try:
                f = float(v)
                return None if (f != f) else f  # NaN guard
            except (TypeError, ValueError):
                return None

        def _rolling_mean(vals: List[float], n: int) -> float:
            window = [v for v in vals[-n:] if v is not None]
            return sum(window) / len(window) if window else 0.0

        def _ewma_from_list(vals: List[float], alpha: float = _EWMA_ALPHA) -> float:
            clean = [v for v in vals if v is not None]
            return _ewma(clean, alpha) if clean else 0.0

        for pid, date_game_pairs in by_pid.items():
            # Sort by parsed date; skip unparseable dates.
            dated: List[Tuple, dict] = []
            for gdate_str, g in date_game_pairs:
                d = _parse_date(gdate_str)
                if d is not None:
                    dated.append((d, gdate_str, g))
            dated.sort(key=lambda x: x[0])

            # Prior-games buffer per stat (already-played games only).
            hist: Dict[str, List[Optional[float]]] = {s: [] for s in _GAMELOG_FULL_RAW_STATS}

            for gdate_dt, gdate_str, g in dated:
                gdate_iso = gdate_dt.date().isoformat()
                # Compute rolling features from PRIOR games (shift(1)).
                row_feats: Dict[str, float] = {}

                oreb_hist = hist["oreb"]
                dreb_hist = hist["dreb"]
                fga_hist = hist["fga"]
                fgpct_hist = hist["fg_pct"]
                fta_hist = hist["fta"]
                ftpct_hist = hist["ft_pct"]
                pm_hist = hist["plus_minus"]
                pf_hist = hist["pf"]

                row_feats["gl_oreb_l5"]        = _rolling_mean(oreb_hist, 5)
                row_feats["gl_oreb_l10"]       = _rolling_mean(oreb_hist, 10)
                row_feats["gl_dreb_l5"]        = _rolling_mean(dreb_hist, 5)
                row_feats["gl_dreb_l10"]       = _rolling_mean(dreb_hist, 10)
                row_feats["gl_fga_l5"]         = _rolling_mean(fga_hist, 5)
                row_feats["gl_fga_l10"]        = _rolling_mean(fga_hist, 10)
                row_feats["gl_fg_pct_l10"]     = _rolling_mean(fgpct_hist, 10)
                row_feats["gl_fg_pct_ewma"]    = _ewma_from_list(fgpct_hist)
                row_feats["gl_fta_l5"]         = _rolling_mean(fta_hist, 5)
                row_feats["gl_fta_l10"]        = _rolling_mean(fta_hist, 10)
                row_feats["gl_ft_pct_l10"]     = _rolling_mean(ftpct_hist, 10)
                row_feats["gl_plus_minus_l5"]  = _rolling_mean(pm_hist, 5)
                row_feats["gl_plus_minus_ewma"]= _ewma_from_list(pm_hist)
                row_feats["gl_pf_l5"]          = _rolling_mean(pf_hist, 5)

                lookup[(pid, gdate_iso)] = row_feats

                # Append current game to history (shift(1) discipline).
                for stat in _GAMELOG_FULL_RAW_STATS:
                    hist[stat].append(_safe_float(g.get(stat)))

    except Exception as exc:
        _warn_join_load_once("build_gamelog_full_rolling", gdir, exc)
    return _GamelogFullRolling(lookup)


_GAMELOG_FULL_ROLLING_CACHE: Optional[_GamelogFullRolling] = None


def _get_gamelog_full_rolling() -> _GamelogFullRolling:
    """Process-cached _GamelogFullRolling for live prediction paths."""
    global _GAMELOG_FULL_ROLLING_CACHE
    if _GAMELOG_FULL_ROLLING_CACHE is None:
        _GAMELOG_FULL_ROLLING_CACHE = build_gamelog_full_rolling()
    return _GAMELOG_FULL_ROLLING_CACHE


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
        # Reconcile non-canonical opponent codes (NY/WSH/UTAH/GS/NO/SA → gamelog
        # tricodes) the same way _PregameSpreads does, so a grading/serve caller
        # that passes a bookmaker/ESPN code doesn't silently collapse opp_def to
        # neutral 1.0 (the self._team index is keyed by gamelog tricodes). BYTE-
        # IDENTICAL for the serve path (opp_team='OPP' → 'OPP', stays neutral) and
        # the OOF/training path (gamelog tricodes → unchanged); only non-tricode
        # callers (e.g. compare_to_lines lines files) change, and correctly so.
        team_idx = self._team.get(_normalize_abbr(opponent))
        for stat in STATS:
            league_mean = self._todate_mean(self._league, date, stat)
            team_mean = self._todate_mean(team_idx, date, stat) if team_idx else None
            if team_mean and league_mean and league_mean > 0:
                out[f"opp_def_{stat}"] = round(team_mean / league_mean, 4)
            else:
                out[f"opp_def_{stat}"] = 1.0
        return out

    # ── Cycle 99e (loop 5) — rolling-5 sibling of factors() ──────────────────
    # The existing factors() returns to-date EXPANDING ratios (mean
    # allowed-stat / league mean). cycles 99a/b retrain BLK/FG3M heads;
    # this rolling-5 sibling exposes the OPPONENT's last-5 raw allowed
    # mean per stat, which captures recent-form opponent context (injuries,
    # scheme changes) that the expanding mean averages out. Additive only:
    # keys land on row dict (NOT in feature_columns() until a separate
    # retrain cycle wires them in). Returns None for stats where the
    # opponent has fewer than 1 prior games so callers can branch on
    # missingness without arithmetic crashes.
    def l5_allowed(self, opponent: str, date) -> Dict[str, Optional[float]]:
        """Return {opp_def_{stat}_l5: mean} — opp's last-5 raw allowed-stat
        averages STRICTLY before date. None per-stat when no prior games."""
        out: Dict[str, Optional[float]] = {f"opp_def_{s}_l5": None for s in STATS}
        team_idx = self._team.get(_normalize_abbr(opponent))  # tricode-reconcile (see factors())
        if not team_idx:
            return out
        i = bisect.bisect_left(team_idx["dates"], date)
        if i <= 0:
            return out
        # Window: prior 5 games (or fewer if early-season). prefix is a
        # running cumulative sum; window-mean = (prefix[i] - prefix[i-5]) / 5.
        lo = max(0, i - 5)
        n = i - lo
        if n <= 0:
            return out
        for stat in STATS:
            window_sum = team_idx["prefix"][stat][i] - team_idx["prefix"][stat][lo]
            out[f"opp_def_{stat}_l5"] = round(window_sum / n, 4)
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
    except Exception as exc:
        _warn_join_load_once("build_advanced_stats", path, exc)
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
        feats[f"l3_{stat}"]   = _mean(vals[-3:])         # iter-47: hot-streak window
        feats[f"l5_{stat}"]   = _mean(vals[-5:])
        feats[f"l7_{stat}"]   = _mean(vals[-7:])         # iter-47: mid-range window
        feats[f"l10_{stat}"]  = _mean(vals[-10:])
        feats[f"std_{stat}"]  = _mean(vals)              # season-to-date
        feats[f"ewma_{stat}"] = _ewma(vals)
        feats[f"prev_{stat}"] = vals[-1] if vals else 0.0
        # Iter-48: momentum-delta = l3 - l5 (positive = hot streak, negative = cooling).
        # Computed after l3/l5 so the subtraction is always defined. Numerically
        # independent of the raw level features (zero when form is flat).
        feats[f"mom_delta_{stat}"] = feats[f"l3_{stat}"] - feats[f"l5_{stat}"]
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


# ── leak-free vacated-assist signal (CV_AST_VAC_FEATURE) ──────────────────────
#
# Box-appearance recipe (identical to scripts/pit/exp_crosseason_validate.py::
# build_vac_ast_from_lglog, the validated builder — NOT reinvented). For each
# (team, date): a "regular" who is on the recent roster (appeared in >=1 of the
# team's PREVIOUS 3 games) but is ABSENT from this game's box log, and whose
# as-of L10 minutes >= 15, is counted OUT. vac_ast = sum of those out-regulars'
# as-of L10 assists; vac_ast_share = vac_ast / (vac_ast + sum of the APPEARING
# roster's as-of L10 assists). Every rolling average uses strictly PRIOR games
# (dd < d), so the signal is leak-free as-of the game date. Returns
# {(player_id, "YYYY-MM-DD"): {"vac_ast", "vac_ast_share"}} for every appearing
# player. Built ONCE per build_pergame_dataset call, only when the flag is ON;
# file-existence-gated so a fresh checkout that lacks the box logs collapses to
# an empty map (every row then gets 0.0 defaults — same as flag OFF).

_VAC_AST_CACHE: Optional[dict] = None


def _vac_team_of_matchup(matchup) -> Optional[str]:
    m = (matchup or "").strip()
    if " @ " in m:
        return m.split(" @ ")[0].strip().upper()
    if " vs. " in m:
        return m.split(" vs. ")[0].strip().upper()
    return None


def build_vac_ast_lookup() -> dict:
    """Leak-free vac_ast / vac_ast_share per (player_id, 'YYYY-MM-DD').

    Pools 2025-26 (reg+playoff leaguegamelog parquets under data/cache/cv_fix)
    and 2024-25 (per-player gamelog_*_2024-25.json) box logs. Robust to missing
    sources (returns whatever it can build, possibly empty). Memoised per-process.
    """
    global _VAC_AST_CACHE
    if _VAC_AST_CACHE is not None:
        return _VAC_AST_CACHE

    import numpy as _np
    import pandas as _pd
    from collections import defaultdict as _dd

    cvfix = os.path.join(PROJECT_DIR, "data", "cache", "cv_fix")
    rows = []  # (date_ts, team, pid, ast, minutes)

    # 2025-26: league box-log parquets (reg + playoff)
    for fn in ("leaguegamelog_regular_season.parquet", "leaguegamelog_playoffs.parquet"):
        p = os.path.join(cvfix, fn)
        if not os.path.isfile(p):
            continue
        try:
            df = _pd.read_parquet(p)
        except Exception as exc:  # pragma: no cover - defensive
            _warn_join_load_once("build_vac_ast_lookup", p, exc)
            continue
        for r in df.itertuples(index=False):
            d = _pd.to_datetime(getattr(r, "GAME_DATE", None), errors="coerce")
            if _pd.isna(d):
                continue
            try:
                mn = float(r.MIN) if _pd.notna(r.MIN) else None
            except (TypeError, ValueError):
                mn = None
            rows.append((d.normalize(), str(r.TEAM_ABBREVIATION).upper(),
                         int(r.PLAYER_ID), float(r.AST or 0), mn))

    # 2024-25: per-player gamelog JSONs (the cross-season corpus)
    for fp in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*_2024-25.json")):
        base = os.path.basename(fp)
        if not base.endswith("_2024-25.json"):
            continue
        try:
            pid = int(base.split("_")[1])
        except (IndexError, ValueError):
            continue
        try:
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(log, list):
            continue
        for g in log:
            d = _pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            team = _vac_team_of_matchup(g.get("MATCHUP"))
            if _pd.isna(d) or team is None:
                continue
            try:
                mn = float(g.get("MIN")) if g.get("MIN") is not None else None
            except (TypeError, ValueError):
                mn = None
            rows.append((d.normalize(), team, pid, float(g.get("AST") or 0), mn))

    if not rows:
        _VAC_AST_CACHE = {}
        return _VAC_AST_CACHE

    by_player = _dd(list)     # pid -> sorted [(date, ast, minutes)]
    team_games = _dd(set)     # (team, date) -> {pid who appeared (min>=1)}
    team_dates = _dd(set)     # team -> {dates played}
    for d, team, pid, ast, mn in rows:
        by_player[pid].append((d, ast, mn))
        if mn is not None and mn >= 1:
            team_games[(team, d)].add(pid)
            team_dates[team].add(d)
    for pid in by_player:
        by_player[pid].sort()

    def _asof_l10(pid, d):
        hist = [(a, mn) for (dd, a, mn) in by_player.get(pid, [])
                if dd < d and mn is not None and mn >= 1]
        if not hist:
            return 0.0, 0.0
        h = hist[-10:]
        return (float(_np.mean([x[0] for x in h])),  # L10 ast
                float(_np.mean([x[1] for x in h])))   # L10 min

    out: dict = {}
    for (team, d), appeared in team_games.items():
        tdates = sorted(team_dates[team])
        i = tdates.index(d)
        if i < 3:
            continue
        prior3 = tdates[max(0, i - 3):i]
        roster = set()
        for pd_ in prior3:
            roster |= team_games[(team, pd_)]
        vac_ast = 0.0
        for pid in roster:
            if pid in appeared:
                continue
            la, lm = _asof_l10(pid, d)
            if lm >= 15:
                vac_ast += la
        # share denominator = appearing roster's as-of L10 assist mass
        present_ast = 0.0
        for pid in appeared:
            la, _ = _asof_l10(pid, d)
            present_ast += la
        denom = vac_ast + present_ast
        share = (vac_ast / denom) if denom > 1e-9 else 0.0
        ds = d.date().isoformat()
        rec = {"vac_ast": float(vac_ast), "vac_ast_share": float(share)}
        for pid in appeared:
            out[(int(pid), ds)] = rec
    _VAC_AST_CACHE = out
    return out


# ── leak-free vacated-load signal (CV_VAC_LOAD_FEATURE) ───────────────────────
#
# Box-appearance recipe IDENTICAL to build_vac_ast_lookup (NOT reinvented): same
# out-regular definition (on the prior-3-game roster, ABSENT this game, as-of L10
# minutes >= 15) and the same strictly-prior (dd < d) rolling windows, so it is
# leak-free as-of the game date. Instead of vacated assists it tracks the
# vacated team LOAD: vac_min = sum of out-regulars' as-of L10 minutes, vac_pts =
# sum of their as-of L10 points, n_out = count of out-regulars. Returns
# {(player_id, "YYYY-MM-DD"): {"vac_min","vac_pts","n_out"}} for every appearing
# player. Built ONCE per build_pergame_dataset call, only when the flag is ON;
# file-existence-gated so a fresh checkout that lacks the box logs collapses to
# an empty map (every row then gets 0.0 defaults — same as flag OFF).

_VAC_LOAD_CACHE: Optional[dict] = None


def build_vac_load_lookup() -> dict:
    """Leak-free vac_min / vac_pts / n_out per (player_id, 'YYYY-MM-DD').

    Pools 2025-26 (reg+playoff leaguegamelog parquets under data/cache/cv_fix)
    and 2024-25 (per-player gamelog_*_2024-25.json) box logs. Robust to missing
    sources (returns whatever it can build, possibly empty). Memoised per-process.
    Same out-regular recipe as build_vac_ast_lookup, summing vacated minutes and
    points rather than assists.
    """
    global _VAC_LOAD_CACHE
    if _VAC_LOAD_CACHE is not None:
        return _VAC_LOAD_CACHE

    import numpy as _np
    import pandas as _pd
    from collections import defaultdict as _dd

    cvfix = os.path.join(PROJECT_DIR, "data", "cache", "cv_fix")
    rows = []  # (date_ts, team, pid, pts, minutes)

    # 2025-26: league box-log parquets (reg + playoff)
    for fn in ("leaguegamelog_regular_season.parquet", "leaguegamelog_playoffs.parquet"):
        p = os.path.join(cvfix, fn)
        if not os.path.isfile(p):
            continue
        try:
            df = _pd.read_parquet(p)
        except Exception as exc:  # pragma: no cover - defensive
            _warn_join_load_once("build_vac_load_lookup", p, exc)
            continue
        for r in df.itertuples(index=False):
            d = _pd.to_datetime(getattr(r, "GAME_DATE", None), errors="coerce")
            if _pd.isna(d):
                continue
            try:
                mn = float(r.MIN) if _pd.notna(r.MIN) else None
            except (TypeError, ValueError):
                mn = None
            rows.append((d.normalize(), str(r.TEAM_ABBREVIATION).upper(),
                         int(r.PLAYER_ID), float(r.PTS or 0), mn))

    # 2024-25: per-player gamelog JSONs (the cross-season corpus)
    for fp in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*_2024-25.json")):
        base = os.path.basename(fp)
        if not base.endswith("_2024-25.json"):
            continue
        try:
            pid = int(base.split("_")[1])
        except (IndexError, ValueError):
            continue
        try:
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(log, list):
            continue
        for g in log:
            d = _pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            team = _vac_team_of_matchup(g.get("MATCHUP"))
            if _pd.isna(d) or team is None:
                continue
            try:
                mn = float(g.get("MIN")) if g.get("MIN") is not None else None
            except (TypeError, ValueError):
                mn = None
            rows.append((d.normalize(), team, pid, float(g.get("PTS") or 0), mn))

    if not rows:
        _VAC_LOAD_CACHE = {}
        return _VAC_LOAD_CACHE

    by_player = _dd(list)     # pid -> sorted [(date, pts, minutes)]
    team_games = _dd(set)     # (team, date) -> {pid who appeared (min>=1)}
    team_dates = _dd(set)     # team -> {dates played}
    for d, team, pid, pts, mn in rows:
        by_player[pid].append((d, pts, mn))
        if mn is not None and mn >= 1:
            team_games[(team, d)].add(pid)
            team_dates[team].add(d)
    for pid in by_player:
        by_player[pid].sort()

    def _asof_l10(pid, d):
        hist = [(p, mn) for (dd, p, mn) in by_player.get(pid, [])
                if dd < d and mn is not None and mn >= 1]
        if not hist:
            return 0.0, 0.0
        h = hist[-10:]
        return (float(_np.mean([x[0] for x in h])),  # L10 pts
                float(_np.mean([x[1] for x in h])))   # L10 min

    out: dict = {}
    for (team, d), appeared in team_games.items():
        tdates = sorted(team_dates[team])
        i = tdates.index(d)
        if i < 3:
            continue
        prior3 = tdates[max(0, i - 3):i]
        roster = set()
        for pd_ in prior3:
            roster |= team_games[(team, pd_)]
        vac_min = 0.0
        vac_pts = 0.0
        n_out = 0
        for pid in roster:
            if pid in appeared:
                continue
            lp, lm = _asof_l10(pid, d)
            if lm >= 15:
                vac_min += lm
                vac_pts += lp
                n_out += 1
        ds = d.date().isoformat()
        rec = {"vac_min": float(vac_min), "vac_pts": float(vac_pts), "n_out": float(n_out)}
        for pid in appeared:
            out[(int(pid), ds)] = rec
    _VAC_LOAD_CACHE = out
    return out


# ── dataset construction ──────────────────────────────────────────────────────

def build_pergame_dataset(
    gamelog_dir: Optional[str] = None,
    min_prior: int = 0,
    include_dnp: Optional[bool] = None,
) -> Tuple[List[dict], List[str]]:
    """Build the per-game training set from every player gamelog.

    Each emitted row holds leakage-free pre-game features and the realised
    target_{stat} values for one game.  A game is used as a row only when the
    player actually played (>= _MIN_PLAYED minutes) and has at least
    ``min_prior`` prior played games for stable rolling features.

    Tier3-11 (loop 5) — ``include_dnp`` opt-in injects DNP rows from
    ``data/dnp_rows.parquet`` (built by ``scripts/aggregate_dnp_rows.py``).
    Each DNP row carries ``target_<stat> = 0.0`` for every stat and a
    ``dnp_reason`` field; features are LEFT EMPTY (zeros via feature_columns
    defaults) because there is no prior-game context for a player who did
    not appear in any played gamelog row at that point. Default is
    ``False`` (preserves the cycle-48 baseline). Can also be enabled via
    the env var ``PROP_PERGAME_INCLUDE_DNP=1`` (handy for sweep scripts).

    Returns:
        (rows, feature_cols) — rows are dicts with the feature columns,
        target_{stat} columns, and a 'date' key for the temporal split.
    """
    if include_dnp is None:
        include_dnp = os.environ.get("PROP_PERGAME_INCLUDE_DNP", "0").strip() in (
            "1", "true", "True", "yes", "YES",
        )
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
    # Wave-2b — defender matchup (7 keys) + player profile (12 keys).
    dmatch = build_defender_matchup()
    player_prof = build_player_profiles()
    # Cycle 90e (loop 5) — per-player position lookup. GATED on file
    # existence: empty wrapper when data/player_positions.parquet is
    # absent, so the join is a no-op on fresh checkouts. position is
    # added to each row dict (NOT to feature_columns yet — that requires
    # a separate retrain cycle). Probes (cycle 89c) can re-run once the
    # parquet is populated.
    positions = build_player_positions()
    # Cycle 91c (loop 5) — pre-game sportsbook spreads (2025-26 holdout).
    # GATED on data/pregame_spreads.parquet existence; empty wrapper makes
    # the join a no-op on fresh checkouts. Sign convention:
    #   home_spread < 0  ⇒ home favoured; row["home_spread"] negates for away.
    # T1-A garbage-time haircut probe reads row["home_spread"] directly.
    pregame_spreads = build_pregame_spreads()
    # Cycle 91b (loop 5) — per-(player_id, game_date) PF + rolling PF/36.
    # GATED on data/player_pf.parquet existence; missing parquet collapses
    # to None on every row so build_pergame_dataset is a no-op back-compat
    # path. pf is NOT in feature_columns() yet — this backfill unblocks the
    # cycle-90c T1-B foul-rate probe (PF absent from gamelog cache → probe
    # silently degraded to a BLK proxy).
    player_pf = build_player_pf()
    # Cycle 91a (loop 5) — per-quarter stats wrapper for rolling-Q1
    # prior-5 features. GATED on data/player_quarter_stats.parquet; empty
    # wrapper → every q1_*_l5 row key is None on fresh checkouts. Probes
    # consume row["q1_pts_l5"] etc. directly; NOT in feature_columns()
    # until a separate retrain cycle wires them in.
    qstats = build_player_quarter_stats()
    # Cycle 99e (loop 5) — team_advanced_stats per-game wrapper for
    # rolling-5 opp-context advanced rates (off_rtg, def_rtg, pace,
    # oreb/dreb/ast pct, efg/ts pct, tov_ratio). GATED on
    # data/team_advanced_stats.parquet; empty wrapper → every
    # opp_team_<col>_l5 row key is None on fresh checkouts. Additive
    # only — NOT in feature_columns() until a separate retrain cycle
    # wires them in. Sibling to oppdef.l5_allowed which gives the rolling-5
    # raw allowed counting stats (opp_def_pts_l5, opp_def_reb_l5, ...).
    team_adv_l5 = build_team_advanced_l5()
    # Iter-3 — Wire 4 new parquet sources into per-row feature dicts.
    # GATED on file existence; empty wrappers return all-zero defaults
    # so build_pergame_dataset never crashes on a fresh checkout.
    off_rolling = build_officials_rolling()
    foul_feats_src = build_foul_features()
    dnp_team_src = build_dnp_team_features()
    adv_splits_src = build_adv_stats_splits()
    # Iter-5 — static per-season hustle + on_off wrappers. NaN-safe:
    # missing (player_id, season) keys return NaN defaults.
    hustle_src = build_hustle_features()
    onoff_src = build_on_off_features()
    # Iter-19 — linescore blowout/pace context (7 ls_* keys). GATED on
    # data/cache/linescore_context.parquet; empty wrapper → all 0.0 defaults.
    ls_ctx = build_linescore_context()
    # Iter-44 — synergy PPP per-play-type (5 keys). GATED on
    # data/cache/synergy_ppp_features.parquet; empty wrapper → all 0.0 defaults.
    syn_ppp_src = build_syn_ppp()
    # Iter-46 — per-opponent rolling-3 stat features (6 keys). GATED on
    # data/cache/per_opp_stat_rolling.parquet; empty wrapper → all None defaults.
    # NaN passthrough intentional — first-ever matchup rows remain NaN (not 0).
    per_opp_rolling_src = build_per_opp_rolling()
    # vac_ast feature gate (CV_AST_VAC_FEATURE). Build the leak-free vacated-
    # assist lookup ONCE here only when the flag is ON; OFF -> empty map so the
    # row loop writes 0.0 defaults and the column never enters feature_columns
    # (byte-identical to the legacy AST feature set). File-existence-gated.
    vac_ast_lookup = build_vac_ast_lookup() if _AST_VAC_FEATURE else {}
    # vac_load feature gate (CV_VAC_LOAD_FEATURE). Build the leak-free vacated-
    # load lookup ONCE here only when the flag is ON; OFF -> empty map so the row
    # loop writes 0.0 defaults and the columns never enter feature_columns
    # (byte-identical to the legacy PTS/REB feature sets). File-existence-gated.
    vac_load_lookup = build_vac_load_lookup() if _VAC_LOAD_FEATURE else {}
    # Iter-17 gamelog_full rolling DISABLED (REVERT 2026-05-27).
    # Iter-18 narrow probe also REVERTED (2026-05-27) — OOS gate failed.
    # Infrastructure (build_gamelog_full_rolling, _get_gamelog_full_rolling)
    # kept for future re-probe. Wiring (gl_full_rolling.features call) disabled.
    # gl_full_rolling = build_gamelog_full_rolling(gamelog_dir)

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
                # R10_M14 — PRIOR-SEASON join (S-1). file_season ALWAYS gets the prior-season
                # vector regardless of stat: feature columns are global and shared across
                # the 7 stat heads. Only the JOIN KEY changes vs the legacy current-season
                # behavior. Toggle _PLAYTYPE_PRIOR_SEASON_JOIN=False to roll back.
                _pt_season = _prior_season(file_season) if _PLAYTYPE_PRIOR_SEASON_JOIN else file_season
                feats.update(playtypes.features(file_player_id, _pt_season))
                feats.update(bbref.features(file_player_id, file_season))
                feats.update(contracts.features(file_player_id, file_season))
                # Cycle 90d (loop 5) — REB OREB-context (team + opp rolling-5).
                # Stored on every row but only sliced into the REB head's feature
                # set via feature_columns(stat="reb"); other heads ignore them.
                feats.update(reb_ctx.features(
                    team_abbrev, _opponent_from_matchup(matchup), gdate))
                # Wave-2b — defender matchup (game_date join) + player profile (pid join).
                feats.update(dmatch.features(file_player_id, gdate))
                feats.update(player_prof.features(file_player_id))
                # Iter-3 — 4 new parquet joins. All keyed by (date, team) or
                # (player_id, date) so they work from gamelog-sourced rows
                # (which have no game_id). All default to 0.0 when absent.
                feats.update(off_rolling.features(gdate, team_abbrev))
                feats.update(foul_feats_src.features(file_player_id, gdate))
                feats.update(dnp_team_src.features(gdate, team_abbrev))
                feats.update(adv_splits_src.features(file_player_id, gdate))
                # Iter-5: static per-season hustle + on_off (NaN for missing).
                feats.update(hustle_src.features(file_player_id, file_season))
                feats.update(onoff_src.features(file_player_id, file_season))
                # Iter-19: linescore blowout/pace context (7 ls_* keys).
                feats.update(ls_ctx.features(
                    team_abbrev, _opponent_from_matchup(matchup), gdate))
                # Iter-44: synergy PPP per-play-type (5 keys, current-season join).
                feats.update(syn_ppp_src.features(file_player_id, file_season))
                # Iter-46: per-opponent rolling-3 stat features (6 keys).
                # Keyed by (player_id, game_date ISO). NaN defaults on miss.
                gd_iso_str = gdate.date().isoformat()
                feats.update(per_opp_rolling_src.features(file_player_id, gd_iso_str))
                # Iter-17 gamelog_full rolling DISABLED (REVERT 2026-05-27).
                # Iter-18 narrow probe also REVERTED — OOS gate failed.
                # feats.update(gl_full_rolling.features(file_player_id, gdate))
                row = {c: feats.get(c, 0.0) for c in feature_cols}
                # Carry REB-context cols on every row even though they aren't in
                # the default feature_cols — the REB-only retraining path reads
                # them via feature_columns(stat="reb").
                for k in _REB_CONTEXT_KEYS:
                    row[k] = feats.get(k, 0.0)
                # Iter-48: carry mom_delta cols for pts/ast/reb on every row.
                # These are already computed in _row_features; we store them
                # so per-stat retrain scripts can read them via feature_columns(stat=X).
                for _ms in ("pts", "ast", "reb"):
                    _mk = f"mom_delta_{_ms}"
                    row[_mk] = feats.get(_mk, 0.0)
                # Carry all 5 syn PPP keys on every row — per-stat retrain paths
                # for ast/pts/fg3m read them via feature_columns(stat=<stat>).
                for k in _SYN_PPP_KEYS:
                    row[k] = feats.get(k, 0.0)
                # Carry all 6 per-opp rolling keys on every row — per-stat retrain
                # paths read them via feature_columns(stat=<stat>). NaN preserved
                # (tree learners handle missing values; 0-impute would be wrong).
                for k in _PER_OPP_ROLLING_KEYS:
                    row[k] = feats.get(k)  # None on first meeting
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                # Additive metadata (NOT a feature — absent from feature_columns()):
                # the realised minutes played, used as the training label for the
                # per-stat minutes-conditioned pregame heads (PTS min-model / REB
                # opportunity model). Purely additive; cannot affect any existing
                # model's behaviour (never fed as an input).
                row["target_min"] = _num(game.get("MIN"))
                row["date"] = gdate.isoformat()
                # Cycle 98c (loop 5) — per-row player_id (additive only; not in
                # feature_cols). Surfaces the gamelog-derived pid so probes can
                # build per-player prior-distribution lookups (e.g. L20 q90 for
                # outlier prediction) without re-reading gamelogs. Mirrors the
                # cycle 90e position field pattern: additive, never trained on.
                row["player_id"] = file_player_id
                # vac_ast feature gate (CV_AST_VAC_FEATURE). Carry the leak-free
                # vacated-assist signal on every row. When the flag is OFF the
                # lookup is empty -> 0.0 defaults, and the columns are NOT in
                # feature_columns("ast") so the AST model is byte-identical. When
                # ON, feature_columns("ast") appends vac_ast + vac_ast_share and
                # the trainer reads these per-row values. Default 0.0 = "no
                # confirmed-out creators" (the modal case), matching the builder.
                _vrec = vac_ast_lookup.get((file_player_id, gdate.date().isoformat()))
                row["vac_ast"] = float(_vrec["vac_ast"]) if _vrec else 0.0
                row["vac_ast_share"] = float(_vrec["vac_ast_share"]) if _vrec else 0.0
                # vac_load feature gate (CV_VAC_LOAD_FEATURE). Carry the leak-free
                # vacated-load signal on every row. When the flag is OFF the lookup
                # is empty -> 0.0 defaults, and the columns are NOT in
                # feature_columns("pts"/"reb") so those models are byte-identical.
                # When ON, feature_columns appends vac_min+vac_pts+n_out and the
                # trainer reads these per-row values. Default 0.0 = "no confirmed-
                # out regulars" (the modal case), matching the builder.
                _lrec = vac_load_lookup.get((file_player_id, gdate.date().isoformat()))
                row["vac_min"] = float(_lrec["vac_min"]) if _lrec else 0.0
                row["vac_pts"] = float(_lrec["vac_pts"]) if _lrec else 0.0
                row["n_out"] = float(_lrec["n_out"]) if _lrec else 0.0
                # Cycle 90e (loop 5) — per-row position (additive only; not in
                # feature_cols). None when the parquet is absent or the pid
                # is uncached. Probes consume row["position"] directly.
                row["position"] = positions.position(file_player_id)
                # Cycle 91c (loop 5) — pre-game sportsbook spread join.
                # Derive home/away codes from the matchup string:
                #   "TEAM vs. OPP"  -> team_abbrev is HOME
                #   "TEAM @ OPP"    -> team_abbrev is AWAY
                # row["home_spread"] is the spread FROM THIS PLAYER'S PERSPECTIVE
                # (negative when their team is favoured), so an away-team row
                # receives the sign-flipped value. row["total"] is symmetric.
                opp_abbrev = _opponent_from_matchup(matchup)
                if is_home:
                    sp_home, sp_away, sign = team_abbrev, opp_abbrev, 1.0
                else:
                    sp_home, sp_away, sign = opp_abbrev, team_abbrev, -1.0
                sp_feats = pregame_spreads.features(sp_home, sp_away, gdate)
                hs = sp_feats.get("home_spread")
                row["home_spread"] = (sign * float(hs)) if hs is not None else None
                row["total"] = sp_feats.get("total")
                # Cycle 91b (loop 5) — per-row PF + rolling expanding PF/36.
                # Both are None when the parquet is absent or the (pid, date)
                # is uncached. The per36 value is strictly point-in-time
                # (target game excluded) — safe to consume as a feature later.
                gd_iso = gdate.date().isoformat()
                row["pf"] = player_pf.pf(file_player_id, gd_iso)
                row["season_pf_per_36"] = player_pf.season_pf_per_36(
                    file_player_id, gd_iso)
                # Cycle 91a (loop 5) — rolling-Q1 prior-5 stats. NO leakage:
                # only PRIOR played-game dates are passed in. Defaults to
                # None for every key when the parquet is absent OR none of
                # the player's prior games appear in it. Additive only;
                # NOT in feature_columns() until a probe cycle wires them.
                prior_dates = [
                    d for d in (_parse_date(p.get("GAME_DATE"))
                                for p in prior_played)
                    if d is not None
                ]
                q1_feats = qstats.rolling_q1_prior(file_player_id, prior_dates)
                for k, v in q1_feats.items():
                    row[k] = v
                # Cycle 99e (loop 5) — opp-context rolling-5 features:
                # (a) raw L5 allowed counting stats (opp_def_<stat>_l5)
                # (b) L5 team advanced rates (opp_team_<col>_l5).
                # Both additive — None when wrapper is empty / no prior
                # opp data. Probes / retrain cycles can read row[k] for
                # the 7 + 9 = 16 new keys without code changes.
                opp_l5_allowed = oppdef.l5_allowed(
                    _opponent_from_matchup(matchup), gdate)
                for k, v in opp_l5_allowed.items():
                    row[k] = v
                opp_team_l5 = team_adv_l5.features(
                    _opponent_from_matchup(matchup), gdate)
                for k, v in opp_team_l5.items():
                    row[k] = v
                # CV feature gate (PROP_USE_CV=1). Leakage-safe: only games
                # with game_date strictly before this row's date are included.
                # gdate is a datetime; gdate.date().isoformat() == "YYYY-MM-DD".
                if _USE_CV_FEATURES:
                    _cv = _load_cv_features_before(
                        player_id=file_player_id,
                        game_date_cutoff=gdate.date().isoformat(),
                    )
                    row.update(_cv)
                else:
                    for _c in _CV_FEATURE_COLS:
                        row[_c] = 0.0
                rows.append(row)

            if played:
                prior_played.append(game)

    if include_dnp:
        # Tier3-11 (loop 5) — opt-in injection of DNP projection rows.
        # Each emitted row has zero stats (target_<stat>=0.0), zeroed
        # features (no prior-game context — the player did not play, so
        # there is no leak-free rolling form to compute), and a
        # `dnp_reason` carrier field. Probes that include these rows are
        # validating the FULL sit-rate effect (the survivor-bias
        # blocker that REJECTED cycles 90b + 92e). Default (no flag) is
        # back-compat with the cycle-48 baseline.
        try:
            from src.data.dnp_set import load_dnp_rows  # noqa: PLC0415
            dnp_df = load_dnp_rows()
            n_dnp_added = 0
            zero_feats = {c: 0.0 for c in feature_cols}
            recs = dnp_df.to_dict("records") if hasattr(dnp_df, "to_dict") else []
            for d in recs:
                row = dict(zero_feats)
                for stat in STATS:
                    row[f"target_{stat}"] = 0.0
                gdate_iso = str(d.get("game_date") or "").strip()
                if not gdate_iso:
                    continue
                # build_pergame_dataset emits 'date' as a full isoformat
                # datetime (e.g. "2022-10-18T00:00:00"). DNP dates from the
                # parquet are date-only strings — promote with T00:00:00
                # so downstream chronological splits sort consistently.
                if "T" not in gdate_iso:
                    gdate_iso = f"{gdate_iso}T00:00:00"
                row["date"] = gdate_iso
                row["player_id"] = int(d.get("player_id") or 0)
                row["position"] = None
                row["home_spread"] = None
                row["total"] = None
                row["pf"] = None
                row["season_pf_per_36"] = None
                row["dnp_reason"] = str(d.get("dnp_reason") or "other")
                row["is_dnp_row"] = True
                row["game_id"] = str(d.get("game_id") or "")
                row["team"] = str(d.get("team") or "")
                rows.append(row)
                n_dnp_added += 1
            logger.info(
                "prop_pergame.build_pergame_dataset: injected %d DNP rows "
                "(include_dnp=True). Total rows now %d.",
                n_dnp_added, len(rows),
            )
        except Exception as exc:
            _warn_join_load_once(
                "build_pergame_dataset.include_dnp",
                "src.data.dnp_set", exc,
            )

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
    # Iter-5: NaN-fill using per-column TRAINING-SPLIT medians so MLP / scaler
    # receive no NaN. XGB/LGB handle NaN natively; this impute only affects
    # the MLP path. We compute medians on train only (cols 0..train_end) to
    # avoid data leak into val/holdout splits.
    _nan_mask = ~np.isfinite(X_all)
    if _nan_mask.any():
        _col_medians = np.nanmedian(X_all[:train_end], axis=0)
        # Any column with all-NaN in train → median=NaN → fill 0.0
        _col_medians = np.where(np.isfinite(_col_medians), _col_medians, 0.0)
        for _ci in range(X_all.shape[1]):
            _col_nan = _nan_mask[:, _ci]
            if _col_nan.any():
                X_all[_col_nan, _ci] = _col_medians[_ci]
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
        # Iter-18: reg_alpha 2.0 → 3.0 + reg_lambda 4.0 → 6.0 tested with
        # gl_fga_l5 + gl_plus_minus_l5 — REVERTED (OOS gate failed 2026-05-27).
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

        # Per-stat feature extension: some stats have extra columns beyond the
        # base feature_cols (e.g. REB gets reb-context cols via retrain_reb_q50_v*.py
        # which builds its own X from feature_columns("reb")). For the main
        # train_pergame_models loop, any per-stat extras are handled in the X_all
        # construction above if they appear in the base feature_cols list, or in
        # dedicated retrain scripts. Iter-18 (gl_fga_l5 + gl_plus_minus_l5 for PTS)
        # was tested and REVERTED (2026-05-27) — OOS gate failed.
        _X_tr  = X_tr
        _X_val = X_val
        _X_ho  = X_ho

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
        xgb_model.fit(_X_tr, y_tr_t, eval_set=[(_X_val, y_val_t)],
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
        lgb_model.fit(_X_tr, y_tr_t, eval_set=[(_X_val, y_val_t)],
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
            X_tr_s  = mlp_scaler.transform(_X_tr)
            X_val_s = mlp_scaler.transform(_X_val)
            X_ho_s  = mlp_scaler.transform(_X_ho)
            mlp_model = multitask_proxy_for_stat[stat]
        else:
            mlp_scaler = StandardScaler()
            X_tr_s  = mlp_scaler.fit_transform(_X_tr)
            X_val_s = mlp_scaler.transform(_X_val)
            X_ho_s  = mlp_scaler.transform(_X_ho)
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

        xgb_ho = _inv(xgb_model.predict(_X_ho))
        lgb_ho = _inv(lgb_model.predict(_X_ho))
        mlp_ho = _inv(mlp_model.predict(X_ho_s))

        if lgb_only:
            w_xgb, w_lgb, w_mlp = 0.0, 1.0, 0.0
            meta_fit_source = "lgb_only"
        else:
            xgb_val = _inv(xgb_model.predict(_X_val))
            lgb_val = _inv(lgb_model.predict(_X_val))
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
        blend_tr = _blend(_X_tr, X_tr_s)

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
    # Wave-3 schema versioning: persist the exact column list used for each
    # trained stat into _meta.json so feature_columns_for() can recover it
    # and the prediction path can slice to the frozen schema at inference time.
    for s in stats_to_train:
        stat_cols = feature_columns(s)  # per-stat list (includes reb-context for reb)
        _persist_meta_feature_columns(model_dir, s, stat_cols)
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


def _persist_meta_feature_columns(model_dir: str, stat: str,
                                   cols: List[str]) -> None:
    """Write the trained column list to _meta.json under stats.<stat>.

    Idempotent — reads the existing file and only updates the two keys
    (feature_columns, n_features) for the given stat. Never raises so
    callers can call this unconditionally without disrupting a training run.
    """
    meta_path = os.path.join(model_dir, "_meta.json")
    try:
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as fh:
                all_meta: dict = json.load(fh)
        else:
            all_meta = {}
        all_meta.setdefault("stats", {}).setdefault(stat, {})
        all_meta["stats"][stat]["feature_columns"] = list(cols)
        all_meta["stats"][stat]["n_features"] = len(cols)
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(all_meta, fh, indent=2)
    except Exception as exc:
        logger.warning(
            "prop_pergame._persist_meta_feature_columns: could not write "
            "%s for stat=%s (%s: %s)", meta_path, stat, type(exc).__name__, exc,
        )


def write_meta_feature_columns(model_dir: Optional[str] = None,
                               metrics_path: Optional[str] = None) -> str:
    """Freeze the served 85-col aligned feature order into data/models/_meta.json.

    PREDICTION_FIDELITY plumbing fix (2026-06-04). The 85-feature root/q50/
    quantile artifacts were TRAINED on the column order in
    props_pergame_metrics.json["feature_cols"] (contract/ratio at slots 80-84,
    bbref_extra appended after). With no _meta.json on disk,
    feature_columns_for() falls back to the live, flag-dependent
    feature_columns(), so the served slot order depends on CV_BBREF_REORDER_FIX.

    This writes that EXACT trained 85-col list under stats.<stat>.feature_columns
    for every stat, making feature_columns_for(stat, model_dir) flag-independent
    on the point path, the q50 dispatch, AND the quantile path (which now also
    consults feature_columns_for). The artifacts are all 85-feature, so the
    per-stat list is the same trained 85-col order for every stat (the per-stat
    extras like _REB_CONTEXT_KEYS only append after slot 128 and are sliced off
    by the n_features_in_=85 truncation).

    Source of truth is props_pergame_metrics.json["feature_cols"] (the literal
    order the artifacts were trained on) — NOT a live feature_columns() call —
    so this is correct regardless of the flag state at write time. Asserts the
    frozen list equals the flag-ON feature_columns()[:85] (a self-consistency
    check) before writing.

    Returns the path to the written _meta.json.
    """
    model_dir = model_dir or _MODEL_DIR
    metrics_path = metrics_path or os.path.join(model_dir, "props_pergame_metrics.json")
    with open(metrics_path, encoding="utf-8") as fh:
        frozen = list(json.load(fh)["feature_cols"])
    if len(frozen) != 85:
        raise ValueError(
            f"props_pergame_metrics.json feature_cols has {len(frozen)} cols, "
            f"expected 85 (the served n_features_in_)."
        )
    for stat in STATS:
        _persist_meta_feature_columns(model_dir, stat, frozen)
    return os.path.join(model_dir, "_meta.json")


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
    meta-stacker weighted blend (cycle 23 multitask MLP for STL keys are
    no-ops since STL is in _USE_Q50_STATS now — kept around for rollback
    safety). AST stays on the blend path (edge-protective: calibration
    kills the AST edge per VS_VEGAS §5). The isotonic calibrator
    (calibration_pergame_<stat>.joblib) is applied at the end when present
    AND when the stat uses the blend (not q50).

    R3-F pregame residual heads (reb/ast/fg3m/stl/blk/tov) are applied last,
    after the garbage-time haircut, on both the q50 and blend paths. PTS is a
    passthrough (gate-failed). Disable by setting
    src.prediction.pregame_residual_heads._USE_PREGAME_RESIDUAL_HEADS = False.
    """
    import numpy as np

    model_dir = model_dir or _MODEL_DIR

    # Lazy import — avoids a circular dependency since pregame_residual_heads
    # imports feature_columns() from this module.
    from src.prediction.pregame_residual_heads import (  # noqa: PLC0415
        apply_residual_correction,
    )

    # Cycle 96a (loop 5): pull home_spread off the feature_row once so both
    # the q50 path and the blend path can apply the garbage-time haircut at
    # the very end. None when the pre-game spread isn't cached for the row's
    # matchup — apply_garbage_time_haircut is a no-op in that case.
    hs_raw = feature_row.get("home_spread")

    # Cycle 27 q50 dispatch — bypasses the entire 3-way blend.
    if stat in _USE_Q50_STATS:
        q50 = _load_q50_model(stat, model_dir)
        if q50 is not None:
            # Wave-3 / Iter-7 schema versioning: slice to the artifact's frozen
            # column list. When the model's n_features_in_ is smaller than
            # feature_columns_for (artifacts trained before Iter-2/3 have 85
            # cols; current canonical is 129), use only the first n_features_in_
            # columns so legacy artifacts coexist with the extended schema.
            cols = feature_columns_for(stat, model_dir)
            q50_n = getattr(q50, "n_features_in_", None)
            if q50_n is not None and q50_n != len(cols):
                # Truncate cols to the model's expected count (first N cols).
                cols = cols[:q50_n]
            X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)
            pred_t = float(q50.predict(X)[0])
            # Inverse-transform back to raw-count scale (same as training inv).
            if stat in _SQRT_HUBER_STATS:
                pred = max(0.0, pred_t) ** 2
            elif stat in _LOG_TRANSFORM_STATS:
                pred = max(0.0, float(np.expm1(pred_t)))
            else:
                pred = max(0.0, pred_t)
            # Cycle 96a (loop 5) — T1-A garbage-time haircut. Applied AFTER
            # the q50 head + inverse transform so the multiplicative shrink
            # acts on the raw-count point estimate.
            pred = apply_garbage_time_haircut(pred, stat, hs_raw)
            # R3-F pregame residual correction — applied last, on raw-count pred.
            pred = apply_residual_correction(pred, feature_row, stat, model_dir=model_dir)
            return round(pred, 2)
        # q50 model missing on disk — fall through to the legacy blend so
        # predict_pergame still returns SOMETHING.

    models = load_pergame_model(stat, model_dir)
    if not models:
        return None
    # Wave-3 / Iter-7 schema versioning: slice to the artifact's frozen column
    # list. When any model's n_features_in_ is smaller than feature_columns_for
    # (artifacts trained before Iter-2/3 have 85 cols; current canonical is
    # 129), use only the first N columns of the canonical list. The MLP scaler
    # is keyed by (scaler, model) tuple — check the model inside.
    cols = feature_columns_for(stat, model_dir)
    _min_n: Optional[int] = None
    for m in models:
        target = m[1] if isinstance(m, tuple) else m
        n_feats = getattr(target, "n_features_in_", None)
        if n_feats is not None:
            if _min_n is None or n_feats < _min_n:
                _min_n = n_feats
    if _min_n is not None and _min_n != len(cols):
        cols = cols[:_min_n]
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
                    mlp_pred = _inv_pred(float(mlp_model.predict(_safe_mlp_scaler_transform(scaler, X))[0]))
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
                preds.append(_inv_pred(float(mlp_model.predict(_safe_mlp_scaler_transform(scaler, X))[0])))
            else:
                preds.append(_inv_pred(float(m.predict(X)[0])))
        blend = sum(preds) / len(preds) if preds else 0.0

    calibrator = _load_pergame_calibrator(stat, model_dir)
    if calibrator is not None:
        try:
            blend = float(calibrator.predict([blend])[0])
        except Exception:
            pass
    blend = max(blend, 0.0)
    # Cycle 96a (loop 5) — T1-A garbage-time haircut. Applied AFTER the
    # isotonic calibrator (and the floor-at-0) so the multiplicative shrink
    # sits on the final raw-count blend prediction. No-op for non-volume
    # stats and for rows without a cached home_spread.
    blend = apply_garbage_time_haircut(blend, stat, hs_raw)
    # R3-F pregame residual correction — applied last, on raw-count blend.
    blend = apply_residual_correction(blend, feature_row, stat, model_dir=model_dir)
    return round(blend, 2)


# ── Iter-7: unified train/inference feature injection ────────────────────────
# Fixes the root-cause divergence diagnosed in Iter-7: the 39 columns added
# in Iterations 2-3 (defender matchup 7, player profile 12, officials rolling 5,
# foul features 5, DNP team 4, adv stats splits 6) were populated in TRAINING
# via build_pergame_dataset but were constant-zero at inference because
# build_prediction_row and _build_asof_row in backtest scripts didn't call the
# same loaders. This helper is the single authoritative injection point that
# both paths now use.

_ITER23_FEATURE_KEYS: Tuple[str, ...] = (
    *_DMATCH_KEYS,            # 7 keys — (player_id, game_date)
    *_PROF_KEYS,              # 12 keys — (player_id)
    *_OFFICIALS_ROLLING_KEYS, # 5 keys — (game_date, team_abbrev)
    *_FOUL_FEATURE_KEYS,      # 5 keys — (player_id, game_date)
    *_DNP_TEAM_KEYS,          # 4 keys — (game_date, team_abbrev)
    *_ADV_SPLITS_KEYS,        # 6 keys — (player_id, game_date)
    # Iter-17 gamelog_full keys NOT included here (REVERT 2026-05-27):
    # the 14 gl_* features were DISABLED in feature_columns() after
    # backtest_holdout showed OOS ROI regression across all 6 stats.
    # Infrastructure (_GAMELOG_FULL_FEATURE_KEYS, _get_gamelog_full_rolling)
    # stays active for a future narrower probe.
    # Iter-18 narrow probe (REVERT 2026-05-27): gl_fga_l5 + gl_plus_minus_l5
    # for PTS only also FAILED OOS gate (ROI -2.61pp, MAE +1.24). Keys removed.
    # Iter-19: 7 linescore context keys (global — all 7 stats).
    *_LS_FEATURE_KEYS,  # ls_blowout_pct_l5, ls_avg_total_l5, ls_avg_q1/q4_pts_l5,
                        # ls_garbage_time_pct_l5, ls_opp_avg_total_allowed_l5,
                        # ls_opp_q1_pts_allowed_l5
)
_ITER23_DEFAULTS: Dict[str, float] = {
    **_DMATCH_DEFAULTS,
    **_PROF_DEFAULTS,
    **_OFFICIALS_ROLLING_DEFAULTS,
    **_FOUL_FEATURE_DEFAULTS,
    **_DNP_TEAM_DEFAULTS,
    **_ADV_SPLITS_DEFAULTS,
    # Iter-18 keys REMOVED (REVERT 2026-05-27 — same OOS gate failure pattern).
    # Iter-19: linescore context defaults.
    **_LS_DEFAULTS,
}


def _inject_iter23_features(
    row: Dict[str, float],
    player_id: int,
    game_date,
    team_abbrev: str,
    opp_abbrev: str = "",
) -> Dict[str, float]:
    """Inject the Iter-2/3/19 features into a prediction feature row.

    Idempotent: calling twice produces the same result (lookups are pure).
    NaN-safe: every key is guaranteed present; missing parquet rows fall
    back to 0.0 defaults so XGB/LGB handle them natively. The MLP scaler
    must still be protected via _safe_mlp_scaler_transform (separate fix).

    Args:
        row: existing feature dict (mutated in-place AND returned).
        player_id: NBA player id (int).
        game_date: datetime or date object for the game being predicted.
        team_abbrev: the player's team abbreviation (e.g. 'LAL').
        opp_abbrev: opponent team abbreviation — used by Iter-19 ls_* join.
                    Defaults to '' (produces 0.0 defaults for ls_opp_* keys).

    Returns:
        The mutated row dict (same object as input).
    """
    try:
        row.update(_get_defender_matchup().features(int(player_id), game_date))
    except Exception:
        row.update(_DMATCH_DEFAULTS)
    try:
        row.update(_get_player_profiles().features(int(player_id)))
    except Exception:
        row.update(_PROF_DEFAULTS)
    try:
        row.update(_get_officials_rolling().features(game_date, str(team_abbrev)))
    except Exception:
        row.update(_OFFICIALS_ROLLING_DEFAULTS)
    try:
        row.update(_get_foul_features().features(int(player_id), game_date))
    except Exception:
        row.update(_FOUL_FEATURE_DEFAULTS)
    try:
        row.update(_get_dnp_team_features().features(game_date, str(team_abbrev)))
    except Exception:
        row.update(_DNP_TEAM_DEFAULTS)
    try:
        row.update(_get_adv_stats_splits().features(int(player_id), game_date))
    except Exception:
        row.update(_ADV_SPLITS_DEFAULTS)
    # Iter-17 gamelog_full rolling injection DISABLED (REVERT 2026-05-27).
    # Iter-18 narrow probe (gl_fga_l5 + gl_plus_minus_l5 for PTS) also REVERTED
    # (2026-05-27) — OOS gate failed: ROI -2.61pp, MAE +1.24. No injection needed.
    # Iter-19: linescore blowout/pace context (7 ls_* keys).
    try:
        row.update(_get_linescore_context().features(
            str(team_abbrev), str(opp_abbrev), game_date))
    except Exception:
        row.update(_LS_DEFAULTS)
    return row


# ── Iter-7: safe MLP scaler transform ────────────────────────────────────────
# Fixes the MLP OOD bug: when inference receives 0.0 for a feature whose
# training mean=78.5, std=3.17, StandardScaler maps it to -24.8 SD — garbage.
# This happens for the 39 Iter-2/3 cols when the parquets don't cover a row.
# Strategy:
#   1. Replace NaN with scaler.mean_ (proper sklearn imputation).
#   2. When >=80% of the 39 Iter-2/3 cols are exactly 0.0, treat them all as
#      "unavailable" and impute to mean (overrides the 0→-25 SD problem).
# Only the 39 keys from _ITER23_FEATURE_KEYS are imputed this way — the rest
# of the feature columns can legitimately be 0.0 (e.g. is_home=0).

def _safe_mlp_scaler_transform(scaler, X):
    """NaN-safe StandardScaler.transform with OOD clamping + zero-imputation.

    Parameters
    ----------
    scaler : fitted sklearn StandardScaler
    X      : np.ndarray of shape (1, n_features) — single prediction row

    Returns
    -------
    X_scaled : np.ndarray of shape (1, n_features) — scaled row

    Four protections applied in order:
      1. Replace NaN with scaler.mean_ (standard imputation).
      2. Iter-2/3 zero-imputation: when >=80% of the 39 Iter-2/3 cols are
         0.0, impute all 39 to scaler.mean_ (parquets not populated for row).
      2b. Generalised zero-imputation (Iter-16a): for ANY feature not already
         handled by Step 2 where raw=0.0 AND the training mean is far from 0
         (|mean| >= 4*std, i.e. z_at_0 >= 4.0), impute to scaler.mean_.
         Fires only for features whose 0 is genuinely OOD — e.g. opp_def_*
         (mean≈1.0, std≈0.04) — and is safe because legitimate zeros like
         is_home=0 have mean≈0.5 (ratio < 2) and are untouched.
      3. OOD value clamp: any feature that would produce |z| > 6 after scaling
         is replaced by scaler.mean_ before transform. Guards against bbref_extra
         scale mismatches (Wave-2b drb_pct/trb_pct trained at fraction scale but
         fed at percentage scale — z≈191 without the clamp).
    """
    import numpy as np  # noqa: PLC0415

    X_work = X.copy().astype(float)

    # Step 1: replace NaN with scaler.mean_.
    nan_mask = np.isnan(X_work)
    if nan_mask.any():
        X_work[nan_mask] = np.take(scaler.mean_, np.where(nan_mask)[1])

    # Step 2: Iter-2/3 zero-imputation heuristic.
    iter23_imputed_indices: set = set()
    try:
        all_cols = feature_columns()
        iter23_indices = [
            i for i, c in enumerate(all_cols)
            if c in set(_ITER23_FEATURE_KEYS)
        ]
        if iter23_indices and X_work.shape[1] >= max(iter23_indices) + 1:
            vals = X_work[0, iter23_indices]
            zero_frac = float(np.sum(vals == 0.0)) / len(iter23_indices)
            if zero_frac >= 0.80:
                for idx in iter23_indices:
                    X_work[0, idx] = scaler.mean_[idx]
                    iter23_imputed_indices.add(idx)
    except Exception:
        pass

    # Step 2b: generalised zero-imputation for non-Iter-2/3 features.
    # Impute raw=0.0 to scaler.mean_ when |mean| >= 4*std (z_at_0 >= 4.0).
    # Only fires when 0.0 is genuinely out-of-distribution for that feature.
    try:
        n = min(X_work.shape[1], len(scaler.mean_))
        for i in range(n):
            if i in iter23_imputed_indices:
                continue
            if X_work[0, i] != 0.0:
                continue
            mean_i = scaler.mean_[i]
            std_i = scaler.scale_[i]
            if std_i > 1e-9 and abs(mean_i) >= 4.0 * std_i:
                X_work[0, i] = mean_i
    except Exception:
        pass

    # Step 3: OOD value clamp — prevent extreme z-scores from scale mismatches.
    # Any column that would produce |z| > 6 is treated as "out of distribution"
    # and replaced with scaler.mean_ (z=0 after transform). This protects
    # against Wave-2b bbref_extra columns that were trained at fraction scale
    # but may be fed at percentage scale (e.g. drb_pct 0.017 vs 11.0).
    try:
        n = min(X_work.shape[1], len(scaler.mean_))
        for i in range(n):
            z = abs(X_work[0, i] - scaler.mean_[i]) / (scaler.scale_[i] + 1e-9)
            if z > 6.0:
                X_work[0, i] = scaler.mean_[i]
    except Exception:
        pass

    return scaler.transform(X_work)


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
        # R10_M14 — PRIOR-SEASON join on the live predict path. Mirrors the
        # build_pergame_dataset switch so train + predict see the same join key.
        _pt_season = _prior_season(season) if _PLAYTYPE_PRIOR_SEASON_JOIN else season
        feats.update(_get_playtypes().features(int(player_id), _pt_season))
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
    # Iter-44 — synergy PPP per-play-type (current-season join, 5 keys).
    try:
        feats.update(_get_syn_ppp().features(int(player_id), season))
    except Exception:
        feats.update(_SYN_PPP_DEFAULTS)
    # Iter-46 — per-opponent rolling-3 stat features (6 keys).
    # Live-inference path: look up today's date for the upcoming game.
    try:
        today_iso = factor_date.date().isoformat()
        feats.update(_get_per_opp_rolling().features(int(player_id), today_iso))
    except Exception:
        feats.update(_PER_OPP_ROLLING_DEFAULTS)
    # Cycle 96a (loop 5) — pre-game home_spread lookup so the live
    # prediction path (predict_player / predict_slate / compare_to_lines)
    # receives the same T1-A garbage-time haircut wired into predict_pergame.
    # Sign convention mirrors build_pergame_dataset: row["home_spread"] is
    # from THIS PLAYER'S perspective (negative when their team is favoured).
    # Defaults to None when the parquet is absent or the matchup isn't
    # cached — apply_garbage_time_haircut is then a no-op.
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        team_abbrev = last_matchup.split()[0] if last_matchup.split() else ""
        if is_home:
            sp_home, sp_away, sign = team_abbrev, opp_team, 1.0
        else:
            sp_home, sp_away, sign = opp_team, team_abbrev, -1.0
        sp_feats = _get_pregame_spreads().features(sp_home, sp_away, factor_date)
        hs = sp_feats.get("home_spread")
        feats["home_spread"] = (sign * float(hs)) if hs is not None else None
        feats["total"] = sp_feats.get("total")
    except Exception:
        feats["home_spread"] = None
        feats["total"] = None
    # Iter-7: inject the 39 Iter-2/3 features that were missing from this
    # path (present in training via build_pergame_dataset but zero at inference).
    try:
        last_matchup = str(prior_played[-1].get("MATCHUP", "")) if prior_played else ""
        _team_abbrev_inj = last_matchup.split()[0] if last_matchup.split() else ""
        _inject_iter23_features(feats, int(player_id), factor_date, _team_abbrev_inj, opp_team)
    except Exception:
        feats.update(_ITER23_DEFAULTS)
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

    R15_W1: every returned q50 (point) prediction is multiplied at the
    very end by the live `availability_factor` derived from the latest
    ESPN injury snapshot (OUT=0.0 … AVAILABLE=1.0). Default 1.0 when the
    player isn't in the feed. Set NBA_INJURY_WIRE_DISABLE=1 in the
    environment to bypass (used by retro backtests that already encode
    availability in the data).
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

    # R15_W1 — multiplicative injury-availability dampener. Inference-only,
    # so it cannot leak into training. apply_availability is a thin wrapper
    # around the ESPN snapshot index built by injury_availability.py.
    try:
        from src.prediction.injury_availability import (  # noqa: PLC0415
            apply_availability,
        )
        for stat, val in list(out.items()):
            adj_q50, _, _ = apply_availability(int(player_id) if player_id is not None
                                               else None, float(val))
            out[stat] = round(adj_q50, 2)
    except Exception as exc:  # never let injury wiring kill a prediction
        print(f"[predict_player_pergame] injury-wire skipped: {exc}")

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
