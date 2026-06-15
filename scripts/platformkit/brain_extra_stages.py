"""brain_extra_stages.py — W112 additive generated-brain stages for brain_pipeline.

Three person-free, no-edge stages over the freshly built ``vault/_Organized`` tree,
kept here (not inline in brain_pipeline) to hold that orchestrator under the LOC cap:

  form_profiles : per-sport leak-free AS-OF form distribution profiles (descriptive)
  consolidate   : merge near-identical stub families into dense notes (+ link-repair)
  redundancy    : standing thin / duplicate / orphan audit report

ORDER MATTERS: ``consolidate`` deletes stub files and repairs dangling wikilinks, so it
runs BEFORE ``redundancy`` (which reports the post-merge state) and AFTER every
link-creating stage the pipeline already ran.  Each stage is guarded — an error is
skipped honestly, never crashing the rebuild.

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
    # CONSOLIDATE redundant stub families -> dense notes (+ repair dangling wikilinks)
    try:
        from scripts.platformkit.brain_consolidate import consolidate  # noqa: PLC0415
        cs = consolidate(organized_root=organized_root, write=True)
        if cs.get("n_families", 0) > 0:
            out.setdefault("_consolidate", {})["consolidated"] = (
                f"{cs['n_families']} families / {cs['n_notes_merged']} stubs merged")
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
    return out
