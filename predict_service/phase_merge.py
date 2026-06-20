"""predict_service.phase_merge -- merge pregame + ingame into a LABELLED number.

WAVE 3, load-bearing honesty rule: a merged pregame+ingame probability is ALWAYS
LABELLED by phase (phase='merged'), NEVER a silent unlabelled average. The merge
function returns a contracts.ProbEstimate whose provenance.phase == PHASE_MERGED
and whose provenance records BOTH source phases, so a consumer can always tell a
merged number from a raw pregame or ingame one.

The merge itself is the honest live rule: ONCE the game is live the in-game
conditional number is the served number (the proven conditioning beat); pregame
is the leak-free prior. We do NOT blend into a hidden scalar -- we surface the
in-game number AS the merged number and stamp the provenance so the label, not an
average, is what a reader sees. When no in-game number exists yet, the result is
simply the pregame estimate (phase stays 'pregame', NOT 'merged').

HONESTY: probability/units only; NO $ field. vs_close is NOT decided here (it
stays UNPROVEN on EdgeRows downstream until a gate proves it).

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse contracts + attribution verbatim.
"""
from __future__ import annotations

from typing import Optional

from predict_service.attribution import provenance_for
from predict_service.contracts import (
    PHASE_INGAME,
    PHASE_MERGED,
    PHASE_PREGAME,
    Interval,
    ProbEstimate,
    Provenance,
)


def merged_estimate(
    label: str,
    pregame_prob: Optional[float],
    ingame_prob: Optional[float] = None,
    *,
    market_type: str = "moneyline",
    side: str = "",
    interval: Optional[Interval] = None,
    pregame_model: str = "mc_sim",
    ingame_model: str = "ingame_conditional",
    calibration: str = "platt",
) -> Optional[ProbEstimate]:
    """A phase-LABELLED estimate from a pregame prior + optional in-game number.

    Rules (no silent average, ever):
      * ingame present -> the served number IS the in-game number; provenance.phase
        = 'merged', model records both source models, signal notes the merge so the
        label is explicit. (The in-game conditional is the proven live beat.)
      * ingame absent  -> the pregame estimate, provenance.phase = 'pregame'
        (NOT 'merged' -- there is nothing to merge).
      * pregame absent too -> None (never fabricate).

    Returns a contracts.ProbEstimate; NO $ field.
    """
    if ingame_prob is not None:
        prov = Provenance(
            model="%s+%s" % (pregame_model, ingame_model),
            signal="phase_merge(pregame_prior->ingame_conditional)",
            calibration=str(calibration or "none"),
            phase=PHASE_MERGED,
        )
        return ProbEstimate(
            label=str(label), prob=round(float(ingame_prob), 6),
            provenance=prov, interval=interval,
            market_type=market_type, side=side)
    if pregame_prob is not None:
        prov = provenance_for(model=pregame_model, calibration=calibration,
                              phase=PHASE_PREGAME)
        return ProbEstimate(
            label=str(label), prob=round(float(pregame_prob), 6),
            provenance=prov, interval=interval,
            market_type=market_type, side=side)
    return None


def is_merged(estimate: Optional[ProbEstimate]) -> bool:
    """True iff *estimate* is a phase-LABELLED merge (provenance.phase=='merged')."""
    if estimate is None:
        return False
    return getattr(estimate.provenance, "phase", None) == PHASE_MERGED


def phase_of(estimate: Optional[ProbEstimate]) -> Optional[str]:
    """The phase label of an estimate ('pregame'/'ingame'/'merged'), or None."""
    if estimate is None:
        return None
    return getattr(estimate.provenance, "phase", None)


__all__ = ["merged_estimate", "is_merged", "phase_of", "PHASE_INGAME"]
