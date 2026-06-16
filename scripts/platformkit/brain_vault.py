"""brain_vault — make vault/_Organized openable as its OWN clean Obsidian vault.

The user keeps their FULL vault at vault/ (untouched). vault/_Organized/ holds the
dense person-free intelligence brain. Opening _Organized as a SEPARATE Obsidian vault
("Open another vault" -> vault/_Organized) gives a graph that shows ONLY the brain
(drivers/mechanisms/archetypes/schemes/identity/MOC hubs) — clean BY CONSTRUCTION,
because that folder contains no matchups/players at all. No graph.json filter needed
and no clobber problem (everything there IS brain).

The one-command rebuild wipes _Organized each run, so this re-seeds its .obsidian
config every rebuild (deterministic; the _Organized vault is a generated view).
HONEST: an intelligence map; markets efficient; calibration is not edge; no edge.
"""
from __future__ import annotations

import colorsys
import json
from pathlib import Path
from typing import Dict, List

_CORE_PLUGINS = ["graph", "backlink", "outline", "page-preview", "tag-pane", "search"]

# Concept-node families (batch 1 + 2). The graph is COLOUR-CODED BY FAMILY: each family
# gets a distinct colour from a golden-angle HSV sweep + lightness tiers (consecutive
# families land ~222 deg apart, never near-identical), by the node's exact frontmatter
# family TAG (e.g. ``tag:#tactics``) — exact tags avoid substring collisions that a
# ``path:`` query would hit (e.g. "Schemes" inside "DefensiveSchemes", "Archetypes"
# inside "SubArchetypes"). Sport is read from the CLUSTERING (each sport is its own
# connected component via its _Concept_Map), so one colour channel encodes family.
_CONCEPT_FAMILIES = [
    "Situational", "Tactics", "StatSignatures", "Mechanisms", "MatchupConcepts",
    "SubArchetypes", "GamePhases", "Environment", "RiskProfiles", "FormDynamics",
    "ShotProfiles", "DefensiveSchemes", "SpecialSituations", "OfficiatingDynamics",
    "WorkloadFatigue", "RosterConstruction", "ProgressionDynamics", "TempoControl",
    "SpacingGeometry", "ConversionEfficiency",
    "TransitionDynamics", "PossessionControl", "PressureResponse", "InGameAdaptation",
    "ChainSequences", "MomentumSwings", "EfficiencyCurves", "DisciplineControl",
    "ClosingExecution", "PredictabilityTendencies",
    "MatchupExploitation", "DecisionQuality", "SpaceCreation", "ZoneControl",
    "RecoveryResilience", "TempoVariation", "ThreatBalance", "InitiationProfiles",
    "DuelOutcomes", "AnticipationReads",
    "DeceptionDisguise", "RoutineConsistency", "AdaptabilityVersatility",
    "VolatilityProfiles", "LeadManagement", "AdjustmentSpeed", "StartQuality",
    "ResourceAllocation", "ErrorCascades", "ExperienceComposure",
    "OpponentScouting", "PsychologicalWarfare", "VenueTravelEffects",
    "OfficialAdaptation", "TechniqueMechanics",
]
# legacy structural categories without a substring clash -> coloured by path.
_LEGACY_PATHS = {"Drivers": 16007990, "Trends": 8754687, "Reference": 9145227,
                 "Archetypes": 5028096, "Schemes": 16770304, "Teams": 0x5B6675}

# Full-coverage fallbacks so NOTHING renders default-grey. Keyed by PATH -- every note
# lives under MLB/NBA/Soccer/Tennis/_Index -- so a node with no family tag (MOC/index
# files, team identity, archetypes) still colours by its sport. _Index is the catch-all.
_SPORT_FALLBACK = {"MLB": 0x2E6FE0, "NBA": 0xE8743B, "Soccer": 0x2EA043, "Tennis": 0xE0C020}
_CATCH_ALL = 0x8B97A6


def _rgb(h: float, s: float, v: float) -> int:
    """HSV (0..1) -> packed 24-bit int Obsidian expects for a colour."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)


# Golden-angle hue stepping: each successive family lands ~222.5 deg around the wheel,
# so no two adjacent families share a near-identical hue (the old even i/n sweep put 55
# families ~6.5 deg apart -> indistinguishable). Three sat/val tiers separate the hues
# that eventually wrap, giving 55 legibly-distinct colours.
_GOLDEN = 0.6180339887498949
_SAT_TIERS = (0.80, 0.62, 0.93)
_VAL_TIERS = (0.96, 0.82, 0.70)


def _family_color(i: int) -> int:
    """Distinct, legible colour for the i-th concept family (golden-angle + tiers)."""
    return _rgb((i * _GOLDEN) % 1.0, _SAT_TIERS[i % 3], _VAL_TIERS[i % 3])


def _color_groups() -> List[Dict]:
    """Per-family colour groups (exact tag) + legacy paths + hubs. Family groups are
    listed FIRST so an exact family tag wins over a broader legacy path match."""
    groups: List[Dict] = []
    for i, fam in enumerate(_CONCEPT_FAMILIES):
        groups.append({"query": f"tag:#{fam.lower()}",
                       "color": {"a": 1, "rgb": _family_color(i)}})
    for name, rgb in _LEGACY_PATHS.items():
        groups.append({"query": f"path:{name}", "color": {"a": 1, "rgb": rgb}})
    # hubs pop white; team identity hubs grey.
    groups.append({"query": ("file:_Concept_Map OR file:_Brain OR file:_WhatWins OR "
                             "file:_Digest OR file:_Cross_Sport"),
                   "color": {"a": 1, "rgb": 16777215}})
    groups.append({"query": "file:_Identity", "color": {"a": 1, "rgb": 12632256}})
    # Sport fallbacks by path (nodes with no family tag) + _Index catch-all -> 100%.
    for sport_path, rgb in _SPORT_FALLBACK.items():
        groups.append({"query": f"path:{sport_path}", "color": {"a": 1, "rgb": rgb}})
    groups.append({"query": "path:_Index", "color": {"a": 1, "rgb": _CATCH_ALL}})
    return groups


# Graph view for the brain-only vault: colour BY FAMILY (+ legacy paths + hubs).
# No "search" scope filter is needed — every node in this vault is brain.
_GRAPH: Dict = {
    "collapse-filter": False, "search": "", "showTags": False,
    "showAttachments": False, "hideUnresolved": True, "showOrphans": True,
    "collapse-color-groups": False,
    "colorGroups": _color_groups(),
    "collapse-display": False, "showArrow": False, "textFadeMultiplier": -0.5,
    # Perf-tuned for a ~4.5k-node graph: smaller nodes/lines render lighter, and a
    # stronger centre/link pull with lower repel lets the force sim settle fast
    # (continuous jitter is the main source of graph lag at this node count).
    "nodeSizeMultiplier": 0.75, "lineSizeMultiplier": 0.4, "collapse-forces": False,
    "centerStrength": 0.85, "repelStrength": 7.0, "linkStrength": 0.9,
    "linkDistance": 110, "scale": 0.18, "close": True,
}


def _w(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def ensure_brain_graph_config(organized_root: Path) -> Dict:
    """Seed/refresh organized_root/.obsidian so _Organized opens as a clean vault.

    Idempotent + deterministic. Returns {"obsidian_dir","files"}.
    """
    organized_root = Path(organized_root)
    obs = organized_root / ".obsidian"
    obs.mkdir(parents=True, exist_ok=True)
    files = {
        "app.json": json.dumps({"alwaysUpdateLinks": True}, indent=2),
        "appearance.json": json.dumps({"accentColor": "", "theme": "obsidian"}, indent=2),
        "core-plugins.json": json.dumps(_CORE_PLUGINS, indent=2),
        "graph.json": json.dumps(_GRAPH, indent=2),
    }
    for name, text in files.items():
        _w(obs / name, text)
    return {"obsidian_dir": str(obs), "files": sorted(files)}


def _main(argv=None) -> int:
    import sys
    root = Path(argv[0]) if (argv := list(sys.argv[1:] if argv is None else argv)) \
        else Path(__file__).resolve().parents[2] / "vault" / "_Organized"
    rep = ensure_brain_graph_config(root)
    print(json.dumps(rep, indent=2))
    print(f"\nOpen this folder as an Obsidian vault for a clean brain-only graph:\n  {root}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["ensure_brain_graph_config"]
