"""Versioned calibration-artifact value object (Milestone-8 ratchet).

A CalibArtifact is the immutable unit the registry versions: a calibrator's
identity (kind), provenance (version, created_at), the fitted params, and the
integrity fields that enforce the hard-learned pkl-integrity invariant --
n_features_in MUST match the meta the artifact was fitted against, or the
artifact is REJECTED before it can ever become CURRENT. This is the
train==inference parity guard distilled to data: a calibrator that silently
expects a different feature width than its meta declares is the most expensive
bug class, so we refuse to promote it.

Sport-blind + stdlib-only (json + dataclasses). No dollar/edge field exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CalibArtifact:
    """One versioned calibration artifact.

    version       : monotonically increasing int (1-based) assigned by registry.
    created_at    : ISO-8601 UTC timestamp string.
    kind          : calibrator family / sport-blind key (e.g. "nba_winprob").
    params        : the fitted calibrator parameters (JSON-serialisable).
    n_features_in : feature width the calibrator was fitted on (parity guard).
    meta          : free-form provenance (corpora, k-folds, scores, seeds...).
    """
    version: int
    created_at: str
    kind: str
    n_features_in: int
    params: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibArtifact":
        if not isinstance(d, dict):
            raise TypeError("CalibArtifact.from_dict expects a dict")
        return cls(
            version=int(d["version"]),
            created_at=str(d["created_at"]),
            kind=str(d["kind"]),
            n_features_in=int(d["n_features_in"]),
            params=dict(d.get("params") or {}),
            meta=dict(d.get("meta") or {}),
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, s: str) -> "CalibArtifact":
        return cls.from_dict(json.loads(s))


def integrity_ok(artifact: CalibArtifact,
                 meta: Optional[Dict[str, Any]] = None) -> bool:
    """True iff the artifact is internally consistent AND parity-safe.

    The pkl-integrity invariant: the artifact's declared n_features_in must
    match the meta it is being validated against (``meta["n_features_in"]``).
    A feature-width mismatch is exactly the train/inference parity break that
    silently reads 0.0 at inference -- we refuse it here so it can never be
    promoted to CURRENT. When ``meta`` is None we fall back to the artifact's
    own embedded meta, so a round-tripped artifact self-validates.
    """
    if not isinstance(artifact, CalibArtifact):
        return False
    if artifact.version < 1:
        return False
    if not artifact.kind or not isinstance(artifact.kind, str):
        return False
    if not isinstance(artifact.n_features_in, int) or artifact.n_features_in < 0:
        return False
    check = meta if meta is not None else artifact.meta
    if not isinstance(check, dict):
        return False
    declared = check.get("n_features_in")
    if declared is None:
        # No claim to contradict; structural checks above already passed.
        return True
    try:
        return int(declared) == int(artifact.n_features_in)
    except (TypeError, ValueError):
        return False
