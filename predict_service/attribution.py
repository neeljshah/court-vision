"""predict_service.attribution -- which model/signal produced each number.

WAVE 3. Builds a contracts.Provenance for an estimate: descriptive, flag-OFF,
NO edge claim. This records the producing machinery (model id), the named signal
path (or '' when the base model alone), the calibration method, and the PHASE the
number was produced under. It never asserts a number beats the close and never
introduces a $ field -- it is pure attribution metadata.

The phase is the load-bearing field: a merged pregame+ingame number carries
phase='merged' so a consumer reads the label, never an unlabelled scalar that
silently averaged two phases.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse contracts.Provenance verbatim; descriptive only.
"""
from __future__ import annotations

from typing import Optional

from predict_service.contracts import (
    PHASE_PREGAME,
    VALID_PHASES,
    Provenance,
)


def provenance_for(
    model: str = "",
    signal: str = "",
    calibration: str = "none",
    phase: str = PHASE_PREGAME,
) -> Provenance:
    """Build a Provenance, guarding the phase to a known value (default pregame).

    An unknown phase degrades to 'pregame' (never silently to 'merged'), so an
    accidental bad label can never make a number look like a labelled merge.
    """
    ph = phase if phase in VALID_PHASES else PHASE_PREGAME
    return Provenance(
        model=str(model or ""),
        signal=str(signal or ""),
        calibration=str(calibration or "none"),
        phase=ph,
    )


def pregame_provenance(model: str = "mc_sim", calibration: str = "platt",
                       signal: str = "") -> Provenance:
    """Provenance for a pregame number (the buyer-facing calibrated model)."""
    return provenance_for(model=model, signal=signal, calibration=calibration,
                          phase=PHASE_PREGAME)


def ingame_provenance(model: str = "ingame_conditional",
                      calibration: str = "platt", signal: str = "") -> Provenance:
    """Provenance for an in-game number (the proven conditioning beat)."""
    from predict_service.contracts import PHASE_INGAME  # noqa: PLC0415
    return provenance_for(model=model, signal=signal, calibration=calibration,
                          phase=PHASE_INGAME)


def describe(prov: Optional[Provenance]) -> str:
    """A short human string for a Provenance (descriptive; no claim)."""
    if prov is None:
        return "unknown"
    parts = [prov.phase or "?"]
    if prov.model:
        parts.append("model=%s" % prov.model)
    if prov.signal:
        parts.append("signal=%s" % prov.signal)
    if prov.calibration and prov.calibration != "none":
        parts.append("cal=%s" % prov.calibration)
    return " ".join(parts)


__all__ = ["provenance_for", "pregame_provenance", "ingame_provenance", "describe"]
