"""brain_extra_stages.py — W112 additive generated-brain stages for brain_pipeline.

Person-free, no-edge stages over the freshly built ``vault/_Organized`` tree, kept here
(not inline in brain_pipeline) to hold that orchestrator under the LOC cap:

  form_profiles : per-sport leak-free AS-OF form distribution profiles (descriptive)
  tennis_depth  : serve/return as-of bands -> style archetypes
  mlb_schemes   : MLB pitching/run-environment scheme taxonomy
  consolidate   : merge near-identical legacy stub families into dense notes (+ link-repair)
  concept_nodes : emit MANY dense person-free concept nodes from scripts/platformkit/specs/*
  concept_map   : per-sport hub linking the concept families + sport-index patch
  redundancy    : standing thin / duplicate / orphan audit report (runs LAST)

ORDER MATTERS: ``consolidate`` (legacy-stub merge) runs BEFORE ``concept_nodes`` so it
never touches the dense concept web; ``concept_map`` runs after ``concept_nodes``; and
``redundancy`` runs LAST so it reports the final tree.  Each stage is guarded — an error
is skipped honestly, never crashing the rebuild.

Intelligence MAP, not a betting edge; markets efficient; calibration is not edge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def run_extra_stages(organized_root: Path) -> Dict:
    """Run the three additive stages over *organized_root*; return artifact flags."""
    out: Dict[str, Dict] = {}
    # per-sport leak-free as-of FORM PROFILES (distribution bands; descriptive only)
    try:
        from scripts.platformkit.brain_form_profiles import build_form_profiles  # noqa: PLC0415
        fp = build_form_profiles(organized_root=organized_root, write=True)
        if fp.get("n_sports", 0) > 0:
            out.setdefault("_form_profiles", {})["form_profiles"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # Tennis serve/return STYLE-ARCHETYPE depth (maps as-of bands -> style concepts)
    try:
        from scripts.platformkit.brain_tennis_depth import build_tennis_depth  # noqa: PLC0415
        td = build_tennis_depth(organized_root=organized_root, write=True)
        if isinstance(td, dict) and td.get("styles"):
            out.setdefault("_tennis_depth", {})["serve_return_archetypes"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # MLB PITCHING SCHEMES depth (fills MLB's empty Schemes category; from as-of+park data)
    try:
        from scripts.platformkit.brain_mlb_schemes import build_mlb_schemes  # noqa: PLC0415
        ms = build_mlb_schemes(organized_root=organized_root, write=True)
        if isinstance(ms, dict) and not ms.get("skipped"):
            out.setdefault("_mlb_schemes", {})["pitching_schemes"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # CONSOLIDATE redundant stub families -> dense notes (+ repair dangling wikilinks)
    try:
        from scripts.platformkit.brain_consolidate import consolidate  # noqa: PLC0415
        cs = consolidate(organized_root=organized_root, write=True)
        if cs.get("n_families", 0) > 0:
            out.setdefault("_consolidate", {})["consolidated"] = (
                f"{cs['n_families']} families / {cs['n_notes_merged']} stubs merged")
    except Exception:  # noqa: BLE001
        pass
    # CONCEPT NODES: emit many dense person-free nodes from scripts/platformkit/specs/*
    # (situational / tactics / stat-signatures / mechanisms / matchups / sub-archetypes /
    # game-phases / environment / risk / form — per sport). The graph-expansion engine:
    # more spec modules => more organized nodes. Runs AFTER consolidate so the merge pass
    # only ever touches legacy stubs, never these dense distinct concept nodes.
    try:
        from scripts.platformkit.brain_concept_nodes import build_concept_nodes  # noqa: PLC0415
        cn = build_concept_nodes(organized_root=organized_root, write=True)
        if isinstance(cn, dict) and cn.get("n_nodes", 0) > 0:
            out.setdefault("_concept_nodes", {})["nodes"] = (
                f"{cn['n_nodes']} nodes / {cn.get('n_modules', 0)} specs")
    except Exception:  # noqa: BLE001
        pass
    # CONCEPT MAP: per-sport hub linking every concept family + patch sport _Index, so the
    # concept web is one navigable connected graph (sport _Index -> Concept Map -> families).
    try:
        from scripts.platformkit.brain_concept_map import build_concept_map  # noqa: PLC0415
        cm = build_concept_map(organized_root=organized_root, write=True)
        if isinstance(cm, dict) and cm.get("n_maps", 0) > 0:
            out.setdefault("_concept_map", {})["concept_map"] = (
                f"{cm['n_maps']} sport hubs")
    except Exception:  # noqa: BLE001
        pass
    # standing REDUNDANCY audit (thin / near-duplicate / orphan) -> _Index report
    try:
        from scripts.platformkit.brain_redundancy import build_redundancy  # noqa: PLC0415
        rd = build_redundancy(organized_root=organized_root, write=True)
        if rd.get("totals"):
            out.setdefault("_redundancy", {})["redundancy_report"] = "written"
    except Exception:  # noqa: BLE001
        pass
    # COHESIVE READ (runs LAST, over the final tree): one honest per-sport document tying
    # brain understanding + the concept graph + calibrated-engine pointers + a self-checked
    # narrative into ONE read.  Deterministic (LLM-OFF); descriptive; no edge claimed.
    try:
        from scripts.platformkit.cohesive_read import write_reads, write_index  # noqa: PLC0415
        paths = write_reads(root=organized_root)
        if paths:
            out.setdefault("_cohesive_read", {})["per_sport_reads"] = f"{len(paths)} written"
        if write_index(root=organized_root):
            out.setdefault("_cohesive_read", {})["index"] = "written"
    except Exception:  # noqa: BLE001
        pass
    return out
