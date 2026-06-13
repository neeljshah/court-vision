"""scripts.platformkit.atlas.build_brain_index — Highest-level person-free brain MOC.

Emits ONE dense map-of-content hub at ``vault/_Index/_Brain.md`` linking every
*person-free* intelligence note (playstyles, archetypes, schemes, positions,
style-matchups, style-trends, scheme-transitions) across all sports.  The Obsidian
graph view then becomes a clean constellation centred on a few dense nodes (this
hub + each sport family) instead of a 3000-note hairball.

PERSON-FREE: links only archetype/scheme/style/playstyle notes — never a person.
A person-named note (``<player-id>_name.md`` or a lowercase ``firstname_lastname``)
in a scanned dir is SKIPPED and counted as "skipped (non-person-free)".  Title-cased
styles, digit archetypes (``3_and_D_Wing``), year files and ``_``-meta notes kept.
Honest framing: an intelligence *map*, not a betting edge — calibration is not edge.

CLI: ``python -m scripts.platformkit.atlas.build_brain_index [vault_dir]``.
Discipline: Py3.9, stdlib-only, ≤ 300 LOC; reuses obsidian_emit.write_note.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.atlas.obsidian_emit import write_note  # noqa: E402

# ---------------------------------------------------------------------------
# Manifest: where person-free notes live + how to label them in the hub.
# ---------------------------------------------------------------------------

# Per-sport family subdirs under vault/Sports/<Sport>/.  (subdir, label, name_check)
# name_check=True (Trends dirs only) adds the lowercase personal-name skip on top of
# the universal id-prefix skip — those dirs mix person notes (``damian_lillard``)
# with meta.  Other families are person-free *by directory* and legitimately use
# snake_case for schemes/archetypes (``drop_coverage``), so name_check must stay off.
_SPORT_FAMILIES: List[Tuple[str, str, bool]] = [
    ("Playstyles", "Playstyles", False),
    ("Archetypes", "Archetypes", False),
    ("StyleMatchups", "Style Matchups", False),
    ("StyleTrends", "Style Trends", False),
    ("SchemeTransitions", "Scheme Transitions", False),
    ("Trends", "Trends", True),
]

# Cross-sport person-free intelligence families under vault/Intelligence/.
_INTEL_FAMILIES: List[Tuple[str, str, bool]] = [
    ("Archetypes", "Archetypes", False),
    ("Schemes", "Schemes", False),
    ("Positions", "Positions", False),
    ("Trends", "Trends", True),
]

# Cross-sport meta notes (basename, label) that may live at vault/_Index/ or
# vault/Sports/.  Linked from the "Cross-sport meta" section when present.
_META_NOTES: List[Tuple[str, str]] = [
    ("_World_Model", "World model"),
    ("_Base_Rates", "Base rates"),
    ("_Archetype_Taxonomy", "Archetype taxonomy"),
    ("_Intelligence_Overview", "Intelligence overview"),
    ("_Signals_Hub", "Signals hub"),
    ("_Calibration_Segments", "Calibration segments"),
    ("_GraphStats", "Graph stats"),
    ("_Graph_Health", "Graph health"),
]

# A <player-id>_name file: >=4 leading digits then underscore then a letter.
_PLAYER_ID_RE = re.compile(r"^\d{4,}_[A-Za-z]")
# A bare personal name: all-lowercase tokens joined by _ or - (e.g.
# ``aaron_holiday``, ``shai_gilgeous-alexander``) with no digits.  Title-cased
# style names and digit-archetypes do NOT match (they carry uppercase/digits).
_PERSON_NAME_RE = re.compile(r"^[a-z]+(?:[_-][a-z]+)+$")

OUT_RELPATH = Path("_Index") / "_Brain.md"


def _is_person_file(stem: str, name_check: bool = True) -> bool:
    """True if *stem* (basename without .md) names a person, not a style/scheme.

    Always skips id-prefixed files (``101108_chris_paul``).  When *name_check* is
    True it additionally skips bare lowercase multi-token names (``aaron_holiday``,
    ``shai_gilgeous-alexander``).  *name_check* must be False for person-free
    snake_case families (schemes/archetypes like ``drop_coverage``,
    ``high_usage_scorer``) where the name pattern would cause false positives.

    Not a person (either mode): ``All_Court_Baseliner``, ``3_and_D_Wing``,
    ``2015``, ``Balanced`` (single token).
    """
    if _PLAYER_ID_RE.match(stem):
        return True
    if name_check:
        return bool(_PERSON_NAME_RE.match(stem))
    return False


def _is_meta_note(stem: str) -> bool:
    """``_``-prefixed index/meta notes are kept but not treated as person files."""
    return stem.startswith("_")


def _scan_family(family_dir: Path, name_check: bool = False) -> Tuple[List[str], int]:
    """Return (kept_basenames_sorted, skipped_person_count) for one directory.

    Missing dir → ([], 0).  Only top-level ``*.md`` files are scanned (nested
    sub-dirs are their own families and handled separately).  *name_check* enables
    the lowercase personal-name skip (Trends families only).
    """
    if not family_dir.is_dir():
        return [], 0
    kept: List[str] = []
    skipped = 0
    for md in family_dir.glob("*.md"):
        stem = md.stem
        if _is_meta_note(stem):
            kept.append(stem)
            continue
        if _is_person_file(stem, name_check=name_check):
            skipped += 1
            continue
        kept.append(stem)
    return sorted(kept), skipped


def _wikilinks(basenames: List[str]) -> str:
    """Render a dense ``· ``-joined run of [[wikilinks]] (basename only)."""
    return " · ".join(f"[[{b}]]" for b in basenames)


def _discover_sports(sports_root: Path) -> List[str]:
    """Sorted display names of sport folders under vault/Sports/ (skip _-prefixed)."""
    if not sports_root.is_dir():
        return []
    return sorted(
        p.name for p in sports_root.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )


def _build_sport_section(sports_root: Path) -> Tuple[List[str], int, int, int]:
    """Build the per-sport lines.  Returns (lines, links, skipped, n_families)."""
    lines: List[str] = []
    total_links = total_skipped = n_families = 0
    for sport in _discover_sports(sports_root):
        sport_dir = sports_root / sport
        fam_lines: List[str] = []
        sport_links = 0
        for subdir, label, name_check in _SPORT_FAMILIES:
            kept, skipped = _scan_family(sport_dir / subdir, name_check=name_check)
            total_skipped += skipped
            if not kept:
                continue
            n_families += 1
            sport_links += len(kept)
            fam_lines.append(f"- **{label}** ({len(kept)}): {_wikilinks(kept)}")
        if not fam_lines:
            continue
        total_links += sport_links
        lines.append(f"### {sport.replace('_', ' ')} ({sport_links})")
        lines.append(f"[[{sport}/_Index]]")
        lines.extend(fam_lines)
        lines.append("")
    return lines, total_links, total_skipped, n_families


def _build_intel_section(intel_root: Path) -> Tuple[List[str], int, int]:
    """Build the cross-sport Intelligence-family lines.  Returns (lines, links, skipped)."""
    lines: List[str] = []
    total_links = total_skipped = 0
    for subdir, label, name_check in _INTEL_FAMILIES:
        kept, skipped = _scan_family(intel_root / subdir, name_check=name_check)
        total_skipped += skipped
        if not kept:
            continue
        total_links += len(kept)
        lines.append(f"- **{label}** ({len(kept)}): {_wikilinks(kept)}")
    return lines, total_links, total_skipped


def _build_meta_section(vault_dir: Path) -> Tuple[List[str], int]:
    """Link any present cross-sport meta notes.  Returns (lines, count)."""
    search_dirs = [vault_dir / "_Index", vault_dir / "Sports", vault_dir]
    lines = [f"- **{label}**: [[{stem}]]" for stem, label in _META_NOTES
             if any((d / f"{stem}.md").is_file() for d in search_dirs)]
    return lines, len(lines)


def _render(
    vault_dir: Path,
    sport_lines: List[str], sport_links: int, sport_skipped: int, n_families: int,
    intel_lines: List[str], intel_links: int, intel_skipped: int,
    meta_lines: List[str], meta_count: int,
) -> str:
    today = date.today().isoformat()
    total_links = sport_links + intel_links
    total_skipped = sport_skipped + intel_skipped
    header = (
        "---\ntags: [memory-graph, brain, moc, person-free, index]\n"
        f"updated: {today}\n---\n"
        "# Brain — Person-Free Intelligence Map\n\n"
        "> Highest-level map-of-content for the multi-sport knowledge graph.\n"
        "> **Person-free:** this hub links only playstyles, archetypes, schemes,\n"
        "> positions, style-matchups and trends — never a player or team by name.\n"
        "> **Calibration is not edge:** this is an intelligence *map*, not a betting\n"
        "> claim; it links knowledge, it never asserts a market lift.\n"
        "> Auto-generated by `scripts/platformkit/atlas/build_brain_index.py` —\n"
        "> edit the generator, not this file.\n\n"
        f"**Index:** {total_links} person-free notes linked across {n_families} "
        f"sport families + {intel_links} cross-sport intelligence notes · "
        f"{meta_count} meta note(s) · {total_skipped} skipped (non-person-free)."
        "\n\n---\n\n"
    )
    sports_body = "\n".join(sport_lines).rstrip() if sport_lines else "_(none found)_"
    sports = (
        f"## Sports\n\nPer-sport person-free families ({sport_links} notes, "
        f"{sport_skipped} skipped).\n\n{sports_body}\n\n---\n\n"
    )
    intel_body = "\n".join(intel_lines).rstrip() if intel_lines else "_(none found)_"
    intel = (
        "## Cross-sport intelligence\n\nShared archetype / scheme / position / "
        f"trend families ({intel_links} notes, {intel_skipped} skipped).\n\n"
        f"{intel_body}\n\n---\n\n"
    )
    meta_body = "\n".join(meta_lines).rstrip() if meta_lines else "_(none present)_"
    meta = (
        "## Cross-sport meta\n\nWorld model / base rates / taxonomy synthesis "
        f"notes ({meta_count}).\n\n{meta_body}\n\n---\n\n"
    )
    footer = (
        "#memory-graph #brain #moc #person-free #index\n\n*Generated "
        f"{today} by `scripts/platformkit/atlas/build_brain_index.py` from "
        f"`{vault_dir.name}/`*\n"
    )
    return header + sports + intel + meta + footer


def build_brain_index(
    vault_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
    stats: Optional[Dict[str, int]] = None,
) -> Path:
    """Scan person-free vault dirs and emit the ``_Index/_Brain.md`` MOC.

    *vault_dir* defaults to ``<repo_root>/vault``; *out_path* to
    ``<vault_dir>/_Index/_Brain.md``.  Pass a *stats* dict to receive the scan
    counts (sport_links, sport_skipped, n_families, intel_links, intel_skipped,
    meta).  Returns the written MOC path.  Robust to missing dirs (empty
    sections, no crash); deterministic (identical input → byte-identical output).
    """
    vault_dir = Path(vault_dir) if vault_dir is not None else (_REPO_ROOT / "vault")
    out_path = Path(out_path) if out_path is not None else (vault_dir / OUT_RELPATH)

    sport_lines, sport_links, sport_skipped, n_families = _build_sport_section(vault_dir / "Sports")
    intel_lines, intel_links, intel_skipped = _build_intel_section(vault_dir / "Intelligence")
    meta_lines, meta_count = _build_meta_section(vault_dir)

    if stats is not None:
        stats.update(sport_links=sport_links, sport_skipped=sport_skipped,
                     n_families=n_families, intel_links=intel_links,
                     intel_skipped=intel_skipped, meta=meta_count)
    body = _render(
        vault_dir,
        sport_lines, sport_links, sport_skipped, n_families,
        intel_lines, intel_links, intel_skipped,
        meta_lines, meta_count,
    )
    return write_note(out_path, body)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    vault_dir = Path(argv[0]) if argv else (_REPO_ROOT / "vault")
    st: Dict[str, int] = {}
    out = build_brain_index(vault_dir=vault_dir, stats=st)
    try:
        disp = str(out.relative_to(_REPO_ROOT))
    except ValueError:
        disp = str(out)
    sep = "=" * 60
    print(f"\n{sep}\nBrain index (person-free MOC) written")
    print(f"  MOC      : {disp}")
    print(f"  Sports   : {st['sport_links']} note(s) across {st['n_families']} family(ies), {st['sport_skipped']} skipped")
    print(f"  Intel    : {st['intel_links']} note(s), {st['intel_skipped']} skipped")
    print(f"  Meta     : {st['meta']} note(s)")
    print(f"  Skipped  : {st['sport_skipped'] + st['intel_skipped']} non-person-free note(s)")
    print(sep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
