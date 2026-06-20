"""predict_service.contracts_v11 -- the 1.1.0 ADDITIVE prediction shapes.

WAVE 3. Factored out of predict_service.contracts (LOC budget) but is part of the
SAME frozen contract: these dataclasses are imported and re-exported by
predict_service.contracts, so a consumer keeps importing everything from
contracts. New in 1.1.0, all ADDITIVE / non-breaking:

  * Provenance  -- WHICH model/signal/calibration/phase produced a number
                   (descriptive, flag-OFF, NO edge claim).
  * Interval    -- a leak-free uncertainty band from HELD-OUT residuals only.
  * ProbEstimate-- a probability + its Provenance + an OPTIONAL Interval.

A merged pregame+ingame number is LABELLED by phase (Provenance.phase='merged'),
NEVER a silent average. NO $ field on any shape -- probability/units only.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge field; dataclasses (stdlib) matching repo convention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

# Phases a probability can be produced under. Re-exported from contracts too.
PHASE_PREGAME = "pregame"
PHASE_INGAME = "ingame"
PHASE_MERGED = "merged"
VALID_PHASES = (PHASE_PREGAME, PHASE_INGAME, PHASE_MERGED)


def _filter_known(cls: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys that are declared fields of *cls* (forward-compat reads)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (data or {}).items() if k in names}


@dataclass
class Provenance:
    """WHICH machinery produced a number (descriptive, flag-OFF, no edge claim).

    model is the producing engine/forecaster id (e.g. 'mc_sim', 'mov_elo'),
    signal the named signal/feature path (or '' when the base model alone), and
    calibration the calibration method applied (e.g. 'platt', 'shin', 'none').
    phase is one of VALID_PHASES -- a merged number carries phase='merged' so it
    is never mistaken for an unlabelled scalar. Purely attributive.
    """
    model: str = ""
    signal: str = ""
    calibration: str = "none"
    phase: str = PHASE_PREGAME

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Provenance":
        return cls(**_filter_known(cls, data))


@dataclass
class Interval:
    """A leak-free uncertainty interval from HELD-OUT residuals only.

    lo/hi bound *prob* at coverage *level* (e.g. 0.80). method records HOW the
    interval was derived ('heldout_residual_quantile') so a reader can confirm it
    is from held-out residuals, never an in-sample / fabricated band. NO $ field.
    """
    lo: float
    hi: float
    level: float = 0.80
    method: str = "heldout_residual_quantile"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interval":
        return cls(**_filter_known(cls, data))


@dataclass
class ProbEstimate:
    """A contracted probability + its provenance + an OPTIONAL held-out interval.

    prob is the calibrated probability for *market_type*/*side*. provenance stamps
    which model/signal/calibration/phase produced it. interval (when present) is
    leak-free, from held-out residuals only. label names the market cell (e.g.
    'home_ml'). NO $ field anywhere -- probability/units only.
    """
    label: str
    prob: float
    provenance: Provenance = field(default_factory=Provenance)
    interval: Optional[Interval] = None
    market_type: str = "moneyline"
    side: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict()
        d["interval"] = self.interval.to_dict() if self.interval is not None else None
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProbEstimate":
        kw = _filter_known(cls, data)
        prov = (data or {}).get("provenance")
        kw["provenance"] = (Provenance.from_dict(prov)
                            if isinstance(prov, dict) else Provenance())
        itv = (data or {}).get("interval")
        kw["interval"] = Interval.from_dict(itv) if isinstance(itv, dict) else None
        return cls(**kw)


__all__ = [
    "PHASE_PREGAME",
    "PHASE_INGAME",
    "PHASE_MERGED",
    "VALID_PHASES",
    "Provenance",
    "Interval",
    "ProbEstimate",
]
