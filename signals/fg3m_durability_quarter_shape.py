"""Signal: fg3m_durability_quarter_shape — durability + quarter-shape atlas helps FG3M.

**Hypothesis**
Made-3 volume is a *minutes x energy x rotation-shape* stat: a player's
durability/load profile (age, minutes-per-game mean/std, high-minutes-game rate,
rolling DNP rate) plus their quarter-shape fade together predict how many 3s a
player actually attempts and makes, beyond what the prod usage/TS%/form features
encode.  Fresh, high-minutes, low-fade players take and make more 3s; aging,
fade-prone, load-managed players regress on a per-game basis the rolling form
features lag behind.

**Evidence (selective ablation, 2026-05-31)**
`scripts/loop/eval_atlas_by_section.py` (walk-forward, all-folds, added on top of
the FULL 129-feature prod prop matrix, n=101,765, device=cuda) found BOTH atlas
sections that materialize into the prop join improve FG3M and BEAT the bulk-add:

    FG3M quarter_shape_fatigue  delta_MAE = -0.0051  (2/3 folds neg, beats_bulk)
    FG3M durability_load        delta_MAE = -0.0036  (2/3 folds neg, beats_bulk)
    (bulk-null all 49 atlas feats on FG3M = -0.0030)

Each single section beats wiring all 49 at once, confirming the selective path.
FG3M was also the ONLY stat the bulk null helped, so it is the natural pregame
ship target.  Result file: `.planning/loop/atlas_by_section.json`.

**Atlas consumed (reinforcement loop)**
`player:<id>` / sections ``durability_load`` + ``quarter_shape_fatigue`` — read
leak-safe via ``self.read_atlas(..., ctx.decision_time)``.  Graceful neutral
(None / neutral fills) when the store is empty or the player has no record.

**Emits**
Dict signal with four sub-features (leak-safe season-level priors):

  * ``minutes_per_game_mean`` — typical minutes (3PA opportunity floor). 0 absent.
  * ``high_minutes_game_rate`` — share of games with heavy load (volume proxy).
  * ``age_years``             — age (3P% / volume aging curve). 0 absent.
  * ``q4_vs_early_ratio``     — Q4 vs early energy (late-game 3PA willingness).
                                Neutral 1.0 when absent.

**Gate expectations**
  - Expected verdict: SHIP for FG3M (only stat the bulk null helped; both
    selective sections beat bulk on FG3M).
  - target = "fg3m", scope = "pregame".
  - Walk-forward: 2/3 folds improved at the section level; the gate's strict
    all-folds bar may push this to VARIANCE_ONLY or a requeue — report honestly.
  - Ablation: judged as a marginal add to the FULL matrix (gate contract).
  - Do NOT extend the target to PTS/REB — those regress with these sections.

**DEFER note**
DEFER-1: durability_load covers ~768 players, quarter_shape_fatigue ~497
(CV/box-derived). Uncovered players return neutral fills — still valid training
rows; the gate evaluates whether the coverage is sufficient for a FG3M SHIP.
DEFER-2: only 2/3 folds were negative at the section level, so this is a weaker
candidate than blk_quarter_shape_fatigue (3/3). If the gate's all-folds bar is
strict, expect a requeue rather than an immediate SHIP.
"""
from __future__ import annotations

import math
from typing import List, Optional

from src.loop.signal import (
    AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# Neutral fills when an atlas record/leaf is absent (leak-safe no-op).
_NEUTRAL = {
    "minutes_per_game_mean": 0.0,
    "high_minutes_game_rate": 0.0,
    "age_years": 0.0,
    "q4_vs_early_ratio": 1.0,
}


def _num(v: object, default: float) -> float:
    """Coerce an atlas leaf to a finite float, falling back to ``default``."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


class Fg3mDurabilityQuarterShape(Signal):
    """Durability + quarter-shape atlas as a leak-safe FG3M pregame feature.

    Reads the ``durability_load`` and ``quarter_shape_fatigue`` atlas sections for
    the subject player (leak-safe, as-of ctx.decision_time) and emits four
    load/energy sub-features the section ablation showed each beat bulk-adding all
    49 atlas features on FG3M.  Returns None when player_id is missing; absent
    atlas leaves degrade to neutral fills (never future information).
    """

    name: str = "fg3m_durability_quarter_shape"
    target: str = "fg3m"
    scope: str = "pregame"
    reads_atlas: List[str] = ["durability_load", "quarter_shape_fatigue"]
    emits: List[str] = [
        "minutes_per_game_mean", "high_minutes_game_rate",
        "age_years", "q4_vs_early_ratio",
    ]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe durability + quarter-shape features for one FG3M decision.

        Args:
            ctx: decision context; player_id must be set.

        Returns:
            Dict of the four emitted sub-features, or None when player_id is
            missing.  All reads are as-of ctx.decision_time (store-enforced); a
            missing record yields neutral fills.
        """
        if ctx.player_id is None:
            return None

        dur = self.read_atlas(
            f"player:{ctx.player_id}", "durability_load", ctx.decision_time)
        qsf = self.read_atlas(
            f"player:{ctx.player_id}", "quarter_shape_fatigue", ctx.decision_time)
        dur = dur if isinstance(dur, dict) else {}
        qsf = qsf if isinstance(qsf, dict) else {}

        return {
            "minutes_per_game_mean": _num(
                dur.get("minutes_per_game_mean"),
                _NEUTRAL["minutes_per_game_mean"]),
            "high_minutes_game_rate": _num(
                dur.get("high_minutes_game_rate"),
                _NEUTRAL["high_minutes_game_rate"]),
            "age_years": _num(dur.get("age_years"), _NEUTRAL["age_years"]),
            "q4_vs_early_ratio": _num(
                qsf.get("q4_vs_early_ratio"), _NEUTRAL["q4_vs_early_ratio"]),
        }

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Made-3 volume is a minutes x energy x rotation-shape stat: "
                "durability/load (minutes mean, high-minutes rate, age) plus "
                "quarter-shape fade predict FG3M beyond prod usage/TS%/form."
            ),
            rationale=(
                "Selective per-section ablation (eval_atlas_by_section.py, "
                "walk-forward, FULL 129-feat matrix, n=101,765): both prop-joinable "
                "sections improve FG3M and BEAT the 49-feature bulk-add "
                "(quarter_shape_fatigue -0.0051, durability_load -0.0036 vs bulk "
                "-0.0030), each on 2/3 folds. FG3M is the only stat the bulk null "
                "helped, so it is the pregame ship target. The same sections HURT "
                "PTS/REB, hence wired for FG3M only. See atlas_by_section.json."
            ),
            source="intel_scanner",
            atlas_fields=["durability_load", "quarter_shape_fatigue"],
            expected_verdict=Verdict.SHIP,
            priority="P1",
        )
