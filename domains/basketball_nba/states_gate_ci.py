"""domains.basketball_nba.states_gate_ci -- game-clustered bootstrap CI on the
NBA states-gate cross-fit deltas, PORTED from domains.basketball_wnba.states_gate_ci
(direct-review advisory hardening).

WHY: crossfit_checkpoint_feature (states_gate.py) reports a point-estimate
Brier delta per direction ("with-term beat anchored, yes/no") but no
uncertainty. At small per-half n a point comparison can flip on noise. This
module adds a GAME-CLUSTERED bootstrap CI95 on each direction's mean per-row
Brier delta (delta = brier_with_term - brier_anchored; delta<0 = improvement),
resampling whole games (not rows) so a game's checkpoint rows never split
across resample draws -- same clustering discipline as
scripts/platformkit/ingame/ingame_tail_scan.py's _band_stats bootstrap
(seeded random.Random, sorted array, 2.5/97.5 percentile cut). That function
is fused to its own tick/band row-shape and not cleanly importable for this
game-row shape, so the pattern is reimplemented locally, not imported.

SURVIVAL RULE (v2, stricter than the v1 point-comparison verdict): a feature
is SUPPORTED at a checkpoint only if BOTH directions show LOWER Brier with
the term AND BOTH directions' delta CI95 excludes 0. One direction passing
and the other not (or a CI straddling 0) is NOT supported -- reported as
CI_INCLUDES_ZERO / MIXED / INSUFFICIENT, never silently upgraded.

INVARIANTS: <=300 LOC; ASCII only; stdlib only (+ states_gate.py's Row type);
no network; no $/roi/edge fields; never mutates states_gate.py's math, only
reads its Row objects and coefficients; deterministic given a seed.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate_ci.py -q
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from domains.basketball_nba.states_gate import CheckpointCrossfitResult, Row, _predict_with_term

EDGE_CLAIMED = False

BOOTSTRAP_ITERS: int = 2000
SEED: int = 13
# Below this many distinct games in an eval half, a CI is not decision-grade;
# reported as None rather than a spuriously narrow interval.
_MIN_GAMES_FOR_CI: int = 5


def _mean_delta(rows: Sequence[Row], feature: str, coef: float) -> float:
    n = len(rows)
    if n == 0:
        return 0.0
    total = 0.0
    for r in rows:
        p_term = _predict_with_term(r, feature, coef)
        total += (p_term - r.outcome) ** 2 - (r.p_anchored - r.outcome) ** 2
    return total / n


def bootstrap_delta_ci(
    eval_rows: Sequence[Row], feature: str, coef: float,
    iters: int = BOOTSTRAP_ITERS, seed: int = SEED,
) -> Optional[List[float]]:
    """Game-clustered bootstrap CI95 on the mean per-row Brier delta
    (with-term minus anchored) over eval_rows, all from ONE eval half.
    Resamples whole games with replacement (seeded, deterministic). Returns
    None if fewer than _MIN_GAMES_FOR_CI distinct games are present."""
    by_game: Dict[str, List[Row]] = {}
    for r in eval_rows:
        by_game.setdefault(r.event_id, []).append(r)
    games = sorted(by_game)
    n_g = len(games)
    if n_g < _MIN_GAMES_FOR_CI:
        return None

    rng = random.Random(seed)
    deltas: List[float] = []
    for _ in range(iters):
        sample: List[Row] = []
        for _ in range(n_g):
            sample.extend(by_game[games[rng.randrange(n_g)]])
        deltas.append(_mean_delta(sample, feature, coef))
    deltas.sort()
    lo_i = int(0.025 * iters)
    hi_i = min(int(0.975 * iters), iters - 1)
    return [round(deltas[lo_i], 6), round(deltas[hi_i], 6)]


def _ci_excludes_zero_below(ci: Optional[List[float]]) -> bool:
    """True iff the CI is entirely < 0 (a real improvement, not noise)."""
    return ci is not None and ci[1] < 0.0


@dataclass
class CrossfitCiResult:
    """v2 wrapper around a CheckpointCrossfitResult: adds per-direction CIs
    and the stricter SUPPORTED/NOT-SUPPORTED survival verdict."""
    base: CheckpointCrossfitResult
    delta_ci95_h1: Optional[List[float]]  # direction A: h0-fit coef, eval h1
    delta_ci95_h0: Optional[List[float]]  # direction B: h1-fit coef, eval h0
    ci_excludes_zero_h1: bool
    ci_excludes_zero_h0: bool
    verdict_v2: str  # SUPPORTED / CI_INCLUDES_ZERO / MIXED / NO_IMPROVEMENT / INSUFFICIENT

    def to_dict(self) -> Dict[str, object]:
        d = self.base.to_dict()
        d["delta_ci95_eval_h1"] = self.delta_ci95_h1
        d["delta_ci95_eval_h0"] = self.delta_ci95_h0
        d["ci_excludes_zero_h1"] = self.ci_excludes_zero_h1
        d["ci_excludes_zero_h0"] = self.ci_excludes_zero_h0
        d["verdict_v2"] = self.verdict_v2
        return d


def crossfit_with_ci(
    rows: Sequence[Row], checkpoint: str, feature: str,
    base_result: CheckpointCrossfitResult,
    iters: int = BOOTSTRAP_ITERS, seed: int = SEED,
) -> CrossfitCiResult:
    """Add bootstrap CIs to an already-computed CheckpointCrossfitResult and
    apply the v2 survival rule. Recomputes eval-half rows from `rows` +
    `checkpoint` (never refits coefficients -- uses base_result's frozen
    coef_fit_on_h0/coef_fit_on_h1, matching what the base result scored)."""
    if base_result.verdict == "INSUFFICIENT":
        return CrossfitCiResult(
            base=base_result, delta_ci95_h1=None, delta_ci95_h0=None,
            ci_excludes_zero_h1=False, ci_excludes_zero_h0=False,
            verdict_v2="INSUFFICIENT",
        )

    cp_rows = [r for r in rows if r.checkpoint == checkpoint]
    h0 = [r for r in cp_rows if r.half == 0]
    h1 = [r for r in cp_rows if r.half == 1]

    ci_h1 = bootstrap_delta_ci(h1, feature, base_result.coef_fit_on_h0, iters=iters, seed=seed)
    ci_h0 = bootstrap_delta_ci(h0, feature, base_result.coef_fit_on_h1, iters=iters, seed=seed)
    excl_h1 = _ci_excludes_zero_below(ci_h1)
    excl_h0 = _ci_excludes_zero_below(ci_h0)

    lower_both = base_result.verdict == "LOWER_BRIER_BOTH_DIRECTIONS"
    if lower_both and excl_h1 and excl_h0:
        verdict_v2 = "SUPPORTED"
    elif lower_both and (excl_h1 or excl_h0):
        verdict_v2 = "CI_INCLUDES_ZERO"
    elif base_result.verdict == "MIXED":
        verdict_v2 = "MIXED"
    else:
        verdict_v2 = "NO_IMPROVEMENT"

    return CrossfitCiResult(
        base=base_result, delta_ci95_h1=ci_h1, delta_ci95_h0=ci_h0,
        ci_excludes_zero_h1=excl_h1, ci_excludes_zero_h0=excl_h0,
        verdict_v2=verdict_v2,
    )


__all__ = [
    "BOOTSTRAP_ITERS", "SEED", "_MIN_GAMES_FOR_CI", "CrossfitCiResult",
    "bootstrap_delta_ci", "crossfit_with_ci",
]
