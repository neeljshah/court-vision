"""scripts.platformkit.sport_read_specs — static specs/templates for sport_read.

Pure data module: query specs, narrative templates, banner text, provenance
list, and default priors used by scripts.platformkit.sport_read.  No logic,
no imports of sibling runtime modules — keeps sport_read.py under the LOC cap
while leaving its public API (build_sport_read, render_markdown) unchanged.
"""
from __future__ import annotations
from typing import Any, Dict

HONEST_BANNER = (
    "HONEST: markets efficient; tested signals REJECT; no edge claimed; "
    "calibration NOT edge; surface shows understanding only."
)
PROVENANCE_MODULES = [
    "scripts.platformkit.brain_query.brain_query",
    "scripts.platformkit.brain_query.prior_verdicts",
    "scripts.platformkit.brain_critic.critique_finding",
    "scripts.platformkit.pipeline_integration.assemble_read",
]
# (query template, kind) — the kind filter guarantees each bucket retrieves notes
# of that kind even when keyword overlap is low (brain_query path-sorts score ties).
QUERY_SPECS = [
    ("{sport} archetype playstyle style", "archetype"),
    ("{sport} scheme coverage defense tactic", "scheme"),
    ("{sport} scheme coverage defense tactic", "concept"),  # routed by _classify_hits
    ("{sport} trend season pattern", "trend"),
]
SAFE_TEMPLATE = (
    "Brain scout for {sport}: style landscape reflects {n_archetypes} archetype(s) "
    "and {n_schemes} scheme(s) in the organized vault. "
    "Empirical market verdict: markets efficient; all tested signals REJECT; NO betting edge. "
    "{surface_note}"
    "This read is understanding only — calibrated structure, not an actionable pick."
)
DEFAULT_PRIORS: Dict[str, Any] = {
    "edge_claimed": False, "market_efficiency": "efficient",
    "tested_signals": "REJECT", "note": "markets efficient; calibration not edge",
}
