"""Signal: blk_quarter_shape_fatigue — quarter-shape/fatigue atlas helps BLK pregame.

**Hypothesis**
A player's per-quarter shape + fatigue profile (how their minutes, scoring and
rebounding decay across Q1->Q4, their back-to-back decay ratio, and their
late-game fade) carries leak-safe information about expected BLOCK production
that the production prop matrix's usage/TS%/form features do NOT already encode.
Block rate is heavily a *minutes-distribution-and-energy* stat: rim protectors
who hold their Q4 minutes and resist b2b decay block more; players whose
quarter-shape collapses late block fewer.  The atlas `quarter_shape_fatigue`
section encodes exactly this rotation/energy shape.

**Evidence (selective ablation, 2026-05-31)**
`scripts/loop/eval_atlas_by_section.py` (walk-forward, all-folds, added on top of
the FULL 129-feature prod prop matrix, n=101,765, device=cuda) found
`quarter_shape_fatigue` is the **only section that improves BLK on all 3 folds**:

    BLK  quarter_shape_fatigue  delta_MAE = -0.0064  (3/3 folds neg, all_improve)

This is the single strict-gate pregame winner across all (stat, section) pairs.
By contrast the SAME section HURTS PTS (+0.243) and REB (+0.066), which is why it
must be wired SELECTIVELY for BLK only and never bulk-added.  Result file:
`.planning/loop/atlas_by_section.json`.

**Atlas consumed (reinforcement loop)**
`player:<id>` / section ``quarter_shape_fatigue`` — read leak-safe via
``self.read_atlas(..., ctx.decision_time)`` (the store returns only records
stamped <= decision_time).  Graceful neutral (None) when the store is empty or
the player has no quarter-shape record (CV-coverage-bound; ~497 players today).

**Emits**
Dict signal with three sub-features (all leak-safe season-level priors):

  * ``q4_vs_early_ratio`` — Q4 production vs early-quarter average (energy/late
    fade; lower = more fade = fewer late blocks).  Neutral 1.0 when absent.
  * ``b2b_decay_ratio``   — back-to-back decay multiplier (1.0 = no decay; <1 =
    suppressed on the 2nd leg).  Neutral 1.0 when absent.
  * ``q4_min``            — typical Q4 minutes (rim-protector floor-time proxy).
    Neutral 0.0 when absent.

**Gate expectations**
  - Expected verdict: SHIP for BLK (only stat with a 3/3-fold negative delta).
  - target = "blk", scope = "pregame".
  - Walk-forward: expected all-folds improve (replicates the section ablation).
  - NULL-SHUFFLE: the directional Q4-fade -> fewer-blocks link should clear null.
  - Ablation: judged as a marginal add to the FULL matrix (the gate's contract),
    exactly as the section ablation already measured.
  - This signal is DELIBERATELY narrow (BLK only). Do NOT extend its target list
    to PTS/REB — those regress with this section (PTS +0.24, REB +0.07).

**DEFER note**
DEFER-1: `quarter_shape_fatigue` covers ~497 players (CV/box-derived). Uncovered
players return None (neutral) — still valid training rows; the gate evaluates
whether this coverage is sufficient for a SHIP on BLK.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from src.loop.signal import (
    AsOfContext, Hypothesis, Signal, SignalValue, Verdict,
)

# Neutral fill values when the atlas record is absent (leak-safe no-op).
_NEUTRAL = {"q4_vs_early_ratio": 1.0, "b2b_decay_ratio": 1.0, "q4_min": 0.0}


def _num(v: object, default: float) -> float:
    """Coerce an atlas leaf to a finite float, falling back to ``default``."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


class BlkQuarterShapeFatigue(Signal):
    """Quarter-shape/fatigue atlas section as a leak-safe BLK pregame feature.

    Reads the ``quarter_shape_fatigue`` atlas section for the subject player
    (leak-safe, as-of ctx.decision_time) and emits three energy/rotation-shape
    sub-features that the section ablation showed improve BLK on all 3 folds.
    Returns None (neutral) when player_id is missing or no record predates the
    decision — those rows fall back to the production matrix unchanged.
    """

    name: str = "blk_quarter_shape_fatigue"
    target: str = "blk"
    scope: str = "pregame"
    reads_atlas: List[str] = ["quarter_shape_fatigue"]
    emits: List[str] = ["q4_vs_early_ratio", "b2b_decay_ratio", "q4_min"]

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute leak-safe quarter-shape/fatigue features for one BLK decision.

        Args:
            ctx: decision context; player_id must be set.

        Returns:
            Dict of the three emitted sub-features, or None when player_id is
            missing.  Absent atlas leaves degrade to neutral values, never future
            information (the store enforces as_of <= ctx.decision_time).
        """
        if ctx.player_id is None:
            return None

        atlas = self.read_atlas(
            f"player:{ctx.player_id}", "quarter_shape_fatigue", ctx.decision_time
        )
        if not isinstance(atlas, dict):
            # Neutral: still a valid training row, no leak, no signal.
            return dict(_NEUTRAL)

        return {
            "q4_vs_early_ratio": _num(
                atlas.get("q4_vs_early_ratio"), _NEUTRAL["q4_vs_early_ratio"]),
            "b2b_decay_ratio": _num(
                atlas.get("b2b_decay_ratio"), _NEUTRAL["b2b_decay_ratio"]),
            "q4_min": _num(atlas.get("q4_min"), _NEUTRAL["q4_min"]),
        }

    def hypothesis(self) -> Hypothesis:
        """Return the testable basketball hypothesis for this signal."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's quarter-shape + fatigue profile (Q4-vs-early energy, "
                "b2b decay, Q4 minutes floor) predicts BLOCK production beyond the "
                "prod usage/TS%/form features. Rim protectors who hold late minutes "
                "and resist b2b decay block more."
            ),
            rationale=(
                "Selective per-section ablation (eval_atlas_by_section.py, "
                "walk-forward all-folds on the FULL 129-feat matrix, n=101,765) "
                "found quarter_shape_fatigue is the ONLY section to improve BLK on "
                "all 3 folds (delta_MAE -0.0064, all_improve=True). The same section "
                "HURTS PTS (+0.243) and REB (+0.066), so it is wired for BLK only. "
                "See .planning/loop/atlas_by_section.json."
            ),
            source="intel_scanner",
            atlas_fields=["quarter_shape_fatigue"],
            expected_verdict=Verdict.SHIP,
            priority="P1",
        )
