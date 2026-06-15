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
_SCOREBOARDS = {
    "platform": "_Index/_Platform_Scoreboard.md",
    "calibration": "_Index/_Calibration_Scoreboard.md",
}
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
    sport_dirs = {"nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis"}
    written: List[str] = []
    for sp in (sports or _SPORTS):
        cr = build_cohesive_read(sp, root=root, use_llm=False)
        out = eff / sport_dirs.get(sp, sp.upper()) / "_Cohesive_Read.md"
        if not out.parent.is_dir():
            continue
        out.write_text(render_markdown(cr), encoding="utf-8")
        written.append(str(out))
    return written


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
