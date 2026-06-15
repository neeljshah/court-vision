"""brain_concept_map — connect the concept-node families into one navigable graph.

``brain_concept_nodes`` emits many ``<SPORT>/<FAMILY>/<slug>.md`` nodes plus a per-family
``_Index.md`` hub.  This module ties those family hubs together so the graph view is one
connected, organized web rather than floating clusters:

  * writes ``<SPORT>/_Concept_Map.md`` — a per-sport hub linking every concept-family
    index (grouped, with node counts), and
  * patches ``<SPORT>/_Index.md`` (idempotently) to add a "## Concept Graph" link to the
    Concept Map, so the concept web hangs off the sport hub (and thus the top Brain MOC).

A concept-family hub is identified by the ``concept`` tag its ``_Index.md`` frontmatter
carries (written by ``brain_concept_nodes._frontmatter``) — so legacy category indexes
(Archetypes / Schemes / Trends / Reference) are never mistaken for concept families.

HONEST: descriptive intelligence map; markets efficient; calibration is not edge; no edge
claimed. Idempotent, deterministic, pure stdlib.

CLI: ``python -m scripts.platformkit.brain_concept_map [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = (
    "> **Intelligence map; markets efficient; calibration is not edge; no edge "
    "claimed.** A navigation hub over the person-free concept graph."
)
_MARK = "## Concept Graph"          # idempotency marker patched into a sport _Index


def _is_concept_index(index_path: Path) -> bool:
    """True if a ``<sport>/<family>/_Index.md`` frontmatter carries the ``concept`` tag."""
    try:
        head = index_path.read_text(encoding="utf-8", errors="replace")[:400]
    except OSError:
        return False
    # frontmatter tag line, e.g. "tags: [organized, nba, situational, concept, person-free]"
    for line in head.splitlines():
        if line.strip().lower().startswith("tags:") and "concept" in line.lower():
            return True
    return False


def _family_count(index_path: Path) -> int:
    """Number of concept nodes a family hub lists (``- [[slug|title]]`` lines)."""
    try:
        txt = index_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for ln in txt.splitlines() if ln.lstrip().startswith("- [["))


def _scan_sport(sport_dir: Path) -> List[Tuple[str, int]]:
    """Ordered (family, node_count) for each concept family under a sport dir."""
    out: List[Tuple[str, int]] = []
    for child in sorted(p for p in sport_dir.iterdir() if p.is_dir()):
        idx = child / "_Index.md"
        if idx.is_file() and _is_concept_index(idx):
            out.append((child.name, _family_count(idx)))
    return out


def _render_map(sport: str, families: List[Tuple[str, int]]) -> str:
    total = sum(n for _, n in families)
    rows = "\n".join(
        f"- [[{fam}/_Index|{fam}]] — {n} node(s)" for fam, n in families
    ) or "_(no concept families yet)_"
    return (
        "---\ntags: [organized, " + sport.lower() + ", concept-map, person-free]\n---\n"
        f"# {sport} — Concept Map\n\n"
        f"{_BANNER}\n\n"
        f"{len(families)} concept famil(ies), {total} concept node(s) total. Each family "
        f"hub links its dense person-free nodes; nodes cross-link related concepts.\n\n"
        "## Concept Families\n\n"
        f"{rows}\n"
    )


def _patch_index(index_path: Path, write: bool) -> bool:
    """Idempotently add a Concept-Graph link to a sport ``_Index.md``. Returns changed."""
    try:
        txt = index_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if _MARK in txt:
        return False
    block = (
        f"\n{_MARK}\n\n"
        "The dense person-free concept web (situational, tactical, stat-signature, "
        "mechanism, matchup, sub-archetype, phase, environment, risk and form nodes):\n\n"
        "- [[_Concept_Map|Concept Map]]\n"
    )
    if write:
        index_path.write_text(txt.rstrip() + "\n" + block, encoding="utf-8")
    return True


def build_concept_map(organized_root=None, write: bool = True) -> dict:
    """Write per-sport Concept-Map hubs and patch sport indexes. Idempotent."""
    if organized_root is None:
        organized_root = _REPO_ROOT / "vault" / "_Organized"
    organized_root = Path(organized_root)
    by_sport: Dict[str, int] = {}
    patched: List[str] = []
    n_maps = 0
    if not organized_root.is_dir():
        return {"n_maps": 0, "by_sport": {}, "patched": [], "_note": "no organized root"}
    for sport_dir in sorted(p for p in organized_root.iterdir() if p.is_dir()):
        if sport_dir.name.startswith("_"):
            continue                                   # skip _Index/ etc.
        families = _scan_sport(sport_dir)
        if not families:
            continue
        if write:
            (sport_dir / "_Concept_Map.md").write_text(
                _render_map(sport_dir.name, families), encoding="utf-8"
            )
        n_maps += 1
        by_sport[sport_dir.name] = sum(n for _, n in families)
        sport_index = sport_dir / "_Index.md"
        if sport_index.is_file() and _patch_index(sport_index, write):
            patched.append(sport_dir.name)
    return {
        "n_maps": n_maps,
        "by_sport": by_sport,
        "patched": patched,
        "_note": ("descriptive navigation hub; markets efficient; calibration is not "
                  "edge; no edge claimed"),
    }


def _main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    positional = [a for a in argv if not a.startswith("--")]
    root = Path(positional[0]) if positional else None
    rep = build_concept_map(organized_root=root, write=True)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
    else:
        print(f"concept map: {rep['n_maps']} sport hub(s); "
              f"patched indexes: {', '.join(rep['patched']) or 'none'}")
        for sport, n in sorted(rep["by_sport"].items()):
            print(f"  {sport}: {n} concept node(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["build_concept_map"]
