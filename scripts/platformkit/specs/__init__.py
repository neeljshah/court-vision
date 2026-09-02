"""scripts.platformkit.specs — person-free CONCEPT-NODE content specs for the brain.

Each spec module in this package declares dense, person-free intelligence concepts that
``brain_concept_nodes.py`` turns into ONE Obsidian node (.md) each, under
``vault/_Organized/<SPORT>/<FAMILY>/<slug>.md``, plus a ``<FAMILY>/_Index.md`` hub, with
``## Related`` wikilinks resolved across concepts.  Adding a spec module multiplies the
graph's nodes — this is how the brain grows to 10x nodes per sport, all organized.

THE CONTRACT — every spec module MUST expose exactly these three module-level names:

    SPORT  : str   # one of "NBA", "MLB", "Soccer", "Tennis"
    FAMILY : str   # node-family / subdir name, e.g. "Situational", "Tactics",
                   #   "StatSignatures", "MatchupConcepts", "Mechanisms"
    CONCEPTS : list[dict]   # one dict per node, each with EXACTLY these keys:
        {
          "slug":           str,   # lowercase_snake, unique within (SPORT, FAMILY); filename stem
          "title":          str,   # display title — a CONCEPT, NEVER a person/team/match name
          "summary":        str,   # 1-2 sentence person-free overview
          "stat_signature": str,   # the measurable signature: rates / thresholds / splits
          "mechanism":      str,   # WHY it matters (causal, person-free)
          "conditions":     str,   # WHEN / against which styles it shows up
          "magnitude":      str,   # typical DESCRIPTIVE effect size (never an edge / ROI / pick)
          "links":          list,  # slugs of related concepts (this or any family/sport)
        }

HONEST + PERSON-FREE RULES (binding — the rebuild gates enforce them):
  - NO specific player / team / match names anywhere (concepts, slugs, titles, prose).
  - NEVER write the literal " vs " between two Title-Case words (it trips the matchup
    lint); use "versus" / "against" / "compared with".
  - DESCRIPTIVE intelligence only: markets are efficient; calibration is not edge; no
    edge / ROI / pick / "beats the market" is ever claimed.
  - Each concept must be DENSE and substantive (real stat-signature + mechanism +
    conditions + magnitude) — no shallow filler nodes.
"""
from __future__ import annotations

# The required module-level names and per-concept dict keys (single source of truth).
SPEC_MODULE_VARS = ("SPORT", "FAMILY", "CONCEPTS")
CONCEPT_KEYS = (
    "slug", "title", "summary", "stat_signature",
    "mechanism", "conditions", "magnitude", "links",
)
VALID_SPORTS = ("NBA", "MLB", "Soccer", "Tennis")


def validate_concept(c: dict) -> list:
    """Return a list of problems with a single concept dict (empty == valid)."""
    problems = []
    for k in CONCEPT_KEYS:
        if k not in c:
            problems.append(f"missing key: {k}")
    slug = c.get("slug", "")
    if slug and slug != slug.lower().strip():
        problems.append(f"slug not lowercase/trimmed: {slug!r}")
    if isinstance(c.get("links"), (str, bytes)):
        problems.append("links must be a list of slugs, not a string")
    for field in ("summary", "stat_signature", "mechanism", "conditions", "magnitude"):
        val = c.get(field, "")
        if isinstance(val, str) and " vs " in f" {val} ":
            problems.append(f"{field} contains ' vs ' (use 'versus'/'against')")
    return problems
