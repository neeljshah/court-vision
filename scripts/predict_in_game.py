"""predict_in_game.py — cycle 88b (loop 5). Live mid-game stat projector.

Component 4 of the live in-game prediction system. Given the live state of a
game in progress (per-player current pts/reb/ast/etc + game period/clock),
projects each player's FINAL stat line using pace-based extrapolation plus
foul-trouble + blowout penalties.

Why this exists: top sharp prop models update mid-game from observed Q1/Q2/Q3
pace + usage. The cycle-37 pre-game predictor and the cycle-39 slate predictor
never update once tip happens — so we leave a large MAE on the table for
in-play prop markets. This script closes that gap.

Live snapshots are produced by `scripts/live_game_poll.py` (cycle 88a) and
written to `data/live/<game_id>_<timestamp>.json`. Canonical schema (matches
`src/data/live.py` — top-level home_team / away_team / home_score / away_score):

    {
        "game_id":    "0022400123",
        "period":     3,                # 1..4 reg, 5+ OT
        "clock":      "07:24",          # remaining in current period (MM:SS)
        "home_team":  "DEN",
        "away_team":  "LAL",
        "home_score": 78,
        "away_score": 58,
        "players":  [
            {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
             "min": 24.5, "pts": 18, "reb": 9, "ast": 7, "fg3m": 1,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2,
             "min_q1": 8.2, "min_q2": 8.4, "min_q3": 8.0, "min_q4": 0.0},
            ...
        ],
    }

Cycle 89a (loop 5): the legacy nested form `{"home": {"abbrev", "score"},
"away": {...}}` is auto-normalized to the canonical top-level form by
`_normalize_snapshot()` so old fixtures keep working.

Projection logic — pure functions in this module so the unit tests (see
tests/test_predict_in_game.py) can validate the math without nba_api / models:

    clock_played_share   = (12 * (period - 1) + (12 - clock_remaining)) / 48
    remaining_share      = max(0.0, 1.0 - clock_played_share)
    projected_remaining  = current_stat * (remaining_share / clock_played_share)
                                       * pace_factor
                                       * foul_trouble_factor
                                       * blowout_factor
    final_proj           = current_stat + projected_remaining

Bench-player handling: a player whose minutes are all in earlier quarters
(MIN > 0 historically but MIN_q<current>=0 AND on the bench now) projects
from the rate they accumulated WHILE PLAYING — not the elapsed game clock.

CLI:
    python scripts/predict_in_game.py --game-id 0022400123
    python scripts/predict_in_game.py --snapshot data/live/x.json
    python scripts/predict_in_game.py --all-live
    python scripts/predict_in_game.py --snapshot x.json \\
        --save data/predictions/2026-05-24_inplay.csv

Output columns (per player per stat):
    name, team, stat, current, projected_final, pregame_pred (if available)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reconfigure stdout to UTF-8 on Windows so accented player names don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")

REG_PERIODS = 4
PERIOD_MIN = 12.0
GAME_MIN = REG_PERIODS * PERIOD_MIN  # 48.0

# ── CV_INGAME_POSS_BASE — possession-anchored player stat base (W-006) ────────
# Default OFF: byte-identical to the pre-W006 serve path.
# When ON, `project_snapshot` replaces the flat 48/clock extrapolation with a
# possession-count-anchored pace multiplier.  The pace is estimated by
# _shrunk_pace_per48 (PACE_PRIOR_K=25, LEAGUE=99) so early-game observations
# blend heavily toward the league prior (~32% weight at 12 min).  When possession
# counts are absent from the snapshot the multiplier collapses to 1.0 and the
# output is identical to the flat path (graceful degradation, depends on W-001
# for full effect with live four-factor counts).
_CV_POSS_BASE: bool = os.environ.get(
    "CV_INGAME_POSS_BASE", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── CV_INGAME_L5_ANCHOR — early-game L5 anchor: kill catastrophic extrapolation
# (W-008) ─────────────────────────────────────────────────────────────────────
# Default OFF: byte-identical to the pre-W008 serve path.
# When ON, `project_remaining` and `project_final` clamp the pace-extrapolation
# factor so that very early game state (played_share < _L5_ANCHOR_MIN_SHARE,
# i.e., game elapsed < 12 min = end of Q1) never drives a catastrophic linear
# projection.  The effective played_share used in the denominator is floored at
# _L5_ANCHOR_MIN_SHARE, limiting the maximum multiplier at midQ1 from ~7–15x
# to ~3x.  Late-game (played_share >= _L5_ANCHOR_MIN_SHARE) is completely
# unchanged — byte-identical to the flag-OFF path.
#
# Separately, `project_final` accepts an optional `l5_value` parameter. When
# the caller supplies the pregame L5 mean for a (player, stat) AND the flag is
# ON AND the game is early, the output is a direct L5-anchored blend:
#   out = max(current, l5_value * share_remaining_from_anchor + current)
# rather than the explosive live rate.  When `l5_value` is None the floor-only
# path activates (no L5 data required).
#
# `_live_shrink_weight` in api/courtvision_router.py also reads this flag to
# force w=0.0 for the first few player-minutes so the router never trusts the
# explosive live extrapolation before sufficient on-court evidence accumulates.
_CV_L5_ANCHOR: bool = os.environ.get(
    "CV_INGAME_L5_ANCHOR", "0"
).strip().lower() not in ("", "0", "false", "off")

# Minimum game-played share used in the extrapolation denominator when
# CV_INGAME_L5_ANCHOR is ON.  0.25 = 12 game-minutes = end of Q1.
# Before this point the denominator is floored here, capping the rate factor.
_L5_ANCHOR_MIN_SHARE: float = 0.25

# ── CV_INGAME_ROTCURVE — per-quarter rotation-curve remaining-minutes base
# (W-009) ─────────────────────────────────────────────────────────────────────
# Default OFF: byte-identical to the pre-W009 serve path.
# When ON, `project_snapshot` replaces the flat game-clock extrapolation with
# an atlas-based per-quarter expected-minutes curve loaded from
# data/player_quarter_stats.parquet.  For each player, the expected remaining
# minutes = sum(mean_min[q] for unplayed quarters q) + partial credit for the
# current quarter.  Player-specific curves are looked up by player_id; when
# the player has no atlas entry the function degrades gracefully to the flat
# game-clock basis (byte-identical to flag-OFF for those players).
#
# The curve is a POPULATION PRIOR (historical season mean), not in-game state.
# Shrink k = _ROTCURVE_SHRINK_K: blend atlas curve toward the flat-pace
# estimate when the player has few observed games.  At k=10 the atlas curve
# dominates once a player has ~20+ game-quarter observations.
#
# W-009 RE-ATTEMPT: fringe-guard branch (same flag, extends existing ON path).
# When cur_min <= _ROTCURVE_FRINGE_THRESH (5 min), the atlas mean is unreliable
# because fringe players have high-variance playing time.  Instead, use a linear
# regression estimate fitted on 14K player-game observations:
#   E[rem] = _ROTCURVE_FRINGE_INTERCEPT
#            + _ROTCURVE_FRINGE_COEF_Q1 * min_q1
#            + _ROTCURVE_FRINGE_COEF_Q2 * min_q2
# Achieves 41.6% better min_q3 MAE than flat atlas mean (2.35→1.37 min).
# Clamp output to [0, 20]; apply same Bayesian shrinkage toward flat_rem.
# Normal players (cur_min > _ROTCURVE_FRINGE_THRESH) fall through to existing
# atlas path unchanged.
#
# Beat bar: must beat flat-pace AND beat trivial l3/l10 blend (+3.07%).
_CV_ROTCURVE: bool = os.environ.get(
    "CV_INGAME_ROTCURVE", "0"
).strip().lower() not in ("", "0", "false", "off")

# Shrinkage weight pseudo-count: blend atlas toward flat when n_games_observed
# is small.  blended = (n/(n+k))*atlas + (k/(n+k))*flat
_ROTCURVE_SHRINK_K: float = 10.0

# Fringe-player threshold: cur_min <= this → use regression estimate, not atlas.
# Fitted on 14K player-game observations; 5 min is the empirically-calibrated
# boundary where the atlas mean starts to be dominated by noise.
_ROTCURVE_FRINGE_THRESH: float = 5.0

# Regression coefficients for fringe-player remaining-minutes estimate.
# E[rem_q3_q4] = intercept + coef_q1*min_q1 + coef_q2*min_q2
# Two additive components: Q3 term (0.882+0.714*q1+0.178*q2) +
#                          Q4 term (3.420+0.160*q1+0.353*q2)
_ROTCURVE_FRINGE_INTERCEPT: float = 0.882 + 3.420   # = 4.302
_ROTCURVE_FRINGE_COEF_Q1: float = 0.714 + 0.160      # = 0.874
_ROTCURVE_FRINGE_COEF_Q2: float = 0.178 + 0.353      # = 0.531

# Lazy-loaded atlas: {player_id: {q: mean_min}} loaded once on first use.
_ROTCURVE_ATLAS: Optional[Dict[int, Dict[int, float]]] = None
_ROTCURVE_N_GAMES: Optional[Dict[int, float]] = None   # player_id -> n game-quarters / 4

_ROTCURVE_PARQUET_PATH: str = os.path.join(
    PROJECT_DIR, "data", "player_quarter_stats.parquet"
)

# ── CV_INGAME_ROTMINUTES — remaining-minutes projection consumer (W-009 RIGHT) ─
# Default OFF: byte-identical to the pre-flag serve path.
#
# THE dominant in-game error lever is minutes-surprise.  The naive W-009
# (CV_INGAME_ROTCURVE) was REJECTED because, on the canonical pig harness, it
# REGRESSED the two biggest-weight stats (pts +0.64%, reb +0.67% at endQ123) —
# its fringe-regression branch and partial-current-quarter atlas credit pulled
# heavy-minutes players' projections off.  This is W-009 done RIGHT.
#
# When ON, `project_snapshot` replaces the flat game-clock remaining-minutes
# basis with a Bayesian blend of the player's season per-quarter rotation curve
# and the flat clock-share extrapolation:
#
#   atlas_rem  = sum(season_mean_min[q] for unplayed FULL quarters q > period),
#                clamped to the remaining game clock          (rotation curve)
#   flat_rem   = cur_min * (remaining_clock / elapsed_clock)  (today's basis)
#   w          = n_games / (n_games + _ROTMIN_SHRINK_K)        (atlas weight)
#   proj_rem_min = w * atlas_rem + (1 - w) * flat_rem
#
# The projected remaining production is then driven off projected minutes:
#   per_min_rate = cur_stat / cur_min
#   proj_remaining = per_min_rate * proj_rem_min * (pace × foul × blow × ...)
# i.e. the SAME per-minute rate the flat path uses, but extrapolated over the
# rotation-aware minutes instead of the naive clock share.  current_stat is
# never altered (a player can never un-score), and the foul-trouble + blowout
# factors continue to multiply the remaining term exactly as in the flat path.
#
# What makes this the RIGHT version (vs the rejected W-009):
#   * NO partial-current-quarter atlas credit (the old version's main bias —
#     it gave a star who'd just played a full Q1 *fewer* future minutes than the
#     clock implied, under-projecting PTS/REB).
#   * NO fringe linear-regression branch (it over-fit low-minute players).
#   * Atlas uses only the unplayed FULL quarters, shrunk toward the flat basis.
#
# Graceful degradation (byte-identical to flag-OFF for affected players):
#   * Player has no 4-quarter atlas entry → proj_rem_min == flat_rem.
#   * Player has 0 minutes (no rate) → handled by project_remaining (rate=0).
#   * Atlas/parquet missing → atlas dict empty → all players use flat_rem.
#
# VALIDATED on ingame_calib_eval (pig projector, --shrink prod) — see
# docs/_audits/INGAME_OVERNIGHT_LOG.md.  All 7 stats improve, no core regression.
_CV_ROTMINUTES: bool = os.environ.get(
    "CV_INGAME_ROTMINUTES", "0"
).strip().lower() not in ("", "0", "false", "off")

# Shrinkage pseudo-count for the atlas/flat blend.  At K=10 the atlas dominates
# once a player has ~20+ game-quarter observations; few-game players lean flat.
_ROTMIN_SHRINK_K: float = 10.0


def rotminutes_expected_rem_min(
    player_id: Optional[int],
    period: int,
    clock_rem: float,
    cur_min: float,
) -> Optional[float]:
    """W-009-RIGHT: expected remaining player minutes via the rotation curve.

    Returns a Bayesian blend of the player's season per-quarter mean minutes
    (unplayed FULL quarters only) and the flat clock-share extrapolation.

    Returns None when the flag is OFF or the player has no usable atlas entry,
    signalling the caller to use the flat path (byte-identical to flag-OFF).

    Args:
        player_id: NBA player_id for the atlas lookup.
        period:    current game period (1..4 regulation; OT handled by clamp).
        clock_rem: minutes remaining in the current period.
        cur_min:   player minutes played so far (the flat-pace basis).
    """
    if not _CV_ROTMINUTES:
        return None

    _load_rotcurve_atlas()
    assert _ROTCURVE_ATLAS is not None
    assert _ROTCURVE_N_GAMES is not None

    pid = int(player_id) if player_id is not None else -1
    curve = _ROTCURVE_ATLAS.get(pid)
    if not curve or len(curve) < 4:
        return None  # no full-curve atlas → flat fallback (byte-identical)

    # Flat clock-share remaining minutes (today's basis).
    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_played <= 1e-6 or share_remaining <= 1e-6:
        return None
    flat_rem = cur_min * (share_remaining / share_played)
    rem_clock = share_remaining * GAME_MIN

    # Atlas remaining: sum of season-mean minutes for the UNPLAYED quarters.
    # The snapshot convention (matched by the live poller AND the calibration
    # harness) is: at an end-of-quarter boundary the snapshot carries period =
    # the quarter ABOUT to start with clock = 12:00 (e.g. endQ1 → period=2,
    # clock=12:00). So when the current period has NOT started (clock ≈ full
    # quarter), the player still has periods P..4 entirely ahead; when the
    # period is in progress we credit only the FULL quarters after it (P+1..4)
    # plus the in-progress remainder of the current quarter, scaled by the
    # atlas mean. NO mid-period over-credit beyond the clock — clamp to rem_clock.
    p = max(1, int(period))
    period_not_started = clock_rem >= PERIOD_MIN - 0.1  # within 6s of full Q
    if period_not_started:
        # periods P..4 are all ahead of the player
        atlas_rem = sum(curve.get(q, 0.0) for q in range(p, 5))
    else:
        # full quarters after the in-progress one, + remainder of current Q
        atlas_rem = sum(curve.get(q, 0.0) for q in range(p + 1, 5))
        cur_q_atlas = curve.get(p, 0.0)
        if cur_q_atlas > 0:
            q_frac_remaining = max(0.0, min(1.0, clock_rem / PERIOD_MIN))
            atlas_rem += cur_q_atlas * q_frac_remaining
    atlas_rem = min(atlas_rem, rem_clock)

    # Bayesian blend toward flat for low-sample players.
    n_g = _ROTCURVE_N_GAMES.get(pid, 0.0)
    w = n_g / (n_g + _ROTMIN_SHRINK_K)
    blended = w * atlas_rem + (1.0 - w) * flat_rem
    return max(0.0, blended)


def _load_rotcurve_atlas() -> None:
    """Load the per-player per-quarter mean minutes atlas on first call.

    Reads data/player_quarter_stats.parquet (the same file used by the
    calibration harness) and computes population-mean minutes per quarter.
    This is a process-level singleton — safe for the serve path because the
    parquet is static during a game session.
    """
    global _ROTCURVE_ATLAS, _ROTCURVE_N_GAMES
    if _ROTCURVE_ATLAS is not None:
        return
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(_ROTCURVE_PARQUET_PATH)
        # Restrict to regulation quarters 1-4 only.
        reg = df[df["period"].isin([1, 2, 3, 4])].copy()
        # Per-player per-quarter mean minutes across the season.
        q_means = (
            reg.groupby(["player_id", "period"])["min"]
            .agg(["mean", "count"])
            .reset_index()
        )
        atlas: Dict[int, Dict[int, float]] = {}
        n_games: Dict[int, float] = {}
        for _, row in q_means.iterrows():
            pid = int(row["player_id"])
            q = int(row["period"])
            m = float(row["mean"])
            c = float(row["count"])
            atlas.setdefault(pid, {})[q] = m
            # Approximate n_games as mean count across quarters / 4
            n_games[pid] = n_games.get(pid, 0) + c / 4.0
        _ROTCURVE_ATLAS = atlas
        _ROTCURVE_N_GAMES = n_games
    except Exception:  # noqa: BLE001
        # If parquet missing or pandas unavailable, degrade gracefully to empty.
        _ROTCURVE_ATLAS = {}
        _ROTCURVE_N_GAMES = {}


def rotcurve_expected_rem_min(
    player_id: Optional[int],
    period: int,
    clock_rem: float,
    cur_min: float,
    min_q1: float = 0.0,
    min_q2: float = 0.0,
) -> float:
    """Return expected remaining player minutes using the atlas per-quarter curve.

    For unplayed full quarters (q > period), contributes atlas_mean[q].
    For the current quarter (partial credit): the player has been on floor
    for (elapsed_in_period * cur_q_share) minutes — we credit the remainder
    of the quarter proportionally using the atlas mean.
    Falls back to the flat game-clock basis when player_id is None or absent
    from the atlas (graceful degradation, byte-identical to flag-OFF).

    Shrinkage: atlas blended toward flat pace using Bayesian weight
    n_games/(n_games + _ROTCURVE_SHRINK_K).

    W-009 RE-ATTEMPT: fringe-guard branch.
    When cur_min <= _ROTCURVE_FRINGE_THRESH, use a linear regression
    estimate E[rem] = intercept + coef_q1*min_q1 + coef_q2*min_q2
    instead of the atlas mean.  Clamp output to [0, 20] then apply
    the same Bayesian shrinkage toward flat_rem.
    Normal players (cur_min > threshold) fall through to the atlas path.
    min_q1 / min_q2: per-quarter minutes from the player row (default 0.0
    so callers that don't supply them still get valid behaviour).
    """
    if not _CV_ROTCURVE:
        return 0.0  # caller must not use when flag OFF

    _load_rotcurve_atlas()
    assert _ROTCURVE_ATLAS is not None
    assert _ROTCURVE_N_GAMES is not None

    pid = int(player_id) if player_id is not None else -1
    has_atlas = pid in _ROTCURVE_ATLAS and len(_ROTCURVE_ATLAS[pid]) == 4

    # Flat-pace fallback (current approach): cur_min * remaining/played
    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_played <= 1e-6:
        return 0.0
    flat_rem = cur_min * (share_remaining / share_played)

    # ── W-009 fringe-guard branch ─────────────────────────────────────────
    # Fringe players (cur_min <= 5) have unreliable atlas entries because
    # their playing time is high-variance.  Use a linear regression fitted
    # on 14K player-game observations instead: 41.6% better min_q3 MAE.
    if cur_min <= _ROTCURVE_FRINGE_THRESH:
        reg_rem = (
            _ROTCURVE_FRINGE_INTERCEPT
            + _ROTCURVE_FRINGE_COEF_Q1 * float(min_q1)
            + _ROTCURVE_FRINGE_COEF_Q2 * float(min_q2)
        )
        reg_rem = max(0.0, min(20.0, reg_rem))   # clamp to [0, 20]
        # Bayesian shrinkage toward flat_rem (same k as atlas path).
        # For fringe players use n_g from atlas when available, else k itself
        # (which gives w=0.5 — moderate trust in the regression).
        n_g_fringe = _ROTCURVE_N_GAMES.get(pid, _ROTCURVE_SHRINK_K)
        w_fringe = n_g_fringe / (n_g_fringe + _ROTCURVE_SHRINK_K)
        return max(0.0, w_fringe * reg_rem + (1.0 - w_fringe) * flat_rem)
    # ── end fringe-guard branch ───────────────────────────────────────────

    if not has_atlas:
        return flat_rem  # graceful degradation

    curve = _ROTCURVE_ATLAS[pid]   # {1: mean, 2: mean, 3: mean, 4: mean}
    n_g = _ROTCURVE_N_GAMES.get(pid, 0)

    # --- atlas-curve remaining ---
    p = max(1, int(period))
    # Contribution from fully unplayed future quarters
    atlas_rem = sum(curve.get(q, 0.0) for q in range(p + 1, 5))
    # Contribution from the rest of the current quarter:
    # estimate current-quarter elapsed = PERIOD_MIN - clock_rem
    # atlas mean for current quarter = curve[p]
    # fraction of current quarter remaining = clock_rem / PERIOD_MIN
    cur_q_atlas = curve.get(p, 0.0)
    if PERIOD_MIN > 0 and cur_q_atlas > 0:
        q_frac_remaining = max(0.0, min(1.0, clock_rem / PERIOD_MIN))
        atlas_rem += cur_q_atlas * q_frac_remaining

    # Bayesian blend: w = n_games / (n_games + K)
    w = n_g / (n_g + _ROTCURVE_SHRINK_K)
    blended = w * atlas_rem + (1.0 - w) * flat_rem
    return max(0.0, blended)


# ── CV_INGAME_OT_FIX — OT extrapolation correctness fix (W-007) ──────────────
# Default OFF: byte-identical to the pre-W007 serve path (OT clamps
# played_share=1.0, zeroing remainder).
# When ON, overtime periods use an effective game length that includes OT
# minutes so remaining OT time still contributes to player projections.
# GAME_MIN_eff = 48 + 5*(n_ot_periods) where n_ot = max(0, period-4).
# Regulation snapshots (period<=4) are completely unaffected: the code path
# is unchanged and the output is byte-identical.
_CV_OT_FIX: bool = os.environ.get(
    "CV_INGAME_OT_FIX", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── CV_QSHAPE_DECAY — Quarter-scoring-shape decay multiplier (W-015) ─────────
# Default OFF: byte-identical to the pre-W015 serve path.
# When ON, `project_snapshot` applies a stat-specific pace_factor derived from
# the league per-minute rate vectors by quarter.  The factor is:
#
#   pace_factor = mean_rate(remaining quarters) / mean_rate(elapsed quarters)
#
# This captures that AST/FG3M/PTS tail off in Q4 vs Q1-Q3, so a snapshot at
# endQ3 should project LESS remaining stat per minute than the historical rate
# from Q1-Q3 implies.  Conversely REB also declines slightly but more modestly.
#
# APPLIES TO: pts, reb, ast, fg3m (the 4 stats the backlog targets).
# EXCLUDES: blk (rises in Q4 — non-uniform direction), tov (net-harmful per
# the backlog sketch), stl (not included in the task's target set).
#
# LEAGUE-UNIFORM coefficients fitted from player_quarter_stats.parquet
# (weighted per-minute rates, ~69K player-quarter rows, 2024-25 season).
# Shape factors at each snapshot boundary (remaining/elapsed weighted rate ratio):
#   endQ1 (1 elapsed, 3 remaining): pts=0.989 reb=0.963 ast=0.914 fg3m=0.910
#   endQ2 (2 elapsed, 2 remaining): pts=0.989 reb=0.962 ast=0.922 fg3m=0.928
#   endQ3 (3 elapsed, 1 remaining): pts=0.963 reb=0.967 ast=0.884 fg3m=0.893
# BLK endQ3 factor = 1.012 (rises) → excluded.  TOV excluded per spec.
#
# Per the acceptance rule: >=4/7 stats must improve on the held-out corpus.
# The expected benefit is 5-6/7 (AST and FG3M see the sharpest Q4 decline).
_CV_QSHAPE_DECAY: bool = os.environ.get(
    "CV_QSHAPE_DECAY", "0"
).strip().lower() not in ("", "0", "false", "off")

# League per-minute rate by quarter (weighted sum of stat / sum of min across
# all player-quarter rows where min > 0; Q1..Q4 regulation only).
# Computed from data/player_quarter_stats.parquet; DO NOT change without
# refitting on the full corpus.
_QSHAPE_RATES: Dict[str, Dict[int, float]] = {
    "pts":  {1: 0.4758, 2: 0.4727, 3: 0.4798, 4: 0.4586},
    "reb":  {1: 0.1880, 2: 0.1845, 3: 0.1803, 4: 0.1782},
    "ast":  {1: 0.1176, 2: 0.1113, 3: 0.1109, 4: 0.1001},
    "fg3m": {1: 0.0598, 2: 0.0559, 3: 0.0562, 4: 0.0512},
}

# Stats that receive the shape adjustment (excludes blk, tov, stl per spec)
_QSHAPE_STATS = frozenset({"pts", "reb", "ast", "fg3m"})


def qshape_pace_factor(stat: str, period: int, clock_remaining_min: float) -> float:
    """Return the quarter-shape decay pace multiplier for a stat at a snapshot.

    Factor = mean_rate(remaining quarters) / mean_rate(elapsed quarters).
    Returns 1.0 if:
      - CV_QSHAPE_DECAY is OFF (caller should not call in this case, but safe)
      - stat is not in the target set (blk/tov/stl → 1.0)
      - period >= 4 and clock <= 0 (no remaining time → no-op)
      - period == 1 at tip-off (no elapsed quarters → use Q1 rate for both → 1.0)

    The factor is computed over FULL remaining quarters only (ignoring the
    partial current quarter) to keep the coefficient league-uniform and
    parameter-free.  For early-period snapshots (mid-quarter), elapsed = the
    completed prior quarters only, remaining = the rest of the current quarter
    plus future quarters.  The current quarter contributes to both numerator and
    denominator proportionally so it cancels, and only the completed-vs-remaining
    full-quarter asymmetry matters.

    Implementation: for a snapshot at (period=P, clock=C):
      - Elapsed full quarters  : Q1 .. Q(P-1)  [if clock < PERIOD_MIN, Q_P also
        contributes elapsed portion but we attribute it to the P-1 completed qs]
      - Remaining full quarters: Q(P+1) .. Q4  [plus the partial current quarter
        but that's symmetric so using only full unplayed quarters is unbiased]

    Special case period=1 mid-quarter: elapsed = just Q1 partial; remaining =
    rest of Q1 + Q2+Q3+Q4.  We approximate: treat elapsed as {Q1} and remaining
    as {Q2,Q3,Q4} (the completed-future shape dominates).

    Clamp to [0.80, 1.20] so no single snapshot can blow up the projection.
    """
    if stat not in _QSHAPE_RATES:
        return 1.0
    rates = _QSHAPE_RATES[stat]
    p = max(1, int(period))

    # Determine elapsed and remaining full quarters.
    #
    # The calibration harness reconstructs "endQ3" as period=4, clock=12:00
    # (the start of Q4) because the snapshot carries stats from Q1+Q2+Q3 only.
    # Similarly, "endQ1" is period=2 clock=12:00, "endQ2" is period=3 clock=12:00.
    #
    # Rule: if clock_remaining_min is close to PERIOD_MIN (full quarter remaining,
    # i.e. the period has NOT started yet), treat the current period as REMAINING,
    # not elapsed.  Otherwise the current period is at least partially elapsed.
    #
    # "Clock near period start" = clock >= PERIOD_MIN - 0.1 (within 6 sec of
    # full quarter remaining).  This matches the "start of new period" convention
    # used by both the calibration harness and the live poller.
    _clock = max(0.0, float(clock_remaining_min))
    _period_not_started = (_clock >= PERIOD_MIN - 0.1)  # e.g. clock=12:00

    if _period_not_started:
        # Current period P has not started: elapsed = Q1..Q(P-1), remaining = QP..Q4
        elapsed_qs = list(range(1, p))
        remaining_qs = list(range(p, 5))
    else:
        # Current period P is in progress: elapsed = Q1..QP (all completed + partial
        # current), remaining = Q(P+1)..Q4
        elapsed_qs = list(range(1, p + 1))
        remaining_qs = list(range(p + 1, 5))

    # Edge case: no elapsed quarters yet (e.g. period=1 start) → factor = 1.0
    if not elapsed_qs:
        return 1.0

    if not remaining_qs:
        # Nothing left — no shape correction needed
        return 1.0

    mean_elapsed = sum(rates.get(q, 0.0) for q in elapsed_qs) / len(elapsed_qs)
    mean_remaining = sum(rates.get(q, 0.0) for q in remaining_qs) / len(remaining_qs)

    if mean_elapsed <= 0.0:
        return 1.0

    factor = mean_remaining / mean_elapsed
    # Clamp: never more than ±20% adjustment
    return max(0.80, min(1.20, factor))


# Mirrors constants in src/sim/rest_of_game_sim.py (kept local so this module
# stays importable without the rest-of-game sim installed).
_LEAGUE_PACE_PER48: float = 99.0   # one team's possessions per 48 min
_PACE_PRIOR_K: float = 25.0        # pseudo-possession weight on the prior
_REG_GAME_LEN_SEC: float = 2880.0  # 48 * 60

# W-006 possession RECONSTRUCTION (combined points-per-possession).
# The parquet-built calibration snapshots carry NO four-factor counts
# (no FGA/FTA/OREB), so the canonical poss estimate FGA-OREB+TOV+0.44*FTA is
# unavailable.  W-006-redone instead reconstructs possessions from SCORING:
#   total_poss ~= total_pts / _POSS_RECON_PPP   (both teams combined)
# Calibrated on the 954-game corpus so the reconstructed one-team pace/48
# centers at ~_LEAGUE_PACE_PER48 (=> mean factor ~1.0, no systematic bias):
# combined 226 pts / 198 poss ~= 1.14.  This makes the in-game tempo factor
# vary game-to-game (fast-scoring games > 1, slow games < 1) instead of being
# a flat 1.0 no-op, so the corpus harness can MEASURE the flag.  Live payloads
# that DO carry total_poss_count/game_elapsed_sec are unaffected (they take
# precedence; reconstruction only fires when those explicit fields are absent).
_POSS_RECON_PPP: float = 1.14


def _shrunk_pace_per48_local(total_poss: float, game_elapsed_sec: float,
                             prior_pace: Optional[float] = None) -> float:
    """Empirical-Bayes possessions-per-48 for one team (W-006).

    Pure function; mirrors src.sim.rest_of_game_sim._shrunk_pace_per48 so this
    module stays self-contained and importable without the sim package.

    ``total_poss`` is BOTH teams combined; divides by 2 to get per-team pace on
    the same scale as ``prior_pace`` (default LEAGUE_PACE_PER48=99.0).
    """
    target = prior_pace if (prior_pace is not None and prior_pace > 0) else _LEAGUE_PACE_PER48
    if game_elapsed_sec <= 0 or total_poss <= 0:
        return target
    # per-team combined possessions per 48 min
    combined_per48 = total_poss * (_REG_GAME_LEN_SEC / game_elapsed_sec)
    one_team_per48 = combined_per48 / 2.0
    # shrink weight: more elapsed time → more weight on in-game tempo
    w_units = total_poss / 2.0
    w = w_units / (w_units + _PACE_PRIOR_K)
    return w * one_team_per48 + (1.0 - w) * target


def _reconstruct_poss_from_snapshot(snap: dict) -> Tuple[float, float]:
    """Reconstruct (total_poss_count, game_elapsed_sec) from a snapshot that
    lacks explicit four-factor counts (W-006-redone).

    The calibration corpus (data/player_quarter_stats.parquet) has no FGA/FTA/
    OREB, so the canonical possession estimate is impossible.  Instead:
      * elapsed = game-clock elapsed seconds from period + clock
      * total_poss = combined points scored / _POSS_RECON_PPP

    Returns (0.0, 0.0) when the snapshot is degenerate (no players / no time
    elapsed) so the caller cleanly falls back to the flat 1.0 factor.
    """
    period = int(snap.get("period") or 1)
    clock_rem = parse_clock(snap.get("clock"))
    share = clock_played_share(period, clock_rem)
    elapsed_sec = share * _REG_GAME_LEN_SEC
    if elapsed_sec <= 0:
        return 0.0, 0.0
    total_pts = 0.0
    for p in snap.get("players") or []:
        total_pts += _num(p.get("pts"))
    if total_pts <= 0:
        return 0.0, 0.0
    total_poss = total_pts / _POSS_RECON_PPP   # both teams combined
    return total_poss, elapsed_sec


def _poss_pace_factor(snap: dict) -> float:
    """Return pace multiplier for possession-anchored projection (W-006).

    Reads optional ``total_poss_count`` and ``game_elapsed_sec`` from the
    snapshot.  When those EXPLICIT fields are present (live payloads carrying
    real four-factor counts), they take precedence.

    W-006-redone: when the explicit fields are ABSENT (calibration snapshots,
    older live payloads), reconstruct possessions from scoring + elapsed clock
    via ``_reconstruct_poss_from_snapshot`` so the factor is measurable on the
    corpus instead of collapsing to a flat 1.0 no-op.  If the reconstruction is
    also degenerate (no players / no elapsed time) the factor is 1.0 (identical
    to the flat path).

    Factor = shrunk_pace / LEAGUE_PACE so >1 when the game is fast (more
    remaining possessions per clock-minute than the league average).
    """
    total_poss = _num(snap.get("total_poss_count", 0))
    elapsed_sec = _num(snap.get("game_elapsed_sec", 0))
    if total_poss <= 0 or elapsed_sec <= 0:
        # No explicit counts → reconstruct from scoring + clock (W-006-redone).
        total_poss, elapsed_sec = _reconstruct_poss_from_snapshot(snap)
    if total_poss <= 0 or elapsed_sec <= 0:
        return 1.0
    prior_pace = _num(snap.get("prior_pace_per48", 0)) or None
    pace = _shrunk_pace_per48_local(total_poss, elapsed_sec, prior_pace)
    factor = pace / _LEAGUE_PACE_PER48
    # Clamp to a reasonable range: never more than ±20% adjustment
    return max(0.80, min(1.20, factor))


# ── pure projector functions (testable, no I/O) ──────────────────────────────

def parse_clock(clock_str: str) -> float:
    """Parse 'MM:SS' / 'M:SS' / 'MM.SS' / '0' to remaining float minutes.

    Returns 0.0 if unparseable so end-of-period inputs always degrade
    gracefully into 'no time remaining'.
    """
    if clock_str is None:
        return 0.0
    if isinstance(clock_str, (int, float)):
        return float(clock_str)
    s = str(clock_str).strip()
    if not s:
        return 0.0
    # PBP "PT07M24.00S" ISO 8601 duration support
    if s.upper().startswith("PT"):
        try:
            body = s[2:].upper()
            mins = 0.0
            secs = 0.0
            if "M" in body:
                m_part, _, rest = body.partition("M")
                mins = float(m_part)
                body = rest
            if "S" in body:
                s_part = body.split("S")[0]
                secs = float(s_part)
            return mins + secs / 60.0
        except (TypeError, ValueError):
            return 0.0
    # MM:SS or MM.SS
    sep = ":" if ":" in s else ("." if "." in s else None)
    if sep is None:
        try:
            return float(s)
        except ValueError:
            return 0.0
    head, _, tail = s.partition(sep)
    try:
        mins = float(head)
        secs = float(tail) if tail else 0.0
        return mins + secs / 60.0
    except ValueError:
        return 0.0


def clock_played_share(period: int, clock_remaining_min: float) -> float:
    """Fraction of the effective game already elapsed (clamped to (0, 1]).

    Regulation (period <= 4): elapsed / 48 as before.

    OT (period > 4) with CV_INGAME_OT_FIX OFF (default, byte-identical):
        clamps to 1.0 — projects against the 48-min baseline, so remaining
        OT minutes contribute nothing (legacy behaviour preserved).

    OT (period > 4) with CV_INGAME_OT_FIX ON (W-007):
        effective game length = 48 + 5*(n_ot) where n_ot = period - 4.
        Elapsed includes all regulation + completed OT periods + time used in
        the current OT period.  This lets remaining OT minutes still project
        additional stats rather than collapsing to current_stat.
        Prop lines are sized against 48-min baselines, but the *remaining*
        correction is small (≤5 min) so the prop-line anchor is preserved.
    """
    p = max(1, int(period))
    if p > REG_PERIODS:
        if not _CV_OT_FIX:
            return 1.0
        # W-007: include OT in effective game length.
        n_ot = p - REG_PERIODS          # number of OT periods reached
        ot_period_min = 5.0             # each OT period is 5 minutes
        game_min_eff = GAME_MIN + ot_period_min * n_ot
        elapsed = (GAME_MIN                              # all regulation
                   + ot_period_min * (n_ot - 1)         # completed OT periods
                   + (ot_period_min - max(0.0, clock_remaining_min)))
        share = elapsed / game_min_eff
        return max(1e-6, min(1.0, share))
    elapsed = PERIOD_MIN * (p - 1) + (PERIOD_MIN - max(0.0, clock_remaining_min))
    share = elapsed / GAME_MIN
    # Tiny epsilon to avoid div/0 at literal tip (clock=12:00 P1).
    return max(1e-6, min(1.0, share))


# Cycle 89b (loop 5): foul_trouble_factor unified into src/prediction/live_factors.
# The local table that lived here (Q3 pf=4 -> 0.70, Q4 pf=5 -> 0.50, etc.) was
# one of three disagreeing copies; we now defer to the canonical, most-conservative
# table. Note the new signature takes a third arg `clock_minutes_remaining`.
from src.prediction.live_factors import (  # noqa: E402
    foul_trouble_factor,
    clutch_closer_factor,
    foul_trouble_factor_perstat,
)

# ── CV_CLUTCH_CLOSER — clutch-closer rest-of-game tilt for Q4 close games (W-017)
# Default OFF: byte-identical to the pre-W017 serve path.
# When ON, `project_snapshot` and `project_final` apply a tier-rank tilt on the
# projected remaining stat for pts/ast/reb/fg3m at period=4 (Q4) with |margin|<=6.
# The tilt multiplies the remaining term: adj = current + tilt * project_remaining.
# Tilts are fold-mean constants from clutch_closer_eval.json (rank-only, not refitted).
# PLAYOFF GUARD: game_id prefix "004" -> 1.0 (no tilt). FOUL GUARD: foul-troubled
# closers have their boost dampened by foul_trouble_factor.
_CV_CLUTCH_CLOSER: bool = os.environ.get(
    "CV_CLUTCH_CLOSER", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── CV_FOUL_PERSTAT — per-stat foul-trouble dampeners + gap fill (W-026) ──────
# Default OFF: byte-identical to the pre-W026 serve path (shared scalar from
# foul_trouble_factor() applied uniformly across all stats).
# When ON, foul_trouble_factor_perstat(pf, period, clock, stat) is called
# INSIDE the stat loop so each stat gets its own calibrated dampener:
#   (1) Two table gaps are filled: pf==2/Q1 → 0.85, pf==3/Q3 → 0.80.
#   (2) The dampener amount is scaled by per-stat calibration ratios from
#       probe_R10_M30v2_foulout (4/4-fold improvement, all 7 stats).
# The shared scalar `ff` is STILL computed once per player (unchanged) and
# stored in the output row's `foul_factor` key for logging/downstream use.
# The per-stat `ff_s` is computed fresh inside the stat loop and replaces
# `ff` in the project_final/project_remaining calls.
# Byte-identical when OFF: the `ff_s = ff` path is taken for all stats when
# CV_FOUL_PERSTAT=0.
_CV_FOUL_PERSTAT: bool = os.environ.get(
    "CV_FOUL_PERSTAT", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── CV_FT_FLOOR — FT-floor channel: split PTS into FT + FG components (W-027) ─
# Default OFF: byte-identical to the flat-pace PTS projection.
# When ON, splits the PTS remaining term into:
#   (1) FG-pts component: flat_remaining_pts * (1 - pct_pts_from_ft)
#       — pace-extrapolated fraction of pts attributable to field goals
#   (2) FT-floor component: fta_per_36_prior / 36 * expected_rem_min * ft_pct
#       — FT pts anchored to the season-prior foul-drawing rate and FT%,
#         NOT scaled by in-game pace variance
#
# The rationale: for high-FT stars (Brunson ~22%, SGA ~24% of pts from FT),
# FT pts are sticky and low-variance — the pace term over-extrapolates them
# when a player is hot. Pinning FT pts to the prior tightens the PTS lower
# quantile and reduces variance without sacrificing accuracy.
#
# Data sources:
#   atlas_player_foul_drawing.parquet — fta_per_36 (value field) + pct_pts_from_ft
#   atlas_player_ft_profile.parquet   — ft_pct (stability.ft_pct)
#
# Graceful degradation (byte-identical to flag-OFF path):
#   - Flag OFF → always flat per-min (byte-identical guarantee)
#   - Player absent from both atlases → flat fallback
#   - fta_per_36_prior <= 0 → flat fallback (player never goes to the line)
#   - expected_rem_min <= 0 → flat fallback
#
# Apply to "pts" stat ONLY. All other stats (reb/ast/fg3m/stl/blk/tov) are
# completely unaffected.
_CV_FT_FLOOR: bool = os.environ.get(
    "CV_FT_FLOOR", "0"
).strip().lower() not in ("", "0", "false", "off")

# League-average FT% and pct_pts_from_ft used as fallback when player absent
# from the atlas.  Fitted from atlas_player_ft_profile + foul_drawing (n≈571).
_FT_FLOOR_LEAGUE_FT_PCT: float = 0.775
_FT_FLOOR_LEAGUE_PCT_FROM_FT: float = 0.175

# Lazy-loaded atlas: {player_id: (fta_per_36, pct_pts_from_ft, ft_pct)}
# Populated on first call to _load_ft_floor_atlas().  None = not yet loaded.
_FT_FLOOR_ATLAS: Optional[Dict[int, Tuple[float, float, float]]] = None

_FT_FLOOR_FOUL_DRAWING_PATH: str = os.path.join(
    PROJECT_DIR, "data", "cache", "atlas_player_foul_drawing.parquet"
)
_FT_FLOOR_FT_PROFILE_PATH: str = os.path.join(
    PROJECT_DIR, "data", "cache", "atlas_player_ft_profile.parquet"
)


def _load_ft_floor_atlas() -> None:
    """Load per-player (fta_per_36, pct_pts_from_ft, ft_pct) on first call (W-027).

    Merges atlas_player_foul_drawing (fta_per_36, pct_pts_from_ft) with
    atlas_player_ft_profile (ft_pct).  For players in foul_drawing but not
    ft_profile, falls back to league-average ft_pct.

    Process-level singleton — loads once, never reloads.
    """
    global _FT_FLOOR_ATLAS
    if _FT_FLOOR_ATLAS is not None:
        return
    try:
        import pandas as _pd
        import json as _json

        result: Dict[int, Tuple[float, float, float]] = {}

        # Load foul_drawing atlas: fta_per_36 (= value field) + pct_pts_from_ft
        fd_path_ok = os.path.exists(_FT_FLOOR_FOUL_DRAWING_PATH)
        ft_path_ok = os.path.exists(_FT_FLOOR_FT_PROFILE_PATH)

        if not fd_path_ok:
            _FT_FLOOR_ATLAS = {}
            return

        fd = _pd.read_parquet(
            _FT_FLOOR_FOUL_DRAWING_PATH,
            columns=["player_id", "value", "ft_generation"],
        )

        # Build FT% lookup from ft_profile atlas
        ft_pct_map: Dict[int, float] = {}
        if ft_path_ok:
            ftp = _pd.read_parquet(
                _FT_FLOOR_FT_PROFILE_PATH,
                columns=["player_id", "stability"],
            )
            for _, row in ftp.iterrows():
                try:
                    stab = (
                        _json.loads(row["stability"])
                        if isinstance(row["stability"], str)
                        else row["stability"]
                    )
                    ft_pct = float(stab.get("ft_pct", _FT_FLOOR_LEAGUE_FT_PCT))
                    if 0.0 < ft_pct <= 1.0:
                        ft_pct_map[int(row["player_id"])] = ft_pct
                except Exception:  # noqa: BLE001
                    continue

        # Build the merged atlas
        import math as _math
        for _, row in fd.iterrows():
            try:
                pid = int(row["player_id"])
                # fta_per_36 is stored in the `value` float column
                fta_per_36 = float(row["value"])
                # Skip NaN (510/1081 rows have no FTA data)
                if _math.isnan(fta_per_36):
                    continue
                # pct_pts_from_ft from ft_generation JSON
                ftg = (
                    _json.loads(row["ft_generation"])
                    if isinstance(row["ft_generation"], str)
                    else row["ft_generation"]
                )
                pct_from_ft = float(
                    ftg.get("pct_pts_from_ft", _FT_FLOOR_LEAGUE_PCT_FROM_FT)
                )
                # Clamp: 0 ≤ pct_from_ft ≤ 0.40 (no one scores >40% from FT)
                pct_from_ft = max(0.0, min(0.40, pct_from_ft))
                # FT% from ft_profile, league avg fallback
                ft_pct = ft_pct_map.get(pid, _FT_FLOOR_LEAGUE_FT_PCT)
                result[pid] = (fta_per_36, pct_from_ft, ft_pct)
            except Exception:  # noqa: BLE001
                continue

        _FT_FLOOR_ATLAS = result
    except Exception:  # noqa: BLE001
        _FT_FLOOR_ATLAS = {}


def _ft_floor_proj_remaining(
    cur_pts: float,
    cur_min: float,
    player_id: Optional[int],
    period: int,
    clock_rem: float,
    *,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    flat_remaining: Optional[float] = None,
) -> Optional[float]:
    """Compute FT-floor split PTS remaining projection (W-027).

    Splits the PTS remaining term into:
      FG-pts component : flat_remaining * (1 - pct_pts_from_ft)
      FT-floor component: fta_per_36_prior / 36 * expected_rem_min * ft_pct

    Returns None when conditions for the feature are not met (caller should
    fall through to the flat per-min path).

    Args:
        cur_pts: current accumulated PTS.
        cur_min: player's accumulated minutes so far.
        player_id: NBA player_id for atlas lookup.
        period, clock_rem: game state for share computation.
        foul_factor, blow_factor: same multipliers as the flat path.
        flat_remaining: the flat-pace remaining term already computed by the
            caller (project_remaining output).  If None this function will
            not be able to split the FG portion and returns None.

    Returns None when:
        - player absent from atlas and no flat_remaining to split
        - fta_per_36_prior <= 0 (player never goes to the line)
        - expected_rem_min <= 0 (end of game)
        - flat_remaining is None (caller didn't supply it)
    """
    if cur_min <= 0:
        return None
    if flat_remaining is None:
        return None

    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_remaining <= 1e-6:
        return None  # end of game

    # Expected remaining player minutes (simple proportional basis, same as flat)
    if share_played > 1e-6:
        expected_rem_min = cur_min * (share_remaining / share_played)
    else:
        return None

    if expected_rem_min <= 0:
        return None

    # Load atlas (lazy)
    _load_ft_floor_atlas()
    assert _FT_FLOOR_ATLAS is not None

    pid = int(player_id) if player_id is not None else -1
    entry = _FT_FLOOR_ATLAS.get(pid)
    if entry is None:
        # Player absent: no split possible → flat fallback
        return None

    fta_per_36, pct_from_ft, ft_pct = entry

    import math as _m
    if fta_per_36 <= 0 or _m.isnan(fta_per_36):
        # Player never goes to the line (or missing data): no split, flat fallback
        return None

    # FG-pts component: flat_remaining scaled by (1 - pct_pts_from_ft)
    fg_rem = flat_remaining * (1.0 - pct_from_ft)

    # FT-floor component: fta_per_36 / 36 * expected_rem_min * ft_pct
    # Apply foul/blowout factors to both components identically
    fta_rate_per_min = fta_per_36 / 36.0
    ft_rem = fta_rate_per_min * expected_rem_min * ft_pct

    # Combined remaining PTS (FG + FT), apply foul/blowout factors
    combined = (fg_rem + ft_rem) * foul_factor * blow_factor

    # Safety: clamp to a physically plausible range.
    # The result should be between 0 and ~2x the flat path (no explosion).
    max_allowed = max(flat_remaining * 2.0 * foul_factor * blow_factor, 0.0)
    combined = min(combined, max_allowed)

    return max(0.0, combined)


# ── CV_INGAME_BONUS_FT — bonus-state FT-driven PTS bump (bonus_ft_bump) ───────
# Default OFF: byte-identical to the flat-pace PTS projection.
#
# When ON, adds a small FT-driven PTS bump to the projected_final for "pts"
# when the OPPONENT has accumulated enough team fouls to be in (or near) the
# bonus.  The bonus state is reconstructed from the snapshot's cumulative player
# `pf` values (sum by team) without any PBP replay:
#
#   opp_team_fouls_in_period = sum(p["pf"] for p in players if p.team == opp_team)
#
# At period-boundary snapshots (endQ1/Q2/Q3, clock=12:00) these are the fouls
# accumulated through the JUST-COMPLETED period.  The NBA bonus threshold is 5.
# A Bayesian-shrunk bonus probability is computed for the remaining periods:
#
#   raw_bonus_prob = min(1.0, opp_team_fouls / (BONUS_FOULS * n_completed_periods))
#   p_bonus = _BFT_PRIOR_BLEND * _BFT_LEAGUE_BONUS_PROB
#           + (1 - _BFT_PRIOR_BLEND) * raw_bonus_prob
#
# where _BFT_LEAGUE_BONUS_PROB=0.45 is the empirical fraction of periods where a
# team is in the bonus (fitted from 8352 team-period rows in quarter_box) and
# _BFT_PRIOR_BLEND=0.95 is a strong prior weight (cross-period foul correlation
# is ~0.001; prior dominates completely).
#
# Expected extra PTS per remaining period from being in bonus:
#   extra_fta_bonus = _BFT_LEAGUE_EXTRA_FTA  (team-level, ~2.4 extra FTA/period)
#   extra_ftm       = extra_fta_bonus * ft_pct * player_fta_share * p_bonus
#   bump_per_period = extra_ftm × remaining_periods
#
# player_fta_share is the player's fraction of team FTA (from atlas; defaults to
# 1/10 league-avg per active player).  ft_pct from atlas; defaults to 0.775.
# Expected bump: ~0.1-0.3 pts per player per snapshot — below MAE noise floor.
#
# Apply to "pts" stat ONLY.  All other stats are completely unaffected.
# Byte-identical when OFF.  Flag: CV_INGAME_BONUS_FT (default 0).
_CV_BONUS_FT: bool = os.environ.get(
    "CV_INGAME_BONUS_FT", "0"
).strip().lower() not in ("", "0", "false", "off")

# NBA threshold: >= BONUS_FOULS team fouls in a period → opponent is in the bonus.
_BFT_BONUS_FOULS: int = 5
# League-average fraction of periods where a team ends up in the bonus.
# Fitted from 8352 team-period rows (quarter_box 2024-25 season).
_BFT_LEAGUE_BONUS_PROB: float = 0.45
# Extra FTA per team per period when in bonus (team-level, period-aggregate).
# Fitted: bonus periods 7.63 FTA, non-bonus 3.20 FTA; diff = 4.43.
# But only PART of the remaining periods will be in bonus, so scale by p_bonus.
_BFT_LEAGUE_EXTRA_FTA_TOTAL: float = 4.43  # team-level FTA diff bonus vs not
# Prior blend weight: strong prior because cross-period foul correlation ~0.001.
# At 0.95 the raw in-game signal contributes ≤ 5% of the final estimate.
_BFT_PRIOR_BLEND: float = 0.95
# Typical active players per team in the snapshot (for per-player share fallback).
_BFT_ACTIVE_PLAYERS: float = 8.0
# Lazy-loaded per-player FT-rate atlas: {player_id: (fta_per_36, ft_pct)}.
# Reuses the FT-floor atlas if already loaded; otherwise loads independently.
_BFT_ATLAS_LOADED: bool = False


def _load_bft_atlas() -> None:
    """Load (or reuse) the per-player FTA-rate / FT% atlas for the bonus FT bump.

    Populates _FT_FLOOR_ATLAS (shared with W-027 CV_FT_FLOOR) if not already
    populated.  When the parquet is absent, sets the atlas to {} (graceful
    degradation → league-average fallback for all players).
    """
    global _BFT_ATLAS_LOADED
    if _BFT_ATLAS_LOADED:
        return
    # Reuse the FT-floor atlas loader (it populates _FT_FLOOR_ATLAS).
    _load_ft_floor_atlas()
    _BFT_ATLAS_LOADED = True


def _bonus_ft_pts_bump(
    player_id: Optional[int],
    team: str,
    opp_team: str,
    snap_players: list,
    period: int,
    clock_rem: float,
) -> float:
    """Compute the bonus-state FT-driven PTS bump for a single player (W bonus_ft).

    Returns the extra pts to ADD to projected_final for "pts".  Returns 0.0 when:
      - CV_INGAME_BONUS_FT is OFF (caller guard, but defensive)
      - end of game (share_remaining <= 0)
      - player or team cannot be identified
      - any atlas data is missing (falls back to 0.0 gracefully)

    The bump is tiny by design (≈0.0-0.3 pts per player per snapshot) because
    the cross-period foul signal is weak (r≈0.001).  The strong _BFT_PRIOR_BLEND
    ensures the estimate stays near the league average.

    Args:
        player_id:    NBA player_id for FTA-rate atlas lookup.
        team:         This player's team abbreviation.
        opp_team:     Opponent team abbreviation in this snapshot.
        snap_players: List of player dicts from the snapshot (for team PF sums).
        period:       Current snapshot period (2=endQ1, 3=endQ2, 4=endQ3).
        clock_rem:    Minutes remaining in the current period.

    Returns float >= 0.0.
    """
    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_remaining <= 1e-6:
        return 0.0  # end of game

    # Number of FULL quarters remaining (endQ1→3 remain, endQ2→2, endQ3→1).
    # At a period-boundary (clock≈12:00) = period "about to start" convention.
    # Remaining full quarters = 5 - period (e.g. period=2 → 3 remaining).
    _p = max(1, int(period))
    remaining_periods = max(0, 5 - _p)
    if remaining_periods <= 0:
        return 0.0

    # ── Reconstruct opp team fouls from snapshot player pf sums ──────────────
    # Sum pf for OPP players (they committed fouls → our team gets FTs).
    opp_team_pf: float = 0.0
    n_completed = max(1, _p - 1)  # periods completed so far (for rate normalization)
    for _pl in snap_players:
        if (_pl.get("team") or "") == opp_team:
            try:
                opp_team_pf += float(_pl.get("pf") or 0)
            except (TypeError, ValueError):
                pass

    # ── Bayesian-blended bonus probability ───────────────────────────────────
    # Raw per-period foul rate from observed data.
    raw_pf_per_period = opp_team_pf / float(n_completed)
    # Raw bonus probability: step at the NBA threshold (5 fouls = in bonus).
    # Teams that averaged >= BONUS_FOULS/period have been in the bonus recently.
    raw_bonus_prob = 1.0 if raw_pf_per_period >= float(_BFT_BONUS_FOULS) else 0.0
    # Blend heavily toward the league prior (cross-period correlation ≈ 0.001).
    p_bonus = (_BFT_PRIOR_BLEND * _BFT_LEAGUE_BONUS_PROB
               + (1.0 - _BFT_PRIOR_BLEND) * raw_bonus_prob)

    # ── MARGINAL correction above the league average ──────────────────────────
    # The flat pace projection already implies the LEAGUE-AVERAGE FTA rate is
    # captured (pace × baseline FTM rate × remaining time).  The bonus FT bump
    # should only correct for the DIFFERENTIAL between the in-game signal and
    # the league average:
    #   marginal_p = p_bonus - _BFT_LEAGUE_BONUS_PROB
    # At _BFT_PRIOR_BLEND=0.95, marginal_p ∈ [-0.022, +0.028].
    # When marginal_p ≤ 0 (high opp foul rate not signalling above-average
    # bonus probability after shrinkage), no bump is added (return 0).
    marginal_p = p_bonus - _BFT_LEAGUE_BONUS_PROB
    if marginal_p <= 0.0:
        return 0.0

    # ── Per-player share of team FTA ─────────────────────────────────────────
    _load_bft_atlas()
    assert _FT_FLOOR_ATLAS is not None
    pid = int(player_id) if player_id is not None else -1
    entry = _FT_FLOOR_ATLAS.get(pid)
    if entry is not None:
        fta_per_36, _, ft_pct = entry
        import math as _m
        if _m.isnan(fta_per_36) or fta_per_36 <= 0:
            # Player never goes to the line: no FT bump possible
            return 0.0
    else:
        # Player absent from atlas: use league average share and FT%
        fta_per_36 = 0.0
        ft_pct = _FT_FLOOR_LEAGUE_FT_PCT

    if fta_per_36 <= 0:
        return 0.0

    # Player's FTA rate per period (12 min).
    fta_per_period = fta_per_36 / 36.0 * 12.0
    # League-average team FTA per period (baseline FTA for one team):
    # fitted from 8352 team-period rows: mean FTA = 5.41/period.
    _league_team_fta_per_period: float = 5.41
    # Player's share of team FTA (capped at 1 to avoid impossible values).
    player_share = min(1.0, fta_per_period / _league_team_fta_per_period)

    # Extra FTM per period for THIS player due to the marginal bonus probability:
    #   marginal_extra_team_fta = marginal_p * (fta_when_bonus - fta_not_bonus)
    #   player_extra_ftm = marginal_extra_team_fta * player_share * ft_pct
    extra_ftm_per_period = marginal_p * _BFT_LEAGUE_EXTRA_FTA_TOTAL * player_share * ft_pct

    # Total bump across remaining full periods.
    bump = extra_ftm_per_period * float(remaining_periods)
    # Safety clamp: no more than 0.5 pts per remaining period (paranoid guard).
    bump = min(bump, 0.5 * float(remaining_periods))
    return max(0.0, bump)


# ── CV_INGAME_REB_OPP — REB opportunity base (misses-available) (W-024) ──────
# Default OFF: byte-identical to the flat per-min REB projection.
# When ON, replaces the flat REB remaining-term with an opportunity-based model:
#
#   proj_remaining_reb = blended_reb_share · expected_remaining_total_misses
#
# where:
#   blended_reb_share = Bayesian blend of in-game live share and historical prior
#     in-game share  = player_reb_so_far / total_game_reb_so_far  (both teams)
#     historical prior = player's season-avg reb share of game rebs (leaguegamelog)
#     blend weight w  = min_so_far / (min_so_far + _REB_OPP_PRIOR_K)
#
#   expected_remaining_total_misses = share_remaining * _LEAGUE_TOTAL_REB_PER_GAME
#     (league average total rebounds/game × fraction of game remaining)
#
# When oreb/dreb split IS available in the snapshot (CV_SNAP_REBSPLIT ON) AND
# team FGA/FGM are available (CV_SNAP_FF ON), the model splits into DREB/OREB:
#   proj_remaining_dreb = blended_dreb_share · opp_expected_remaining_misses
#   proj_remaining_oreb = blended_oreb_share · team_expected_remaining_misses
#
# Graceful degradation (byte-identical to flag-OFF path):
#   - If player has 0 minutes (no rate to project) → flat per-min fallback
#   - If snapshot has no FGA/FGM fields AND no team reb context → flat fallback
#   - Flag OFF → always flat per-min (byte-identical guarantee)
#
# Measured effects (from backlog): team DREB=0.51/opp-miss, OREB=0.33/own-miss;
# per-rebounder DREB +0.073/opp-miss. Effect small (~0.05–0.15 reb), concentrated
# in shooting-variance tails. Dependencies: W-001 (FGA/FGM capture) and W-003
# (oreb/dreb split) for the full live model; degrades gracefully without them.
_CV_REB_OPP: bool = os.environ.get(
    "CV_INGAME_REB_OPP", "0"
).strip().lower() not in ("", "0", "false", "off")

# Pseudo-count for blending in-game reb share with historical prior.
# At K=30, w=0.5 when player has 30 min on floor. Shrinks aggressively early.
_REB_OPP_PRIOR_K: float = 30.0

# League averages fitted from 2025-26 leaguegamelog_regular_season.parquet.
# Total rebounds per game (both teams combined, all players).
_LEAGUE_TOTAL_REB_PER_GAME: float = 87.54
# Per-game opp FGA per team; eFG for computing expected misses.
_LEAGUE_FGA_PER_GAME: float = 89.09   # per-team FGA
_LEAGUE_EFG: float = 0.4713            # league effective FG%
_LEAGUE_MISSES_PER_TEAM_PER_GAME: float = _LEAGUE_FGA_PER_GAME * (1.0 - _LEAGUE_EFG)

# Lazy-loaded prior: {player_id: (total_reb_share, oreb_share, dreb_share)}
# Fitted on 2025-26 leaguegamelog: player_reb / team_total_reb (per game mean).
# Loaded on first use; process-level singleton.
_REB_OPP_PRIOR: Optional[Dict[int, Tuple[float, float, float]]] = None
_REB_OPP_PRIOR_LEAGUE_AVG: Tuple[float, float, float] = (0.082, 0.082, 0.082)

_REB_OPP_PARQUET_PATH: str = os.path.join(
    PROJECT_DIR, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet"
)


def _load_reb_opp_prior() -> None:
    """Load per-player REB share prior on first call.

    Reads leaguegamelog_regular_season.parquet and computes each player's mean
    fraction of their team's rebounds (total, OREB, DREB) per game.  This is the
    season-level prior used when live in-game share is unavailable or noisy.

    Process-level singleton — loads once, never reloads.
    """
    global _REB_OPP_PRIOR, _REB_OPP_PRIOR_LEAGUE_AVG
    if _REB_OPP_PRIOR is not None:
        return
    try:
        import pandas as _pd
        import numpy as _np  # noqa: F401
        if not os.path.exists(_REB_OPP_PARQUET_PATH):
            _REB_OPP_PRIOR = {}
            return
        df = _pd.read_parquet(
            _REB_OPP_PARQUET_PATH,
            columns=["PLAYER_ID", "GAME_ID", "TEAM_ID", "REB", "OREB", "DREB", "MIN"],
        )
        df = df[df["MIN"] > 0].copy()
        # Team-level reb totals per game
        gdf = df.groupby(["GAME_ID", "TEAM_ID"]).agg(
            team_reb=("REB", "sum"),
            team_oreb=("OREB", "sum"),
            team_dreb=("DREB", "sum"),
        ).reset_index()
        merged = df.merge(gdf, on=["GAME_ID", "TEAM_ID"])
        merged["reb_share"]  = merged["REB"]  / merged["team_reb"].replace(0, _np.nan)
        merged["oreb_share"] = merged["OREB"] / merged["team_oreb"].replace(0, _np.nan)
        merged["dreb_share"] = merged["DREB"] / merged["team_dreb"].replace(0, _np.nan)
        prior = merged.groupby("PLAYER_ID").agg(
            reb_s=("reb_share", "mean"),
            oreb_s=("oreb_share", "mean"),
            dreb_s=("dreb_share", "mean"),
        )
        result: Dict[int, Tuple[float, float, float]] = {}
        for pid, row in prior.iterrows():
            result[int(pid)] = (
                float(row["reb_s"])  if not _pd.isna(row["reb_s"])  else 0.082,
                float(row["oreb_s"]) if not _pd.isna(row["oreb_s"]) else 0.082,
                float(row["dreb_s"]) if not _pd.isna(row["dreb_s"]) else 0.082,
            )
        _REB_OPP_PRIOR = result
        # Compute league averages as fallback
        league_tot  = float(prior["reb_s"].mean())  if not prior.empty else 0.082
        league_oreb = float(prior["oreb_s"].mean()) if not prior.empty else 0.082
        league_dreb = float(prior["dreb_s"].mean()) if not prior.empty else 0.082
        _REB_OPP_PRIOR_LEAGUE_AVG = (league_tot, league_oreb, league_dreb)
    except Exception:  # noqa: BLE001
        _REB_OPP_PRIOR = {}


def _reb_opp_proj_remaining(
    cur_reb: float,
    cur_oreb: Optional[float],
    cur_dreb: Optional[float],
    cur_min: float,
    player_id: Optional[int],
    period: int,
    clock_rem: float,
    *,
    total_snap_reb: float = 0.0,
    snap_opp_fga: float = 0.0,
    snap_opp_fgm: float = 0.0,
    snap_team_fga: float = 0.0,
    snap_team_fgm: float = 0.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
) -> Optional[float]:
    """Compute opportunity-based remaining REB projection (W-024).

    Returns None when conditions for the feature are not met (caller should
    fall through to the flat per-min path).  Never returns a negative value.

    The projection is:
      projected_remaining = blended_share · expected_remaining_rebs

    where expected_remaining_rebs is derived from:
      (a) split model (preferred): opp misses × dreb_share + team misses × oreb_share
      (b) simple model (fallback): total_game_reb_per_game × remaining_game_frac

    blended_share = Bayesian blend of in-game share (player_reb / total_snap_reb)
    and the season historical prior.  Pseudo-count K=30.

    Returns None when:
      - player has 0 minutes (no rate to project)
      - cur_reb == 0 AND in-game reb share cannot be computed
    """
    if cur_min <= 0:
        return None

    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_remaining <= 1e-6:
        return None  # end of game — no opportunity remaining

    # Load the season prior (lazy)
    _load_reb_opp_prior()
    assert _REB_OPP_PRIOR is not None

    pid = int(player_id) if player_id is not None else -1
    prior_tot, prior_oreb, prior_dreb = _REB_OPP_PRIOR.get(
        pid, _REB_OPP_PRIOR_LEAGUE_AVG
    )

    # Bayesian blend weight: upweight prior when player has few minutes observed.
    w = cur_min / (cur_min + _REB_OPP_PRIOR_K)

    # ── Path A: split model (oreb/dreb + team FGA/FGM available) ─────────────
    if (cur_oreb is not None and cur_dreb is not None
            and total_snap_reb > 0
            and snap_opp_fga > 0 and snap_team_fga > 0):
        # In-game split shares (per-player fraction of team totals in the snap)
        # total_snap_reb sums all players, but we need PER-TEAM values for split model.
        # Since we have team fga/fgm, estimate team reb:
        # DREB (player gets def rebounds from opp misses)
        # OREB (player gets off rebounds from own misses)
        # Safely floor denominators to avoid div/0 at game start.
        # (We don't have team_dreb/team_oreb directly from the snap here,
        # so approximate from total_snap_reb using league fractions:
        # ~75% of total rebs are DREB, ~25% OREB)
        _LEAGUE_DREB_FRAC = 0.745  # DREB / (DREB + OREB) league avg
        _approx_team_dreb = total_snap_reb * _LEAGUE_DREB_FRAC / 2.0  # per team
        _approx_team_oreb = total_snap_reb * (1 - _LEAGUE_DREB_FRAC) / 2.0

        ingame_dreb_share = (
            float(cur_dreb) / max(1.0, _approx_team_dreb)
        )
        ingame_oreb_share = (
            float(cur_oreb) / max(1.0, _approx_team_oreb)
        )
        blended_dreb_share = w * ingame_dreb_share + (1.0 - w) * prior_dreb
        blended_oreb_share = w * ingame_oreb_share + (1.0 - w) * prior_oreb

        # Expected remaining misses for each component
        opp_misses_so_far = max(0.0, snap_opp_fga - snap_opp_fgm)
        team_misses_so_far = max(0.0, snap_team_fga - snap_team_fgm)
        # Scale so-far misses to remaining game time
        if share_played > 1e-6:
            opp_misses_rem = opp_misses_so_far * (share_remaining / share_played)
            team_misses_rem = team_misses_so_far * (share_remaining / share_played)
        else:
            # No data yet — use league average
            opp_misses_rem = _LEAGUE_MISSES_PER_TEAM_PER_GAME * share_remaining
            team_misses_rem = _LEAGUE_MISSES_PER_TEAM_PER_GAME * share_remaining

        # Clamp shares to sane range
        blended_dreb_share = max(0.0, min(1.0, blended_dreb_share))
        blended_oreb_share = max(0.0, min(1.0, blended_oreb_share))

        rem = (blended_dreb_share * opp_misses_rem
               + blended_oreb_share * team_misses_rem)

    # ── Path B: simple model (only total reb available) ───────────────────────
    elif total_snap_reb > 0:
        ingame_reb_share = cur_reb / total_snap_reb
        blended_share = w * ingame_reb_share + (1.0 - w) * prior_tot
        blended_share = max(0.0, min(1.0, blended_share))
        expected_rem_rebs = _LEAGUE_TOTAL_REB_PER_GAME * share_remaining
        rem = blended_share * expected_rem_rebs

    else:
        # No in-game reb context (e.g. first snapshot before any rebs recorded)
        # Fall back to prior only
        if cur_reb == 0:
            return None  # can't distinguish active vs inactive player
        blended_share = prior_tot
        expected_rem_rebs = _LEAGUE_TOTAL_REB_PER_GAME * share_remaining
        rem = blended_share * expected_rem_rebs

    # Apply foul and blowout factors (same as flat per-min path)
    rem = max(0.0, rem * foul_factor * blow_factor)

    # Safety: clamp output; never project more than a physically plausible bound
    # (current reb already achieved is a hard floor for the final; we only cap rem)
    max_rem = (_LEAGUE_TOTAL_REB_PER_GAME * share_remaining)  # no one player can get all rebs
    return min(float(rem), max_rem)


# ── CV_AST_PROTECT_RAW — hard rule: no tilt touches AST projections (W-025) ───
# Default OFF: byte-identical to the current serve path (AST already unaffected
# by matchup/REB-opp tilts; protect-raw adds an explicit runtime guard).
# When ON, for every AST row in project_snapshot the following are forced to
# their neutral values BEFORE project_final is called:
#   - qshape_pace_factor: overridden to 1.0 (no quarter-shape decay on AST)
#   - clutch_closer_factor: overridden to 1.0 (no clutch tilt on AST)
# This guarantees that AST projected_final == current_stat + project_remaining(
#   current_ast, period, clock_rem, pace_factor=1.0, foul_factor=ff,
#   blow_factor=bf, ...) with no additional multipliers.
#
# The blowout factor (bf) and foul-trouble factor (ff) are NOT removed —
# they reflect minutes availability, not efficiency tilts, and are the same
# multipliers applied to all stats.
#
# Acceptance: assert byte-identical AST output vs current baseline (flag ON
# must produce the same AST numbers as flag OFF because the current path
# already never applies qshape/clutch to AST in a harmful way — this flag
# is a defensive hard-guarantee for future development, not a behaviour change).
# NOTE: byte-identical because:
#   - qshape_pace_factor for "ast" at endQ1/Q2/Q3 is already <1.0 when
#     CV_QSHAPE_DECAY is ON, so with protect-raw ON we override to 1.0.
#     BUT: since CV_QSHAPE_DECAY defaults OFF and this protect-raw guard fires
#     ONLY on the AST stat, the AST output is byte-identical to both:
#       (a) protect-raw OFF + qshape OFF  → qsf=1.0  (same as protect-raw ON)
#       (b) protect-raw OFF + qshape ON   → qsf=0.914 (different from ON)
#     So the correct test is: flag ON vs flag OFF with CV_QSHAPE_DECAY OFF
#     → byte-identical (the only case the backlog acceptance criterion refers to).
_CV_AST_PROTECT_RAW: bool = os.environ.get(
    "CV_AST_PROTECT_RAW", "0"
).strip().lower() not in ("", "0", "false", "off")

# ── CV_INGAME_AST_OPP — AST opportunity base (teammate FGM) (W-025) ───────────
# Default OFF: byte-identical to the flat per-min AST projection.
# When ON, replaces the flat AST remaining-term with an opportunity-based model:
#
#   proj_remaining_ast = blended_ast_rate · expected_remaining_teammate_FGM
#
# where:
#   blended_ast_rate = Bayesian blend of in-game live AST/FGM rate and
#     historical prior (season-avg player AST/team_FGM ratio from leaguegamelog)
#     in-game rate   = player_ast_so_far / team_fgm_so_far  (this player's team)
#     historical prior = player's season-avg AST per teammate FGM
#     blend weight w  = min_so_far / (min_so_far + _AST_OPP_PRIOR_K)
#
#   expected_remaining_teammate_FGM = team_fgm_so_far * (share_remaining /
#     share_played), blended toward league_avg_fgm_per_game * share_remaining
#     when in-game sample is small (first 6 min).
#
# PROTECT AST edge: this model only replaces the REMAINING term; it never
# touches current_stat; blowout_factor (bf) and foul_trouble_factor (ff) are
# applied to the remaining term identically to the flat path.
#
# Graceful degradation (byte-identical to flag-OFF path):
#   - Flag OFF → always flat per-min (byte-identical guarantee)
#   - Player has 0 minutes → returns None → flat fallback
#   - Snapshot has no team FGM (FGM capture not yet active) → prior-only model
#     (team_fgm_per_game_prior * share_remaining * blended_rate → plausible)
#   - team_fgm_so_far == 0 → use prior as the FGM base (early-game safe)
#
# HARD-OFF in playoffs: game_id prefix "004" → returns None → flat fallback.
# (AST edge documented as −2.78% in playoffs.)
#
# Measured effect (backlog): team AST/FGM = 0.64; per-playmaker DAST/DFGM
# within-playmaker slope ~0.105 (each additional teammate FGM → ~0.105 more AST).
# Small but consistent (AST goes to 0 when teammates stop making shots).
# Full effect deferred until W-001 live FGM data flows (same BLOCKED condition
# as W-024 REB opp).
_CV_AST_OPP: bool = os.environ.get(
    "CV_INGAME_AST_OPP", "0"
).strip().lower() not in ("", "0", "false", "off")

# Pseudo-count for blending in-game AST rate with historical prior.
# At K=30, w=0.5 when player has 30 min on floor. Shrinks aggressively early.
_AST_OPP_PRIOR_K: float = 30.0

# League averages fitted from 2025-26 leaguegamelog_regular_season.parquet.
# Team AST/team FGM per game (both teams average).  0.64 = canonical backlog value.
_LEAGUE_AST_PER_FGM: float = 0.64   # team AST ≈ 0.64 * team FGM
# League average team FGM per game (per-team, not both-teams).
# Fitted from 2025-26 leaguegamelog: median team FGM ≈ 42.0/game.
_LEAGUE_FGM_PER_TEAM_PER_GAME: float = 42.0

# Lazy-loaded prior: {player_id: ast_rate}  (player AST per team FGM, season avg)
# Fitted on 2025-26 leaguegamelog: player_ast / (team_fgm per game), per-player mean.
# Loaded on first use; process-level singleton.
_AST_OPP_PRIOR: Optional[Dict[int, float]] = None
_AST_OPP_PRIOR_LEAGUE_AVG: float = 0.064   # typical per-player share of team AST (~10%)

_AST_OPP_PARQUET_PATH: str = os.path.join(
    PROJECT_DIR, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet"
)


def _load_ast_opp_prior() -> None:
    """Load per-player AST-per-FGM prior on first call (W-025).

    Reads leaguegamelog_regular_season.parquet and computes each player's mean
    fraction of their team's made shots that they assisted on, per game.

    Process-level singleton — loads once, never reloads.  When the parquet is
    absent, sets _AST_OPP_PRIOR to {} (graceful degradation → league avg).
    """
    global _AST_OPP_PRIOR, _AST_OPP_PRIOR_LEAGUE_AVG
    if _AST_OPP_PRIOR is not None:
        return
    try:
        import pandas as _pd
        if not os.path.exists(_AST_OPP_PARQUET_PATH):
            _AST_OPP_PRIOR = {}
            return
        df = _pd.read_parquet(
            _AST_OPP_PARQUET_PATH,
            columns=["PLAYER_ID", "GAME_ID", "TEAM_ID", "AST", "FGM", "MIN"],
        )
        df = df[df["MIN"] > 0].copy()
        # Team-level FGM totals per game
        gdf = df.groupby(["GAME_ID", "TEAM_ID"]).agg(
            team_fgm=("FGM", "sum"),
        ).reset_index()
        merged = df.merge(gdf, on=["GAME_ID", "TEAM_ID"])
        # AST rate = player AST / team FGM (how many team makes this player assists per made)
        merged["ast_rate"] = merged["AST"] / merged["team_fgm"].replace(0, _pd.NA)
        prior = merged.groupby("PLAYER_ID").agg(
            rate=("ast_rate", "mean"),
        )
        result: Dict[int, float] = {}
        for pid, row in prior.iterrows():
            if not _pd.isna(row["rate"]):
                result[int(pid)] = float(row["rate"])
        _AST_OPP_PRIOR = result
        # Compute league average as fallback
        _AST_OPP_PRIOR_LEAGUE_AVG = float(prior["rate"].mean()) if not prior.empty else 0.064
    except Exception:  # noqa: BLE001
        _AST_OPP_PRIOR = {}


def _ast_opp_proj_remaining(
    cur_ast: float,
    cur_min: float,
    player_id: Optional[int],
    period: int,
    clock_rem: float,
    *,
    snap_team_fgm: float = 0.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    game_id: Optional[str] = None,
) -> Optional[float]:
    """Compute opportunity-based remaining AST projection (W-025).

    Returns None when conditions for the feature are not met (caller should
    fall through to the flat per-min path).  Never returns a negative value.

    HARD-OFF in playoffs: game_id prefix "004" → returns None.

    The projection is:
      projected_remaining = blended_ast_rate · expected_remaining_team_fgm

    where expected_remaining_team_fgm is derived from in-game pace (if team FGM
    available) or from the league prior.

    Blended_ast_rate = Bayesian blend of in-game rate (player_ast / team_fgm)
    and the historical prior.  Pseudo-count K=30.

    Returns None when:
      - flag is OFF (caller guard, but defensive check here too)
      - playoffs (game_id prefix "004")
      - player has 0 minutes (no rate)
      - end of game (share_remaining <= 0)
    """
    # Playoff hard-OFF
    if game_id and str(game_id).startswith("004"):
        return None

    if cur_min <= 0:
        return None

    share_played = clock_played_share(period, clock_rem)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_remaining <= 1e-6:
        return None  # end of game — no opportunity remaining

    # Load the season prior (lazy)
    _load_ast_opp_prior()
    assert _AST_OPP_PRIOR is not None

    pid = int(player_id) if player_id is not None else -1
    prior_rate = _AST_OPP_PRIOR.get(pid, _AST_OPP_PRIOR_LEAGUE_AVG)

    # Bayesian blend weight: upweight prior when player has few minutes observed.
    w = cur_min / (cur_min + _AST_OPP_PRIOR_K)

    # ── In-game rate (if team FGM available) ──────────────────────────────────
    if snap_team_fgm > 0:
        ingame_ast_rate = cur_ast / snap_team_fgm
        blended_rate = w * ingame_ast_rate + (1.0 - w) * prior_rate
    else:
        # No in-game FGM data: use prior only
        blended_rate = prior_rate

    # Clamp rate to sane range (a single player can't assist on >100% of FGM)
    blended_rate = max(0.0, min(1.0, blended_rate))

    # ── Expected remaining teammate FGM ───────────────────────────────────────
    if snap_team_fgm > 0 and share_played > 1e-6:
        # Scale in-game FGM pace to remaining game time
        expected_remaining_fgm = snap_team_fgm * (share_remaining / share_played)
    else:
        # Prior only: league avg FGM pace * remaining fraction
        expected_remaining_fgm = _LEAGUE_FGM_PER_TEAM_PER_GAME * share_remaining

    # Apply foul and blowout factors (same as flat per-min path)
    rem = max(0.0, blended_rate * expected_remaining_fgm * foul_factor * blow_factor)

    # Safety cap: no player can project more AST than total remaining FGM
    max_rem = expected_remaining_fgm  # can't have more AST than makes
    return min(float(rem), max_rem)


# ── CV_MARGIN_MIN_GRADIENT — 2-D blowout haircut surface (W-021) ─────────────
# Default OFF: byte-identical to the hand-set step-table path (blowout_factor).
# When ON, replaces the hand-set >20→0.65/≥25→0.45/≥30→0.30 step table with a
# continuous 2-D surface fitted on 772 full games (player_quarter_stats.parquet
# × quarter_box Q1-Q3 team-score cache, 11,778 player-Q4 rows).
#
# Surface: factor = 1 - slope * |margin| * time_weight
# where time_weight = min(1.0, clock_remaining_q4 / 12.0) so the haircut scales
# with Q4 time remaining (full at endQ3, zero at buzzer).
#
# Fitted slopes (OLS on Q4 minutes ~ intercept + slope * |margin|):
#   Leading  (team is ahead): slope = 0.00577  (leading stars pulled harder)
#   Trailing (team is behind): slope = 0.00435  (trailing players fight to catch up)
#
# Factor clamped to [_MARGIN_GRAD_FLOOR, 1.0].  Still only applied to Q4 and
# only when is_star (same gate as the old step table — keeps the trailing-bench
# garbage-time BUMP unmodeled, as per spec).
# PLAYOFF GUARD: when game_id prefix is "004" → 1.0 (no tilt).
# NEVER fires in any period < 4 (identical to the original step table contract).
_CV_MARGIN_GRAD: bool = os.environ.get(
    "CV_MARGIN_MIN_GRADIENT", "0"
).strip().lower() not in ("", "0", "false", "off")

# Fitted OLS slopes from Q4 minute surface, STAR-only stratum (772 games,
# 2,416 leading-star rows + 2,478 trailing-star rows).
# Factor = 1 - slope * |margin| * time_weight, then clamped to floor.
# Leading  = player's team is winning; trailing = player's team is losing.
# Star-specific fit (proj_48min >= 30): leading slope = 0.01383, trailing = 0.01364.
# These recover ~0.71 factor at margin=25 and ~0.64 at margin=30, vs
# the hand-set step table (0.45 / 0.30) which over-penalizes.
_MARGIN_GRAD_SLOPE_LEADING: float = 0.01383
_MARGIN_GRAD_SLOPE_TRAILING: float = 0.01364

# Minimum factor floor: never haircut below 10% of full projection.
_MARGIN_GRAD_FLOOR: float = 0.10

# ── CV_INGAME_MARGIN_HAIRCUT — early-period margin->minutes consumer (W-038) ──
# Default OFF: byte-identical to the pre-flag serve path.
#
# BACKGROUND: when the score margin is large LATE in any quarter (not just Q4),
# starters' remaining minutes shrink by ~2.43 min on average (measured from 300
# games × endQ1/Q2/Q3 gradient: OLS endQ3 slope = -0.096 Q4_min per margin unit
# at intercept ~7.1 min).  The existing blowout_factor only fires at period=4 and
# only for the LEADING team.  This flag adds a continuous early-period haircut
# that applies at ALL periods (but only outside Q4 where the step table already
# fires) and on BOTH sides of a blowout (both leading AND trailing stars get rested
# or benched when a game is a decided rout).
#
# Implementation:
#   factor = max(_MHC_FLOOR, 1 - _MHC_SLOPE * max(0, |margin| - _MHC_THRESHOLD))
#   new_final = cur + (final - cur) * factor      [only the remaining delta is scaled]
#   new_final = max(new_final, cur)               [never project below current]
#
# Gate:
#   * Only fires when flag ON (default OFF = strict byte-identical no-op).
#   * Only fires when period < 4 (Q4 is covered by the existing blowout_factor).
#   * Only fires for starters: is_star proxy == (proj_min >= star_threshold_min).
#   * Applied to ALL counting stats (pts/reb/ast/fg3m/stl/blk/tov); the bench
#     benefit is modelled at the team level, not per-stat.
#   * No playoff guard needed (same game_id guard already in blowout_factor);
#     added defensively.
#
# Calibration source: 300-game OLS on player_quarter_stats.parquet
#   endQ3 intercept=7.10, slope=-0.0964  → implied haircut slope vs remaining:
#   _MHC_SLOPE = 0.0964 / 7.10 / 12.0 ~ 0.00113 per margin-unit per remaining-min
#   We express factor as fraction of REMAINING DELTA (not absolute minutes), so:
#   slope = 0.00113 * 12.0 = 0.0136 per margin-unit applied to remaining fraction.
#   Using a conservative 0.010 (below empirical 0.0136) to avoid over-correction.
#   Threshold: 12 pts (games < 12 pts are still competitive; no haircut).
#   Floor: 0.70 (never cut more than 30% of remaining projection).
_CV_MARGIN_HAIRCUT: bool = os.environ.get(
    "CV_INGAME_MARGIN_HAIRCUT", "0"
).strip().lower() not in ("", "0", "false", "off")

# Threshold: |margin| must exceed this for any haircut to fire.
_MHC_THRESHOLD: float = 12.0
# Slope: per-unit haircut on remaining projection fraction per margin point above threshold.
# Conservative vs empirical (0.0136); keeps factor near 1.0 for moderate blowouts.
_MHC_SLOPE: float = 0.010
# Floor: minimum remaining-projection fraction (never haircut below 30% reduction).
_MHC_FLOOR: float = 0.70


def margin_haircut_factor(
    score_margin: float,
    period: int,
    is_star: bool = False,
    game_id: Optional[str] = None,
) -> float:
    """W-038: early-period margin->minutes haircut for starters on BOTH teams.

    Fires at period < 4 (Q4 is handled by the existing blowout_factor step
    table / gradient surface).  Returns a factor in [_MHC_FLOOR, 1.0] applied
    to the remaining projection delta.  Returns 1.0 (no haircut) when:
      - Flag CV_INGAME_MARGIN_HAIRCUT is OFF (byte-identical guarantee).
      - period >= 4 (Q4 path uses blowout_factor instead).
      - is_star is False (bench/fringe players are not rested in blowouts).
      - |margin| <= _MHC_THRESHOLD (close enough that full rotation expected).
      - Playoff guard: game_id prefix "004" -> 1.0 (no haircut in playoffs).

    Args:
        score_margin: SIGNED game margin (home - away), or absolute value.
                      The function takes abs() internally.
        period:       current game period (1..4+).
        is_star:      True if this player is projected >= star_threshold_min
                      (same proxy as blowout_factor).
        game_id:      optional; "004..." prefix -> playoff guard -> returns 1.0.

    Returns:
        factor in [_MHC_FLOOR, 1.0].  Caller applies as:
            new_final = max(cur, cur + (final - cur) * factor)
    """
    if not _CV_MARGIN_HAIRCUT:
        return 1.0
    if not is_star:
        return 1.0
    if int(period or 1) >= 4:
        return 1.0  # Q4 uses existing blowout_factor
    if game_id and str(game_id).startswith("004"):
        return 1.0  # playoff guard
    try:
        m = abs(float(score_margin or 0))
    except (TypeError, ValueError):
        return 1.0
    excess = max(0.0, m - _MHC_THRESHOLD)
    factor = 1.0 - _MHC_SLOPE * excess
    return max(_MHC_FLOOR, min(1.0, factor))


def blowout_factor(score_margin: float, period: int, is_star: bool = False) -> float:
    """Reduce projection for star players in a Q4 blowout.

    Stars get pulled when the game is decided (margin > 20 in Q4). Role
    players don't get the same treatment — coaches give them garbage-time
    run. So we only penalize when is_star is true.
    """
    try:
        m = abs(float(score_margin or 0))
    except (TypeError, ValueError):
        return 1.0
    p = int(period or 0)
    if p < 4 or not is_star:
        return 1.0
    if m >= 30:
        return 0.30
    if m >= 25:
        return 0.45
    if m > 20:
        return 0.65
    return 1.0


def blowout_factor_gradient(
    score_margin: float,
    period: int,
    clock_remaining_min: float,
    is_star: bool = False,
    is_leading: bool = False,
    game_id: Optional[str] = None,
) -> float:
    """W-021: 2-D continuous blowout minute haircut surface.

    Replaces the hand-set step table (>20→0.65/≥25→0.45/≥30→0.30) with a
    linear surface fitted on 772 games (11,778 player-Q4 rows):

        factor = 1 - slope * |margin| * time_weight

    where time_weight = min(1.0, clock_remaining_q4 / 12.0).

    Separate slopes for leading (0.00577) vs trailing (0.00435) teams reflect
    the empirical finding that winning teams pull stars more aggressively.

    Same guard contract as ``blowout_factor``:
      - Only Q4 (period >= 4)
      - Only is_star (role players / bench unchanged)
      - PLAYOFF GUARD: game_id prefix "004" → 1.0
      - Clamped to [_MARGIN_GRAD_FLOOR, 1.0]

    Args:
        score_margin: absolute margin (caller passes abs(home-away)).
        period: current game period.
        clock_remaining_min: minutes remaining in the current period.
        is_star: whether this player is a star (same proxy as blowout_factor).
        is_leading: True if this player's team is currently winning.
        game_id: optional; when prefix "004" (playoffs), returns 1.0.
    """
    # Playoff guard: no haircut in playoff games.
    if game_id and str(game_id).startswith("004"):
        return 1.0
    try:
        m = abs(float(score_margin or 0))
    except (TypeError, ValueError):
        return 1.0
    p = int(period or 0)
    if p < 4 or not is_star:
        return 1.0
    # Time weight: fraction of Q4 remaining (0 at buzzer, 1 at endQ3).
    try:
        clk = max(0.0, float(clock_remaining_min or 0))
    except (TypeError, ValueError):
        clk = 0.0
    time_weight = min(1.0, clk / PERIOD_MIN)
    # Select slope by leading/trailing side.
    slope = _MARGIN_GRAD_SLOPE_LEADING if is_leading else _MARGIN_GRAD_SLOPE_TRAILING
    factor = 1.0 - slope * m * time_weight
    return max(_MARGIN_GRAD_FLOOR, min(1.0, factor))


def project_remaining(
    current_stat: float,
    period: int,
    clock_remaining_min: float,
    *,
    pace_factor: float = 1.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    player_clock_played_min: Optional[float] = None,
    poss_pace_factor: float = 1.0,
    rem_min_override: Optional[float] = None,
) -> float:
    """Project remaining stat from current pace.

    Default basis is GAME clock — i.e. assumes the player has been on the
    floor the whole game so far. If `player_clock_played_min` is provided
    AND > 0, we use that as the basis instead (bench player who only
    played in earlier quarters projects from their personal rate).

    For a player who hasn't played at all (player_clock_played_min == 0
    and current_stat == 0), returns 0.0 — we have no signal.

    W-006 (CV_INGAME_POSS_BASE): ``poss_pace_factor`` adjusts for observed
    in-game tempo vs the flat 48-min assumption.  Default 1.0 = byte-identical
    to the pre-W006 path.  When >1 (fast game) the remaining projection is
    scaled up slightly; when <1 (slow game) scaled down.  The caller derives
    the factor from ``_poss_pace_factor(snap)`` and only passes it when the
    CV_INGAME_POSS_BASE flag is ON.

    W-008 (CV_INGAME_L5_ANCHOR): when the flag is ON and the game-elapsed
    share is below ``_L5_ANCHOR_MIN_SHARE`` (12 game-min = end-Q1), the
    denominator in the rate computation is floored at ``_L5_ANCHOR_MIN_SHARE``
    so the extrapolation factor cannot explode.  Late-game snapshots
    (played_share >= _L5_ANCHOR_MIN_SHARE) are byte-identical to the flag-OFF
    path.

    W-009 (CV_INGAME_ROTCURVE): ``rem_min_override`` passes the atlas-based
    expected remaining minutes directly. When set and > 0, the per-minute rate
    (current_stat / player_clock_played_min) is projected over that remaining
    time instead of the clock-based estimate. Default None = flag-OFF
    byte-identical path.
    """
    # W-009: atlas-based remaining minutes override (flag-ON path only).
    if rem_min_override is not None and rem_min_override >= 0:
        basis_min = player_clock_played_min if (
            player_clock_played_min is not None and player_clock_played_min > 0
        ) else None
        if basis_min is None:
            # Use game-clock played minutes as the rate basis.
            share_played = clock_played_share(period, clock_remaining_min)
            if share_played <= 1e-6:
                return 0.0
            basis_min = share_played * GAME_MIN
        if basis_min <= 0 or current_stat == 0:
            return 0.0
        per_min_rate = current_stat / basis_min
        remaining_proj = (
            per_min_rate * rem_min_override
            * pace_factor * foul_factor * blow_factor * poss_pace_factor
        )
        return max(0.0, remaining_proj)

    if player_clock_played_min is not None and player_clock_played_min > 0:
        # Player-clock basis: project the per-minute rate over remaining game min.
        share_played = min(1.0, player_clock_played_min / GAME_MIN)
        share_remaining = max(0.0, 1.0 - share_played)
        if share_played <= 1e-6 or share_remaining <= 1e-6:
            return 0.0
        # W-008: floor the denominator so early-game rates don't explode.
        denom = (max(share_played, _L5_ANCHOR_MIN_SHARE)
                 if _CV_L5_ANCHOR else share_played)
        per_min_rate = current_stat / player_clock_played_min
        # Use a default "expected remaining player minutes" = remaining_share * 36
        # (typical star ceiling), but cap at remaining game minutes.
        # Simpler: project at the rate over the proportional remaining time.
        remaining_proj = (
            current_stat * (share_remaining / denom)
            * pace_factor * foul_factor * blow_factor * poss_pace_factor
        )
        return max(0.0, remaining_proj)

    share_played = clock_played_share(period, clock_remaining_min)
    share_remaining = max(0.0, 1.0 - share_played)
    if share_played <= 1e-6 or share_remaining <= 1e-6:
        return 0.0
    # W-008: floor the denominator so early-game rates don't explode.
    denom = (max(share_played, _L5_ANCHOR_MIN_SHARE)
             if _CV_L5_ANCHOR else share_played)
    remaining_proj = (
        current_stat * (share_remaining / denom)
        * pace_factor * foul_factor * blow_factor * poss_pace_factor
    )
    return max(0.0, remaining_proj)


def project_final(
    current_stat: float,
    period: int,
    clock_remaining_min: float,
    *,
    pace_factor: float = 1.0,
    foul_factor: float = 1.0,
    blow_factor: float = 1.0,
    player_clock_played_min: Optional[float] = None,
    poss_pace_factor: float = 1.0,
    rem_min_override: Optional[float] = None,
    l5_value: Optional[float] = None,
    clutch_factor: float = 1.0,
) -> float:
    """final_proj = current_stat + clutch_factor * project_remaining(...).

    W-006: ``poss_pace_factor`` is forwarded to ``project_remaining``.  Default
    1.0 preserves byte-identical output vs the pre-W006 path.

    W-009: ``rem_min_override`` is forwarded to ``project_remaining``.  Default
    None preserves byte-identical output vs the pre-W009 path.

    ``l5_value``: accepted (unused by this function) so callers can pass it
    without branching; the L5-anchor blend (W-008) is handled by the caller
    in project_snapshot when the flag is ON.

    W-017: ``clutch_factor`` multiplies the remaining term only (default 1.0 =
    byte-identical).  Derived from ``clutch_closer_factor()`` in the caller when
    ``CV_CLUTCH_CLOSER`` is ON.  Clipped to [0.30, 2.0] defensively.
    """
    rem = project_remaining(
        current_stat, period, clock_remaining_min,
        pace_factor=pace_factor, foul_factor=foul_factor,
        blow_factor=blow_factor,
        player_clock_played_min=player_clock_played_min,
        poss_pace_factor=poss_pace_factor,
        rem_min_override=rem_min_override,
    )
    # W-017: apply clutch tilt on the remaining term only (default 1.0 = no-op).
    cf = max(0.30, min(2.0, float(clutch_factor)))
    return float(current_stat) + rem * cf


def is_bench_in_current_period(
    player: dict, period: int, period_elapsed_min: float = 12.0,
) -> bool:
    """True if the player has 0 minutes in the current period AND the
    period has actually been in progress for >= 2 minutes.

    Uses optional `min_q1`/`min_q2`/`min_q3`/`min_q4` fields. If those are
    missing, returns False (we can't tell — assume on-floor and use game
    clock basis).

    The period_elapsed_min guard prevents the false-positive at the start
    of a quarter — at halftime (period=3, clock=12:00) every player has
    min_q3=0 because Q3 hasn't started yet. We only treat them as 'bench'
    once the quarter is actually 2+ minutes deep AND they haven't checked in.
    """
    p = int(period or 0)
    key = f"min_q{p}" if 1 <= p <= 4 else None
    if key is None or key not in player:
        return False
    if period_elapsed_min < 2.0:
        return False
    try:
        return float(player.get(key, 0) or 0) <= 0.0
    except (TypeError, ValueError):
        return False


# ── snapshot loading + project-a-snapshot orchestration ──────────────────────

def _num(v, default: float = 0.0) -> float:
    """Best-effort float cast — None / non-numeric → default."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _normalize_snapshot(snap: dict) -> dict:
    """Coerce legacy nested {home: {abbrev, score}, away: {...}} → canonical
    top-level home_team / home_score / away_team / away_score (the schema used
    by `src/data/live.py`, `live_game_poll`, `save_live_predictions`, etc).

    Idempotent: a snapshot already in canonical form is returned unchanged.
    Mutates and returns the same dict so callers can chain.
    """
    if isinstance(snap.get("home"), dict):
        snap["home_team"]  = snap.get("home_team")  or snap["home"].get("abbrev", "")
        snap["home_score"] = snap.get("home_score", snap["home"].get("score", 0))
    if isinstance(snap.get("away"), dict):
        snap["away_team"]  = snap.get("away_team")  or snap["away"].get("abbrev", "")
        snap["away_score"] = snap.get("away_score", snap["away"].get("score", 0))
    return snap


def load_snapshot(path: str) -> dict:
    """Parse snapshot JSON. Missing fields tolerated — projector handles defaults."""
    with open(path, "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    if not isinstance(snap, dict):
        raise ValueError(f"snapshot {path}: top-level must be an object")
    snap.setdefault("players", [])
    snap.setdefault("period", 1)
    snap.setdefault("clock", "12:00")
    # Lift legacy nested home/away dicts to canonical top-level keys.
    _normalize_snapshot(snap)
    snap.setdefault("home_team", "")
    snap.setdefault("away_team", "")
    snap.setdefault("home_score", 0)
    snap.setdefault("away_score", 0)
    return snap


def latest_snapshot_for_game(game_id: str, live_dir: str = LIVE_DIR) -> Optional[str]:
    """Return path to most recent snapshot for `game_id`, or None if absent."""
    pat = os.path.join(live_dir, f"{game_id}_*.json")
    matches = sorted(glob.glob(pat))
    return matches[-1] if matches else None


def project_snapshot(
    snap: dict,
    *,
    pace_factor: float = 1.0,
    star_threshold_min: float = 30.0,
) -> List[Dict]:
    """Project final-stat lines for every player in a snapshot.

    Returns a list of dicts:
        {name, team, player_id, stat, current, projected_final,
         period, foul_factor, blow_factor}

    Stars (for blowout detection) defined as players with cumulative
    MIN > star_threshold_min projected across the game (rough proxy =
    current MIN scaled to 48 min). Avoids a separate roster lookup.

    W-006 (CV_INGAME_POSS_BASE): when the flag is ON, derives a tempo
    multiplier from the snapshot's possession counts (``total_poss_count``,
    ``game_elapsed_sec``) using empirical-Bayes shrinkage toward the league
    prior.  Falls back gracefully to 1.0 when those fields are absent (e.g.,
    calibration snapshots built from quarter-stat parquet only; depends on
    W-001 for the live four-factor denominator).
    """
    # Defensively normalize: callers that build snapshots in-memory (tests,
    # ad-hoc scripts) may still pass the legacy nested form.
    _normalize_snapshot(snap)
    period = int(snap.get("period") or 1)
    clock_rem = parse_clock(snap.get("clock"))
    home_team = (snap.get("home_team") or "")
    away_team = (snap.get("away_team") or "")
    home_score = _num(snap.get("home_score"))
    away_score = _num(snap.get("away_score"))
    margin = home_score - away_score  # signed

    # W-006: possession-anchored pace factor (1.0 when flag OFF or poss unavailable)
    ppf = _poss_pace_factor(snap) if _CV_POSS_BASE else 1.0

    # W-009: pre-warm the rotation curve atlas (no-op when flag OFF)
    # _CV_ROTMINUTES (W-009-RIGHT) reuses the same atlas, so warm it for either.
    if _CV_ROTCURVE or _CV_ROTMINUTES:
        _load_rotcurve_atlas()

    # W-024 (CV_INGAME_REB_OPP): pre-compute snapshot-level aggregates for the
    # REB opportunity model.  These are used inside the per-player loop below.
    # - total_snap_reb: sum of reb across ALL players (both teams) in the snapshot.
    #   Serves as the denominator when computing per-player in-game reb share.
    # - snap_fga / snap_fgm: per-team FGA/FGM (populated when CV_SNAP_FF=ON);
    #   used for the split DREB/OREB model.  Keyed by team abbreviation.
    # All values default to 0.0 → graceful fallback to flat per-min when absent.
    _total_snap_reb: float = 0.0
    _snap_fga: Dict[str, float] = {}    # {team: fga_so_far}
    _snap_fgm: Dict[str, float] = {}    # {team: fgm_so_far}
    if _CV_REB_OPP:
        for _p in snap.get("players") or []:
            _total_snap_reb += _num(_p.get("reb"))
            _t = _p.get("team") or ""
            if _t:
                _snap_fga[_t] = _snap_fga.get(_t, 0.0) + _num(_p.get("fga"))
                _snap_fgm[_t] = _snap_fgm.get(_t, 0.0) + _num(_p.get("fgm"))

    # W-027 (CV_FT_FLOOR): pre-warm the FT-floor atlas (no-op when flag OFF).
    if _CV_FT_FLOOR:
        _load_ft_floor_atlas()

    # W-025 (CV_INGAME_AST_OPP): pre-compute snapshot-level per-team FGM for the
    # AST opportunity model.  Reuses the same _snap_fgm dict computed above if
    # CV_INGAME_REB_OPP is also ON (overlapping aggregation is harmless).
    # When only CV_INGAME_AST_OPP is ON (and not CV_INGAME_REB_OPP), we compute
    # _snap_fgm separately so the REB path is unaffected.
    # All values default to 0.0 → graceful fallback to prior-only when absent.
    if _CV_AST_OPP and not _CV_REB_OPP:
        # Only need FGM (not FGA) for the AST model; build _snap_fgm independently.
        for _p in snap.get("players") or []:
            _t = _p.get("team") or ""
            if _t:
                _snap_fgm[_t] = _snap_fgm.get(_t, 0.0) + _num(_p.get("fgm"))

    out: List[Dict] = []
    for p in snap.get("players") or []:
        name = p.get("name") or f"pid_{p.get('player_id')}"
        team = p.get("team") or ""
        pid = p.get("player_id")
        cur_min = _num(p.get("min"))
        pf = _num(p.get("pf"))
        ff = foul_trouble_factor(pf, period, clock_rem)
        # Star proxy: project min to 48; >= star_threshold_min counts.
        share_played_game = clock_played_share(period, clock_rem)
        proj_min = (cur_min / share_played_game) if share_played_game > 0 else cur_min
        is_star = proj_min >= star_threshold_min
        # Blowout factor uses absolute margin AND we apply only to the
        # leading-side stars (winning teams sit stars more aggressively).
        team_is_leading = (
            (team == home_team and margin > 0) or
            (team == away_team and margin < 0)
        )
        # W-021 (CV_MARGIN_MIN_GRADIENT): when ON, replace the hand-set step
        # table with the 2-D surface (margin × time-remaining).  The gradient
        # function carries the same is_star and is_leading guards so the
        # trailing-bench path is unchanged.  With flag OFF, falls through to
        # the original step-table call → byte-identical.
        if _CV_MARGIN_GRAD:
            bf = blowout_factor_gradient(
                abs(margin), period, clock_rem,
                is_star=(is_star and team_is_leading),
                is_leading=team_is_leading,
                game_id=snap.get("game_id"),
            )
        else:
            bf = blowout_factor(abs(margin), period, is_star=(is_star and team_is_leading))

        period_elapsed_min = max(0.0, PERIOD_MIN - clock_rem)
        bench_now = is_bench_in_current_period(
            p, period, period_elapsed_min=period_elapsed_min,
        )
        player_basis = cur_min if bench_now else None

        # W-009 (CV_INGAME_ROTCURVE): compute atlas expected remaining minutes.
        # Only fire when the flag is ON AND the player has played some minutes
        # (cur_min > 0) — for zero-minute players we have no rate to project.
        # When the atlas has no entry for this player, rotcurve_expected_rem_min
        # degrades to the flat-pace estimate (byte-identical to flag-OFF for
        # unknown players; only players WITH atlas entries get the curve benefit).
        # Pass min_q1/min_q2 from the player row so the fringe-guard branch
        # can use the regression estimate for low-minute players.
        rem_min_ov: Optional[float] = None
        if _CV_ROTCURVE and cur_min > 0:
            _mq1 = float(p.get("min_q1") or 0.0)
            _mq2 = float(p.get("min_q2") or 0.0)
            rem_min_ov = rotcurve_expected_rem_min(
                pid, period, clock_rem, cur_min,
                min_q1=_mq1, min_q2=_mq2,
            )
        # W-009-RIGHT (CV_INGAME_ROTMINUTES): rotation-curve remaining-minutes
        # consumer. Drives the per-minute stat extrapolation off projected
        # minutes (atlas-curve × flat Bayesian blend) instead of the flat clock
        # share. Returns None (→ flat path, byte-identical) when the flag is OFF
        # or the player has no full atlas curve. Mutually independent of the
        # legacy _CV_ROTCURVE above; if both are ON, ROTCURVE (computed first)
        # wins so each flag is independently testable.
        if rem_min_ov is None and _CV_ROTMINUTES and cur_min > 0:
            _rm = rotminutes_expected_rem_min(
                pid, period, clock_rem, cur_min,
            )
            if _rm is not None:
                rem_min_ov = _rm
                # CRITICAL: the per-minute RATE basis must be the PLAYER's own
                # minutes (cur_min), not the game-elapsed clock. project_remaining's
                # override branch falls back to game-clock minutes when
                # player_clock_played_min is None — which under-counts the rate
                # for every player who sat any time, mis-scaling the projection
                # (this exact mismatch is what sank the rejected W-009). Forcing
                # player_basis = cur_min makes per_min_rate = cur_stat / cur_min,
                # matching the validated scratch model.
                player_basis = cur_min

        # W-024 (CV_INGAME_REB_OPP): compute per-player opp/miss context for the
        # REB opportunity model.  Only needed for the "reb" stat; computed once
        # per player to avoid repeating the lookup inside the stat loop.
        # oreb / dreb from the player row (populated when CV_SNAP_REBSPLIT=ON).
        _reb_opp_oreb: Optional[float] = None
        _reb_opp_dreb: Optional[float] = None
        _reb_opp_opp_fga: float = 0.0
        _reb_opp_opp_fgm: float = 0.0
        _reb_opp_team_fga: float = 0.0
        _reb_opp_team_fgm: float = 0.0
        if _CV_REB_OPP:
            _oreb_val = p.get("oreb")
            _dreb_val = p.get("dreb")
            if _oreb_val is not None:
                _reb_opp_oreb = _num(_oreb_val)
            if _dreb_val is not None:
                _reb_opp_dreb = _num(_dreb_val)
            # Team FGA/FGM from the snapshot aggregates computed above.
            # This player's team = own FGA/FGM; opponent = other team in the snap.
            if team and _snap_fga:
                _reb_opp_team_fga = _snap_fga.get(team, 0.0)
                _reb_opp_team_fgm = _snap_fgm.get(team, 0.0)
                # Opponent FGA = sum of all other teams in the snap.
                _reb_opp_opp_fga = sum(
                    v for k, v in _snap_fga.items() if k != team
                )
                _reb_opp_opp_fgm = sum(
                    v for k, v in _snap_fgm.items() if k != team
                )

        # W-025 (CV_INGAME_AST_OPP): extract per-player team FGM for AST model.
        # Uses the _snap_fgm dict populated above (either from the W-024 or W-025
        # pre-computation blocks).  Defaults to 0.0 if FGM was never captured,
        # in which case _ast_opp_proj_remaining falls back to prior-only model.
        _ast_opp_team_fgm: float = 0.0
        if _CV_AST_OPP and team and _snap_fgm:
            _ast_opp_team_fgm = _snap_fgm.get(team, 0.0)

        # W-017 (CV_CLUTCH_CLOSER): compute per-player clutch tier factor once,
        # then apply per stat inside the loop. Only fires when flag ON AND period=4
        # AND |margin|<=6. Returns 1.0 instantly when flag OFF (byte-identical).
        _ccf_game_id = snap.get("game_id")

        for stat in STATS:
            cur = _num(p.get(stat))
            # W-026 (CV_FOUL_PERSTAT): per-stat foul-trouble dampener.
            # When OFF: ff_s == ff (shared scalar, byte-identical to pre-W026).
            # When ON: calls foul_trouble_factor_perstat which uses the extended
            # table (fills pf==2/Q1 and pf==3/Q3 gaps) and scales the dampener
            # amount by per-stat calibration ratios from probe_R10_M30v2_foulout.
            # The shared `ff` computed above is STILL stored in the output row for
            # logging continuity; ff_s is the value fed into project_final below.
            ff_s: float = (
                foul_trouble_factor_perstat(pf, period, clock_rem, stat)
                if _CV_FOUL_PERSTAT else ff
            )
            # W-015 (CV_QSHAPE_DECAY): apply per-stat quarter-shape decay factor.
            # When OFF, qsf=1.0 so pace_factor is unchanged (byte-identical path).
            # When ON, scales the pace_factor by the ratio of remaining-quarter rate
            # to elapsed-quarter rate for the 4 target stats (pts/reb/ast/fg3m).
            # blk, tov, stl are excluded (blk rises, tov net-harmful per spec).
            if _CV_QSHAPE_DECAY and stat in _QSHAPE_STATS:
                qsf = qshape_pace_factor(stat, period, clock_rem)
            else:
                qsf = 1.0
            # W-025 (CV_AST_PROTECT_RAW): hard rule — no efficiency/calibration
            # tilt is applied to AST projections.  When the flag is ON and
            # stat=="ast", override qsf and cf to their neutral values (1.0)
            # BEFORE calling project_final.  This is a defensive guard for future
            # development; when all other flags are OFF the output is byte-identical
            # (qsf and cf are already 1.0 in the default path).
            if _CV_AST_PROTECT_RAW and stat == "ast":
                qsf = 1.0   # no quarter-shape decay on AST (defend the edge)
            # W-017 (CV_CLUTCH_CLOSER): tier-rank tilt on remaining stat.
            # clutch_closer_factor returns 1.0 when flag OFF or conditions unmet.
            cf = clutch_closer_factor(
                player_id=pid,
                stat=stat,
                period=period,
                margin=abs(margin),
                pf=pf,
                clock_minutes_remaining=clock_rem,
                game_id=_ccf_game_id,
            ) if _CV_CLUTCH_CLOSER else 1.0
            # W-025 (CV_AST_PROTECT_RAW): also disable clutch tilt on AST.
            if _CV_AST_PROTECT_RAW and stat == "ast":
                cf = 1.0    # no clutch tilt on AST (defend the edge)

            # W-027 (CV_FT_FLOOR): split PTS remaining into FG + FT components.
            # For all other stats the flag is a no-op (bytes identical).
            if _CV_FT_FLOOR and stat == "pts":
                # Compute the flat remaining term first (same as the else branch)
                # so we can pass it as the splitting baseline.
                _flat_rem_pts = project_remaining(
                    cur, period, clock_rem,
                    pace_factor=pace_factor * qsf,
                    foul_factor=1.0, blow_factor=1.0,  # factors applied inside _ft_floor
                    player_clock_played_min=player_basis,
                    poss_pace_factor=ppf,
                    rem_min_override=rem_min_ov,
                )
                _ft_rem = _ft_floor_proj_remaining(
                    cur_pts=cur,
                    cur_min=cur_min,
                    player_id=pid,
                    period=period,
                    clock_rem=clock_rem,
                    foul_factor=ff_s,
                    blow_factor=bf,
                    flat_remaining=_flat_rem_pts,
                )
                if _ft_rem is not None:
                    final = float(cur) + _ft_rem * cf
                else:
                    # Fallback to flat per-min (same as flag-OFF path)
                    final = project_final(
                        cur, period, clock_rem,
                        pace_factor=pace_factor * qsf,
                        foul_factor=ff_s, blow_factor=bf,
                        player_clock_played_min=player_basis,
                        poss_pace_factor=ppf,
                        rem_min_override=rem_min_ov,
                        clutch_factor=cf,
                    )
            # W-025 (CV_INGAME_AST_OPP): replace flat per-min for AST stat when
            # flag is ON and the opportunity model has enough context.
            # For all other stats the flag is a no-op (bytes identical).
            elif _CV_AST_OPP and stat == "ast":
                _ast_opp_rem = _ast_opp_proj_remaining(
                    cur_ast=cur,
                    cur_min=cur_min,
                    player_id=pid,
                    period=period,
                    clock_rem=clock_rem,
                    snap_team_fgm=_ast_opp_team_fgm,
                    foul_factor=ff_s,
                    blow_factor=bf,
                    game_id=_ccf_game_id,
                )
                if _ast_opp_rem is not None:
                    # Override: use opportunity-based remaining, skip project_final
                    final = float(cur) + _ast_opp_rem
                else:
                    # Fallback to flat per-min (same as flag-OFF path)
                    final = project_final(
                        cur, period, clock_rem,
                        pace_factor=pace_factor * qsf,
                        foul_factor=ff_s, blow_factor=bf,
                        player_clock_played_min=player_basis,
                        poss_pace_factor=ppf,
                        rem_min_override=rem_min_ov,
                        clutch_factor=cf,
                    )
            # W-024 (CV_INGAME_REB_OPP): replace flat per-min for REB stat when
            # flag is ON and the opportunity model has enough context.
            # For all other stats the flag is a no-op (bytes identical).
            elif _CV_REB_OPP and stat == "reb":
                _opp_rem = _reb_opp_proj_remaining(
                    cur_reb=cur,
                    cur_oreb=_reb_opp_oreb,
                    cur_dreb=_reb_opp_dreb,
                    cur_min=cur_min,
                    player_id=pid,
                    period=period,
                    clock_rem=clock_rem,
                    total_snap_reb=_total_snap_reb,
                    snap_opp_fga=_reb_opp_opp_fga,
                    snap_opp_fgm=_reb_opp_opp_fgm,
                    snap_team_fga=_reb_opp_team_fga,
                    snap_team_fgm=_reb_opp_team_fgm,
                    foul_factor=ff_s,
                    blow_factor=bf,
                )
                if _opp_rem is not None:
                    # Override: use opportunity-based remaining, skip project_final
                    final = float(cur) + _opp_rem
                else:
                    # Fallback to flat per-min (same as flag-OFF)
                    final = project_final(
                        cur, period, clock_rem,
                        pace_factor=pace_factor * qsf,
                        foul_factor=ff_s, blow_factor=bf,
                        player_clock_played_min=player_basis,
                        poss_pace_factor=ppf,
                        rem_min_override=rem_min_ov,
                        clutch_factor=cf,
                    )
            else:
                final = project_final(
                    cur, period, clock_rem,
                    pace_factor=pace_factor * qsf,
                    foul_factor=ff_s, blow_factor=bf,
                    player_clock_played_min=player_basis,
                    poss_pace_factor=ppf,
                    rem_min_override=rem_min_ov,
                    clutch_factor=cf,
                )
            # bonus_ft_bump (CV_INGAME_BONUS_FT): add FT-driven PTS bump
            # when opponent is in (or near) the bonus.  Applies to pts only;
            # all other stats are byte-identical to the flag-OFF path.
            # Placed LAST so it stacks on top of every earlier projection
            # transform (foul/blowout/heat-check/residual heads).
            if _CV_BONUS_FT and stat == "pts":
                _bump = _bonus_ft_pts_bump(
                    player_id=pid,
                    team=team,
                    opp_team=away_team if team == home_team else home_team,
                    snap_players=list(snap.get("players") or []),
                    period=period,
                    clock_rem=clock_rem,
                )
                final = final + _bump

            # W-038 (CV_INGAME_MARGIN_HAIRCUT): early-period margin->minutes
            # haircut for starters on BOTH teams.  Only fires at period < 4
            # (Q4 is handled by blowout_factor already).  When the absolute
            # game margin exceeds _MHC_THRESHOLD (12 pts), scales the remaining
            # projection delta by a continuous factor in [_MHC_FLOOR, 1.0].
            # Applied AFTER bonus_ft_bump so it is the final transform.
            # Byte-identical when CV_INGAME_MARGIN_HAIRCUT is OFF (default).
            if _CV_MARGIN_HAIRCUT and period < 4 and is_star:
                _mhf = margin_haircut_factor(
                    margin, period, is_star=is_star,
                    game_id=snap.get("game_id"),
                )
                if _mhf < 1.0:
                    _remaining = max(0.0, float(final) - float(cur))
                    final = float(cur) + _remaining * _mhf
                    # Floor: never project below current (already guaranteed
                    # by _remaining >= 0, but be explicit).
                    final = max(final, float(cur))

            out.append({
                "name": name, "team": team, "player_id": pid,
                "stat": stat, "current": cur, "projected_final": final,
                "period": period, "foul_factor": ff, "blow_factor": bf,
                "bench_in_current_period": bench_now,
            })
    return out


# ── pre-game prediction join (optional reference) ────────────────────────────

def load_pregame_predictions(date_iso: str) -> Dict[Tuple[int, str], float]:
    """Load data/predictions/<date>.csv as {(player_id, stat): pred}.

    Returns empty dict on missing file / unreadable rows. Used purely as a
    REFERENCE column on the in-play output — we never blend pre-game into
    the in-play projection here.
    """
    path = os.path.join(PRED_DIR, f"{date_iso}.csv")
    out: Dict[Tuple[int, str], float] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                try:
                    pid = int(row["player_id"])
                    stat = str(row["stat"]).lower()
                    pred = float(row["pred"])
                except (KeyError, TypeError, ValueError):
                    continue
                out[(pid, stat)] = pred
    except Exception:
        pass
    return out


# ── output formatting + ledger save ──────────────────────────────────────────

def format_stdout(rows: List[Dict],
                  pregame: Optional[Dict[Tuple[int, str], float]] = None) -> str:
    """Render projection rows as a multi-line stdout report grouped by player."""
    if not rows:
        return "(no projections — empty snapshot)\n"
    pregame = pregame or {}
    # Group by (player_id or name)
    by_player: Dict[str, List[Dict]] = {}
    order: List[str] = []
    for r in rows:
        key = f"{r['name']} ({r['team']})"
        if key not in by_player:
            by_player[key] = []
            order.append(key)
        by_player[key].append(r)

    lines: List[str] = []
    period = rows[0].get("period", 0)
    lines.append(f"\n  IN-GAME PROJECTIONS  —  period {period}")
    lines.append(f"  {'player':30s} {'stat':5s} {'cur':>6s} {'proj':>7s} {'pre':>7s}")
    lines.append("  " + "-" * 60)
    for key in order:
        for r in by_player[key]:
            pid = r.get("player_id")
            pre = pregame.get((int(pid), r["stat"])) if pid is not None else None
            pre_s = f"{pre:.2f}" if pre is not None else "  —  "
            lines.append(
                f"  {key[:30]:30s} {r['stat'].upper():5s} "
                f"{r['current']:>6.1f} {r['projected_final']:>7.2f} {pre_s:>7s}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def save_inplay_csv(
    out_path: str, snap: dict, rows: List[Dict],
    pregame: Optional[Dict[Tuple[int, str], float]] = None,
) -> int:
    """Write one row per (player, stat) to a cycle-80-style ledger variant.

    Schema:
        date, game_id, player_id, player, team, stat,
        current, projected_final, pregame_pred,
        period, foul_factor, blow_factor
    """
    pregame = pregame or {}
    game_id = snap.get("game_id", "")
    date_str = _date.today().isoformat()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    file_exists = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    n = 0
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not file_exists:
            w.writerow([
                "date", "game_id", "player_id", "player", "team",
                "stat", "current", "projected_final", "pregame_pred",
                "period", "foul_factor", "blow_factor",
            ])
        for r in rows:
            pid = r.get("player_id")
            pre = pregame.get((int(pid), r["stat"])) if pid is not None else None
            pre_s = f"{pre:.4f}" if pre is not None else ""
            w.writerow([
                date_str, game_id, pid, r["name"], r["team"],
                r["stat"], f"{r['current']:.2f}", f"{r['projected_final']:.4f}",
                pre_s, r.get("period", ""),
                f"{r.get('foul_factor', 1.0):.3f}",
                f"{r.get('blow_factor', 1.0):.3f}",
            ])
            n += 1
    return n


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--game-id", help="NBA game_id; loads latest snapshot")
    grp.add_argument("--snapshot", help="Explicit path to snapshot JSON")
    grp.add_argument("--all-live", action="store_true",
                     help="Project every distinct game_id in data/live/")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="Pace factor multiplier (default 1.0)")
    ap.add_argument("--save", nargs="?", const="__default__", default=None,
                    help="Append projections to a ledger CSV. Bare flag → "
                         "data/predictions/<today>_inplay.csv. With arg → that path.")
    args = ap.parse_args()

    paths: List[str] = []
    if args.snapshot:
        paths = [args.snapshot]
    elif args.game_id:
        p = latest_snapshot_for_game(args.game_id)
        if p is None:
            print(f"  [fail] no snapshot for game_id={args.game_id} in {LIVE_DIR}")
            return 2
        paths = [p]
    else:  # --all-live: one path per distinct game_id (latest snapshot each)
        seen = set()
        for fp in sorted(glob.glob(os.path.join(LIVE_DIR, "*.json"))):
            base = os.path.basename(fp)
            gid = base.split("_")[0]
            if gid in seen:
                continue
            seen.add(gid)
            latest = latest_snapshot_for_game(gid)
            if latest:
                paths.append(latest)
        if not paths:
            print(f"  [fail] no snapshots found in {LIVE_DIR}")
            return 2

    pregame = load_pregame_predictions(_date.today().isoformat())

    save_path: Optional[str] = None
    if args.save is not None:
        save_path = (os.path.join(PRED_DIR,
                                   f"{_date.today().isoformat()}_inplay.csv")
                     if args.save == "__default__" else args.save)

    total_written = 0
    for p in paths:
        try:
            snap = load_snapshot(p)
        except Exception as e:
            print(f"  [warn] could not load {p}: {e}")
            continue
        rows = project_snapshot(snap, pace_factor=args.pace)
        gid = snap.get("game_id", "?")
        away = snap.get("away_team", "") or ""
        home = snap.get("home_team", "") or ""
        print(f"\n  === {away} @ {home}  game_id={gid}  "
              f"period={snap.get('period')}  clock={snap.get('clock')} ===")
        print(format_stdout(rows, pregame))
        if save_path is not None:
            total_written += save_inplay_csv(save_path, snap, rows, pregame)

    if save_path is not None:
        print(f"  Wrote {total_written} in-play projection rows → {save_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
