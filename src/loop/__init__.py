"""src.loop -- the autonomous self-improving NBA loop (two arms, one substrate).

ARM A (SIGNALS): error_miner -> Hypothesis -> Signal.build (leak-safe, reads atlases)
  -> gate (walk-forward + null-shuffle + ablation-vs-full + calibration + CLV)
  -> wiring (GPU retrain + regime-gate register + write learned values back as atlas
  field) -> ledger.

ARM B (INTELLIGENCE): AtlasSection.build (leak-safe, deep descriptive) ->
  intel_validator (leak/face/coverage/dedup/CV-slot) -> profile_factory_bridge
  (extend build_persistent_profiles.py, 1 parquet + 1 sec_ fn) -> memory_writer ->
  report_generator -> ledger.

Both arms share :class:`~src.loop.store.PointInTimeStore`. The orchestrator drives
the loop; the simulator emits the JOINT distribution for joint/ablation evaluation.

This module re-exports the stable contracts so builders import from one place:

    from src.loop import (Signal, AsOfContext, Hypothesis, Verdict, GateResult,
                          AtlasSection, AtlasArtifact, CVSlot, PointInTimeStore,
                          get_store)
"""
from __future__ import annotations

from .atlas import (AtlasArtifact, AtlasSection, CVSlot, confidence_from_n)
from .signal import (AsOfContext, GateResult, Hypothesis, Signal, SignalValue,
                     Verdict, SCOPES, TARGETS)
from .store import (PointInTimeStore, StoreRecord, entity_key, get_store,
                    KIND_ATLAS, KIND_CV, KIND_SIGNAL)

__all__ = [
    # signal contract
    "Signal", "SignalValue", "AsOfContext", "Hypothesis", "Verdict",
    "GateResult", "SCOPES", "TARGETS",
    # atlas contract
    "AtlasSection", "AtlasArtifact", "CVSlot", "confidence_from_n",
    # store
    "PointInTimeStore", "StoreRecord", "entity_key", "get_store",
    "KIND_ATLAS", "KIND_SIGNAL", "KIND_CV",
]

__version__ = "0.1.0"
