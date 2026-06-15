"""scripts.platformkit.concept_landscape — read the person-free CONCEPT graph per sport.

Surfaces (a) the family coverage of the 2k+ node concept graph and (b) the top
concept hits relevant to a query, so the concept graph becomes part of the cohesive
per-sport read instead of being invisible to it.

Descriptive intelligence only — NEVER a probability / odds / edge / pick.  Markets are
efficient; calibration is not edge.

Public API:
    build_concept_landscape(sport, query=None, root=None, top_k=8) -> dict
    render_markdown(land: dict) -> str
CLI:
    python -m scripts.platformkit.concept_landscape --sport nba [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.brain_query import brain_query, _resolve_root
from scripts.platformkit.brain_vault import _CONCEPT_FAMILIES

# Authoritative person-free concept-EXPANSION families (Situational ... Predictability-
# Tendencies).  Scopes the landscape to the real concept graph and excludes the legacy
# structural categories (Drivers/Reference/Archetypes/Schemes/Trends) that sport_read's
# scout already surfaces, so the two layers compose without double-counting.
_FAMILY_SET = frozenset(f.lower() for f in _CONCEPT_FAMILIES)
# Canonical on-disk sport dir names under vault/_Organized/.
_SPORT_DIRS = {"nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis"}
_NOTE = "descriptive concept map; not a probability/edge; markets efficient"


def _family_counts(sport_root: Path) -> List[Dict[str, Any]]:
    """Per-family node counts for the concept families present under a sport dir."""
    out: List[Dict[str, Any]] = []
    for d in sorted(sport_root.iterdir()):
        if not d.is_dir() or d.name.lower() not in _FAMILY_SET:
            continue
        n = sum(1 for p in d.glob("*.md") if not p.name.startswith("_"))
        if n:
            out.append({"family": d.name, "count": n})
    out.sort(key=lambda x: (-x["count"], x["family"]))
    return out


def build_concept_landscape(
    sport: str,
    query: Optional[str] = None,
    root: Optional[Path] = None,
    top_k: int = 8,
) -> Dict[str, Any]:
    """Build the concept-graph landscape for *sport*.

    Returns sport, n_nodes, n_families, families (count per family), top_hits
    (concept notes most relevant to *query*), and an honest note.  No numbers that
    could drive a bet are ever produced.
    """
    sport_l = sport.lower()
    rp = Path(root) if root else None
    eff = _resolve_root(rp)
    families: List[Dict[str, Any]] = []
    if eff is not None:
        sp_dir = eff / _SPORT_DIRS.get(sport_l, sport.upper())
        if sp_dir.is_dir():
            families = _family_counts(sp_dir)
    n_nodes = sum(f["count"] for f in families)
    q = query or f"{sport_l} style tendency matchup tactic"
    # Over-fetch then keep only true expansion-family hits (drop legacy structural notes).
    hits = brain_query(q, sport=sport_l, kind="concept", root=rp, top_k=top_k * 4)
    top_hits = [
        {"title": h.title, "family": Path(h.path).parent.name,
         "provenance": h.provenance, "prevalence": h.prevalence}
        for h in hits if Path(h.path).parent.name.lower() in _FAMILY_SET
    ][:top_k]
    return {
        "sport": sport_l,
        "n_nodes": n_nodes,
        "n_families": len(families),
        "families": families,
        "top_hits": top_hits,
        "note": _NOTE,
    }


def render_markdown(land: Dict[str, Any]) -> str:
    """Render a concept landscape as human-readable Markdown."""
    sport = land.get("sport", "unknown").upper()
    n_nodes = land.get("n_nodes", 0)
    n_fam = land.get("n_families", 0)
    L: List[str] = [
        f"### Concept Graph — {sport}  _({n_nodes} nodes · {n_fam} families)_",
        f"> _{land.get('note', '')}_",
        "",
    ]
    fams = land.get("families", [])
    if fams:
        top = ", ".join(f"{f['family']} ({f['count']})" for f in fams[:12])
        L.append(f"- **Families:** {top}")
    else:
        L.append("- _no concept families found for this sport_")
    hits = land.get("top_hits", [])
    if hits:
        L.append("- **Relevant concepts:**")
        for h in hits:
            L.append(f"  - **{h['title']}** _({h['family']})_  `{h['provenance']}`")
    L.append("")
    return "\n".join(L)


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="concept_landscape: per-sport concept-graph read; never a number.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--query", default=None)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    land = build_concept_landscape(a.sport, query=a.query, top_k=a.top_k)
    if a.json:
        print(json.dumps(land, indent=2))
    else:
        print(render_markdown(land))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
