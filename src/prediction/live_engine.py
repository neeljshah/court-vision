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
# projection). Default OFF -- bands are available on request via
# src.prediction.live_quantile_bands.project_from_snapshot_with_bands or by
# flipping this flag to True (in which case project_from_snapshot attaches
# q10/q50/q90 to every returned row). q50 ALWAYS equals projected_final --
# the point prediction is never altered. Bands are wide-open (q10=0,
# q90=2*q50) when the calibration artifact is absent (back-compat).
_INCLUDE_QUANTILE_BANDS = False

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
]


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

    # cycle 106a (loop 5): replace projected_final with period_specific_heads
    # prediction at endQ1 / endQ2 boundaries when artifacts exist. endQ3 is
    # intentionally NOT wired (cycle-88 linear is already near-optimal at
    # 36 min observed). Mid-quarter snapshots fall through unchanged.
    if _USE_PERIOD_HEADS:
        rows = _apply_period_heads(snap, rows)

    # tier1-2 (loop 5): stratified foul_change residual override. Only
    # applies at endQ3 (period=4) snapshots where the residual model is
    # validated; earlier periods keep the cycle-88b heuristic path.
    if _USE_FOUL_RESIDUAL and int(snap_period or 0) == 4:
        rows = _apply_stratified_foul_residual(snap, rows)
    # cycle 102a (loop 5): SECOND stratified override -- blowout_flip
    # residual replaces blow_factor when the live proxy gate fires
    # (|Q3 margin| <= 18 AND |velocity| >= 4). Independent of the foul
    # override; the two override different multiplicative factors so they
    # compose safely.
    if _USE_BLOWOUT_RESIDUAL and int(snap_period or 0) == 4:
        rows = _apply_stratified_blowout_residual(snap, rows)
    # cycle 103b (loop 5): THIRD stratified override -- heat_check shrinkage
    # multiplies projected_final on the REMAINING portion for pts/ast/fg3m
    # when q3_ppm > 1.5 * q12_ppm (with q12_ppm > 0.3). Composes safely with
    # the foul + blowout overrides above (those rewrite projected_final
    # absolutely; this scales the REMAINING delta from current_stat).
    if _USE_HEAT_CHECK_SHRINKAGE and int(snap_period or 0) == 4:
        rows = _apply_heat_check_shrinkage(snap, rows)
    # cycle 105c (loop 5): opt-in quantile bands. q50 == projected_final
    # always; q10/q90 are additive. Guarded so the existing point-only
    # consumers (live_dashboard, save_live_predictions, edge_eval) see no
    # row-shape change when the flag is off (the default).
    if _INCLUDE_QUANTILE_BANDS:
        try:
            from src.prediction.live_quantile_bands import (
                bands_for, load_calibration, period_to_point,
            )
            point = period_to_point(snap_period) if snap_period is not None else None
            cal = load_calibration()
            for r in rows:
                stat = r.get("stat")
                try:
                    q50 = float(r.get("projected_final", 0.0) or 0.0)
                except (TypeError, ValueError):
                    q50 = 0.0
                b = bands_for(stat, q50, point, calibration=cal)
                r["q10"] = b["q10"]
                r["q50"] = b["q50"]
                r["q90"] = b["q90"]
        except Exception:
            # Bands are advisory -- never break the hot path.
            pass
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
    """
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

    # The Q3 score velocity is not present in the canonical snapshot schema;
    # snapshot supplies snap.get("score_velocity_q3") when the upstream
    # builder included it (e.g. probe_blowout_stratified_blend.py for retro),
    # otherwise defaults to 0 (gate won't fire). Live snapshots from
    # src.data.live currently do NOT track Q-by-Q score history -- the
    # override degrades to a no-op until that field is wired upstream.
    snap_velocity = snap.get("score_velocity_q3", 0.0)
    try:
        velocity = float(snap_velocity or 0)
    except (TypeError, ValueError):
        velocity = 0.0

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
