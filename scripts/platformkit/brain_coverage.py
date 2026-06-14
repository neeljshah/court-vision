"""brain_coverage.py — the brain's green-cell COVERAGE map (meta-cognition).

06_INTELLIGENCE's honest success metric is **coverage**, not survivor count: which
(sport x artifact) cells the organized brain actually has, and where the gaps are.
This walks ``vault/_Organized/`` and reports, per sport, the presence + size of each
intelligence artifact — so the platform (and the next wave) knows what it knows and
exactly where to deepen.

Honest: a coverage map is an intelligence inventory, NOT a betting edge. No number
here is a prediction.  Some gaps are STRUCTURAL and correct (tennis = player-level,
no team base-rates; soccer = outside the binary calibrated stack, no model card).

CLI: ``python -m scripts.platformkit.brain_coverage [<root>] [--write] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPORT_DIRS = ["NBA", "MLB", "Soccer", "Tennis"]

# (label, relative path under <SPORT>/, is_dir) — the expected artifacts.
_ARTIFACTS = [
    ("Teams", "Teams", True), ("Archetypes", "Archetypes", True),
    ("Schemes", "Schemes", True), ("Trends", "Trends", True),
    ("Reference", "Reference", True), ("Digest", "_Digest.md", False),
    ("Read", "_Read.md", False), ("ModelCard", "_Model_Card.md", False),
    ("BaseRates", "_Team_Base_Rates_EB.md", False),
]
# Structural gaps that are CORRECT, not missing work (kept honest in the report).
_EXPECTED_ABSENT = {
    ("Tennis", "Teams"), ("Tennis", "BaseRates"), ("Tennis", "Schemes"),
    ("Soccer", "ModelCard"), ("Soccer", "BaseRates"),  # soccer HAS schemes
    ("MLB", "Schemes"),
}


def _count_md(path: Path) -> int:
    return sum(1 for _ in path.rglob("*.md")) if path.is_dir() else 0


def build_coverage(organized_root: Optional[Path] = None) -> Dict:
    """Build the per-sport x artifact coverage matrix from *organized_root*."""
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    sports: Dict[str, Dict] = {}
    real_gaps: List[str] = []
    for sp in _SPORT_DIRS:
        sdir = root / sp
        if not sdir.is_dir():
            continue
        cells: Dict[str, Dict] = {}
        for label, rel, is_dir in _ARTIFACTS:
            target = sdir / rel
            present = target.is_dir() if is_dir else target.is_file()
            count = _count_md(target) if is_dir else (1 if present else 0)
            cells[label] = {"present": present, "count": count}
            if not present and (sp, label) not in _EXPECTED_ABSENT:
                real_gaps.append(f"{sp}/{label}")
        have = sum(1 for c in cells.values() if c["present"])
        expected = len(_ARTIFACTS) - sum(1 for a in _ARTIFACTS if (sp, a[0]) in _EXPECTED_ABSENT)
        cells_present = have
        sports[sp] = {"cells": cells, "present": cells_present,
                      "expected": expected,
                      "complete": cells_present >= expected}
    return {"root": str(root), "sports": sports, "real_gaps": sorted(set(real_gaps)),
            "n_sports": len(sports),
            "note": "coverage = intelligence inventory, NOT a betting edge"}


def render_markdown(rep: Dict) -> str:
    labels = [a[0] for a in _ARTIFACTS]
    lines = [
        "---\ntags: [organized, coverage, meta]\n---",
        "# Brain Coverage Map — green-cell inventory (meta-cognition)\n",
        f"> **{rep['note']}.** Coverage is 06's honest success metric (not survivor "
        "count). `o` = structural-absent-by-design.\n",
        "| Sport | " + " | ".join(labels) + " | Complete |",
        "|-------|" + "|".join(["---"] * len(labels)) + "|:--------:|",
    ]
    for sp, info in rep["sports"].items():
        row = [sp]
        for lab in labels:
            c = info["cells"][lab]
            if c["present"]:
                row.append(f"Y({c['count']})" if c["count"] > 1 else "Y")
            else:
                row.append("o" if (sp, lab) in _EXPECTED_ABSENT else "**X**")
        row.append("YES" if info["complete"] else "no")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    if rep["real_gaps"]:
        lines.append("**Real gaps (deepenable):** " + ", ".join(rep["real_gaps"]))
    else:
        lines.append("**No real gaps** — every non-structural cell is covered.")
    lines.append("\n_o = structural-absent-by-design (tennis player-level / soccer "
                 "outside binary stack / MLB no schemes). Not a gap._")
    return "\n".join(lines) + "\n"


def write_artifact(rep: Dict, organized_root: Optional[Path] = None) -> str:
    root = organized_root or (_REPO_ROOT / "vault" / "_Organized")
    out = Path(root) / "_Index" / "_Coverage.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(rep), encoding="utf-8")
    return str(out)


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_coverage(Path(root_arg) if root_arg else None)
    if "--write" in argv:
        rep["artifact"] = write_artifact(rep)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"brain_coverage: {rep['root']}  ({rep['n_sports']} sports)\nNOTE: {rep['note']}\n")
    for sp, info in rep["sports"].items():
        present = [lab for lab, c in info["cells"].items() if c["present"]]
        print(f"  [{sp:<7}] {info['present']}/{info['expected']} "
              f"{'COMPLETE' if info['complete'] else 'partial'} -> {', '.join(present)}")
    print(f"\n  real gaps: {rep['real_gaps'] or 'none (all non-structural cells covered)'}")
    if rep.get("artifact"):
        print(f"  artifact -> {rep['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
