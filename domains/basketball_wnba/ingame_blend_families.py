"""domains.basketball_wnba.ingame_blend_families -- pre-declared in-game blend
candidate family fitting + cross-corpus selection (LANE 4 step 2-3).

Wave 2's honest check (ingame_blend_check.json v1) showed the FIXED-constant
blend (ingame_blend.blend_prob_fixed_legacy, K_SCORE=3.0, never fit) LOSES to a
naive score-diff sigmoid at half (.2316 vs .1915) and end_q3 (.2318 vs .1606)
on 150 2026 games. This module settles the family choice: 4 PRE-DECLARED
candidates (no open-ended search), each fit ONLY on 2024, validated on 2025,
final OOS on 2026. A family is adopted only if it beats every other family on
BOTH 2025 AND 2026 independently -- ties/inconsistency are recorded honestly.

CANDIDATE FAMILIES (k / w(t) params are the ONLY fit knobs):
  (a) fixed       -- ingame_blend.blend_prob_fixed_legacy AS-IS (K_SCORE=3.0,
                     hardcoded, not fit -- the wave-2 incumbent baseline).
  (b) naive       -- p = sigmoid(k * score_diff). k fit on 2024 (grid search
                     minimizing pooled Brier over all 3 checkpoints). No
                     prior, no time term -- replaces wave-2's fixed-guess
                     _K_NAIVE=0.06 with a properly fit k.
  (c) time_scaled -- p = sigmoid(k * score_diff / sqrt(minutes_remaining)),
                     floor-clamped (_MIN_REMAIN_FLOOR) so it never diverges
                     near the buzzer. k fit the same way as (b).
  (d) anchored    -- p = sigmoid(logit(p0) * w0*(1-t) + k * score_diff /
                     sqrt(minutes_remaining)). w0 in [0,1] fit jointly with k
                     via a 2-D grid search on 2024. w0=1 recovers a linear
                     prior-decay (same SHAPE as the legacy w_prior(t)); w0=0
                     collapses to (c).

FIT METHOD (leak-free by construction): all fittable params are grid-searched
using ONLY 2024 games' (p0, score_diff, minutes_remaining, outcome) tuples,
pooled across the 3 checkpoints, with walk-forward Elo p0 computed the SAME
way run_ingame_blend_check.py does (all games strictly before the given game,
replayed across the FULL 2024-2026 corpus so later seasons' ratings build on
2024 history -- standard walk-forward, does NOT leak future OUTCOMES into the
2024 fit: p0 for a 2024 game never depends on any later game). Only the FIT
GRID SEARCH is restricted to 2024 ROWS; the p0 feature column is leak-free
per-row regardless.

Determinism: grid search over a fixed, sorted parameter list -- no randomness.
No network at import time; no src.*/kernel.* imports (F5). EDGE_CLAIMED = False.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_blend_families.py -q
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from domains.basketball_wnba.ingame_blend import (
    REG_SEC,
    LiveState,
    blend_prob_fixed_legacy as fixed_blend_prob,
    fraction_elapsed as _fraction_elapsed,
    sec_remaining as _sec_remaining,
)
from domains.basketball_wnba.ratings import walk_forward_elo

EDGE_CLAIMED = False

FAMILY_NAMES: Tuple[str, ...] = ("fixed", "naive", "time_scaled", "anchored")

# Checkpoint name -> (period, clock_s) at that CUMULATIVE moment (regulation).
# Same convention as run_ingame_blend_check._CHECKPOINTS.
CHECKPOINTS: Dict[str, Tuple[int, float]] = {
    "end_q1": (1, 0.0), "half": (2, 0.0), "end_q3": (3, 0.0),
}

# Floor on minutes_remaining inside the 1/sqrt(minutes_remaining) term, so it
# never diverges as minutes_remaining -> 0. 25s floor (same floor ingame_blend
# uses inside its own ramp term) expressed in minutes.
_MIN_REMAIN_FLOOR: float = 25.0 / 60.0

# Grid search ranges -- fixed, pre-declared, deterministic (sorted ascending).
# Range chosen wide enough that the 2024 train-fit optimum for every family
# falls strictly inside it (verified: naive k*=0.15, time_scaled k*=0.67,
# anchored k*=0.63/w0*=1.0 -- none clip the 0.01..1.20 boundary).
_K_GRID: Tuple[float, ...] = tuple(round(0.01 + 0.01 * i, 4) for i in range(120))  # 0.01..1.20
_W0_GRID: Tuple[float, ...] = tuple(round(0.1 * i, 2) for i in range(11))  # 0.0..1.0


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _logit(p: float) -> float:
    pc = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(pc / (1.0 - pc))


def minutes_remaining(period: int, clock_s: float) -> float:
    """Minutes left in regulation/OT, floor-clamped. Thin unit-conversion wrapper
    around ingame_blend.sec_remaining (seconds -> minutes), NOT a redefinition."""
    return max(_sec_remaining(period, clock_s) / 60.0, _MIN_REMAIN_FLOOR)


def fraction_elapsed(period: int, clock_s: float) -> float:
    """Reuse ingame_blend.fraction_elapsed verbatim -- single source of truth."""
    return _fraction_elapsed(period, clock_s)


@dataclass(frozen=True)
class Row:
    """One (checkpoint, game) sample: leak-free p0 + realized score state +
    outcome. Pure data, no I/O."""
    p0: float
    score_diff: float
    period: int
    clock_s: float
    outcome: float


def _checkpoint_diff(ls: pd.Series, period: int) -> float:
    """Cumulative (home - away) score at *period*'s checkpoint (ingest_linescores
    schema). Single source of truth for the period -> column-pair mapping."""
    if period == 1:
        return float(ls["home_end_q1"]) - float(ls["away_end_q1"])
    if period == 2:
        return float(ls["home_half"]) - float(ls["away_half"])
    return float(ls["home_end_q3"]) - float(ls["away_end_q3"])


def _joined_rows_by_checkpoint(
    games_with_p0: pd.DataFrame, linescores_df: pd.DataFrame
) -> Dict[str, List[Row]]:
    """Join walk-forward p0 with per-checkpoint cumulative scores on event_id
    (unmatched games skipped, never faked). checkpoint-name -> list[Row];
    shared by build_rows (pooled) and score_family_by_checkpoint (per-cp)."""
    ls_by_id = {str(r["event_id"]): r for _, r in linescores_df.iterrows()}
    out: Dict[str, List[Row]] = {cp: [] for cp in CHECKPOINTS}
    for _, g in games_with_p0.iterrows():
        ls = ls_by_id.get(str(g["event_id"]))
        if ls is None:
            continue
        p0, outcome = float(g["p_home_elo"]), float(g["home_win"])
        for cp, (period, clock_s) in CHECKPOINTS.items():
            out[cp].append(Row(p0=p0, score_diff=_checkpoint_diff(ls, period),
                                period=period, clock_s=clock_s, outcome=outcome))
    return out


def build_rows(games_with_p0: pd.DataFrame, linescores_df: pd.DataFrame) -> List[Row]:
    """One Row per (game, checkpoint), pooled across all 3 checkpoints -- the
    fit objective's training set."""
    by_cp = _joined_rows_by_checkpoint(games_with_p0, linescores_df)
    rows: List[Row] = []
    for cp in CHECKPOINTS:
        rows.extend(by_cp[cp])
    return rows


def brier(preds: Sequence[float], outcomes: Sequence[float]) -> Optional[float]:
    if not preds:
        return None
    return float(sum((p - y) ** 2 for p, y in zip(preds, outcomes)) / len(preds))


# ---------------------------------------------------------------------------
# Family predict functions (pure; take fitted params explicitly)
# ---------------------------------------------------------------------------


def predict_fixed(row: Row) -> float:
    """Family (a): the legacy hardcoded blend (blend_prob_fixed_legacy),
    unchanged -- the wave-2 incumbent, kept as a comparison baseline."""
    # blend_prob_fixed_legacy only ever consumes (home_score - away_score), so
    # a 2-score pair reconstructed as (home=diff, away=0) yields the same diff.
    state = LiveState(period=row.period, clock_s=row.clock_s,
                       home_score=row.score_diff, away_score=0.0)
    return fixed_blend_prob(row.p0, state)


def predict_naive(row: Row, k: float) -> float:
    """Family (b): p = sigmoid(k * score_diff). No prior, no time term."""
    return _sigmoid(k * row.score_diff)


def predict_time_scaled(row: Row, k: float) -> float:
    """Family (c): p = sigmoid(k * score_diff / sqrt(minutes_remaining))."""
    mr = minutes_remaining(row.period, row.clock_s)
    return _sigmoid(k * row.score_diff / math.sqrt(mr))


def predict_anchored(row: Row, k: float, w0: float) -> float:
    """Family (d): p = sigmoid(logit(p0)*w0*(1-t) + k*score_diff/sqrt(minutes_remaining))."""
    t = fraction_elapsed(row.period, row.clock_s)
    mr = minutes_remaining(row.period, row.clock_s)
    w = w0 * (1.0 - t)
    z = _logit(row.p0) * w + k * row.score_diff / math.sqrt(mr)
    return _sigmoid(z)


# ---------------------------------------------------------------------------
# Fitting (grid search on 2024 rows only, deterministic)
# ---------------------------------------------------------------------------


def _argmin_brier_1d(train_rows: Sequence[Row], predict_fn, k_grid: Sequence[float]) -> float:
    """Shared 1-D grid-search core: argmin pooled Brier over k_grid (fixed,
    sorted ascending; first-seen tie winner for determinism)."""
    outcomes = [r.outcome for r in train_rows]
    best_k, best_score = k_grid[0], float("inf")
    for k in k_grid:
        b = brier([predict_fn(r, k) for r in train_rows], outcomes)
        if b is not None and b < best_score:
            best_score, best_k = b, k
    return float(best_k)


def fit_naive_k(train_rows: Sequence[Row], k_grid: Sequence[float] = _K_GRID) -> float:
    return _argmin_brier_1d(train_rows, predict_naive, k_grid)


def fit_time_scaled_k(train_rows: Sequence[Row], k_grid: Sequence[float] = _K_GRID) -> float:
    return _argmin_brier_1d(train_rows, predict_time_scaled, k_grid)


def fit_anchored_params(
    train_rows: Sequence[Row],
    k_grid: Sequence[float] = _K_GRID,
    w0_grid: Sequence[float] = _W0_GRID,
) -> Tuple[float, float]:
    """argmin pooled Brier over the (k, w0) grid, deterministic 2-D scan."""
    outcomes = [r.outcome for r in train_rows]
    best_k, best_w0, best_score = k_grid[0], w0_grid[0], float("inf")
    for k in k_grid:
        for w0 in w0_grid:
            b = brier([predict_anchored(r, k, w0) for r in train_rows], outcomes)
            if b is not None and b < best_score:
                best_score, best_k, best_w0 = b, k, w0
    return float(best_k), float(best_w0)


@dataclass(frozen=True)
class FittedFamilies:
    """Params fit ONCE on 2024; frozen and reused unchanged for 2025/2026."""
    naive_k: float
    time_scaled_k: float
    anchored_k: float
    anchored_w0: float


def fit_all_families(train_rows: Sequence[Row]) -> FittedFamilies:
    """Fit (b), (c), (d) on train_rows (2024 only). (a) has no fittable params."""
    naive_k = fit_naive_k(train_rows)
    ts_k = fit_time_scaled_k(train_rows)
    a_k, a_w0 = fit_anchored_params(train_rows)
    return FittedFamilies(naive_k=naive_k, time_scaled_k=ts_k,
                           anchored_k=a_k, anchored_w0=a_w0)


def predict_family(name: str, row: Row, fitted: FittedFamilies) -> float:
    if name == "fixed":
        return predict_fixed(row)
    if name == "naive":
        return predict_naive(row, fitted.naive_k)
    if name == "time_scaled":
        return predict_time_scaled(row, fitted.time_scaled_k)
    if name == "anchored":
        return predict_anchored(row, fitted.anchored_k, fitted.anchored_w0)
    raise ValueError(f"unknown family {name!r}")


def score_family_by_checkpoint(
    name: str,
    games_with_p0: pd.DataFrame,
    linescores_df: pd.DataFrame,
    fitted: FittedFamilies,
) -> Dict[str, Dict[str, object]]:
    """Per-checkpoint Brier for one family over one corpus (games_with_p0 already
    restricted to the target season/split by the caller)."""
    by_cp = _joined_rows_by_checkpoint(games_with_p0, linescores_df)
    result: Dict[str, Dict[str, object]] = {}
    for cp, rows in by_cp.items():
        preds = [predict_family(name, r, fitted) for r in rows]
        outcomes = [r.outcome for r in rows]
        result[cp] = {"n": len(preds), "brier": brier(preds, outcomes)}
    return result


def build_corpus_with_p0(full_games_df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Leak-free walk-forward p0 over the FULL games corpus (ratings accumulate
    across seasons), filtered to *season* rows: p0 for a season-S game depends
    only on games strictly before it (any season), never on later outcomes."""
    wf = walk_forward_elo(full_games_df.copy())
    return wf[wf["season"].astype(str) == str(season)].reset_index(drop=True)


__all__ = [
    "FAMILY_NAMES", "CHECKPOINTS", "Row", "FittedFamilies",
    "build_rows", "brier", "minutes_remaining", "fraction_elapsed",
    "predict_fixed", "predict_naive", "predict_time_scaled", "predict_anchored",
    "fit_naive_k", "fit_time_scaled_k", "fit_anchored_params", "fit_all_families",
    "predict_family", "score_family_by_checkpoint", "build_corpus_with_p0",
]
