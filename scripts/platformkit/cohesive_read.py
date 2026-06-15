"""scripts.platformkit.cohesive_read — ONE honest per-sport read tying every layer together.

Composes the whole system into a single per-sport document:
  - BRAIN understanding  -> sport_read (scout over the organized graph + priors + critic)
  - CONCEPT graph        -> concept_landscape (the 2k+ node person-free concept map)
  - ENGINE numbers       -> model competence (calibration) + scoreboard artifact pointer
  - LLM narrative        -> sport_read narrative, self-checked by brain_critic

Every number is a CALIBRATION metric produced by the gate/engine; the LLM writes prose
only.  No un-gated pick, no edge — markets are efficient; calibration is not edge.

Public API:
    build_cohesive_read(sport, jd=None, root=None, use_llm=None, top_k=6) -> dict
    render_markdown(read: dict) -> str
    write_reads(sports=None, root=None) -> list[str]
CLI:
    python -m scripts.platformkit.cohesive_read --sport nba [--markdown|--json]
    python -m scripts.platformkit.cohesive_read --all --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.sport_read import build_sport_read, render_markdown as _read_md
from scripts.platformkit.concept_landscape import (
    build_concept_landscape, render_markdown as _land_md)
from scripts.platformkit.brain_query import _resolve_root

_SPORTS = ("nba", "mlb", "soccer", "tennis")
_SPORT_DIRS = {"nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis"}
_SCOREBOARDS = {
    "platform": "_Index/_Platform_Scoreboard.md",
    "calibration": "_Index/_Calibration_Scoreboard.md",
}
# Per-sport knowledge hubs the rebuild writes (label, filename within <SPORT>/).
_PER_SPORT_HUBS = [
    ("Digest", "_Digest.md"),
    ("What Wins — drivers", "_WhatWins.md"),
    ("Form Profiles — as-of bands", "_Form_Profiles.md"),
    ("Key Stats — win/loss separation", "_KeyStats.md"),
    ("Validated Improvements", "_Validated_Improvements.md"),
    ("Concept Map", "_Concept_Map.md"),
    ("Model Card", "_Model_Card.md"),
    ("Team Base Rates (EB)", "_Team_Base_Rates_EB.md"),
]
# Cross-sport hubs (label, path within _Organized/).
_CROSS_SPORT_HUBS = [
    ("Cross-Sport Transfer", "_Index/_Cross_Sport_Transfer.md"),
    ("Cross-Sport Digest", "_Index/_Cross_Sport_Digest.md"),
    ("Coverage Map", "_Index/_Coverage.md"),
]
_BANNER = ("COHESIVE READ — one system: brain understanding + concept graph + "
           "calibrated engine + self-checked narrative. No edge; markets efficient.")


def _scoreboard_pointer(root: Optional[Path]) -> Dict[str, str]:
    """Locate the scoreboard artifacts the rebuild wrote (consumed, never recomputed)."""
    eff = _resolve_root(Path(root) if root else None)
    out: Dict[str, str] = {}
    if eff is None:
        return out
    for key, rel in _SCOREBOARDS.items():
        p = eff / rel
        if p.is_file():
            out[key] = f"brain:{rel}"
    return out


def _excerpt(path: Path) -> str:
    """First substantive prose line of a hub note (skips frontmatter/headings/tables)."""
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = raw.strip()
            if not ln or ln.startswith(("#", "---", "|", ">", "tags:", "- [[", "![")):
                continue
            return ln[:140]
    except OSError:
        pass
    return ""


def _knowledge_layers(sport: str, root: Optional[Path]) -> List[Dict[str, str]]:
    """Link every per-sport + cross-sport knowledge hub that exists (consumed, not recomputed)."""
    eff = _resolve_root(Path(root) if root else None)
    if eff is None:
        return []
    sp_dir = eff / _SPORT_DIRS.get(sport.lower(), sport.upper())
    out: List[Dict[str, str]] = []
    for label, fn in _PER_SPORT_HUBS:
        p = sp_dir / fn
        if p.is_file():
            out.append({"label": label, "provenance": f"brain:{_SPORT_DIRS.get(sport.lower(), sport.upper())}/{fn}",
                        "excerpt": _excerpt(p)})
    for label, rel in _CROSS_SPORT_HUBS:
        p = eff / rel
        if p.is_file():
            out.append({"label": label, "provenance": f"brain:{rel}", "excerpt": _excerpt(p)})
    return out


def build_cohesive_read(
    sport: str,
    jd: Any = None,
    root: Optional[Path] = None,
    use_llm: Optional[bool] = None,
    top_k: int = 6,
) -> Dict[str, Any]:
    """Assemble the single per-sport cohesive read dict (understanding + numbers + prose)."""
    sport_l = sport.lower()
    read = build_sport_read(sport_l, jd=jd, root=root, use_llm=use_llm, top_k=top_k)
    landscape = build_concept_landscape(sport_l, root=root, top_k=top_k)
    return {
        "sport": sport_l,
        "banner": _BANNER,
        "read": read,
        "concept_landscape": landscape,
        "knowledge_layers": _knowledge_layers(sport_l, root),
        "scoreboards": _scoreboard_pointer(root),
        "edge_claimed": False,
    }


def render_markdown(cr: Dict[str, Any]) -> str:
    """Render the cohesive read as ONE Markdown document."""
    sport = cr.get("sport", "unknown").upper()
    L: List[str] = [
        f"# Cohesive Read — {sport}", "",
        f"> **{cr.get('banner', '')}**", "",
        _read_md(cr["read"]), "",
        _land_md(cr["concept_landscape"]),
    ]
    layers = cr.get("knowledge_layers", [])
    if layers:
        L.append("### Knowledge Layers _(every artifact the rebuild produced — descriptive)_")
        for k in layers:
            ex = f" — _{k['excerpt']}_" if k.get("excerpt") else ""
            L.append(f"- **{k['label']}**  `{k['provenance']}`{ex}")
        L.append("")
    sb = cr.get("scoreboards", {})
    L.append("### Engine Quality _(calibration, not edge)_")
    if sb:
        for key, prov in sb.items():
            L.append(f"- {key} scoreboard: `{prov}`")
    else:
        L.append("- _(no scoreboard artifact found — run the brain rebuild first)_")
    L += ["", "> Numbers are calibration metrics from the gate/engine; the LLM writes "
          "prose only. No un-gated pick is produced; no edge is claimed.", ""]
    return "\n".join(L)


def write_reads(sports: Optional[List[str]] = None,
                root: Optional[Path] = None) -> List[str]:
    """Write per-sport _Cohesive_Read.md into the organized vault; return paths written."""
    eff = _resolve_root(Path(root) if root else None)
    if eff is None:
        return []
    written: List[str] = []
    for sp in (sports or _SPORTS):
        # Pass the validated predictor's demo JointDistribution so assemble_read runs and the
        # read carries a REAL calibrated surface (the central cohesion fix). Guarded -> None.
        jd = None
        try:
            from scripts.platformkit.predictor_jd import get_demo_jd  # noqa: PLC0415
            jd = get_demo_jd(sp)
        except Exception:  # noqa: BLE001 — degrade gracefully to surface=None
            jd = None
        cr = build_cohesive_read(sp, jd=jd, root=root, use_llm=False)
        out = eff / _SPORT_DIRS.get(sp, sp.upper()) / "_Cohesive_Read.md"
        if not out.parent.is_dir():
            continue
        out.write_text(render_markdown(cr), encoding="utf-8")
        written.append(str(out))
    return written


def render_index(root: Optional[Path] = None) -> str:
    """Render the ONE cross-sport landing page linking every per-sport cohesive read."""
    eff = _resolve_root(Path(root) if root else None)
    L: List[str] = [
        "---\ntags: [organized, cohesive-index]\n---",
        "# Cohesive Brain — System Index", "",
        f"> **{_BANNER}**", "",
        "One honest read per sport tying brain understanding + the concept graph + the "
        "calibrated engine + a self-checked narrative into a single document.", "",
        "## Per-Sport Cohesive Reads",
    ]
    for sp in _SPORTS:
        d = _SPORT_DIRS[sp]
        if eff is not None and (eff / d / "_Cohesive_Read.md").is_file():
            land = build_concept_landscape(sp, root=root)
            L.append(f"- [[{d}/_Cohesive_Read|{d} — Cohesive Read]]  "
                     f"_({land['n_nodes']} concept nodes · {land['n_families']} families)_")
    L += ["", "## Engine Quality _(calibration, not edge)_"]
    for key, rel in _SCOREBOARDS.items():
        if eff is not None and (eff / rel).is_file():
            L.append(f"- [[{Path(rel).stem}|{key} scoreboard]]")
    L += ["", "> The LLM scouts/synthesizes/explains; the GATE owns every number. "
          "No un-gated pick; no edge — markets are efficient; calibration is not edge.", ""]
    return "\n".join(L)


def write_index(root: Optional[Path] = None) -> Optional[str]:
    """Write the cross-sport _Cohesive_Index.md landing page; return its path or None."""
    eff = _resolve_root(Path(root) if root else None)
    if eff is None or not (eff / "_Index").is_dir():
        return None
    out = eff / "_Index" / "_Cohesive_Index.md"
    out.write_text(render_index(root), encoding="utf-8")
    return str(out)


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="cohesive_read: one honest per-sport read across every layer.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--all", action="store_true", help="all four sports")
    ap.add_argument("--write", action="store_true", help="write _Cohesive_Read.md per sport")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--use-llm", action="store_true", default=False)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        paths = write_reads(None if a.all else [a.sport])
        for p in paths:
            print(f"wrote {p}")
        idx = write_index()
        if idx:
            print(f"wrote {idx}")
        return 0
    sports = _SPORTS if a.all else [a.sport]
    for sp in sports:
        cr = build_cohesive_read(sp, use_llm=a.use_llm if a.use_llm else None,
                                 top_k=a.top_k)
        if a.json:
            print(json.dumps(cr, indent=2, default=str))
        else:
            print(render_markdown(cr))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
