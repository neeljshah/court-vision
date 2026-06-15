"""concept_dirs.py — the generated CONCEPT directories, shared by the gates.

Notes under these directories are person-free CONCEPT nodes BY CONSTRUCTION (archetype /
scheme / driver / mechanism slugs + the W115 concept-node families).  Their two-word
slugs (``wind_vector_field``) and two-word headings (``# Second-Chance Generation``) are
CONCEPTS, not people — so the player-node SHAPE heuristic and the ``named_title`` heading
heuristic are exempted here.  The dangerous guards (id-prefixed player files, ``X vs Y``
matchups, ``<digits>_<word>_<word>`` filenames) stay active EVERYWHERE.

Single source of truth imported by ``graph_cleanliness`` and ``vault_person_free_lint``.
"""
from __future__ import annotations

CONCEPT_DIRS = frozenset((
    "drivers mechanisms archetypes schemes trends reference _index "
    # batch 1 concept families
    "situational tactics statsignatures matchupconcepts subarchetypes gamephases "
    "environment riskprofiles formdynamics "
    # batch 2 concept families
    "shotprofiles defensiveschemes specialsituations officiatingdynamics workloadfatigue "
    "rosterconstruction progressiondynamics tempocontrol spacinggeometry conversionefficiency "
    # batch 3 concept families
    "transitiondynamics possessioncontrol pressureresponse ingameadaptation chainsequences "
    "momentumswings efficiencycurves disciplinecontrol closingexecution predictabilitytendencies "
    # batch 4 concept families
    "matchupexploitation decisionquality spacecreation zonecontrol recoveryresilience "
    "tempovariation threatbalance initiationprofiles dueloutcomes anticipationreads "
    # batch 5 concept families
    "deceptiondisguise routineconsistency adaptabilityversatility volatilityprofiles "
    "leadmanagement adjustmentspeed startquality resourceallocation errorcascades "
    "experiencecomposure "
    # batch 6 concept families (to 10x)
    "opponentscouting psychologicalwarfare venuetraveleffects officialadaptation "
    "techniquemechanics").split())


def under_concept_dir(rel: str) -> bool:
    """True if a vault-relative path lives under any generated concept directory."""
    return any(p.lower() in CONCEPT_DIRS for p in rel.split("/")[:-1])
