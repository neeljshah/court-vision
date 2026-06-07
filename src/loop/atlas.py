"""AtlasSection contract for ARM-B (deep descriptive basketball intelligence).

An *atlas section* is one slice of an ULTRA-DETAILED player/team profile (how a
player actually plays). It is built leak-safe at an ``as_of`` date and produces a
provenance/confidence-stamped artifact that:
  1. is VALIDATED (leak-free + face-validity + coverage + dedup) by intel_validator,
  2. is PERSISTED by EXTENDING ``scripts/build_persistent_profiles.py`` via the
     profile_factory_bridge (1 parquet + 1 ``sec_`` fn -- never rebuild the factory),
  3. RESERVES named CV slots (set null now) that the CV branch fills later, and
  4. is READ BACK by signals as features / shrinkage priors (the reinforcement loop).

The artifact shape mirrors the profile-factory section payload (spec_intel_memory.md
section 1.3 / 1.4): a section is ``(data, prov)`` where ``prov`` carries
``{source, n, confidence, as_of}``. This module wraps that in a typed
:class:`AtlasArtifact` plus the :class:`AtlasSection` builder contract that all
``intel/*.py`` modules subclass.
"""
from __future__ import annotations

import abc
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Confidence ladder matches the profile factory (high>=20 / med>=5 / low).
CONFIDENCE_LEVELS = ("low", "med", "high")
_CONF_ORDER = {"low": 0, "med": 1, "high": 2}


def confidence_from_n(n: int, cap: Optional[str] = None) -> str:
    """Map a sample size to a confidence level (mirrors ``conf_from_n``).

    high if n>=20, med if n>=5, else low. ``cap`` clamps the maximum level
    (e.g. CV-derived fields are capped "med").
    """
    if n >= 20:
        level = "high"
    elif n >= 5:
        level = "med"
    else:
        level = "low"
    if cap is not None and _CONF_ORDER[level] > _CONF_ORDER[cap]:
        return cap
    return level


@dataclass
class CVSlot:
    """A reserved computer-vision slot the CV branch fills later.

    Attributes:
        name:        slot key (e.g. "defender_distance_dist").
        dtype:       expected value type ("float" | "dist" | "list" | "categorical").
        description: what the CV pipeline should populate.
        unit:        physical unit if any (e.g. "ft", "deg", "s").
        value:       None until CV fills it (FROZEN under the CV-session boundary).
    """

    name: str
    dtype: str = "float"
    description: str = ""
    unit: Optional[str] = None
    value: Any = None


@dataclass
class AtlasArtifact:
    """The built, validatable, persistable atlas-section artifact.

    Attributes:
        section:    section key (e.g. "shot_profile").
        entity:     "player" | "team".
        entity_id:  player_id (int) or team tricode (str).
        value:      the headline scalar/summary value (optional convenience).
        sub_fields: the deeply-nested descriptive payload (the real content).
        provenance: ``{"source": str, "n": int, "confidence": str, "as_of": str}``.
        confidence: "low" | "med" | "high" (also mirrored inside provenance).
        as_of:      ISO date this artifact is valid as-of (leak boundary).
        cv_fields:  reserved CV slots ``{name: CVSlot}`` (values null until CV fills).
    """

    section: str
    entity: str
    entity_id: Any
    value: Any = None
    sub_fields: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"
    as_of: Optional[str] = None
    cv_fields: Dict[str, CVSlot] = field(default_factory=dict)

    def to_profile_payload(self) -> tuple:
        """Return ``(data, prov)`` exactly as the profile factory's ``sec_`` fns do.

        The CV slots are embedded under ``data["_cv_fields"]`` (null values now) so
        the persisted JSON carries the reserved schema for the CV branch.
        """
        data = dict(self.sub_fields)
        if self.value is not None:
            data.setdefault("value", self.value)
        data["_cv_fields"] = {
            name: {"dtype": s.dtype, "unit": s.unit,
                   "description": s.description, "value": s.value}
            for name, s in self.cv_fields.items()
        }
        prov = {
            "source": self.provenance.get("source", "unknown"),
            "n": int(self.provenance.get("n", 0)),
            "confidence": self.confidence,
            "as_of": self.as_of,
        }
        return data, prov


class AtlasSection(abc.ABC):
    """Base class for a descriptive atlas section (ARM-B).

    Subclasses (``intel/<entity>_<name>.py``) set ``name`` and ``entity`` and
    implement :meth:`build` (leak-safe), :meth:`validate`, and :meth:`cv_fields`.
    They MUST reuse existing parquets / profile-factory sources (spec_features.md,
    spec_intel_memory.md) rather than re-derive, and mark missing sub-fields DEFER.

    Class attributes:
        name:        section key (e.g. "shot_profile").
        entity:      "player" | "team".
        source_name: provenance source label (parquet/atlas it reads).
        conf_cap:    optional max confidence (e.g. "med" for CV-derived fields).
    """

    name: str = "base_section"
    entity: str = "player"
    source_name: str = "unknown"
    conf_cap: Optional[str] = None

    @abc.abstractmethod
    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the leak-safe artifact for one entity as-of a date.

        MUST only use data with ``as_of <= as_of``. Returns an
        :class:`AtlasArtifact` (with cv_fields populated as reserved/null slots)
        or ``None`` if the entity/source is missing (skip).
        """
        raise NotImplementedError

    @abc.abstractmethod
    def validate(self, artifact: AtlasArtifact) -> bool:
        """Cheap self-validation (sane ranges/monotonicities, schema present).

        The full leak/coverage/dedup gate lives in ``src.loop.intel_validator``;
        this is the section's own face-validity check. Return True iff the
        artifact is internally well-formed.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cv_fields(self) -> Dict[str, CVSlot]:
        """Return the reserved CV-slot schema for this section (values null now).

        These slots are persisted into the profile JSON so the CV branch can fill
        them later WITHOUT a profile-factory rebuild. Keys are stable contract.
        """
        raise NotImplementedError

    # ----- shared helpers (concrete) -----------------------------------------
    def section_key(self) -> str:
        """Profile-factory section key used by the bridge / merge_section."""
        return self.name

    def sec_fn_name(self) -> str:
        """Name of the ``sec_<name>`` function the bridge registers."""
        return f"sec_{self.name}"

    def parquet_name(self) -> str:
        """Standard disjoint parquet name the bridge writes/reads."""
        return f"atlas_{self.entity}_{self.name}.parquet"
