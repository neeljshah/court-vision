"""archetype_taxonomy.py — Cross-sport archetype taxonomy meta-note generator.

Scans vault/Sports/<Sport>/{Playstyles,Archetypes}/*.md, parses archetype
names + tags + one-line descriptions, groups them under cross-sport THEMES,
and writes vault/Sports/_Archetype_Taxonomy.md.

Public API::

    from scripts.platformkit.atlas.archetype_taxonomy import build_taxonomy
    out = build_taxonomy()                    # auto-detects repo vault/Sports
    out = build_taxonomy(vault_sports_dir)    # explicit path

No person names; teams referenced only via existing [[wikilinks]]; Py 3.9.
"""
from __future__ import annotations

import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Theme table: (id, display_name, shared_idea, match_keywords)
# A note matches a theme when ANY keyword appears in slug+description+tags.
# ---------------------------------------------------------------------------
_THEMES: List[Tuple[str, str, str, List[str]]] = [
    ("aggressive_scorers", "Aggressive Scorers / High-Tempo Attack",
     "Offense-first style: maximise scoring output, dominate possession, accept defensive "
     "trade-offs. Manifests as high usage, high run-scoring, heavy serve, or relentless attack.",
     ["high_usage", "high usage", "scoring_guard", "creator", "power_run",
      "attacking", "high-scoring", "fast_court", "big_server", "server",
      "offensive", "high_usage_creator"]),

    ("defensive_specialists", "Defensive Specialists / Low-Risk",
     "Defense-first identity: suppress opponent scoring, protect leads, minimise concessions. "
     "Low-scoring contests are the expected output across all sports.",
     ["defensive", "anchor", "3_and_d", "three_and_d", "low-block",
      "pitching", "run_prevention", "low_scoring", "grinder", "defense"]),

    ("balanced_allrounders", "Balanced All-Rounders",
     "Near-median profile on both sides; adaptable to opposition and context without a single "
     "tactical extreme dominating. Consistent performers across varied conditions.",
     ["balanced", "versatile", "all_court", "all-court", "contender",
      "playmaking", "grand_slam", "two-way", "two_way"]),

    ("high_variance", "High-Variance / Unpredictable",
     "Wildcard identity: contests swing sharply; high peaks and deep troughs occur frequently. "
     "Box-score distributions are wide and upsets happen in either direction.",
     ["high_variance", "high-variance", "entertainer", "leaky", "high-risk",
      "variance", "deficit", "rebuilding", "run_deficit", "btts"]),

    ("surface_specialists", "Surface / Condition Specialists",
     "Performance conditional on environment: a specific surface, venue, or structural trait "
     "unlocks consistently superior results; output degrades when conditions are absent.",
     ["clay", "grass", "hard_court", "hard court", "surface", "specialist",
      "left_handed", "left-handed", "strong_at_home", "home_fortress", "home-fortress"]),

    ("role_players", "Role Players / System Cogs",
     "Lower-profile contributors whose value is systemic, not individual. Minimal possession "
     "demand; efficiency within a defined role; journeymen and depth that stabilise the whole.",
     ["bench_contributor", "bench contributor", "low_usage", "low usage",
      "connector", "journeyman", "draw-prone", "draw_prone", "role"]),

    ("playmakers_orchestrators", "Playmakers / Orchestrators",
     "Creation-oriented identity: primary source of assists or ball movement. Generates "
     "opportunity for others rather than accumulating individual scoring.",
     ["playmaking", "playmaker", "creator", "high_usage_creator", "assist", "orchestrat"]),
]

_SUBDIRS = ("Playstyles", "Archetypes")
_OUT_FILENAME = "_Archetype_Taxonomy.md"
_H1_RE = re.compile(r"^#\s+(.+)", re.MULTILINE)
_ITALIC_RE = re.compile(r"^\*(.+?)\*\s*$", re.MULTILINE)


@dataclass
class _Entry:
    sport: str
    subdir: str
    slug: str
    display_name: str
    description: str
    link: str
    tags: List[str] = field(default_factory=list)


def _parse_note(path: pathlib.Path, sport: str, subdir: str) -> Optional[_Entry]:
    """Parse one .md file; returns None for index files or on I/O error."""
    if path.stem.startswith("_"):
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    h1 = _H1_RE.search(text)
    name = re.sub(r"^Playstyle:\s*", "", h1.group(1) if h1 else path.stem.replace("_", " ")).strip()
    italic = _ITALIC_RE.search(text)
    desc = italic.group(1).strip() if italic else ""
    if not desc:
        m = re.search(r"##\s+Description\s*\n(.+?)(?=\n##|\Z)", text, re.DOTALL)
        if m:
            first = m.group(1).strip().splitlines()[0].strip()
            if first and not first.startswith("#"):
                desc = first
    tags = re.findall(r"^\s*-\s+(\S+)", text, re.MULTILINE) + re.findall(r"#([\w/]+)", text)
    return _Entry(sport=sport, subdir=subdir, slug=path.stem,
                  display_name=name, description=desc,
                  link=f"[[{sport}/{subdir}/{path.stem}]]", tags=list(dict.fromkeys(tags)))


def _matches(entry: _Entry, keywords: List[str]) -> bool:
    hay = (entry.slug + " " + entry.description + " " + " ".join(entry.tags)).lower().replace("-", "_")
    return any(kw.lower().replace("-", "_") in hay for kw in keywords)


def _scan(sport_dir: pathlib.Path) -> List[_Entry]:
    entries: List[_Entry] = []
    for sub in _SUBDIRS:
        d = sport_dir / sub
        if d.is_dir():
            for md in sorted(d.glob("*.md")):
                e = _parse_note(md, sport_dir.name, sub)
                if e:
                    entries.append(e)
    return entries


def _render(themes_data: List[Tuple[str, str, List[_Entry]]], sports: List[str]) -> str:
    total = sum(len(e) for _, _, e in themes_data)
    L: List[str] = [
        "---",
        "tags: [archetype, taxonomy, cross-sport, meta]",
        f"generated: {time.strftime('%Y-%m-%d')}",
        "---", "",
        "# Archetype Taxonomy — Cross-Sport Playstyle Meta-Note", "",
        "> Auto-generated by `scripts/platformkit/atlas/archetype_taxonomy.py` — do not hand-edit.",
        "> Re-run `build_taxonomy()` to refresh.", "",
        "Up: [[_Hub]]", "", "---", "",
        "## Overview", "",
        "Cross-sport archetype mapping grouped under sport-blind tactical themes.",
        "No individual entity names appear; teams referenced via existing wikilinks only.", "",
        "| Stat | Value |", "|------|-------|",
        f"| Sports scanned | **{len(sports)}** ({', '.join(sports)}) |",
        f"| Themes defined | **{len(themes_data)}** |",
        f"| Total archetype links mapped | **{total}** |",
        "", "---", "",
    ]
    for display_name, shared_idea, entries in themes_data:
        L += [f"## {display_name}", "", f"*{shared_idea}*", ""]
        if not entries:
            L += ["> No archetypes matched this theme in the current vault.", ""]
            continue
        by_sport: Dict[str, List[_Entry]] = {}
        for e in entries:
            by_sport.setdefault(e.sport, []).append(e)
        for sport, sport_entries in sorted(by_sport.items()):
            L.append(f"**{sport.replace('_', ' ')}**")
            L.append("")
            for e in sport_entries:
                suffix = f" — {e.description}" if e.description else ""
                L.append(f"- {e.link}{suffix}")
            L.append("")
    L += ["---", "",
          f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
          f"{len(sports)} sport(s) · {total} archetype link(s)*"]
    return "\n".join(L) + "\n"


def build_taxonomy(vault_sports_dir: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Scan vault_sports_dir, group archetypes into cross-sport themes, write taxonomy note.

    Parameters
    ----------
    vault_sports_dir:
        Path to vault/Sports.  Auto-detected from repo root when None.

    Returns
    -------
    pathlib.Path
        Written _Archetype_Taxonomy.md path.
    """
    if vault_sports_dir is None:
        vault_sports_dir = pathlib.Path(__file__).resolve().parents[3] / "vault" / "Sports"
    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    all_entries: List[_Entry] = []
    sports: List[str] = []
    for d in sorted(d for d in vault_sports_dir.iterdir() if d.is_dir() and not d.name.startswith("_")):
        entries = _scan(d)
        if entries:
            all_entries.extend(entries)
            sports.append(d.name)

    themes_data: List[Tuple[str, str, List[_Entry]]] = []
    for _id, display, idea, kws in _THEMES:
        matched = [e for e in all_entries if _matches(e, kws)]
        themes_data.append((display, idea, matched))

    content = _render(themes_data, sports)
    out = vault_sports_dir / _OUT_FILENAME
    return write_note(out, content)


if __name__ == "__main__":
    import sys
    vault_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    out = build_taxonomy(vault_dir)
    print(f"Written: {out}")
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ") and line != "## Overview":
            print(f"  Theme: {line[3:]}")
