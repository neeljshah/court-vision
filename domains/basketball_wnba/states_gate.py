"""domains.basketball_wnba.states_gate -- LANE 5 WNBA states gate (core math).

PRE-DECLARED QUESTION: does adding run_last_3min (and, separately, in_bonus)
as a SINGLE logit-additive term to the frozen ANCHORED blend (domains.
basketball_wnba.ingame_blend.blend_prob, ANCHORED_K=0.63/ANCHORED_W0=1.0)
improve checkpoint Brier on the 168-game 2026 CDN-backfill/linescores
overlap, cross-fitted md5 halves (fit h0 eval h1, and vice versa, per
checkpoint)? One coefficient per feature, no interactions, no other searches.

    p_test = sigmoid( logit(p_anchored) + coef * feature )

feature = run_last_3min (raw) or in_bonus_diff = in_bonus_home - in_bonus_away
(in {-1,0,1}). coef is a coarse deterministic 1-D grid search (same style as
ingame_blend_families._argmin_brier_1d) minimizing pooled Brier on the FIT
half only, scored on the EVAL half. coef=0 always in-grid (no-term case).

THE ANCHORED BLEND ITSELF IS NEVER REFIT OR MODIFIED -- only an ADDITIVE
candidate term on top of its frozen output is evaluated. Adoption of a
winning term is a FUTURE HUMAN-QUEUE ITEM, not automatic.

CROSS-FIT (leak-free): games split into 2 halves by md5(str(event_id)) parity
(deterministic, no RNG). Fit on h0 eval on h1 (direction A); fit on h1 eval
on h0 (direction B). Neither direction's fit ever sees its own eval rows.

HONEST FLOORS: n=168 games x 3 checkpoints; per-HALF n~84/checkpoint. Below
_MIN_N_PER_HALF the cell is INSUFFICIENT (CIs hopeless), never SHIP/REJECT.

PROVENANCE: cdn_backfill_states.parquet is VALIDATION (provenance=
cdn_backfill), joined to linescores.parquet ONLY for this pre-declared check
-- never pooled with a forward-only capture stream, per AUTONOMY_CHARTER.

This module = Row/build_rows/fit_coef/crossfit/descriptive_stats (pure
computation). See states_gate_runner.py for the parquet-reading entry point
(run_gate/write_gate/CLI) that assembles this into states_gate_validation.json.

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network; no
$/roi/edge fields; never mutates ingame_blend.py or ingame_blend_families.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate.py -q
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from domains.basketball_wnba.ingame_blend import LiveState, blend_prob as anchored_blend_prob

EDGE_CLAIMED = False

CHECKPOINTS: Tuple[str, ...] = ("end_q1", "half", "end_q3")
_CHECKPOINT_PERIOD = {"end_q1": 1, "half": 2, "end_q3": 3}
FEATURES: Tuple[str, ...] = ("run_last_3min", "in_bonus")

# Honest floor: a checkpoint-half cell below this n is reported INSUFFICIENT,
# never scored SHIP/REJECT (CIs at n<40 games are not decision-grade).
_MIN_N_PER_HALF = 40

# Coefficient grid: fixed, sorted, deterministic -- 0.0 always included so
# "no improvement over 0" is representable exactly. run_last_3min is raw
# point-margin scale (~[-15,15]); in_bonus_diff is a {-1,0,1} indicator.
_COEF_GRID_RUN: Tuple[float, ...] = tuple(round(-0.30 + 0.01 * i, 4) for i in range(61))  # -0.30..0.30
_COEF_GRID_BONUS: Tuple[float, ...] = tuple(round(-1.50 + 0.05 * i, 4) for i in range(61))  # -1.50..1.50


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _logit(p: float) -> float:
    pc = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(pc / (1.0 - pc))


def _brier(preds: Sequence[float], outcomes: Sequence[float]) -> Optional[float]:
    if not preds:
        return None
    return float(sum((p - y) ** 2 for p, y in zip(preds, outcomes)) / len(preds))


def half_of(event_id: str) -> int:
    """Deterministic md5-based half assignment: 0 or 1. No RNG, stable across
    runs and across processes (md5 of the event_id string)."""
    h = hashlib.md5(str(event_id).encode("utf-8")).hexdigest()
    return int(h[0], 16) % 2


@dataclass(frozen=True)
class Row:
    """One (checkpoint, game) sample for the states gate: frozen anchored p,
    outcome, and the two candidate feature values."""
    event_id: str
    checkpoint: str
    p_anchored: float
    outcome: float
    run_last_3min: float
    in_bonus_diff: float
    half: int


def _checkpoint_diff(ls: pd.Series, period: int) -> float:
    if period == 1:
        return float(ls["home_end_q1"]) - float(ls["away_end_q1"])
    if period == 2:
        return float(ls["home_half"]) - float(ls["away_half"])
    return float(ls["home_end_q3"]) - float(ls["away_end_q3"])


def build_rows(
    games_with_p0: pd.DataFrame,
    linescores_df: pd.DataFrame,
    states_df: pd.DataFrame,
    game_id_to_event_id: Dict[str, str],
) -> List[Row]:
    """Join CDN checkpoint states -> event_id (via game_id_to_event_id) ->
    linescores checkpoint score-diff + walk-forward p0 -> one Row per
    (game, checkpoint) with the frozen anchored p and both candidate features.
    Games/checkpoints missing any leg of the join are skipped, never faked."""
    ls_by_id = {str(r["event_id"]): r for _, r in linescores_df.iterrows()}
    p0_by_id = {str(r["event_id"]): float(r["p_home_elo"]) for _, r in games_with_p0.iterrows()}
    outcome_by_id = {str(r["event_id"]): float(r["home_win"]) for _, r in games_with_p0.iterrows()}

    states_by_game: Dict[str, Dict[str, pd.Series]] = {}
    for _, r in states_df.iterrows():
        gid = str(r["game_id"])
        states_by_game.setdefault(gid, {})[str(r["checkpoint"])] = r

    rows: List[Row] = []
    for gid, event_id in game_id_to_event_id.items():
        ls = ls_by_id.get(event_id)
        p0 = p0_by_id.get(event_id)
        outcome = outcome_by_id.get(event_id)
        if ls is None or p0 is None or outcome is None:
            continue
        cp_states = states_by_game.get(gid, {})
        for cp in CHECKPOINTS:
            st = cp_states.get(cp)
            if st is None:
                continue
            period = _CHECKPOINT_PERIOD[cp]
            score_diff = _checkpoint_diff(ls, period)
            live = LiveState(period=period, clock_s=0.0,
                              home_score=score_diff, away_score=0.0)
            p_anchored = anchored_blend_prob(p0, live)
            in_bonus_diff = float(bool(st["in_bonus_home"])) - float(bool(st["in_bonus_away"]))
            rows.append(Row(
                event_id=event_id, checkpoint=cp, p_anchored=p_anchored,
                outcome=outcome, run_last_3min=float(st["run_last_3min"]),
                in_bonus_diff=in_bonus_diff, half=half_of(event_id),
            ))
    return rows


def _feature_value(row: Row, feature: str) -> float:
    if feature == "run_last_3min":
        return row.run_last_3min
    if feature == "in_bonus":
        return row.in_bonus_diff
    raise ValueError(f"unknown feature {feature!r}")


def _predict_with_term(row: Row, feature: str, coef: float) -> float:
    z = _logit(row.p_anchored) + coef * _feature_value(row, feature)
    return _sigmoid(z)


def fit_coef(rows: Sequence[Row], feature: str) -> float:
    """Argmin pooled Brier over the fixed coef grid (first-seen tie winner,
    deterministic). rows should already be restricted to the FIT half."""
    grid = _COEF_GRID_RUN if feature == "run_last_3min" else _COEF_GRID_BONUS
    outcomes = [r.outcome for r in rows]
    best_coef, best_score = 0.0, float("inf")
    for coef in grid:
        preds = [_predict_with_term(r, feature, coef) for r in rows]
        b = _brier(preds, outcomes)
        if b is not None and b < best_score:
            best_score, best_coef = b, coef
    return float(best_coef)


@dataclass
class CheckpointCrossfitResult:
    checkpoint: str
    feature: str
    n_h0: int
    n_h1: int
    coef_fit_on_h0: float
    coef_fit_on_h1: float
    brier_anchored_h1: Optional[float]      # baseline (no term), eval on h1
    brier_with_term_h1: Optional[float]     # h0-fit coef, eval on h1
    brier_anchored_h0: Optional[float]      # baseline (no term), eval on h0
    brier_with_term_h0: Optional[float]     # h1-fit coef, eval on h0
    verdict: str  # IMPROVED_BOTH_DIRECTIONS / MIXED / NO_IMPROVEMENT / INSUFFICIENT

    def to_dict(self) -> Dict[str, object]:
        return {
            "checkpoint": self.checkpoint, "feature": self.feature,
            "n_h0": self.n_h0, "n_h1": self.n_h1,
            "coef_fit_on_h0": self.coef_fit_on_h0, "coef_fit_on_h1": self.coef_fit_on_h1,
            "brier_anchored_eval_h1": self.brier_anchored_h1,
            "brier_with_term_eval_h1": self.brier_with_term_h1,
            "brier_anchored_eval_h0": self.brier_anchored_h0,
            "brier_with_term_eval_h0": self.brier_with_term_h0,
            "verdict": self.verdict,
        }


def crossfit_checkpoint_feature(
    rows: Sequence[Row], checkpoint: str, feature: str,
    min_n_per_half: int = _MIN_N_PER_HALF,
) -> CheckpointCrossfitResult:
    """Fit coef on h0, eval on h1; fit coef on h1, eval on h0. Neither
    direction's fit ever sees its own eval rows (leak-free by construction)."""
    cp_rows = [r for r in rows if r.checkpoint == checkpoint]
    h0 = [r for r in cp_rows if r.half == 0]
    h1 = [r for r in cp_rows if r.half == 1]

    if len(h0) < min_n_per_half or len(h1) < min_n_per_half:
        return CheckpointCrossfitResult(
            checkpoint=checkpoint, feature=feature, n_h0=len(h0), n_h1=len(h1),
            coef_fit_on_h0=0.0, coef_fit_on_h1=0.0,
            brier_anchored_h1=None, brier_with_term_h1=None,
            brier_anchored_h0=None, brier_with_term_h0=None,
            verdict="INSUFFICIENT",
        )

    coef_h0 = fit_coef(h0, feature)
    coef_h1 = fit_coef(h1, feature)

    brier_anchored_h1 = _brier([r.p_anchored for r in h1], [r.outcome for r in h1])
    brier_with_term_h1 = _brier([_predict_with_term(r, feature, coef_h0) for r in h1],
                                 [r.outcome for r in h1])
    brier_anchored_h0 = _brier([r.p_anchored for r in h0], [r.outcome for r in h0])
    brier_with_term_h0 = _brier([_predict_with_term(r, feature, coef_h1) for r in h0],
                                 [r.outcome for r in h0])

    improved_dir_a = brier_with_term_h1 is not None and brier_anchored_h1 is not None \
        and brier_with_term_h1 < brier_anchored_h1
    improved_dir_b = brier_with_term_h0 is not None and brier_anchored_h0 is not None \
        and brier_with_term_h0 < brier_anchored_h0

    if improved_dir_a and improved_dir_b:
        verdict = "IMPROVED_BOTH_DIRECTIONS"
    elif improved_dir_a or improved_dir_b:
        verdict = "MIXED"
    else:
        verdict = "NO_IMPROVEMENT"

    return CheckpointCrossfitResult(
        checkpoint=checkpoint, feature=feature, n_h0=len(h0), n_h1=len(h1),
        coef_fit_on_h0=coef_h0, coef_fit_on_h1=coef_h1,
        brier_anchored_h1=brier_anchored_h1, brier_with_term_h1=brier_with_term_h1,
        brier_anchored_h0=brier_anchored_h0, brier_with_term_h0=brier_with_term_h0,
        verdict=verdict,
    )


def descriptive_stats(rows: Sequence[Row]) -> Dict[str, object]:
    """Context stats: how often a team is in the bonus, run-distribution --
    reported regardless of gate verdict (answers 'does this carry signal at
    all', per LANE 5 step 3)."""
    out: Dict[str, object] = {}
    for cp in CHECKPOINTS:
        cp_rows = [r for r in rows if r.checkpoint == cp]
        if not cp_rows:
            out[cp] = {"n": 0}
            continue
        n = len(cp_rows)
        bonus_either = sum(1 for r in cp_rows if r.in_bonus_diff != 0.0) / n
        bonus_home = sum(1 for r in cp_rows if r.in_bonus_diff > 0.0) / n
        runs = sorted(r.run_last_3min for r in cp_rows)
        mean_run = sum(runs) / n
        mid = n // 2
        median_run = runs[mid] if n % 2 == 1 else (runs[mid - 1] + runs[mid]) / 2.0
        out[cp] = {
            "n": n,
            "frac_either_team_in_bonus": round(bonus_either, 4),
            "frac_home_in_bonus_away_not": round(bonus_home, 4),
            "run_last_3min_mean": round(mean_run, 4),
            "run_last_3min_median": round(median_run, 4),
            "run_last_3min_min": round(runs[0], 4),
            "run_last_3min_max": round(runs[-1], 4),
        }
    return out


__all__ = [
    "CHECKPOINTS", "FEATURES", "_MIN_N_PER_HALF", "Row", "CheckpointCrossfitResult",
    "half_of", "build_rows", "fit_coef", "crossfit_checkpoint_feature",
    "descriptive_stats",
]
