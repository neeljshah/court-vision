"""live_engine.py -- consolidated entry point for live in-game predictions.

Cycle 95c (loop 5) -- ENTRY-POINT consolidation, not code consolidation.

Background
----------
The cycle-88 in-game prediction system currently exists as 14 scripts
(live_game_poll, predict_in_game, foul_trouble_adjust, blowout_adjust,
save_live_predictions, live_dashboard, live_player, live_edge_eval, ...).
Cycle 94d EMPIRICALLY VALIDATED that this stack beats the cycle-47/49/80
PRE-GAME predictor at endQ3 on 7/7 stats (PTS -42%, BLK -56% MAE), but the
operational surface is fragmented -- consumers must remember which script
owns which transform.

This module gives ONE clean functional API for the validated core:

    project_from_snapshot(snap)   -> per-(player, stat) projections
    project_full_slate(date_iso)  -> {game_id: [rows]} for today's games
    edge_vs_pregame(snap)         -> projections + pregame_pred deltas
    write_ledger(rows, date_iso)  -> append to data/predictions/<d>_inplay.csv

Design rule -- WRAPPERS, NOT REWRITES
-------------------------------------
This module does NOT re-implement any projection math. It calls:

  * ``scripts.predict_in_game.project_snapshot`` (cycle 88b -- the validated core)
  * ``src.prediction.live_factors.foul_trouble_factor`` (cycle 89b canonical table)
  * ``scripts.blowout_adjust.blowout_factor`` (cycle 88f buckets)
  * ``scripts.save_live_predictions.derive_inplay_predictions`` +
    ``append_to_ledger`` (cycle 88n ledger schema)
  * ``src.data.live`` loader helpers (canonical snapshot schema)

The existing consumers (live_dashboard, live_player, live_edge_eval, ...)
keep their current imports -- this module is ADDITIVE, providing one
clean entry point for NEW consumers and for orchestrators that want a
single import to drive the whole live stack.

See ``tests/test_live_engine.py`` for the 5 regression + integration tests.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# scripts/ is on the load path so we can call the validated pure functions
# without copying them.
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Canonical snapshot loaders + helpers.
from src.data.live import (  # noqa: E402
    list_today_snapshots,
    latest_snapshot_path,
    load_live_state,
)

# Pre-import heavy packages at module load time so the first
# project_from_snapshot() call on a warm server doesn't pay
# the 1.2s lightgbm + sklearn import tax.  The warmup thread
# (register_with_app → _warm_all → _build_slate) triggers this
# import once; every subsequent cache-miss path is free of it.
try:
    import lightgbm as _lgb_preload  # noqa: F401
except ImportError:
    pass
try:
    import sklearn as _sk_preload  # noqa: F401
except ImportError:
    pass

PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")

# tier1-2 (loop 5): foul_change residual head + stratified blend.
# When True, project_from_snapshot consults the foul-change residual model
# for endQ3 (period=4) snapshots and dispatches to its prediction when the
# gate fires (q3_pf >= 2, OR pf_through_q3 >= 3, OR foul-out edge); the
# global cycle 9d3 minute_trajectory model handles the rest. Probe
# scripts/probe_stratified_blend.py validated SHIP: PTS MAE -0.24 on
# foul_change stratum vs heuristic; 0.00 regression on non-foul; WF 4/4
# folds negative. If either artifact is missing the dispatch transparently
# falls back to the heuristic (back-compat preserved).
_USE_FOUL_RESIDUAL = True

# cycle 102a (loop 5): blowout_flip residual head + stratified dispatch.
# When True, project_from_snapshot consults the blowout-residual model for
# endQ3 (period=4) snapshots and dispatches to its prediction when the
# live-proxy gate fires (|Q3 margin| <= 18 AND |velocity| >= 4); the
# cycle-88f blowout_factor heuristic handles the rest. Probe
# scripts/probe_blowout_stratified_blend.py validated SHIP: PTS MAE -0.28
# on blowout_flip stratum vs heuristic; non_blowout IMPROVES -0.08 (not a
# regression); WF 4/4 folds negative (-0.13 to -0.26). Dispatches SECOND
# AFTER the foul_residual override -- the two are independent (foul
# residual overrides foul_factor, blowout residual overrides blow_factor).
# If the artifact is missing the dispatch transparently falls back to the
# heuristic (back-compat preserved).
_USE_BLOWOUT_RESIDUAL = True

# cycle 103b (loop 5): heat_check shrinkage residual v2. When True,
# project_from_snapshot applies a learned shrinkage factor ∈ [0.70, 1.00]
# to the cycle-88 PTS/AST/FG3M projection on heat_check rows at endQ3.
# Probe scripts/probe_heat_check_shrinkage_blend.py validated SHIP:
# heat_check PTS MAE -0.43 vs heuristic, non_heat 0.0 regression, WF 4/4
# negative (-0.37 to -0.46). Applied AFTER foul + blowout overrides
# (multiplies projected_final, never current_stat). Missing artifact -> no-op.
_USE_HEAT_CHECK_SHRINKAGE = True

# cycle 105c (loop 5): in-play quantile bands (q10/q50/q90 around the point
# projection). Enabled cycle 107a after v2 recalibration against live_engine
# projections (endQ2: 7/7 SHIP, endQ3: 7/7 SHIP on held-out half).
# q50 ALWAYS equals projected_final -- the point prediction is never altered.
# Bands are wide-open (q10=0, q90=2*q50) for endQ1 / mid-period snapshots
# where no calibration artifact exists (back-compat).
_INCLUDE_QUANTILE_BANDS = True

# cycle 106a (loop 5): wire cycle-105b period_specific_heads into
# project_from_snapshot. When True, at endQ1 (period=2, clock≈12:00) and
# endQ2 (period=3, clock≈12:00) boundaries we REPLACE the cycle-88 linear
# extrapolation per-(player, stat) with the period-specific LightGBM
# regressor prediction (projected_final = current_stat + predict_remaining).
# endQ3 (period=4 boundary) is INTENTIONALLY NOT wired -- cycle 105b
# rejected endQ3 head because cycle-88 linear extrap is already near-optimal
# at 36 min observed. Mid-quarter snapshots fall through to cycle-88. The
# three stratified residual overrides (foul / blowout / heat_check) still
# fire on top of whatever projection source produced the row. Each row is
# tagged with `projection_source` ∈ {"endQ1_head", "endQ2_head",
# "cycle_88_linear"} for downstream debugging. Missing artifacts fall
# through transparently (back-compat preserved).
_USE_PERIOD_HEADS = True

# cycle 110 (loop 5): learned Q4 minutes at endQ3. When True,
# project_from_snapshot at period=4 replaces the heuristic foul_trouble_factor
# with `learned_remaining_min/12.0` from MinuteTrajectoryModel for every
# player (not just foul-trouble). Pace + blowout + bench logic unchanged.
# Probe scripts/probe_110_learned_q4_minutes.py validated SHIP on 1508-game
# corpus: PTS MAE -0.2312, REB -0.1002, AST -0.1020, FG3M -0.0693,
# STL -0.0617, BLK -0.0393, TOV -0.0752 (7/7 stats win), WF 4/4 folds
# negative (-0.2052 to -0.2470). Because the learned-minute substitution
# is much larger than the prior foul/blowout/heat_check residual overrides
# (those were measured against the cycle-88 heuristic foul_factor that
# we're now replacing), the legacy endQ3 overrides are intentionally
# skipped when this flag is on. Missing artifact -> transparent fallback.
_USE_LEARNED_Q4_MINUTES = True

# cycle R2_F (loop 5): per-stat residual heads at endQ3. When True,
# project_from_snapshot at period=4 adds a learned residual correction to
# each (player, stat) projection AFTER the cycle 110 learned-Q4-minutes path
# (or after period heads when cycle 110 falls back). Applied last so it
# operates on the best available point projection.
# Probe scripts/probe_R2_F_residual_heads.py validated SHIP:
# PTS MAE -0.0965, 7/7 stats win, WF 4/4 folds negative.
# Artifacts: data/models/residual_heads/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
# Missing artifact dir -> transparent no-op (back-compat preserved).
_USE_RESIDUAL_HEADS = True

# cycle R3_A (loop 5): per-stat residual heads at endQ2. When True,
# project_from_snapshot at period=3 (endQ2 boundary, after the period-specific
# head fires via _USE_PERIOD_HEADS) adds a learned residual correction to
# each (player, stat) projection. Applied AFTER the period_specific_heads
# block so the residual stacks on top of the endQ2_head projection.
# Probe scripts/probe_R3_A_residual_heads_endq2.py validated SHIP:
# PTS MAE -0.1095, 7/7 stats win, WF 4/4 folds negative (-0.10 to -0.11).
# Artifacts: data/models/residual_heads_endq2/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
# Missing artifact dir -> transparent no-op (back-compat preserved).
_USE_RESIDUAL_HEADS_ENDQ2 = True

# R10_M5 (loop 5): in-play home-team WIN PROBABILITY at endQ1/endQ2/endQ3.
# When True, project_from_snapshot stamps every row with the snapshot-conditional
# home win probability produced by src.prediction.inplay_winprob (LightGBM
# boosters under data/models/inplay_winprob_<snap>.lgb). Probe R10_M5 validated
# SHIP at endQ3: walk-forward mean Brier 0.1350 (gate 0.183), accuracy 81.33%,
# AUC 0.901 vs pregame baseline Brier 0.2653. endQ1/endQ2 fail the ship gate
# but are still loaded as priors over the naive home-rate baseline (0.523).
# Each row gets two new fields: ``home_win_prob_inplay`` (the model output,
# None at non-boundary snapshots or when the artifact is missing) and
# ``inplay_winprob_snapshot`` (one of {"endQ1", "endQ2", "endQ3", None}).
# Existing consumers (live_dashboard, save_live_predictions, edge_eval)
# tolerate the extra keys (they only read declared columns).
_USE_INPLAY_WINPROB = True

# W-037 (CV_STL_BANDS): Poisson-remainder STL interval bands at endQ2/endQ3.
# When CV_STL_BANDS is set (any non-empty string), the standard empirical
# sigma from live_quantile_calibration.json is replaced with a per-player
# Poisson-remainder sigma derived from the projected remaining steals.
#
# STL is a low-count Poisson process.  The correct residual distribution
# for REMAINING steals is Poisson(lambda_rem) where lambda_rem = the
# projected remaining count = max(0, projected_final - current_stl).
# Var[Poisson(k)] = k, so sigma = sqrt(k).  This automatically shrinks
# the band width late (few steals remaining) and widens it early (many
# steals remaining), matching the true count distribution.
#
# Implementation:
#   remaining_stl = max(0, projected_final - current_stl)
#   sigma         = max(_STL_SIGMA_FLOOR, sqrt(remaining_stl))
#   half_wid      = _STL_Z80 * sigma       [80% coverage z-score]
#   q10           = max(0, q50 - half_wid)  [asymmetric, floor at 0]
#   q90           = q50 + half_wid
#
# Using remaining_stl (not rate*time) ensures that for a player with
# current_stl=0 and projected_final=0.3, sigma=sqrt(0.3)≈0.55 so
# q10=max(0, 0.3-0.71)=0 and actual=0 is covered (correct).
# A floor of 0.10 steals prevents degenerate zero-width bands when
# remaining_stl ≈ 0 (e.g. player who has already hit their L5 total).
#
# Byte-identical when CV_STL_BANDS is unset (the default).
# Validated: coverage check per (50/80/90 bucket × endQ2, endQ3).

# Remaining game-clock minutes by snapshot boundary name (informational;
# not used directly in the Poisson formula which keys on projected count).
_STL_REMAINING_MIN: Dict[str, float] = {
    "endQ1": 36.0,   # Q2+Q3+Q4 remaining
    "endQ2": 24.0,   # Q3+Q4 remaining
    "endQ3": 12.0,   # Q4 remaining
}
# z-score for 80% symmetric interval (P10..P90); STL is treated asymmetric
# so we floor q10 at 0 (matches ASYMMETRIC_STATS in live_quantile_bands.py).
_STL_Z80: float = 1.2816
# Minimum sigma (in steals) to avoid degenerate zero-width bands.
_STL_SIGMA_FLOOR: float = 0.10


def _stl_poisson_band(q50: float, current_stl: float) -> Dict[str, float]:
    """Compute Poisson-remainder q10/q50/q90 for a single STL projection.

    Uses the projected remaining count as the Poisson parameter:
        remaining_stl = max(0, projected_final - current_stl)
        sigma         = max(_STL_SIGMA_FLOOR, sqrt(remaining_stl))
        half_wid      = _STL_Z80 * sigma
        q10           = max(0, q50 - half_wid)   [floor at 0]
        q90           = q50 + half_wid

    q50 is always unchanged (= projected_final).

    Args:
        q50: total projected_final (not just remaining) -- q50 is unchanged.
        current_stl: steals accumulated so far this game.

    Returns dict with q10, q50, q90 keys (monotone, q10 >= 0).
    """
    import math as _math
    try:
        q50f = float(q50)
    except (TypeError, ValueError):
        q50f = 0.0
    try:
        cur_stl = float(current_stl)
    except (TypeError, ValueError):
        cur_stl = 0.0

    remaining_stl = max(0.0, q50f - cur_stl)
    sigma = _math.sqrt(remaining_stl) if remaining_stl > 0.0 else 0.0
    sigma = max(sigma, _STL_SIGMA_FLOOR)

    half = _STL_Z80 * sigma
    q10v = max(0.0, q50f - half)
    q90v = q50f + half
    # Guarantee monotonicity.
    if q10v > q50f:
        q10v = q50f
    if q90v < q50f:
        q90v = q50f
    return {"q10": float(q10v), "q50": float(q50f), "q90": float(q90v)}


# Module-scope lazy caches -- loaded once on first project_from_snapshot
# call, then reused across the whole live polling loop.
_GLOBAL_MIN_MODEL = None
_FOUL_RESIDUAL_MODEL = None
_BLOWOUT_RESIDUAL_MODEL = None
_HEAT_CHECK_SHRINKAGE_MODEL = None
_MODELS_LOADED = False


def _load_models_once():
    """Idempotent loader for the cycle 9d3 + tier1-2 + cycle 102a artifacts.

    Returns (global_model, foul_residual, blowout_residual). Any may be None
    if its artifact is absent -- callers tolerate None via stratified dispatch.
    """
    global _GLOBAL_MIN_MODEL, _FOUL_RESIDUAL_MODEL, _BLOWOUT_RESIDUAL_MODEL
    global _HEAT_CHECK_SHRINKAGE_MODEL, _MODELS_LOADED
    if _MODELS_LOADED:
        return (_GLOBAL_MIN_MODEL, _FOUL_RESIDUAL_MODEL,
                _BLOWOUT_RESIDUAL_MODEL, _HEAT_CHECK_SHRINKAGE_MODEL)
    try:
        from src.prediction.minute_trajectory import MinuteTrajectoryModel
        _GLOBAL_MIN_MODEL = MinuteTrajectoryModel.load()
    except Exception:
        _GLOBAL_MIN_MODEL = None
    try:
        from src.prediction.minute_trajectory_foul_residual import (
            FoulChangeResidualModel,
        )
        _FOUL_RESIDUAL_MODEL = FoulChangeResidualModel.load()
    except Exception:
        _FOUL_RESIDUAL_MODEL = None
    try:
        from src.prediction.blowout_residual import BlowoutResidualModel
        _BLOWOUT_RESIDUAL_MODEL = BlowoutResidualModel.load()
    except Exception:
        _BLOWOUT_RESIDUAL_MODEL = None
    try:
        from src.prediction.heat_check_shrinkage_residual import (
            HeatCheckShrinkageResidualModel,
        )
        _HEAT_CHECK_SHRINKAGE_MODEL = HeatCheckShrinkageResidualModel.load()
    except Exception:
        _HEAT_CHECK_SHRINKAGE_MODEL = None
    _MODELS_LOADED = True
    return (_GLOBAL_MIN_MODEL, _FOUL_RESIDUAL_MODEL,
            _BLOWOUT_RESIDUAL_MODEL, _HEAT_CHECK_SHRINKAGE_MODEL)


__all__ = [
    "project_from_snapshot",
    "project_full_slate",
    "edge_vs_pregame",
    "write_ledger",
    "_USE_FOUL_RESIDUAL",
    "_USE_BLOWOUT_RESIDUAL",
    "_USE_HEAT_CHECK_SHRINKAGE",
    "_INCLUDE_QUANTILE_BANDS",
    "_USE_PERIOD_HEADS",
    "_USE_LEARNED_Q4_MINUTES",
    "_USE_RESIDUAL_HEADS",
    "_USE_RESIDUAL_HEADS_ENDQ2",
    "_USE_INPLAY_WINPROB",
]


# Module-scope cache for cycle 110 learned-Q4-minutes wiring.
_LEARNED_Q4_POSITIONS = None
_LEARNED_Q4_LOAD_FAILED = False

# W-013 (CV_PTS_MIN_CALIB): module-scope cache for the endQ2 minute-trajectory
# model (minute_trajectory_q2.lgb). Loaded lazily on first use; None when
# the artifact is absent (graceful no-op path preserved).
_PTS_MIN_CALIB_MODEL_Q2 = None
_PTS_MIN_CALIB_LOAD_FAILED = False


def _apply_learned_q4_minutes(snap: dict, rows: list):
    """cycle 110: replace projected_final at period=4 with the projection
    produced by ``probe_minute_trajectory_replacement
    .project_snapshot_with_learned_minutes`` -- i.e. swap the heuristic
    ``foul_trouble_factor`` for ``learned_remaining_min / 12.0`` from
    ``MinuteTrajectoryModel`` for every player.

    Returns ``(rows, applied: bool)``. ``applied=False`` triggers fallback
    to the legacy foul/blowout/heat_check residual overrides at endQ3.
    Any failure (missing model, missing scaffold, runtime error) is caught
    and returns ``(rows, False)`` -- the hot path never breaks.
    """
    global _LEARNED_Q4_POSITIONS, _LEARNED_Q4_LOAD_FAILED
    if _LEARNED_Q4_LOAD_FAILED:
        return rows, False
    model, _, _, _ = _load_models_once()
    if model is None:
        return rows, False
    try:
        # Lazy import: probe lives under scripts/ which is on sys.path via
        # the project root append at top of this module.
        import sys as _sys
        scripts_dir = os.path.join(PROJECT_DIR, "scripts")
        if scripts_dir not in _sys.path:
            _sys.path.insert(0, scripts_dir)
        from probe_minute_trajectory_replacement import (
            project_snapshot_with_learned_minutes,
        )
        if _LEARNED_Q4_POSITIONS is None:
            import train_minute_trajectory as tmt
            _LEARNED_Q4_POSITIONS = tmt.load_positions() or {}
        # L20/L5 lookups are optional features for the model -- pass empty
        # dicts so it falls back to None internally. The retro probe used
        # per-game date-aware lookups; live snapshots don't reliably carry
        # game_date, so the simpler path is to omit them. Bulk of the gain
        # is the substitution itself, not the rolling features.
        projs = project_snapshot_with_learned_minutes(
            snap, model, _LEARNED_Q4_POSITIONS, {}, {},
        )
    except Exception:
        _LEARNED_Q4_LOAD_FAILED = True
        return rows, False
    if not projs:
        return rows, False
    for r in rows:
        try:
            pid = int(r.get("player_id"))
        except (TypeError, ValueError):
            continue
        stat = r.get("stat")
        new = projs.get((pid, stat))
        if new is None:
            continue
        r["projected_final"] = float(new)
        r["projection_source"] = "learned_q4_minutes_v1"
    return rows, True


def _apply_pts_min_calib(snap: dict, rows: list) -> list:
    """W-013 (CV_PTS_MIN_CALIB): per-period minutes-trajectory recalibration.

    At the endQ2 boundary (period=3, clock near 12:00): use the trained
    ``minute_trajectory_q2.lgb`` model to predict each player's remaining
    minutes (Q3+Q4) and scale the remaining-PTS delta accordingly.

    The correction compares learned remaining minutes to the minutes IMPLICITLY
    assumed by the current projection:

        per_min_rate  = current_pts / min_through_q2  (player scoring rate)
        implied_rem_min = remaining_delta / per_min_rate
        ratio = learned_remaining_min / implied_rem_min
        new_pts_final = current_pts + remaining_delta * ratio

    Using the projection-implied denominator (not a fixed 24-min constant)
    keeps the ratio centred around 1.0 — it adjusts only when the minute model
    diverges from the projection's assumption. The ratio is clamped to [0.1, 2.0]
    to prevent extreme rescaling on noisy rows.

    Only fires at the endQ2 boundary; all other snapshots and all non-PTS stats
    are passed through unchanged. Any failure (missing model, parse error,
    etc.) returns ``rows`` unmodified -- the hot path never breaks.

    Returns the (possibly mutated) rows list.
    """
    global _PTS_MIN_CALIB_MODEL_Q2, _PTS_MIN_CALIB_LOAD_FAILED
    if _PTS_MIN_CALIB_LOAD_FAILED:
        return rows

    # Gate to endQ2 boundary only (period=3, clock near 12:00).
    snap_period = snap.get("period")
    snap_clock = snap.get("clock")
    try:
        from src.prediction.period_specific_heads import snapshot_point_for as _spf
        if _spf(snap_period, snap_clock) != "endQ2":
            return rows
    except Exception:
        return rows

    # Lazy-load the Q2 minute-trajectory model artifact.
    if _PTS_MIN_CALIB_MODEL_Q2 is None:
        try:
            import json as _json_load
            _q2_model_path = os.path.join(
                PROJECT_DIR, "data", "models", "minute_trajectory_q2.lgb")
            _q2_meta_path = os.path.join(
                PROJECT_DIR, "data", "models", "minute_trajectory_q2_meta.json")
            if (not os.path.exists(_q2_model_path)
                    or not os.path.exists(_q2_meta_path)):
                _PTS_MIN_CALIB_LOAD_FAILED = True
                return rows
            import lightgbm as lgb
            _booster = lgb.Booster(model_file=_q2_model_path)
            with open(_q2_meta_path, "r", encoding="utf-8") as _fh:
                _meta = _json_load.load(_fh)
            _PTS_MIN_CALIB_MODEL_Q2 = (_booster, _meta.get("feature_names", []))
        except Exception:
            _PTS_MIN_CALIB_LOAD_FAILED = True
            return rows

    try:
        booster, feature_names = _PTS_MIN_CALIB_MODEL_Q2
    except (TypeError, ValueError):
        _PTS_MIN_CALIB_LOAD_FAILED = True
        return rows

    try:
        import numpy as _np
        from scripts.train_minute_trajectory_q2 import (  # noqa: E402
            build_feature_row_q2,
        )
    except Exception:
        return rows

    # Parse game context.
    try:
        home_score = float(snap.get("home_score") or 0)
    except (TypeError, ValueError):
        home_score = 0.0
    try:
        away_score = float(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        away_score = 0.0
    margin_abs = abs(home_score - away_score)
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""

    # Index players by pid.
    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    for r in rows:
        if r.get("stat") != "pts":
            continue
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue
        p = by_pid.get(pid_i)
        if p is None:
            continue

        try:
            current_pts = float(r.get("current") or p.get("pts") or 0)
        except (TypeError, ValueError):
            current_pts = 0.0
        try:
            projected_final = float(r.get("projected_final") or 0)
        except (TypeError, ValueError):
            continue

        remaining_delta = projected_final - current_pts
        if remaining_delta <= 0.0:
            # Nothing to scale (player has 0 or negative remaining projected).
            continue

        # Gather per-quarter minutes played through Q2.
        try:
            min_q1 = float(p.get("min_q1") or 0)
        except (TypeError, ValueError):
            min_q1 = 0.0
        try:
            min_q2_raw = p.get("min_q2")
            min_q2 = float(min_q2_raw) if min_q2_raw is not None else 0.0
        except (TypeError, ValueError):
            min_q2 = 0.0
        min_through = min_q1 + min_q2
        # If per-quarter splits absent, fall back to cumulative min split evenly.
        if min_through <= 0.0:
            try:
                min_through = float(p.get("min") or 0)
                min_q1 = min_through / 2.0
                min_q2 = min_through / 2.0
            except (TypeError, ValueError):
                pass

        # Skip players with negligible minutes (no useful rate signal).
        if min_through < 0.5 or current_pts <= 0.0:
            continue

        # Implied remaining minutes from the current projection:
        #   per_min_rate = current_pts / min_through
        #   implied_rem_min = remaining_delta / per_min_rate
        per_min_rate = current_pts / min_through
        implied_rem_min = remaining_delta / per_min_rate
        if implied_rem_min <= 0.0:
            continue

        try:
            pf_through_q2 = float(p.get("pf") or 0)
        except (TypeError, ValueError):
            pf_through_q2 = 0.0

        team = p.get("team") or ""
        is_leading = (
            (team == home_team and home_score > away_score)
            or (team == away_team and away_score > home_score)
        )

        l20_min = p.get("l20_min")
        try:
            l20_min = float(l20_min) if l20_min is not None else None
        except (TypeError, ValueError):
            l20_min = None

        l5_min = p.get("l5_min")
        try:
            l5_min = float(l5_min) if l5_min is not None else None
        except (TypeError, ValueError):
            l5_min = None

        try:
            feat_row = build_feature_row_q2(
                pf_through_q2=pf_through_q2,
                min_q1=min_q1,
                min_q2=min_q2,
                score_margin_abs=margin_abs,
                is_leading_team=1 if is_leading else 0,
                position_proxy=p.get("position"),
                l20_min=l20_min,
                l5_min=l5_min,
            )
            arr = _np.asarray([feat_row], dtype=_np.float64)
            learned_min = float(_np.clip(booster.predict(arr)[0], 0.0, 36.0))
        except Exception:
            continue

        # Scale factor relative to the projection's own implied remaining minutes.
        # Clamped to [0.1, 2.0] to prevent extreme adjustments on noisy rows.
        ratio = learned_min / implied_rem_min
        ratio = max(0.1, min(2.0, ratio))

        new_final = current_pts + remaining_delta * ratio
        # Never project below current (can't un-score points).
        new_final = max(new_final, current_pts)

        r["projected_final"] = float(new_final)
        src = str(r.get("projection_source") or "")
        if "+pts_min_calib" not in src:
            r["projection_source"] = src + "+pts_min_calib"

    return rows


def _apply_unified_routed(snap: dict, rows: List[Dict]) -> List[Dict]:
    """Overlay the VALIDATED routed in-game player-line ensemble onto base rows.

    Pure no-op unless the canonical ``CV_INGAME_SBS`` env flag is set (so tests
    and the default serving config are byte-identical to the cycle-88 core). When
    enabled, replaces each row's ``projected_final`` with the routed ensemble's
    projection (held-out pooled player MAE 1.01 vs 1.87 production). The team
    possession sim is skipped (``n_sims=1``) — only the player lines are served
    here. ANY exception returns ``rows`` unchanged: the overlay can never break
    live serving.
    """
    try:
        from src.ingame.sbs_shadow import is_enabled
    except Exception:
        return rows
    if not is_enabled():
        return rows
    try:
        from src.ingame.unified_projector import project_unified
        as_of = snap.get("game_date") or snap.get("date")
        # Optional leak-free serve-time ridge POINT for the team score (the
        # measured-best point estimate: total MAE 9.88 vs sim 10.91). Graceful
        # no-op until the artifact exists -> score ensemble falls back to sim-mean.
        ridge_point = None
        try:
            from src.ingame.serve_ridge_point import predict_serve_ridge
            ridge_point = predict_serve_ridge(snap, as_of=as_of)
        except Exception:
            ridge_point = None
        try:
            n_sims = int(os.environ.get("CV_INGAME_NSIMS", "400") or "400")
        except (TypeError, ValueError):
            n_sims = 400
        unified = project_unified(
            snap, as_of=as_of, n_sims=n_sims, ridge_point=ridge_point,
        )
        if not isinstance(unified, dict):  # disabled pass-through safety
            return rows

        # ── (1) player-line overlay — the validated headline win (MAE 1.01 vs 1.87)
        routed: Dict = {}
        for pl in (unified.get("player_lines") or []):
            try:
                routed[(int(pl["player_id"]), pl["stat"])] = pl
            except (KeyError, TypeError, ValueError):
                continue
        for r in rows:
            try:
                pl = routed.get((int(r.get("player_id")), r.get("stat")))
            except (TypeError, ValueError):
                pl = None
            if pl is None:
                continue
            r["projected_final"] = float(pl["projected_final"])
            r["projection_source"] = "unified_routed"
            r["route_head"] = pl.get("route_head")

        # ── (2) team final-score + win-prob — validated possession-sim / score
        #        ensemble (final score: total MAE ~10 vs production ~21, 7/7 buckets).
        #        Final-score projection is ADDITIVE at every game-time. The win-prob
        #        OVERRIDE is gated to Q4 (period>=4), the measured crossover where the
        #        sim beats the production sigmoid on Brier AND LogLoss (endQ3+ Brier
        #        0.126 vs 0.136; midQ4 0.079 vs 0.088). Before Q4 the sigmoid wins, so
        #        it is left UNTOUCHED.
        team = unified.get("team") or {}
        if team:
            for r in rows:
                r["proj_home_final"] = team.get("home_final_mean")
                r["proj_away_final"] = team.get("away_final_mean")
                r["proj_total"] = team.get("total_mean")
                r["proj_margin"] = team.get("margin_mean")
                r["proj_point_source"] = team.get("point_source")
                # sim win-prob is attached here but PROMOTED to home_win_prob_inplay
                # only at the Q4 finalizer below — the production inplay_winprob model
                # runs AFTER this overlay, so overriding here would be clobbered.
                r["sim_home_win_prob"] = team.get("home_win_prob")
        return rows
    except Exception:
        # Never let the unified overlay break the validated cycle-88 serving path.
        return rows


# ── 1. project_from_snapshot ──────────────────────────────────────────────────

def project_from_snapshot(snap: dict, *, period: Optional[int] = None) -> List[Dict]:
    """Single entry point: snapshot dict -> per-(player, stat) projections.

    Thin wrapper around ``scripts.predict_in_game.project_snapshot`` (cycle 88b)
    which composes:

      * pace-based extrapolation against the regulation 48-min baseline
      * ``src.prediction.live_factors.foul_trouble_factor`` (cycle 89b canonical)
      * ``scripts.blowout_adjust.blowout_factor`` semantics (cycle 88f)
      * bench-player handling (project at player-clock rate, not game-clock)

    Empirically validated by **cycle 94d** -- this combined system beats the
    cycle-47/49/80 pre-game predictor at endQ3 on 7/7 stats (PTS MAE -42%,
    BLK MAE -56%) on the retro_inplay_mae_v2 backtest.

    Parameters
    ----------
    snap : dict
        Canonical snapshot per ``src/data/live.py``. Legacy nested
        ``{home: {abbrev, score}}`` form is auto-normalized.
    period : int, optional
        Override the snapshot's reported period. Useful when the caller has
        a more authoritative period (e.g. end-of-period trigger). When None
        (the default), the snapshot's own ``period`` field is used.

    Returns
    -------
    list of dict
        One row per (player, stat). Keys:

            player_id, name, team, stat,
            current, projected_final,
            period, foul_factor, blow_factor,
            snapshot_period, snapshot_clock
    """
    import predict_in_game as pig    # local import: keeps module import cheap

    if period is not None:
        # Don't mutate the caller's dict -- shallow-copy.
        snap = dict(snap)
        snap["period"] = int(period)

    rows = pig.project_snapshot(snap)
    snap_period = snap.get("period")
    snap_clock = snap.get("clock")
    for r in rows:
        # Match the cycle-88n ledger schema for downstream consumers.
        r.setdefault("snapshot_period", snap_period)
        r.setdefault("snapshot_clock", snap_clock)
        # cycle 106a: default projection source is the cycle-88 linear
        # extrapolator (set above by pig.project_snapshot). Overridden
        # per-row below when a period_specific_heads artifact is wired in.
        r.setdefault("projection_source", "cycle_88_linear")

    # FULL-SEND (2026-05-31): serve the VALIDATED routed in-game player-line
    # ensemble. Gated on the canonical CV_INGAME_SBS env flag (default OFF =>
    # this block is a pure no-op and serving is byte-identical to today; tests
    # never set the env so they stay green). When the live server sets the flag,
    # overlay the routed projection (held-out pooled player MAE 1.01 vs 1.87
    # production, .planning/ingame/eval_routed.json) onto the base rows. Placed
    # BEFORE the endQ boundary heads so those validated late-game overrides still
    # take precedence where they fire (the router itself defers to snapshot late,
    # so they compose). Wrapped so ANY failure falls back to the production rows
    # -- the routed overlay can never break live serving.
    rows = _apply_unified_routed(snap, rows)

    # cycle 106a (loop 5): replace projected_final with period_specific_heads
    # prediction at endQ1 / endQ2 boundaries when artifacts exist. endQ3 is
    # intentionally NOT wired (cycle-88 linear is already near-optimal at
    # 36 min observed). Mid-quarter snapshots fall through unchanged.
    if _USE_PERIOD_HEADS:
        rows = _apply_period_heads(snap, rows)

    # cycle R3_A (loop 5): per-stat residual heads at endQ2. Applied AFTER
    # period_specific_heads so the correction stacks on the endQ2_head
    # projection (period=3 boundary). Gated identically to period_heads:
    # only fires when snapshot_point_for(period, clock) == "endQ2" (clock
    # near 12:00 at start of Q3). Mid-quarter period=3 snapshots fall through
    # unchanged. Graceful no-op when artifacts are missing.
    if _USE_RESIDUAL_HEADS_ENDQ2 and int(snap_period or 0) == 3:
        try:
            from src.prediction.period_specific_heads import snapshot_point_for as _spf
            _at_endq2 = _spf(snap_period, snap_clock) == "endQ2"
        except Exception:
            _at_endq2 = False
        if _at_endq2:
            rows = _apply_residual_heads_endq2(snap, rows)

    # W-013 (CV_PTS_MIN_CALIB): per-period minutes-trajectory recalibration for
    # PTS at endQ2. When CV_PTS_MIN_CALIB is set (any non-empty string), apply
    # the learned Q2 minute-trajectory correction to PTS projected_final rows
    # at the endQ2 boundary. Pure no-op for any other period or stat.
    # Applied AFTER period_specific_heads and endQ2 residual heads so the
    # minutes correction stacks on the best available point projection.
    # Byte-identical when the flag is OFF (the default).
    if os.environ.get("CV_PTS_MIN_CALIB"):
        rows = _apply_pts_min_calib(snap, rows)

    # W-014 (CV_INGAME_HEAT_GEN): generalized heat-check heat^0.20 mean-reversion.
    # Fires at EVERY snapshot (not just endQ3) whenever the player has >= 3 min
    # and an L5 per-min prior is available on the player row. Applies to
    # pts/fg3m/ast remaining-delta only; never STL/BLK/TOV/REB; never alters
    # current_stat. Byte-identical when CV_INGAME_HEAT_GEN is unset (default).
    # PROTECT AST: this tilt is applied to AST remaining-delta but uses a
    # per-player L5 AST rate so the direction tracks actual AST pace, not PTS.
    rows = _apply_heat_check_generalized(snap, rows)

    # cycle 110 (loop 5): learned Q4 minutes override at endQ3. When the
    # flag is on AND the snapshot is at period=4 AND MinuteTrajectoryModel
    # loaded, replace projected_final using `learned_remaining_min/12.0` in
    # place of foul_trouble_factor for ALL players. Validated PTS -0.23
    # on 1508-game corpus, 7/7 stats, WF 4/4. Returns a flag so we can
    # skip the now-stale legacy residual overrides which were trained
    # against the heuristic foul_factor we're replacing.
    #
    # BUGFIX (live Q4 correctness): every endQ3 override below was previously
    # gated only on ``int(snap_period) == 4``, so it fired on EVERY period-4
    # snapshot -- all of mid-Q4 AND the clock=0:00 game-over snapshot -- not
    # just the endQ3 BOUNDARY it was trained/validated against. The learned-Q4
    # minutes model, the stratified foul/blowout/heat-check residuals, and the
    # endQ3 residual heads are all defined relative to "36 min observed, 12 min
    # remaining"; applying them mid-Q4 (or at 0:00) corrupts the live
    # projection. Gate them all on the same boundary the period_heads use:
    # snapshot_point_for(period, clock) == "endQ3" (period==4 AND clock near
    # 12:00), mirroring the _USE_RESIDUAL_HEADS_ENDQ2 pattern above.
    if int(snap_period or 0) == 4:
        try:
            from src.prediction.period_specific_heads import snapshot_point_for as _spf
            _at_endq3 = _spf(snap_period, snap_clock) == "endQ3"
        except Exception:
            _at_endq3 = False
    else:
        _at_endq3 = False

    # cycle 110 (loop 5): learned Q4 minutes override at endQ3. When the
    # flag is on AND the snapshot is at the endQ3 boundary AND
    # MinuteTrajectoryModel loaded, replace projected_final using
    # `learned_remaining_min/12.0` in place of foul_trouble_factor for ALL
    # players. Validated PTS -0.23 on 1508-game corpus, 7/7 stats, WF 4/4.
    # Returns a flag so we can skip the now-stale legacy residual overrides
    # which were trained against the heuristic foul_factor we're replacing.
    learned_q4_applied = False
    if _USE_LEARNED_Q4_MINUTES and _at_endq3:
        rows, learned_q4_applied = _apply_learned_q4_minutes(snap, rows)
    # tier1-2 (loop 5): stratified foul_change residual override. Only
    # applies at the endQ3 boundary where the residual model is validated;
    # earlier periods and mid-Q4 keep the cycle-88b heuristic path.
    if (_USE_FOUL_RESIDUAL and _at_endq3
            and not learned_q4_applied):
        rows = _apply_stratified_foul_residual(snap, rows)
    # cycle 102a (loop 5): SECOND stratified override -- blowout_flip
    # residual replaces blow_factor when the live proxy gate fires
    # (|Q3 margin| <= 18 AND |velocity| >= 4). Independent of the foul
    # override; the two override different multiplicative factors so they
    # compose safely.
    if (_USE_BLOWOUT_RESIDUAL and _at_endq3
            and not learned_q4_applied):
        rows = _apply_stratified_blowout_residual(snap, rows)
    # cycle 103b (loop 5): THIRD stratified override -- heat_check shrinkage
    # multiplies projected_final on the REMAINING portion for pts/ast/fg3m
    # when q3_ppm > 1.5 * q12_ppm (with q12_ppm > 0.3). Composes safely with
    # the foul + blowout overrides above (those rewrite projected_final
    # absolutely; this scales the REMAINING delta from current_stat).
    if (_USE_HEAT_CHECK_SHRINKAGE and _at_endq3
            and not learned_q4_applied):
        rows = _apply_heat_check_shrinkage(snap, rows)
    # cycle R2_F (loop 5): per-stat residual heads at endQ3. Applied AFTER all
    # projection source overrides (learned_q4_minutes / period_heads / legacy
    # foul+blowout+heat_check) so the residual correction stacks on the best
    # available point projection. Graceful no-op when artifacts are missing.
    if _USE_RESIDUAL_HEADS and _at_endq3:
        rows = _apply_residual_heads(snap, rows)

    # bonus_ft_bump (CV_INGAME_BONUS_FT): FT-driven PTS bump when opponent is
    # in the bonus.  Applied LAST among projection transforms (after all period
    # heads and residual corrections) so it stacks on the best available
    # projection without being overwritten.  Byte-identical when the flag is OFF.
    # Only affects pts stat; all other stats unchanged.
    if os.environ.get("CV_INGAME_BONUS_FT"):
        try:
            from predict_in_game import _bonus_ft_pts_bump as _bft_bump, _CV_BONUS_FT
            if _CV_BONUS_FT:
                _bft_snap_period = int(snap_period or 1)
                import predict_in_game as _pig_bft
                _bft_clock = float(_pig_bft.parse_clock(snap_clock)) if snap_clock else 12.0
                _bft_home = snap.get("home_team") or ""
                _bft_away = snap.get("away_team") or ""
                _bft_snap_players = list(snap.get("players") or [])
                for _r in rows:
                    if _r.get("stat") != "pts":
                        continue
                    _r_team = _r.get("team") or ""
                    _r_opp = _bft_away if _r_team == _bft_home else _bft_home
                    if not _r_team or not _r_opp:
                        continue
                    _pid = _r.get("player_id")
                    _bump = _bft_bump(
                        player_id=_pid,
                        team=_r_team,
                        opp_team=_r_opp,
                        snap_players=_bft_snap_players,
                        period=_bft_snap_period,
                        clock_rem=_bft_clock,
                    )
                    if _bump > 0.0:
                        _r["projected_final"] = float(_r.get("projected_final", 0.0) or 0.0) + _bump
        except Exception:
            pass  # never break the hot path

    # CV_INGAME_ONOFF_TILT: lineup net-rtg tilt for on-court players.
    # Applied AFTER all point-projection overrides (period heads, residuals,
    # heat_check, bonus_ft) so it scales whatever projection has been produced.
    # Byte-identical when CV_INGAME_ONOFF_TILT is unset (the default).
    # Graceful: any import or data error falls through silently.
    if os.environ.get("CV_INGAME_ONOFF_TILT"):
        try:
            from src.ingame.snapshot_onoff_tilt_enricher import apply_onoff_tilt
            rows = apply_onoff_tilt(snap, rows)
        except Exception:
            pass  # never break the hot path

    # CV_INGAME_MATCHUP_TILT: scheme-based matchup tilt (accuracy-only).
    # Tilts remaining projected delta by each player's historical per-scheme
    # splits vs the opponent team's dominant defensive scheme.
    # Applied AFTER onoff_tilt (stacks on top). Byte-identical when unset.
    # Accuracy-only: vs_scheme atlas has in-season leakage so NOT for betting.
    # Graceful: any import or data error falls through silently.
    if os.environ.get("CV_INGAME_MATCHUP_TILT"):
        try:
            from src.ingame.snapshot_matchup_tilt_enricher import apply_matchup_tilt
            rows = apply_matchup_tilt(snap, rows)
        except Exception:
            pass  # never break the hot path

    # cycle 105c + R1_D_v2 (loop 5): opt-in quantile bands. q50 == projected_final
    # always; q10/q90 are additive. Guarded so the existing point-only
    # consumers (live_dashboard, save_live_predictions, edge_eval) see no
    # row-shape change when the flag is off (the default).
    # R1_D_v2: pass pid + game_date per-row so bands_for can apply per-player
    # variance modulation when the per_player_quantile_calibration artifact is
    # present. game_date is taken from snap.get("game_date") -- if absent (the
    # common live case today) bands_for transparently falls back to the legacy
    # population-level band (back-compat preserved).
    if _INCLUDE_QUANTILE_BANDS:
        try:
            from src.prediction.live_quantile_bands import (
                bands_for, load_calibration, period_to_point,
            )
            point = period_to_point(snap_period) if snap_period is not None else None
            cal = load_calibration()
            snap_game_date: Optional[str] = snap.get("game_date") or None
            # W-037 (CV_STL_BANDS): build a per-player current-stl lookup from
            # the snapshot so the Poisson-remainder path can compute a
            # per-player sigma without re-reading snap["players"] on every row.
            _stl_bands_on = bool(os.environ.get("CV_STL_BANDS"))
            _stl_cur_lookup: Dict[int, float] = {}  # pid -> current_stl
            if _stl_bands_on:
                for _sp in (snap.get("players") or []):
                    try:
                        _pid_sp = int(_sp["player_id"])
                        _stl_val = float(_sp.get("stl") or 0.0)
                        _stl_cur_lookup[_pid_sp] = _stl_val
                    except (TypeError, ValueError, KeyError):
                        pass
            _stl_remaining = _STL_REMAINING_MIN.get(point, 0.0) if point else 0.0
            for r in rows:
                stat = r.get("stat")
                try:
                    q50 = float(r.get("projected_final", 0.0) or 0.0)
                except (TypeError, ValueError):
                    q50 = 0.0
                try:
                    row_pid: Optional[int] = int(r["player_id"]) if r.get("player_id") is not None else None
                except (TypeError, ValueError):
                    row_pid = None
                b = bands_for(stat, q50, point, calibration=cal,
                              pid=row_pid, game_date=snap_game_date)
                r["q10"] = b["q10"]
                r["q50"] = b["q50"]
                r["q90"] = b["q90"]
                # W-037 (CV_STL_BANDS): override STL bands with Poisson
                # remainder when the flag is on and we're at a supported
                # snapshot boundary with meaningful remaining time.
                if (_stl_bands_on and stat == "stl"
                        and _stl_remaining > 0.0
                        and row_pid is not None):
                    try:
                        cur_stl = _stl_cur_lookup.get(row_pid, 0.0)
                        pb = _stl_poisson_band(q50, cur_stl)
                        r["q10"] = pb["q10"]
                        r["q50"] = pb["q50"]
                        r["q90"] = pb["q90"]
                    except Exception:
                        pass  # fall through to empirical band already set
        except Exception:
            # Bands are advisory -- never break the hot path.
            pass

    # R10_M5 (loop 5): stamp every row with the snapshot-conditional in-play
    # home-team win probability. Computed ONCE per snapshot then broadcast to
    # all (player, stat) rows so per-row consumers (UI, ledger, edge eval) can
    # condition on it without re-running the booster. SHIP gate cleared at
    # endQ3 (Brier 0.1350); endQ1/endQ2 outputs are below-gate but still
    # better-than-baseline priors over the 0.523 home rate. Falls back to None
    # when artifacts are missing OR the snapshot is mid-quarter -- callers
    # that need a WP at non-boundary snapshots should keep using the pregame
    # WP. Never breaks the hot path.
    if _USE_INPLAY_WINPROB:
        try:
            from src.prediction.inplay_winprob import (
                features_from_snapshot as _iwp_features,
                predict_home_win_prob as _iwp_predict,
                _period_to_snapshot as _iwp_snap_for,
            )
            iwp_snap_name = _iwp_snap_for(snap_period, snap_clock)
            iwp_prob: Optional[float] = None
            if iwp_snap_name is not None:
                iwp_features = _iwp_features(snap)
                if iwp_features:
                    iwp_prob = _iwp_predict(iwp_features, iwp_snap_name)
            for r in rows:
                r["home_win_prob_inplay"] = iwp_prob
                r["inplay_winprob_snapshot"] = iwp_snap_name
        except Exception:
            # WP is advisory -- never break the hot path. Stamp Nones so
            # downstream schema stays uniform across rows.
            for r in rows:
                r.setdefault("home_win_prob_inplay", None)
                r.setdefault("inplay_winprob_snapshot", None)

    # FULL-SEND Q4 win-prob promotion: in Q4 (period>=4), promote the possession-sim
    # win-prob (attached as sim_home_win_prob by _apply_unified_routed when
    # CV_INGAME_SBS is on) to the SERVED home_win_prob_inplay. Runs AFTER the
    # production inplay_winprob block so it is not clobbered. The sim is the
    # measured-best win-prob from endQ3 on (Brier 0.126 vs 0.136, LogLoss 0.40 vs
    # 0.43) AND fills non-boundary Q4 snapshots where the boundary model returns
    # None. Only fires when the unified head ran (sim_home_win_prob present); before
    # Q4 the production win-prob is left untouched (sigmoid/model wins there).
    try:
        _q4 = int(snap_period or 0) >= 4
    except (TypeError, ValueError):
        _q4 = False
    if _q4:
        for r in rows:
            _swp = r.get("sim_home_win_prob")
            if _swp is not None:
                r["home_win_prob_inplay"] = float(_swp)
                r["winprob_source"] = "possession_sim"

    # SANE CEILING on pace-extrapolated projections (Bug B fix, 2026-05-31).
    # The cycle-88 linear pace extrapolation has no per-stat upper bound, so
    # mid-quarter snapshots can produce impossible lines (e.g. mid-Q1 6 min /
    # 10 pts → projected_final ≈ 80, fg3m=24). These appear for snapshot-only
    # players without a pregame prior AND survive shrink because shrink only
    # multiplies the remaining delta.  Apply a generous-but-physical single-game
    # maximum BEFORE the floor-at-current loop so the floor always wins when
    # current > cap (never possible with the caps below, but belt-and-suspenders).
    #
    # Cap values cite NBA single-game records (generous, not tight):
    #   pts  ≤ 70  (Chamberlain 100 in 1962, modern era record 81 Kobe 2006)
    #   reb  ≤ 30  (Chamberlain 55 in 1960; modern era ≈ 28 Rodman)
    #   ast  ≤ 25  (Scott Skiles 30 in 1990; modern era ≈ 24)
    #   fg3m ≤ 14  (Klay Thompson 14 in 2016)
    #   stl  ≤ 10  (Larry Kenon 11 in 1976; modern era ≈ 9)
    #   blk  ≤ 12  (Elmore Smith 17 in 1973; modern era ≈ 11)
    #   tov  ≤ 12  (plausible game-high; NBA leaders rarely exceed 11)
    #
    # For fg3m specifically: three-point pace is bursty and not rate-stable;
    # early-minute extrapolations are most unreliable.  When minutes_elapsed
    # is < 12 (approximately Q1), dampen the remaining portion with a square-
    # root schedule so the projection converges toward the player's already-
    # scored fg3m + a conservative remainder rather than the raw linear rate.
    # This is a SAFETY CLAMP on the cycle-88 linear projection only — the
    # validated routed-head path (_apply_unified_routed) is not altered.
    _STAT_CAPS = {
        "pts": 70.0,
        "reb": 30.0,
        "ast": 25.0,
        "fg3m": 14.0,
        "stl": 10.0,
        "blk": 12.0,
        "tov": 12.0,
    }
    # Estimate minutes elapsed from the snapshot (best-effort; mid-quarter path).
    try:
        _snap_period_num = int(snap_period or 1)
        _snap_clock_str = str(snap_clock or "12:00")
        _clock_parts = _snap_clock_str.split(":")
        _clock_min = float(_clock_parts[0]) + float(_clock_parts[1]) / 60.0
        # minutes_elapsed = completed quarters * 12 + minutes played this quarter
        _minutes_elapsed = max(0.0, (_snap_period_num - 1) * 12.0 + (12.0 - _clock_min))
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        _minutes_elapsed = 0.0

    import math as _math

    for r in rows:
        stat = r.get("stat")
        cap = _STAT_CAPS.get(stat)
        if cap is None:
            continue
        pf = r.get("projected_final")
        cur = r.get("current")
        if pf is None:
            continue
        try:
            pf_f = float(pf)
            cur_f = float(cur) if cur is not None else 0.0
        except (TypeError, ValueError):
            continue

        # fg3m early-minute sqrt-damping: when < 12 min elapsed, compress the
        # remaining delta toward sqrt-scaled remaining to reduce burst sensitivity.
        if stat == "fg3m" and _minutes_elapsed < 12.0 and pf_f > cur_f:
            _elapsed_frac = max(0.01, _minutes_elapsed / 48.0)
            _remaining_linear = pf_f - cur_f
            # sqrt-damped remaining: scales from 0 (at tip-off) to 1 (at 12 min)
            _sqrt_scale = _math.sqrt(_minutes_elapsed / 12.0)
            _damped_remaining = _remaining_linear * _sqrt_scale
            pf_f = cur_f + _damped_remaining

        # Apply cap: proj = max(min(proj, cap), current).
        # The max(... current) ensures the floor-at-current loop below always wins
        # (caps are generous enough that current never exceeds them in practice).
        pf_f = min(pf_f, cap)
        pf_f = max(pf_f, cur_f)   # never go below what's already recorded
        r["projected_final"] = pf_f

    # FLOOR projected_final at current: a player's FINAL counting stat can never
    # be below what they have ALREADY recorded. Guards the box/cards from showing
    # a projection under the live total (e.g. a player already past his projection).
    for r in rows:
        cur, pf = r.get("current"), r.get("projected_final")
        if cur is not None and pf is not None:
            try:
                if float(pf) < float(cur):
                    r["projected_final"] = float(cur)
            except (TypeError, ValueError):
                pass

    # W-018 (CV_DEFENDER_MATCHUP): Bayesian-shrunk defender-matchup PPP multiplier.
    # Gated default-OFF — byte-identical to baseline when the flag is unset.
    #
    # When ON:
    #   1. Seed snap["matchups"] from the series-prior CSV (most-poss defender).
    #   2. Override with live BoxScoreMatchupsV3 data for the current game.
    #      If the CDN is blocked, writes matchups_source:"unavailable" and
    #      falls through to the series-prior seed.
    #   3. Per row, call apply_matchup_adjustment(player_id, stat, proj, snap)
    #      which Bayesian-shrinks with lambda=poss/(poss+60), MIN_POSS=30 guard,
    #      clamp [0.55,1.55]. No-ops cleanly when defender is unknown.
    # PROTECT AST: AST is the one real edge — skip AST adjustments entirely.
    # Never raises: any failure falls through to unchanged projection.
    if os.environ.get("CV_DEFENDER_MATCHUP"):
        try:
            from src.data.live_matchup_seeder import (
                seed_matchups_from_series,
                override_matchups_from_live_game,
            )
            from src.prediction.defender_matchup_residual import (
                apply_matchup_adjustment,
            )

            # Step 1: seed from series prior (no-op if CSV absent).
            seed_matchups_from_series(snap)

            # Step 2: override with live game matchup data (current game).
            # fetch_fn=None triggers the real fetch; write unavailable marker
            # if the CDN fetch fails / returns nothing.
            _gid = snap.get("game_id")
            _live_overrides_applied = False
            if _gid:
                _snap_before = len((snap.get("matchups") or {}))
                override_matchups_from_live_game(snap, game_id=_gid)
                _meta = snap.get("_matchups_meta") or {}
                _live_overrides = _meta.get("live_overrides", 0)
                # If the override returned 0 entries AND the series seed also
                # gave 0, mark the source unavailable so consumers can log it.
                if (not snap.get("matchups")
                        and _live_overrides == 0):
                    snap["matchups_source"] = "unavailable"
                else:
                    _live_overrides_applied = (_live_overrides > 0)
                    snap["matchups_source"] = (
                        "live_game" if _live_overrides_applied else "series_prior"
                    )
            else:
                if not snap.get("matchups"):
                    snap["matchups_source"] = "unavailable"
                else:
                    snap["matchups_source"] = "series_prior"

            # Step 3: apply per-row matchup adjustment (SKIP AST — protected edge).
            _MATCHUP_STATS = ("pts", "fg3m", "stl", "blk", "tov")
            for r in rows:
                stat = r.get("stat")
                if stat not in _MATCHUP_STATS:
                    # REBounds not in matchup tape; AST is the protected edge.
                    continue
                pid = r.get("player_id")
                pf = r.get("projected_final")
                if pid is None or pf is None:
                    continue
                try:
                    adj_pf, reason = apply_matchup_adjustment(
                        pid, stat, pf, snapshot=snap,
                    )
                    if adj_pf != pf:
                        r["projected_final"] = float(adj_pf)
                        src = str(r.get("projection_source") or "")
                        if "+matchup" not in src:
                            r["projection_source"] = src + "+matchup"
                    r["matchup_reason"] = reason
                except Exception:
                    pass  # Never let matchup adjustment break the hot path.
        except Exception:
            # Belt-and-suspenders: if anything in the whole W-018 block fails,
            # fall through with the unchanged rows.
            pass

    # W-023 (CV_INGAME_VAC_AST): star-stagger / vac_ast attach to live rows.
    # Gated default-OFF — byte-identical to baseline when the flag is unset.
    # HARD-OFF in playoffs (game_id prefix "004") — the AST edge inverts
    # postseason (-2.78% gated). When ON + regular-season + game_date known:
    #   1. Build the leak-free vac_ast lookup (memoised per-process).
    #   2. For each AST row: look up (player_id, game_date); scale projected_final
    #      up by 1.25x (vac_ast>=3) or 1.50x (vac_ast>=6).
    #   3. Attach vac_ast field (0.0 default) to EVERY row so downstream
    #      callers (bet_selector, edge UI) can read it without another lookup.
    # Sizing is conservative (durable ~+5-8% floor, NOT the +15.6% in-window
    # peak) per the campaign lesson: size on the floor, never the regime peak.
    # Byte-identical when OFF: the gate is the very first check.
    rows = _apply_ingame_vac_ast(snap, rows)

    # CV_INGAME_STATE (P3.1/P3.2): the consolidated Bayesian in-game player update
    # (src/ingame/live_state_hook.apply_ingame_state -> GameState + bayes_player_update).
    # Replaces the 4-5 endQ3 correction heads with ONE parametric posterior whose DEFAULT
    # trust curve is IDENTITY -> trust_w==0 -> posterior == prior -> every row is left
    # UNTOUCHED -> byte-identical to the OFF path. The hook only re-prices once a
    # trust-curve json is GATED on RMSE+bias (scripts/ingame/ingame_rmsebias_harness.py).
    # Default-OFF (flag unset) = pure no-op. Never breaks the hot path (the helper is
    # internally wrapped). Placed BEFORE the deterministic guards so final-freeze / foul-out
    # still have the final word on a frozen box.
    if os.environ.get("CV_INGAME_STATE"):
        try:
            from src.ingame.live_state_hook import apply_ingame_state
            rows = apply_ingame_state(snap, rows)
        except Exception:
            pass  # never break the hot path

    # ── DETERMINISTIC END-STATE GUARDS (applied LAST, so they are the final word
    #    on the SERVED projected_final regardless of which head — base cycle-88 or
    #    the routed/v2 overlay (_apply_unified_routed) — produced it). Both are
    #    gated default-OFF and byte-identical when their flag is unset. ───────────
    #
    # LIVE-BOX-SCORE ACCURACY (CV_INGAME_SHRINK): the routed/v2 head systematically
    # OVER-projects sparse defensive stats and late-game scoring (it extrapolates a
    # rate forward where little/nothing actually accumulates). Held-out fold-3
    # decomposition (ingame_eval_cache, 539k rows): freezing blk -22.4% / stl -13.7%
    # MAE; late-game (>=42 elapsed min) pts -23.5% / reb -27.6%; fg3m/tov 30%-shrink
    # -3.8/-2.9%. Shrink projected_final toward current per the validated per-stat
    # weights. Applied BEFORE the freeze/foul-out guards so those still fully override
    # their edge cases. Default-OFF = byte-identical. doc LIVE_BOXSCORE_ACCURACY.md.
    rows = _apply_sparse_shrink(snap, rows)

    # BUG-5 FINAL-FREEZE (CV_INGAME_FINAL_FREEZE): a finished game (game_status
    # FINAL, or regulation clock expired with no OT possible) cannot accumulate
    # any further stats, so the served projected_final MUST equal the current box
    # value for every row. The served routed/v2 head adds a learned remaining-delta
    # even at zero remaining time (sweep: 6 real FINAL snapshots over-projected PTS
    # +1.58 avg, max +4.61 — Wemby 26->30.6). Freezing every row to current removes
    # the phantom extrapolation. Applied BEFORE the foul-out cap (a final game is a
    # superset freeze); fouled-out rows are then a no-op under the same value.
    rows = _apply_final_freeze(snap, rows)

    # BUG-1 FOUL-OUT (CV_INGAME_FOULOUT_CAP): a player disqualified with >= 6
    # personal fouls is ejected and cannot play another second, so every counting
    # stat's projected_final MUST equal the current box value (deterministic from
    # the box). The served v2 head is nearly flat on foul state (sweep: pf=1->6
    # moves only 0.03 pts while a fouled-out player is over-projected +5.2 pts at
    # midQ3), biasing every fouled-out prop toward the OVER. The snapshot carries
    # per-player ``pf`` (the live poller emits it), so this is a pure box clamp.
    rows = _apply_foulout_cap(snap, rows)

    # CV_INGAME_UNIVERSAL_WP (P3.4): the projected-final win-prob INTERFACE
    # (src/ingame/live_state_hook.apply_universal_winprob -> universal_winprob). Computed from
    # the PROJECTED final margin (sum of final pts projections, never the raw live margin),
    # using the FINAL post-guard projections here at the tail of the pipeline. Routes into the
    # served home_win_prob_inplay ONLY when eligible (Q4+ AND coverage_class==mc_full AND a
    # projection exists); otherwise FAILS CLOSED to the existing inplay/sim win-prob stack.
    # Default-OFF (flag unset) = pure no-op (byte-identical). Never breaks the hot path.
    if os.environ.get("CV_INGAME_UNIVERSAL_WP"):
        try:
            from src.ingame.live_state_hook import apply_universal_winprob
            rows = apply_universal_winprob(snap, rows)
        except Exception:
            pass  # never break the hot path

    return rows


# ── DETERMINISTIC END-STATE GUARDS (BUG-1 foul-out, BUG-5 final freeze) ────────

# The 7 counting stats that are frozen/capped to the current box value. These are
# exactly the per-(player, stat) rows project_from_snapshot emits.
_FROZEN_COUNTING_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# A player is DISQUALIFIED (fouled out) at >= 6 personal fouls — they are ejected
# and accumulate nothing further, so the final box == the current box.
_FOULOUT_PF = 6.0


def _freeze_row_to_current(r: dict) -> None:
    """Set a projection row's projected_final (and q50 if present) to current.

    Deterministic clamp used by both end-state guards: a frozen/disqualified row
    can accumulate nothing further, so the final == the current box value. Only
    touches projected_final and the q50 band mirror (q50 == projected_final by the
    band contract); q10/q90 are left as-is (advisory). Never raises.
    """
    cur = r.get("current")
    if cur is None:
        return
    try:
        cur_f = float(cur)
    except (TypeError, ValueError):
        return
    r["projected_final"] = cur_f
    # q50 mirrors projected_final by the live_quantile_bands contract; keep it
    # coherent when bands were already attached upstream.
    if "q50" in r:
        r["q50"] = cur_f


def _game_is_final(snap: dict) -> bool:
    """True when the game is over for projection purposes (BUG-5).

    A game is final when EITHER:
      * game_status indicates FINAL (canonical src/data/live.is_final semantics), OR
      * the regulation/OT clock has expired with no further period possible:
        period >= 4 AND parsed clock <= 0:00 AND the score is not tied (a tie at
        the end of regulation -> OT, so the game is NOT over — do not freeze).

    Pure read of the snapshot; never raises. The clock-expired branch is a belt-
    and-suspenders fallback for snapshots that carry a 0:00 clock before the feed
    flips game_status to FINAL.
    """
    status = str(snap.get("game_status") or "").strip().upper()
    if status == "FINAL":
        return True
    try:
        period = int(snap.get("period") or 0)
    except (TypeError, ValueError):
        period = 0
    if period < 4:
        return False
    # Parse the clock via the canonical live helper (handles 'M:SS' / '' / None).
    try:
        from src.data.live import parse_clock as _parse_clock
        clock_rem = _parse_clock(snap.get("clock"))
    except Exception:
        return False
    if clock_rem > 0.0:
        return False
    # Clock 0:00 in Q4+: only final if the game can't go to OT (not tied).
    try:
        home = float(snap.get("home_score") or 0.0)
        away = float(snap.get("away_score") or 0.0)
    except (TypeError, ValueError):
        return False
    return home != away


def _apply_final_freeze(snap: dict, rows: List[Dict]) -> List[Dict]:
    """BUG-5 (CV_INGAME_FINAL_FREEZE): freeze every projection to current when the
    game is over. Gated default-OFF (byte-identical when the flag is unset).

    A finished game cannot accumulate any further stats, so the served
    projected_final == the current box value for every (player, stat) row. Acts on
    whatever projected_final the upstream heads produced (base or routed/v2), so it
    corrects the served value under the golive SBS stack. Never raises.
    """
    if not os.environ.get("CV_INGAME_FINAL_FREEZE"):
        return rows
    try:
        if not _game_is_final(snap):
            return rows
        for r in rows:
            _freeze_row_to_current(r)
            src = str(r.get("projection_source") or "")
            if "+final_freeze" not in src:
                r["projection_source"] = src + "+final_freeze"
    except Exception:
        # Never let the freeze guard break the hot path.
        return rows
    return rows


def _apply_foulout_cap(snap: dict, rows: List[Dict]) -> List[Dict]:
    """BUG-1 (CV_INGAME_FOULOUT_CAP): cap every counting-stat projection to current
    for any player who has fouled out (pf >= 6). Gated default-OFF (byte-identical
    when the flag is unset).

    A disqualified player is ejected and cannot accumulate further, so the final
    box == the current box. The snapshot carries per-player ``pf`` (the live poller
    emits it); when a row's player is not found in the snapshot or carries no pf,
    it is left unchanged (no fabrication). Acts on whatever projected_final the
    upstream heads produced (base or routed/v2). Never raises.
    """
    if not os.environ.get("CV_INGAME_FOULOUT_CAP"):
        return rows
    try:
        # Build a leak-free pid -> pf lookup straight from the snapshot box.
        pf_by_pid: Dict[int, float] = {}
        for p in (snap.get("players") or []):
            pid_raw = p.get("player_id")
            if pid_raw is None:
                continue
            try:
                pid_k = int(pid_raw)
            except (TypeError, ValueError):
                continue
            pf_val = p.get("pf")
            if pf_val is None:
                continue
            try:
                pf_by_pid[pid_k] = float(pf_val)
            except (TypeError, ValueError):
                continue
        if not pf_by_pid:
            return rows
        for r in rows:
            if r.get("stat") not in _FROZEN_COUNTING_STATS:
                continue
            pid_raw = r.get("player_id")
            if pid_raw is None:
                continue
            try:
                pid_k = int(pid_raw)
            except (TypeError, ValueError):
                continue
            pf_val = pf_by_pid.get(pid_k)
            if pf_val is None or pf_val < _FOULOUT_PF:
                continue
            _freeze_row_to_current(r)
            src = str(r.get("projection_source") or "")
            if "+foulout_cap" not in src:
                r["projection_source"] = src + "+foulout_cap"
    except Exception:
        # Never let the foul-out cap break the hot path.
        return rows
    return rows


# CV_INGAME_SHRINK weights — shrink projected_final TOWARD current. The routed/v2
# head over-projects these stats (extrapolates a rate forward where little
# accumulates). Held-out fold-3 optimum was ~1.0 for blk/stl; we use 0.9 to keep a
# sliver of forward signal (still captures the bulk of the -22%/-14%). AST is
# DELIBERATELY EXCLUDED (sacred edge stat — never reshape its served projection).
_INGAME_SHRINK_W = {"blk": 0.9, "stl": 0.9, "fg3m": 0.3, "tov": 0.3, "reb": 0.1, "pts": 0.05}
# Additional heavy shrink for pts/reb once the game is late (>=42 elapsed min),
# where the head over-projects remaining scoring/rebounding the most (-23%/-28%).
_INGAME_LATE_SHRINK_W = {"pts": 0.7, "reb": 0.7}
_INGAME_LATE_MIN = 42.0


def _snap_elapsed_min(snap: dict) -> float:
    """Approximate game minutes elapsed from period + clock. Safe 0.0 default."""
    try:
        period = int(snap.get("period") or 1)
        clk = snap.get("clock")
        if clk is None:
            csec = 0.0
        elif isinstance(clk, (int, float)):
            csec = float(clk)
        else:
            s = str(clk).strip()
            csec = (float(s.split(":")[0]) * 60 + float(s.split(":")[1])) if ":" in s else float(s)
        per_len = 720.0 if period <= 4 else 300.0
        elapsed_in_per = max(0.0, per_len - csec)
        if period <= 4:
            return ((period - 1) * 720.0 + elapsed_in_per) / 60.0
        return (2880.0 + (period - 5) * 300.0 + elapsed_in_per) / 60.0
    except Exception:
        return 0.0


def _apply_sparse_shrink(snap: dict, rows: List[Dict]) -> List[Dict]:
    """CV_INGAME_SHRINK (default OFF = byte-identical): shrink each row's
    projected_final toward current per the validated per-stat weights, plus a heavy
    late-game shrink for pts/reb. The routed/v2 head over-projects sparse defensive
    stats and late-game production; this is a deterministic, leak-free box-score
    accuracy fix (held-out fold-3 MAE: blk -22.4%, stl -13.7%, late pts -23.5%,
    late reb -27.6%, fg3m -3.8%, tov -2.9%). AST excluded (sacred). Never raises.
    """
    if not os.environ.get("CV_INGAME_SHRINK"):
        return rows
    try:
        is_late = _snap_elapsed_min(snap) >= _INGAME_LATE_MIN
        for r in rows:
            stat = r.get("stat")
            w = _INGAME_SHRINK_W.get(stat, 0.0)
            if is_late and stat in _INGAME_LATE_SHRINK_W:
                w = max(w, _INGAME_LATE_SHRINK_W[stat])
            if w <= 0.0:
                continue
            cur, pf = r.get("current"), r.get("projected_final")
            if cur is None or pf is None:
                continue
            try:
                new = w * float(cur) + (1.0 - w) * float(pf)
            except (TypeError, ValueError):
                continue
            r["projected_final"] = new
            if "q50" in r:
                r["q50"] = new
            src = str(r.get("projection_source") or "")
            if "+shrink" not in src:
                r["projection_source"] = src + "+shrink"
    except Exception:
        return rows
    return rows


# W-023: module-scope lazy cache for the vac_ast lookup (built once per process).
_VAC_AST_INGAME_CACHE: Optional[dict] = None
_VAC_AST_INGAME_LOAD_FAILED: bool = False

# Sizing constants (mirror intel_selection.py — size on durable ~+5-8%, NOT peak).
_INGAME_VAC_AST_MIN = 3.0        # minimum vacated L10 assists to trigger
_INGAME_VAC_AST_BIG = 6.0        # threshold for the larger multiplier
_INGAME_VAC_AST_MULT_BASE = 1.25  # base up-size when vac_ast >= 3
_INGAME_VAC_AST_MULT_BIG = 1.50   # larger up-size when vac_ast >= 6 (2+ creators out)


def _apply_ingame_vac_ast(snap: dict, rows: list) -> list:
    """W-023: attach vac_ast to live rows; scale AST projected_final up when
    a primary creator is confirmed OUT (reg-season only; HARD-OFF in playoffs).

    Gated by CV_INGAME_VAC_AST (default OFF = byte-identical to baseline).
    HARD-OFF for any game_id with prefix "004" (postseason) because the AST
    edge inverts in playoffs (-2.78% gated vs +7% regular-season).

    When ON + regular season + game_date resolvable:
      - Loads the leak-free vac_ast lookup from prop_pergame (memoised).
      - Attaches ``vac_ast`` field (0.0 default) to EVERY row.
      - For AST rows with vac_ast >= 3: scales projected_final by 1.25x;
        1.50x when vac_ast >= 6 (two+ creators out). Sizing is conservative
        — the durable floor is ~+5-8%, not the +15.6% in-window peak.
      - Never touches current_stat; only the remaining projection delta.
      - Any failure falls through with rows unchanged (never breaks hot path).

    Args:
        snap:  canonical live snapshot dict (must have game_id; game_date
               optional — falls back to no-op when unresolvable).
        rows:  list of projection row dicts from project_from_snapshot.

    Returns:
        rows with vac_ast attached; AST projected_final scaled for confirmed-out
        creators; unchanged rows when the gate is OFF or conditions unmet.
    """
    global _VAC_AST_INGAME_CACHE, _VAC_AST_INGAME_LOAD_FAILED

    # Gate 1: flag must be set truthy (default OFF = strict byte-identical no-op).
    if not os.environ.get("CV_INGAME_VAC_AST"):
        return rows

    # Gate 2: HARD-OFF in playoffs (game_id prefix "004").
    game_id = str(snap.get("game_id") or "")
    if game_id.startswith("004"):
        return rows

    # Gate 3: resolve game_date (YYYY-MM-DD).  The live serve path writes
    # game_date into the snapshot; retro calibration snapshots don't have it.
    # When absent, we fall through to a no-op so the retro harness stays
    # byte-identical (the live benefit is structural, not measurable retro).
    game_date: Optional[str] = snap.get("game_date") or None
    if game_date is None:
        # Attach 0.0 vac_ast to all rows for schema consistency, then bail.
        for r in rows:
            r.setdefault("vac_ast", 0.0)
        return rows

    # Normalise to 'YYYY-MM-DD' (accept ISO datetime too).
    try:
        game_date = str(game_date)[:10]
    except Exception:
        for r in rows:
            r.setdefault("vac_ast", 0.0)
        return rows

    # Load the vac_ast lookup (memoised; built once per process).
    if not _VAC_AST_INGAME_LOAD_FAILED and _VAC_AST_INGAME_CACHE is None:
        try:
            from src.prediction.prop_pergame import build_vac_ast_lookup
            _VAC_AST_INGAME_CACHE = build_vac_ast_lookup()
        except Exception:
            _VAC_AST_INGAME_LOAD_FAILED = True
            _VAC_AST_INGAME_CACHE = {}

    lkp = _VAC_AST_INGAME_CACHE or {}

    # Apply per row.
    try:
        for r in rows:
            stat = r.get("stat")
            pid = r.get("player_id")
            pid_key = int(pid) if pid is not None else None
            rec = lkp.get((pid_key, game_date)) if pid_key is not None else None
            va = float(rec["vac_ast"]) if (rec and rec.get("vac_ast") is not None) else 0.0
            r["vac_ast"] = va

            # Scale AST projected_final for confirmed-out creator scenarios.
            if stat != "ast" or va < _INGAME_VAC_AST_MIN:
                continue
            pf = r.get("projected_final")
            cur = r.get("current")
            if pf is None:
                continue
            try:
                pf_f = float(pf)
                cur_f = float(cur) if cur is not None else 0.0
            except (TypeError, ValueError):
                continue
            # Only scale the REMAINING projection (not what's already scored).
            remaining = pf_f - cur_f
            if remaining <= 0.0:
                continue
            mult = _INGAME_VAC_AST_MULT_BIG if va >= _INGAME_VAC_AST_BIG else _INGAME_VAC_AST_MULT_BASE
            r["projected_final"] = cur_f + remaining * mult
            src = str(r.get("projection_source") or "")
            if "+vac_ast" not in src:
                r["projection_source"] = src + "+vac_ast"
    except Exception:
        # Belt-and-suspenders: never let vac_ast scaling break the hot path.
        pass

    return rows


def _apply_residual_heads(snap: dict, rows: list) -> list:
    """cycle R2_F: add per-(player, stat) residual head correction at endQ3.

    Calls ``src.prediction.residual_heads.apply_residual_correction`` to get
    updated projected_final values, then tags each modified row's
    ``projection_source`` with "+residual_head". Graceful no-op if the
    helper import fails or no artifacts are present.
    """
    try:
        from src.prediction.residual_heads import (
            apply_residual_correction,
            load_heads,
        )
    except Exception:
        return rows

    try:
        heads = load_heads()
        if not heads:
            return rows
    except Exception:
        return rows

    # Build projs dict from current rows for the helper.
    projs: Dict = {}
    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            projs[(int(pid), str(stat))] = float(r.get("projected_final") or 0.0)
        except (TypeError, ValueError):
            continue

    try:
        updated = apply_residual_correction(snap, projs)
    except Exception:
        # Never break the hot path.
        return rows

    # Apply updated projections back to rows.
    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            key = (int(pid), str(stat))
        except (TypeError, ValueError):
            continue
        new_val = updated.get(key)
        if new_val is None:
            continue
        old_val = r.get("projected_final")
        # Only tag + update when the correction actually changed the value.
        try:
            changed = abs(float(new_val) - float(old_val or 0.0)) > 1e-9
        except (TypeError, ValueError):
            changed = True
        if changed:
            r["projected_final"] = float(new_val)
            src = str(r.get("projection_source") or "")
            if not src.endswith("+residual_head"):
                r["projection_source"] = src + "+residual_head"

    return rows


def _apply_residual_heads_endq2(snap: dict, rows: list) -> list:
    """cycle R3_A: add per-(player, stat) residual head correction at endQ2.

    Calls ``src.prediction.residual_heads.apply_residual_correction_endq2``
    to get updated projected_final values, then tags each modified row's
    ``projection_source`` with "+residual_head_endq2". Graceful no-op if
    the helper import fails or no artifacts are present.
    """
    try:
        from src.prediction.residual_heads import (
            apply_residual_correction_endq2,
            load_heads_endq2,
        )
    except Exception:
        return rows

    try:
        heads = load_heads_endq2()
        if not heads:
            return rows
    except Exception:
        return rows

    # Build projs dict from current rows for the helper.
    projs: Dict = {}
    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            projs[(int(pid), str(stat))] = float(r.get("projected_final") or 0.0)
        except (TypeError, ValueError):
            continue

    try:
        updated = apply_residual_correction_endq2(snap, projs)
    except Exception:
        # Never break the hot path.
        return rows

    # Apply updated projections back to rows.
    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            key = (int(pid), str(stat))
        except (TypeError, ValueError):
            continue
        new_val = updated.get(key)
        if new_val is None:
            continue
        old_val = r.get("projected_final")
        # Only tag + update when the correction actually changed the value.
        try:
            changed = abs(float(new_val) - float(old_val or 0.0)) > 1e-9
        except (TypeError, ValueError):
            changed = True
        if changed:
            r["projected_final"] = float(new_val)
            src = str(r.get("projection_source") or "")
            if not src.endswith("+residual_head_endq2"):
                r["projection_source"] = src + "+residual_head_endq2"

    return rows


def _apply_period_heads(snap: dict, rows: list) -> list:
    """cycle 106a: replace projected_final using cycle-105b period-specific
    LightGBM heads at endQ1 / endQ2 boundaries.

    For each (player, stat) row, if the snapshot is at an endQ1 or endQ2
    boundary AND the corresponding head artifact loads, set
    ``projected_final = current_stat + predict_remaining(...)`` and tag
    ``projection_source`` accordingly. Otherwise leave the row untouched
    (cycle-88 linear extrap output is preserved).
    """
    try:
        from src.prediction import period_specific_heads as psh
    except Exception:
        return rows

    snap_period = snap.get("period")
    snap_clock = snap.get("clock")
    point = psh.snapshot_point_for(snap_period, snap_clock)
    # Only endQ1 + endQ2 are wired; endQ3 (period=4 boundary) deliberately
    # excluded per cycle 105b ship notes.
    if point not in ("endQ1", "endQ2"):
        return rows

    # cycle 107b: enrich snapshot player dicts with pregame rolling features
    # (l5/l20/position) before head inference.  The period heads were trained
    # on these features; without enrichment LightGBM sees NaN for 4/12 inputs
    # and falls back to unconditional splits.  Enrichment is best-effort —
    # if the gamelog is absent the keys stay absent (back-compat NaN path).
    try:
        from src.prediction.pregame_enrichment import (
            enrich_snapshot_with_pregame_features,
        )
        snap = enrich_snapshot_with_pregame_features(snap)
    except Exception:
        pass

    src_tag = f"{point}_head"
    observed_qs = psh.SNAPSHOT_QUARTERS[point]

    # Index players by pid for per-row feature lookup.
    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    # Score context (shared across all players in this snapshot).
    try:
        home_score = float(snap.get("home_score") or 0)
    except (TypeError, ValueError):
        home_score = 0.0
    try:
        away_score = float(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        away_score = 0.0
    margin_signed = home_score - away_score
    margin_abs = abs(margin_signed)
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""

    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat not in psh.STATS:
            continue
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            continue
        p = by_pid.get(pid_i)
        if p is None:
            continue

        # current stat through the snapshot.
        try:
            current_stat = float(p.get(stat) or 0)
        except (TypeError, ValueError):
            current_stat = 0.0

        # min_through = sum of per-quarter min for OBSERVED quarters; fall
        # back to player's reported `min` if per-quarter splits missing.
        min_through = 0.0
        any_q = False
        for q in observed_qs:
            v = p.get(f"min_q{q}")
            if v is not None:
                any_q = True
                try:
                    min_through += float(v or 0)
                except (TypeError, ValueError):
                    pass
        if not any_q:
            try:
                min_through = float(p.get("min") or 0)
            except (TypeError, ValueError):
                min_through = 0.0

        try:
            pf_through = float(p.get("pf") or 0)
        except (TypeError, ValueError):
            pf_through = 0.0

        team = p.get("team") or ""
        team_is_leading = (
            (team == home_team and margin_signed > 0)
            or (team == away_team and margin_signed < 0)
        )

        try:
            remaining = psh.predict_remaining(
                stat, point,
                current_stat=current_stat,
                min_through=min_through,
                pf_through=pf_through,
                score_margin_abs=margin_abs,
                is_leading_team=1 if team_is_leading else 0,
                l5_stat=p.get(f"l5_{stat}"),
                l20_stat=p.get(f"l20_{stat}"),
                l20_min=p.get("l20_min"),
                position_proxy=p.get("position"),
            )
        except Exception:
            remaining = None

        if remaining is None:
            # Artifact missing -> keep cycle-88 linear projection.
            continue

        r["projected_final"] = float(current_stat + max(0.0, float(remaining)))
        r["projection_source"] = src_tag

    return rows


def _apply_stratified_foul_residual(snap: dict, rows: list) -> list:
    """Re-project per-player stats using stratified_minute_factor when the
    foul_change gate fires. Returns a new list with overrides applied
    in-place on the original row dicts.

    Untouched when both LightGBM artifacts are absent (graceful no-op).
    """
    global_model, residual_model, _, _ = _load_models_once()
    # If NEITHER model is loaded we have nothing to add over the heuristic.
    if global_model is None and residual_model is None:
        return rows

    import predict_in_game as pig
    from src.prediction.minute_trajectory_foul_residual import (
        stratified_minute_factor,
    )

    period = int(snap.get("period") or 0)
    clock_rem = pig.parse_clock(snap.get("clock"))
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""
    try:
        home_score = float(snap.get("home_score") or 0)
    except (TypeError, ValueError):
        home_score = 0.0
    try:
        away_score = float(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        away_score = 0.0
    margin = home_score - away_score

    # Index input players for fast lookup by player_id.
    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    # Group output rows by player_id for in-place rewrite.
    rows_by_pid: dict = {}
    for r in rows:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            rows_by_pid.setdefault(int(pid), []).append(r)
        except (TypeError, ValueError):
            continue

    for pid, p in by_pid.items():
        try:
            snap_pf = float(p.get("pf") or 0)
            cur_min = float(p.get("min") or 0)
            min_q1 = float(p.get("min_q1") or 0)
            min_q2 = float(p.get("min_q2") or 0)
            min_q3 = float(p.get("min_q3") or 0)
        except (TypeError, ValueError):
            continue
        # We don't have an authoritative q3_pf alone; approximate by the
        # standard endQ3 heuristic used in probe_stratified_blend.py.
        q3_pf_proxy = max(0.0, snap_pf - 2.0)
        team = p.get("team") or ""
        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )
        ff = stratified_minute_factor(
            global_model=global_model,
            residual_model=residual_model,
            pf_through_q3=snap_pf,
            q3_pf=q3_pf_proxy,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            score_margin_abs=abs(margin),
            is_leading_team=1 if team_is_leading else 0,
            position_proxy=p.get("position"),
            l20_min=p.get("l20_min"),
            l5_min=p.get("l5_min"),
            q2_pf=p.get("q2_pf", 0),
        )
        share_played_game = pig.clock_played_share(period, clock_rem)
        proj_min = ((cur_min / share_played_game)
                    if share_played_game > 0 else cur_min)
        is_star = proj_min >= 30.0
        bf = pig.blowout_factor(
            abs(margin), period, is_star=(is_star and team_is_leading))
        period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
        bench_now = pig.is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min)
        player_basis = cur_min if bench_now else None

        out_rows = rows_by_pid.get(pid, [])
        for r in out_rows:
            stat = r.get("stat")
            if stat not in pig.STATS:
                continue
            try:
                cur = float(p.get(stat) or 0)
            except (TypeError, ValueError):
                cur = 0.0
            new_final = pig.project_final(
                cur, period, clock_rem,
                pace_factor=1.0, foul_factor=ff, blow_factor=bf,
                player_clock_played_min=player_basis,
            )
            r["projected_final"] = float(new_final)
            r["foul_factor"] = ff
            r["blow_factor"] = bf
            r["minute_factor_source"] = (
                "foul_residual"
                if (residual_model is not None
                    and _foul_change_gate_inline(snap_pf, q3_pf_proxy))
                else "global_min_trajectory"
            )
    return rows


def _foul_change_gate_inline(snap_pf, q3_pf):
    """Local copy of in_foul_change_stratum to avoid a tight import loop in
    the override hot path. Mirrors src.prediction.minute_trajectory_foul_residual.
    """
    try:
        sp = int(snap_pf)
        q3 = int(q3_pf)
    except (TypeError, ValueError):
        return False
    if q3 >= 2:
        return True
    if sp >= 3:
        return True
    if q3 == 0 and sp == 4:
        return True
    return False


# ── cycle 102a: blowout_flip residual override ────────────────────────────────

def _apply_stratified_blowout_residual(snap: dict, rows: list) -> list:
    """Re-project per-player stats using stratified_blowout_factor when the
    blowout_flip live-proxy gate fires. Returns the same list with
    overrides applied in-place on the original row dicts.

    Composes cleanly with the foul_residual override: the foul override
    rewrote ``foul_factor``; this one rewrites ``blow_factor``. Both
    multiplicative inputs feed the same ``pig.project_final``.

    Untouched when the blowout_residual artifact is absent (graceful no-op).

    W-020 (CV_BLOWOUT_RESIDUAL_LIVE): when the flag is set, derives
    ``score_velocity_q3`` from available per-quarter score fields on the snap
    (home_q3/away_q3) and adds a playoff guard (game_id prefix "004").
    When the flag is OFF (the default) the function degrades to a no-op
    because ``score_velocity_q3`` defaults to 0 and the live-proxy gate
    never fires -- byte-identical to the pre-flag baseline.
    """
    # W-020 (CV_BLOWOUT_RESIDUAL_LIVE): early-exit when flag is OFF.
    # The existing code path defaults score_velocity_q3 to 0, so the live-proxy
    # gate never fires and the function is already a no-op in practice.
    # Exiting early here makes the byte-identical guarantee explicit and avoids
    # paying the model-load overhead in the default serving config.
    if not os.environ.get("CV_BLOWOUT_RESIDUAL_LIVE"):
        return rows

    # Playoff guard: blowout dynamics differ in the playoffs (smaller sample,
    # lower predictability). Never fire in playoff games (game_id prefix "004").
    game_id = str(snap.get("game_id") or "")
    if game_id.startswith("004"):
        return rows

    _, _, blowout_model, _ = _load_models_once()
    if blowout_model is None:
        return rows

    import predict_in_game as pig
    from src.prediction.blowout_residual import (
        in_blowout_flip_live_proxy,
        stratified_blowout_factor,
    )

    period = int(snap.get("period") or 0)
    clock_rem = pig.parse_clock(snap.get("clock"))
    home_team = snap.get("home_team") or ""
    away_team = snap.get("away_team") or ""
    try:
        home_score = float(snap.get("home_score") or 0)
    except (TypeError, ValueError):
        home_score = 0.0
    try:
        away_score = float(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        away_score = 0.0
    margin = home_score - away_score   # signed home POV

    # W-020: Derive score_velocity_q3 from available snapshot fields.
    # Priority order:
    #   1. Explicit snap.get("score_velocity_q3") -- set by probe scripts / W-030
    #   2. snap.get("home_q3") - snap.get("away_q3") -- per-quarter score injected
    #      by the win-prob path (courtvision_router.py) or W-030 enrichment.
    #      At endQ3, home_q3/away_q3 = team points scored IN Q3 specifically,
    #      so their difference = Q3 margin swing (= velocity from Q2 to Q3 POV).
    #   3. Sum player pts_q3 per team -- available in the retro calibration corpus
    #      (retro_inplay_mae.py attaches min_q1..min_q4; pts_q3 is in the parquet).
    #   4. Fall back to 0.0 (gate won't fire -- graceful no-op).
    velocity: float = 0.0
    snap_velocity = snap.get("score_velocity_q3")
    if snap_velocity is not None:
        try:
            velocity = float(snap_velocity)
        except (TypeError, ValueError):
            velocity = 0.0
    else:
        # Try per-quarter team scores injected by the win-prob router path.
        hq3 = snap.get("home_q3")
        aq3 = snap.get("away_q3")
        if hq3 is not None and aq3 is not None:
            try:
                # velocity = Q3 margin - Q2 margin.  Since home_q3/away_q3 are
                # the points scored *in* Q3 (not cumulative), the delta is simply
                # home_q3 - away_q3 (positive = home pulled away in Q3).
                velocity = float(hq3) - float(aq3)
            except (TypeError, ValueError):
                velocity = 0.0
        else:
            # Fallback: aggregate pts_q3 from player rows (retro calibration corpus
            # path). Players in the retro corpus carry min_q1..q4 but not pts_q3;
            # this branch fires only when pts_q3 is explicitly present on rows.
            home_q3_pts: float = 0.0
            away_q3_pts: float = 0.0
            for _p in snap.get("players") or []:
                _team = _p.get("team") or ""
                _pts3 = _p.get("pts_q3")
                if _pts3 is None:
                    continue
                try:
                    _v = float(_pts3)
                except (TypeError, ValueError):
                    continue
                if _team == home_team:
                    home_q3_pts += _v
                elif _team == away_team:
                    away_q3_pts += _v
            if home_q3_pts > 0 or away_q3_pts > 0:
                velocity = home_q3_pts - away_q3_pts

    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    rows_by_pid: dict = {}
    for r in rows:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            rows_by_pid.setdefault(int(pid), []).append(r)
        except (TypeError, ValueError):
            continue

    for pid, p in by_pid.items():
        try:
            snap_pf = float(p.get("pf") or 0)
            cur_min = float(p.get("min") or 0)
            min_q1 = float(p.get("min_q1") or 0)
            min_q2 = float(p.get("min_q2") or 0)
            min_q3 = float(p.get("min_q3") or 0)
        except (TypeError, ValueError):
            continue
        q3_pf_proxy = max(0.0, snap_pf - 2.0)
        team = p.get("team") or ""
        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )
        # Signed Q3 margin from this team's POV.
        if team == home_team:
            signed_q3 = margin
        elif team == away_team:
            signed_q3 = -margin
        else:
            signed_q3 = 0.0
        # Gate fires only inside the close-Q3 band with material velocity.
        gate_fires = in_blowout_flip_live_proxy(
            q3_margin_abs=abs(signed_q3),
            score_velocity_q3=velocity,
        )

        # W-020: use is_starter + l10_min as a better star proxy (W-004 DONE).
        # is_starter is now reliably captured (W-004 fixed the all-true parse bug).
        # Fallback: proj_min >= 30 (the original heuristic) when is_starter absent.
        is_starter_flag = p.get("is_starter")
        if is_starter_flag is not None:
            try:
                is_star = bool(is_starter_flag)
            except (TypeError, ValueError):
                is_star = False
            # Additional guard: is_starter can be unreliable for shallow bench
            # players. Require l10_min >= 20 when is_starter is True.
            if is_star:
                try:
                    l10_check = float(p.get("l10_min") or 0)
                except (TypeError, ValueError):
                    l10_check = 0.0
                is_star = is_star and (l10_check >= 20.0)
        else:
            share_played_game = pig.clock_played_share(period, clock_rem)
            proj_min = ((cur_min / share_played_game)
                        if share_played_game > 0 else cur_min)
            is_star = proj_min >= 30.0
        heuristic_bf = pig.blowout_factor(
            abs(margin), period, is_star=(is_star and team_is_leading))

        new_bf = stratified_blowout_factor(
            heuristic_factor=heuristic_bf,
            residual_model=blowout_model,
            pf_through_q3=snap_pf, q3_pf=q3_pf_proxy,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            score_margin_abs=abs(signed_q3),
            score_margin_signed_q3=signed_q3,
            score_velocity_q3=velocity,
            is_leading_team=1 if team_is_leading else 0,
            position_proxy=p.get("position"),
            l20_min=p.get("l20_min"),
            l5_min=p.get("l5_min"),
        )

        if new_bf == heuristic_bf:
            # Gate didn't fire -- nothing to override.
            continue

        period_elapsed_min = max(0.0, pig.PERIOD_MIN - clock_rem)
        bench_now = pig.is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min)
        player_basis = cur_min if bench_now else None

        out_rows = rows_by_pid.get(pid, [])
        for r in out_rows:
            stat = r.get("stat")
            if stat not in pig.STATS:
                continue
            try:
                cur = float(p.get(stat) or 0)
            except (TypeError, ValueError):
                cur = 0.0
            # Preserve the foul_factor potentially set by the earlier
            # _apply_stratified_foul_residual override.
            ff_existing = r.get("foul_factor", 1.0)
            try:
                ff = float(ff_existing)
            except (TypeError, ValueError):
                ff = 1.0
            new_final = pig.project_final(
                cur, period, clock_rem,
                pace_factor=1.0, foul_factor=ff, blow_factor=new_bf,
                player_clock_played_min=player_basis,
            )
            r["projected_final"] = float(new_final)
            r["blow_factor"] = new_bf
            r["blow_factor_source"] = (
                "blowout_residual" if gate_fires else "heuristic_blowout"
            )
    return rows


# ── cycle 103b: heat_check shrinkage override (PTS/AST/FG3M only) ─────────────

def _apply_heat_check_shrinkage(snap: dict, rows: list) -> list:
    """Multiply projected_final by a learned shrinkage factor ∈ [0.70, 1.00]
    for pts/ast/fg3m on heat_check rows. Operates on the REMAINING delta
    (projected_final - current_stat); current_stat is never altered.

    Graceful no-op when the artifact is absent.
    """
    _, _, _, shrink_model = _load_models_once()
    if shrink_model is None:
        return rows

    from src.prediction.heat_check_shrinkage_residual import (
        HEAT_CHECK_STATS,
        apply_shrinkage_to_projection,
        heat_check_shrinkage_factor,
    )

    try:
        home_score = float(snap.get("home_score") or 0)
    except (TypeError, ValueError):
        home_score = 0.0
    try:
        away_score = float(snap.get("away_score") or 0)
    except (TypeError, ValueError):
        away_score = 0.0
    margin_abs = abs(home_score - away_score)

    # Index input players by pid for per-player Q1/Q2/Q3 lookups.
    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    rows_by_pid: dict = {}
    for r in rows:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            rows_by_pid.setdefault(int(pid), []).append(r)
        except (TypeError, ValueError):
            continue

    # Per-player factor cache (one factor per player; reused for pts/ast/fg3m).
    for pid, p in by_pid.items():
        try:
            q1_pts = float(p.get("pts_q1") or 0)
            q2_pts = float(p.get("pts_q2") or 0)
            q3_pts = float(p.get("pts_q3") or 0)
            min_q1 = float(p.get("min_q1") or 0)
            min_q2 = float(p.get("min_q2") or 0)
            min_q3 = float(p.get("min_q3") or 0)
        except (TypeError, ValueError):
            continue
        if min_q3 <= 0.0 or (min_q1 + min_q2) <= 0.0:
            continue

        factor = heat_check_shrinkage_factor(
            residual_model=shrink_model,
            q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
            min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
            season_pts_per_min=p.get("season_pts_per_min"),
            l5_pts_per_min=p.get("l5_pts_per_min"),
            position_proxy=p.get("position"),
            score_margin_abs=margin_abs,
        )
        if factor >= 0.999:
            # No-op (gate didn't fire or model says no shrinkage).
            continue

        out_rows = rows_by_pid.get(pid, [])
        for r in out_rows:
            stat = r.get("stat")
            if stat not in HEAT_CHECK_STATS:
                continue
            try:
                cur = float(r.get("current") or 0)
                proj = float(r.get("projected_final") or 0)
            except (TypeError, ValueError):
                continue
            new_proj = apply_shrinkage_to_projection(proj, cur, factor)
            r["projected_final"] = float(new_proj)
            r["heat_check_shrinkage"] = float(factor)
    return rows


# ── W-014: generalized heat-check heat^0.20 mean-reversion ───────────────────

_HEAT_GEN_STATS: frozenset = frozenset({"pts", "ast", "fg3m"})
_HEAT_GEN_GAMMA: float = 0.20   # g in the formula: factor = heat^{g-1} = heat^{-0.80}
_HEAT_CLAMP_LO: float = 0.25
_HEAT_CLAMP_HI: float = 4.0
_HEAT_MIN_MIN: float = 3.0   # require at least 3 game-min to fire

# Mapping stat -> L5 per-minute field name on the player row.
_HEAT_GEN_L5_FIELD = {
    "pts":  "l5_pts_per_min",
    "ast":  "l5_ast_per_min",
    "fg3m": "l5_fg3m_per_min",
}
# Fallback: compute from raw l5_<stat> / l5_min if per-min field absent.
_HEAT_GEN_L5_RAW = {
    "pts":  "l5_pts",
    "ast":  "l5_ast",
    "fg3m": "l5_fg3m",
}


def _apply_heat_check_generalized(snap: dict, rows: list) -> list:
    """Generalized heat-check mean-reversion at EVERY snapshot.

    Implements the W-014 spec formula:

        heat = (live per-min rate) / (L5 per-min rate)  clamped [0.25, 4.0]
        rest  = L5_per_min_rate * expected_remaining_min * heat^0.20

    Algebraically, with the cycle-88 remaining ≈ live_rate * rem_min, this is
    equivalent to scaling the existing remaining delta by heat^{0.20-1} = heat^{-0.80}.

        factor = heat^{-0.80}
        new_proj = current + (projected_final - current) * factor

    For a HOT player (heat > 1): factor < 1 → mean-revert toward L5 (shrink).
    For a COLD player (heat < 1): factor > 1 → mean-revert toward L5 (expand).

    Applied to pts/fg3m/ast remaining-delta only; current_stat never altered.
    STL/BLK/TOV/REB are excluded (no heat-check dynamic on defensive counts).

    Graceful no-op when:
      * CV_INGAME_HEAT_GEN env flag is not set (default → byte-identical)
      * player has < 3 minutes played (too noisy)
      * L5 per-min prior is absent or zero on the player row
      * any exception (per-row try/except)
    """
    import math
    import os
    if not os.environ.get("CV_INGAME_HEAT_GEN"):
        return rows

    # Index player rows by pid so we can look up L5 priors once.
    by_pid: dict = {}
    for p in snap.get("players") or []:
        try:
            by_pid[int(p.get("player_id"))] = p
        except (TypeError, ValueError):
            continue

    rows_by_pid: dict = {}
    for r in rows:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            rows_by_pid.setdefault(int(pid), []).append(r)
        except (TypeError, ValueError):
            continue

    for pid, p in by_pid.items():
        try:
            cur_min = float(p.get("min") or 0)
        except (TypeError, ValueError):
            continue
        if cur_min < _HEAT_MIN_MIN:
            continue

        out_rows = rows_by_pid.get(pid, [])
        for r in out_rows:
            stat = r.get("stat")
            if stat not in _HEAT_GEN_STATS:
                continue
            try:
                cur = float(p.get(stat) or 0)
                proj = float(r.get("projected_final") or 0)
            except (TypeError, ValueError):
                continue

            # Live per-min rate for this stat.
            live_rate = cur / cur_min  # safe: cur_min >= 3.0

            # L5 per-min rate: prefer pre-computed field, fall back to raw.
            l5_rate: float = 0.0
            l5_field = _HEAT_GEN_L5_FIELD.get(stat, "")
            if l5_field:
                v = p.get(l5_field)
                if v is not None:
                    try:
                        l5_rate = float(v)
                    except (TypeError, ValueError):
                        l5_rate = 0.0
            if l5_rate <= 0.0:
                # Fallback: raw l5_<stat> / l5_min
                raw_field = _HEAT_GEN_L5_RAW.get(stat, "")
                l5_min_v = p.get("l5_min")
                if raw_field and l5_min_v is not None:
                    try:
                        l5_raw = float(p.get(raw_field) or 0)
                        l5_min_f = float(l5_min_v)
                        if l5_min_f > 0 and l5_raw >= 0:
                            l5_rate = l5_raw / l5_min_f
                    except (TypeError, ValueError):
                        l5_rate = 0.0
            if l5_rate <= 0.0:
                # No L5 prior available → no-op for this (player, stat).
                continue

            # Compute heat ratio and the mean-reversion shrink factor.
            # The spec formula: rest = L5_rate * rem * heat^0.20
            # With old_remaining ≈ live_rate * rem:
            #   new_remaining = old_remaining * (L5_rate/live_rate) * heat^0.20
            #                 = old_remaining * heat^{-1} * heat^{0.20}
            #                 = old_remaining * heat^{-0.80}
            # So: factor = heat^{-(1-gamma)} = heat^{-0.80}
            try:
                if live_rate <= 0.0:
                    # Zero live rate = maximally COLD. A player with real minutes
                    # who has 0 in this stat will not stay at 0 -- he should
                    # mean-revert toward his L5 baseline, not stay frozen at the
                    # cold linear extrapolation (the Bridges-0-pts case). Treat
                    # heat as the cold clamp floor so the cold-EXPAND factor fires.
                    heat = _HEAT_CLAMP_LO
                else:
                    heat = live_rate / l5_rate
                heat_clamped = max(_HEAT_CLAMP_LO, min(_HEAT_CLAMP_HI, heat))
                # factor = heat^{gamma - 1} = heat^{-0.80}: shrinks hot, expands cold.
                factor = math.pow(heat_clamped, _HEAT_GEN_GAMMA - 1.0)
                remaining = proj - cur
                if abs(remaining) < 1e-9:
                    continue
                new_proj = cur + remaining * factor
                # Never project below current_stat (can't un-score).
                new_proj = max(new_proj, cur)
                r["projected_final"] = float(new_proj)
                src = str(r.get("projection_source") or "")
                if "+heat_gen" not in src:
                    r["projection_source"] = src + "+heat_gen"
                r["heat_gen_factor"] = float(factor)
            except Exception:
                continue

    return rows


# ── 2. project_full_slate ─────────────────────────────────────────────────────

def project_full_slate(date_iso: Optional[str] = None) -> Dict[str, List[Dict]]:
    """For every active game today, project all players.

    Iterates the latest snapshot per ``game_id`` discovered in
    ``data/live/`` for the requested date.

    Parameters
    ----------
    date_iso : str, optional
        Target date (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    dict[str, list[dict]]
        ``{game_id: [projection_row, ...]}``. Games with no snapshot or
        an empty snapshot are silently skipped.
    """
    if date_iso is None:
        date_iso = _date.today().isoformat()

    out: Dict[str, List[Dict]] = {}
    for path in list_today_snapshots(date_iso):
        snap = load_live_state(path)
        if not snap:
            continue
        game_id = str(snap.get("game_id") or "")
        if not game_id:
            continue
        # R10_M16: inject game_date into the snap so the endQ3 residual
        # heads can look up prior-game streak features for fg3m/stl/blk/tov.
        # No-op for snapshots that already carry game_date.
        if not snap.get("game_date"):
            snap["game_date"] = date_iso
        rows = project_from_snapshot(snap)
        out[game_id] = rows
    return out


# ── 3. edge_vs_pregame ────────────────────────────────────────────────────────

def edge_vs_pregame(snap: dict,
                    date_iso: Optional[str] = None) -> List[Dict]:
    """Project from snapshot, then attach pregame_pred + delta when available.

    Joins each (player_id, stat) projection against the cycle-47/49/80
    pre-game ledger ``data/predictions/<date>.csv``. When the ledger is
    absent or a player/stat is missing, the row is returned unchanged
    (no ``pregame_pred`` key, ``delta`` not set) -- callers that want a
    strict-join should filter on ``"pregame_pred" in row``.

    Parameters
    ----------
    snap : dict
        Canonical snapshot.
    date_iso : str, optional
        Target date (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    list of dict
        Projection rows. When the ledger is present and a match exists,
        each row also carries ``pregame_pred`` (float) and ``delta``
        (projected_final - pregame_pred).
    """
    import predict_in_game as pig    # cycle 88b loader is the source of truth

    if date_iso is None:
        date_iso = _date.today().isoformat()

    pregame = pig.load_pregame_predictions(date_iso)
    rows = project_from_snapshot(snap)

    if not pregame:
        return rows

    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            key = (int(pid), str(stat).lower())
        except (TypeError, ValueError):
            continue
        pred = pregame.get(key)
        if pred is None:
            continue
        r["pregame_pred"] = float(pred)
        try:
            r["delta"] = float(r.get("projected_final", 0.0)) - float(pred)
        except (TypeError, ValueError):
            pass
    return rows


# ── 4. write_ledger ───────────────────────────────────────────────────────────

# Ledger schema mirrors scripts/save_live_predictions.py (cycle 88n).
_LEDGER_FIELDS = [
    "date", "game_id", "player_id", "player", "team", "opp", "venue",
    "stat", "pred", "lineup_status", "lineup_class", "play_pct",
    "injury_status", "pred_kind", "snapshot_period", "snapshot_clock",
    "current_stat",
]


def write_ledger(rows: List[Dict], date_iso: str,
                 out_path: Optional[str] = None) -> int:
    """Append projection rows to ``data/predictions/<date>_inplay.csv``.

    Accepts BOTH row shapes:

      * Rows from ``project_from_snapshot`` (cycle 88b output --
        keys: player_id/name/team/stat/projected_final/current/...).
      * Rows already in the cycle-88n ledger shape (output of
        ``scripts.save_live_predictions.derive_inplay_predictions``).

    For the former, this function coerces each row into the canonical
    cycle-88n schema before append; for the latter, the row is written
    through unchanged. The header is written iff the file doesn't yet
    exist (idempotent, matches ``save_live_predictions.append_to_ledger``).

    Parameters
    ----------
    rows : list of dict
        Projection rows in either shape above.
    date_iso : str
        Date stamp written into each row's ``date`` column. Also drives
        the default ``out_path``.
    out_path : str, optional
        Override the default ``data/predictions/<date>_inplay.csv``.

    Returns
    -------
    int
        Number of rows appended.
    """
    from scripts.save_live_predictions import append_to_ledger  # noqa: PLC0415

    if out_path is None:
        out_path = os.path.join(PRED_DIR, f"{date_iso}_inplay.csv")

    coerced: List[Dict] = []
    for r in rows:
        # If the row already speaks the cycle-88n schema (has 'pred' +
        # 'player' keys), trust it.
        if "pred" in r and "player" in r:
            row = dict(r)
            row.setdefault("date", date_iso)
            for key in _LEDGER_FIELDS:
                row.setdefault(key, "")
            coerced.append(row)
            continue

        # Otherwise it came from project_from_snapshot -- coerce.
        try:
            current = float(r.get("current", 0) or 0)
        except (TypeError, ValueError):
            current = 0.0
        try:
            pred = float(r.get("projected_final", 0) or 0)
        except (TypeError, ValueError):
            pred = 0.0

        period = r.get("snapshot_period", r.get("period", ""))
        period_str = str(period) if period not in (None, "") else ""
        kind = f"Q{period_str}_inplay" if period_str else "inplay"
        coerced.append({
            "date": date_iso,
            "game_id": r.get("game_id", ""),
            "player_id": r.get("player_id", ""),
            "player": r.get("name", ""),
            "team": r.get("team", ""),
            "opp": r.get("opp", ""),
            "venue": r.get("venue", ""),
            "stat": r.get("stat", ""),
            "pred": f"{pred:.4f}",
            "lineup_status": r.get("lineup_status", ""),
            "lineup_class": r.get("lineup_class", ""),
            "play_pct": r.get("play_pct", ""),
            "injury_status": r.get("injury_status", ""),
            "pred_kind": r.get("pred_kind", kind),
            "snapshot_period": period_str,
            "snapshot_clock": r.get("snapshot_clock", ""),
            "current_stat": f"{current:.4f}",
        })

    return append_to_ledger(coerced, out_path)
