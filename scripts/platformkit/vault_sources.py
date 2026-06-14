"""vault_sources.py — Per-sport source descriptors + small parsers for the multi-sport
Obsidian vault organizer.

Defines a frozen SportSpec dataclass describing WHERE each sport's notes live inside
``vault/`` and what categories to include vs drop (see the inline field comments on
the dataclass).  The ``source_specs`` factory returns one SportSpec per supported
sport.  Also exposes the person-FREE ``build_identity`` team-hub renderer and small
sport-generic parsers.  Pure stdlib; NO pandas/pyarrow imports at module top.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from scripts.platformkit.arch_intel_data import ARCH_INTEL_RAW

# --- sport-generic parsers used by vault_organize_multi --------------------- #

_PLAYER_ID_RE = re.compile(r"^(\d{3,})_")
_TEAM_LINE_RE = re.compile(r"^\*\*Team:\*\*\s*\[\[([A-Za-z0-9_]+)\]\]")
_POS_RE = re.compile(r"\*\*Position:?\*\*\s*([A-Za-z/ -]+)")
_USAGE_RE = re.compile(r"\*\*Usage rate:?\*\*\s*([\d.]+%?)")
# person-free structured team fields (scheme/driver tags, density, composite z)
_DOM_TAG_RE = re.compile(r"\*\*Dominant tag:?\*\*\s*([A-Z][A-Z \-]+)")
_ALL_TAGS_RE = re.compile(r"\*\*All tags:?\*\*\s*([A-Z][A-Z ,|\-]+)")
_DENSITY_RE = re.compile(r"data_density_tier:?\*{0,2}\s*([a-z]+)")
_COMPOSITE_RE = re.compile(r"Composite Intensity\*{0,2}\s*\|\s*([+\-]?[\d.]+)")


def parse_player_id(stem: str) -> Optional[str]:
    """Leading digit prefix of a filename stem, else None (e.g. '2544' from '2544_lebron')."""
    m = _PLAYER_ID_RE.match(stem)
    return m.group(1) if m else None


def parse_team_from_body(text: str) -> Optional[str]:
    """Extract team tricode from ``**Team:** [[XXX]]`` body line."""
    for raw in text.splitlines():
        m = _TEAM_LINE_RE.match(raw.strip())
        if m:
            return m.group(1)
    return None


def parse_position(text: str) -> str:
    """Player position from ``- **Position:** Guard`` body line ('' if absent)."""
    m = _POS_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_usage(text: str) -> str:
    """Player usage rate from ``- **Usage rate:** 15.9%`` ('' if absent)."""
    m = _USAGE_RE.search(text)
    return m.group(1).strip() if m else ""


def roster_aggregate(recs: List[dict]) -> Dict:
    """Aggregate a team's player records (each with archetype + full text) into
    archetype/position distributions, roster rows, and a top-3 style signature.
    """
    arch_hist: Dict[str, int] = {}
    pos_hist: Dict[str, int] = {}
    rows: List[Dict[str, str]] = []
    for r in recs:
        arch = r.get("archetype", "") or "Unknown"
        arch_hist[arch] = arch_hist.get(arch, 0) + 1
        txt = r.get("text", "")
        pos = parse_position(txt) or "—"
        pos_hist[pos] = pos_hist.get(pos, 0) + 1
        rows.append({"stem": r.get("stem", ""), "archetype": arch,
                     "position": pos, "usage": parse_usage(txt) or "—"})
    n = max(len(recs), 1)
    top = sorted(arch_hist.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    sig = ", ".join(f"{a} ({c * 100 // n}%)" for a, c in top)
    return {"n": len(recs), "arch_hist": arch_hist, "pos_hist": pos_hist,
            "rows": rows, "style_signature": sig}


# --- person-free team identity (NO roster, NO names, NO matchups) ----------- #

def parse_scheme_tags(text: str) -> List[str]:
    """Person-free scheme/driver tags from a team note (dominant + all-tags list)."""
    tags: List[str] = []
    dom = _DOM_TAG_RE.search(text)
    if dom:
        tags.append(dom.group(1).strip())
    allm = _ALL_TAGS_RE.search(text)
    if allm:
        for t in re.split(r"[|,]", allm.group(1)):
            t = t.strip()
            if t and t not in tags:
                tags.append(t)
    return tags


def parse_density(text: str) -> str:
    """data_density_tier label ('' if absent)."""
    m = _DENSITY_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_composite(text: str) -> str:
    """Composite-intensity z-score from the defensive table ('' if absent)."""
    m = _COMPOSITE_RE.search(text)
    return m.group(1).strip() if m else ""


def _arch_stem(name: str) -> str:
    """Archetype display name → filesystem stem (lowercase, spaces→_, strip punct)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# Parse archetype intel from companion data module (tendency + vulnerability per archetype).
_ARCH_INTEL: Dict[str, tuple] = {
    row[0]: (row[1], row[2])
    for line in ARCH_INTEL_RAW.strip().splitlines()
    for row in (line.split("|"),)
    if len(row) == 3
}
_ARCH_TENDENCY: Dict[str, str] = {k: v[0] for k, v in _ARCH_INTEL.items()}
_ARCH_VULNERABILITY_MAP: Dict[str, str] = {k: v[1] for k, v in _ARCH_INTEL.items()}


def _style_one_liner(top_archs: List[str]) -> str:
    """Person-free style summary from top-2 archetypes (deduped)."""
    parts = list(dict.fromkeys(_ARCH_TENDENCY.get(a.lower(), a) for a in top_archs[:2]))
    return "; ".join(parts) if parts else "Style unclassified"


def _vuln(top_archs: List[str]) -> str:
    """Top-arch stylistic vulnerability (archetype-phrased, no player names)."""
    if not top_archs:
        return "Insufficient archetype data to characterize vulnerability."
    return _ARCH_VULNERABILITY_MAP.get(top_archs[0].lower(),
        f"Primary {top_archs[0]} concentration; style matchups may shift under pressure.")


def build_identity(team: str, source_text: Optional[str], recs: List[dict],
                   sport: str = "") -> str:
    """Person-FREE ``_Identity.md``: dense style hub with archetype table, style
    signature, tendencies, vulnerabilities, and resolving wikilinks into the archetype
    graph.  NO roster table, NO named players, NO 'X vs Y' matchups — style-level only.
    """
    agg = roster_aggregate(recs) if recs else None
    src = source_text or ""
    tags = parse_scheme_tags(src)
    density = parse_density(src)
    composite = parse_composite(src)
    top_archs: List[str] = (
        [a for a, _ in sorted(agg["arch_hist"].items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
        if agg and agg["arch_hist"] else []
    )
    hub_links = ["[[../../_Index|Sport Index]]",
                 "[[../../../_Index/_Brain|Brain MOC]]",
                 "[[../../Archetypes/_Archetypes_Index|Archetypes]]"]
    if tags:
        hub_links.append("[[../../Schemes/_Scheme_Effects_Matrix|Schemes]]")
    hub_links += [f"[[../../Archetypes/{_arch_stem(a)}|{a}]]" for a in top_archs]
    lines = [
        "---\ntags: [organized, team, identity, person-free]\n---",
        f"# {team} — Style Identity\n",
        "> Person-free style identity. Auto-generated by "
        "`scripts/platformkit/vault_organize_multi.py`. Intelligence map only — "
        "markets efficient; calibration is not edge.\n",
        " | ".join(hub_links) + "\n",
    ]
    if agg and agg["style_signature"]:
        lines.append(f"**Style signature:** {agg['style_signature']}\n")
    if top_archs:
        lines.append(f"**Style one-liner:** {_style_one_liner(top_archs)}\n")
    if tags:
        lines.append("**Scheme / driver tags:** " + ", ".join(tags) + "\n")
    meta_parts = ([f"defensive composite z = {composite}"] if composite else []) + \
                 ([f"data density = {density}"] if density else [])
    if meta_parts:
        lines.append("**Profile:** " + " · ".join(meta_parts) + "\n")
    if top_archs:
        lines += ["## Stylistic Tendencies\n"] + \
                 [f"- {_ARCH_TENDENCY.get(a.lower(), a)}" for a in top_archs[:3]] + [""]
    lines += ["## Stylistic Vulnerabilities\n", _vuln(top_archs) + "\n"]
    if agg and agg["arch_hist"]:
        n = agg["n"]
        lines += ["## Archetype Distribution\n",
                  "| Archetype | Count | Share | Tendency |", "|---|---|---|---|"]
        for arch, cnt in sorted(agg["arch_hist"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {arch} | {cnt} | {cnt * 100 // n}% "
                         f"| {_ARCH_TENDENCY.get(arch.lower(), '—')} |")
        lines.append("")
    return "\n".join(lines) + "\n"


# concept words that make a "X vs Y" line a tactical comparison, NOT a person matchup.
_VS_CONCEPT = frozenset((
    "drop switch zone man help base balanced paint perimeter pace iso transition "
    "halfcourt closeout coverage scheme defense offense run-scoring run-prevention "
    "power grinder speed contact stars q1 q2 q3 q4 league rmse mae").split())
_VS_LINE_RE = re.compile(r"\b([A-Z][\w'.-]+)\s+vs\.?\s+([A-Za-z][\w'.-]+)")


# Wikilink with player-id prefix: [[Players/123_first_last|Display]] or [[123_first_last]]
_PLAYER_WIKILINK_RE = re.compile(
    r"\[\[(?:Players/)?(?:\d{3,}_[a-z_]+)(?:\|([^\]]+))?\]\]",
    re.IGNORECASE,
)


def scrub_player_links(text: str) -> str:
    """Replace [[Players/id_name|Display]] wikilinks with display text (removes graph edge)."""
    def _replace(m: re.Match) -> str:
        d = m.group(1); return d if d else ""
    return _PLAYER_WIKILINK_RE.sub(_replace, text)


def scrub_person_lines(text: str) -> str:
    """Drop lines with person 'X vs Y' matchups; keep tactical concept comparisons.
    Also strips player-ID wikilinks. Person-free hygiene for Archetypes/Schemes/Trends.
    """
    text = scrub_player_links(text)
    def _keep(line: str) -> bool:
        m = _VS_LINE_RE.search(line)
        return not (m and m.group(1).lower() not in _VS_CONCEPT)
    kept = [ln for ln in text.splitlines() if _keep(ln)]
    return "\n".join(kept) + ("\n" if text.endswith("\n") else "")


@dataclass(frozen=True)
class SportSpec:
    """Immutable descriptor of a sport's source layout inside vault/."""
    name: str                                    # output folder key, e.g. "NBA"
    is_solo: bool                                # True → no team nesting
    teams_dir: Optional[Path]                    # <TRI>.md team files
    players_dir: Optional[Path]                  # player .md files (may be None)
    team_note_dir: Optional[Path]                # content folded into _Team hubs
    archetype_dirs: List[Path] = field(default_factory=list)
    scheme_dirs: List[Path] = field(default_factory=list)
    trend_dirs: List[Path] = field(default_factory=list)
    reference_dirs: List[Path] = field(default_factory=list)
    drop_dirs: List[Path] = field(default_factory=list)

def source_specs(vault_dir: Path) -> List[SportSpec]:
    """Return one SportSpec per supported sport rooted at *vault_dir*."""
    v = vault_dir
    nba_root = v / "Sports" / "Basketball_NBA"
    nba_intel = v / "Intelligence"
    nba = SportSpec(
        name="NBA", is_solo=False,
        teams_dir=nba_intel / "Teams", players_dir=nba_intel / "Players",
        team_note_dir=nba_intel / "Teams",
        archetype_dirs=[nba_intel / "Archetypes",
                        nba_root / "Archetypes" / "Archetypes"],
        scheme_dirs=[nba_intel / "Schemes"],
        trend_dirs=[nba_intel / "Trends", nba_root / "Trends" / "Trends"],
        reference_dirs=[nba_root / "Scouting", nba_root / "Seasons",
                        nba_root / "Seasons" / "Seasons"],
        drop_dirs=[nba_intel / "Matchups", v / "Intelligence" / "Pairs"],
    )
    mlb_root = v / "Sports" / "MLB"
    mlb = SportSpec(
        name="MLB", is_solo=False,
        teams_dir=mlb_root / "Teams", players_dir=None,
        team_note_dir=mlb_root / "Teams",
        archetype_dirs=[mlb_root / "Playstyles"], scheme_dirs=[],
        trend_dirs=[mlb_root / "StyleTrends"],
        reference_dirs=[mlb_root / "HomeEnvironment", mlb_root / "Leagues",
                        mlb_root / "Seasons", mlb_root / "Signals",
                        mlb_root / "Scouting"],
        drop_dirs=[mlb_root / "Matchups", mlb_root / "StyleMatchups"],
    )
    soccer_root = v / "Sports" / "Soccer"
    soccer = SportSpec(
        name="Soccer", is_solo=False,
        teams_dir=soccer_root / "Teams", players_dir=None,
        team_note_dir=soccer_root / "Teams",
        archetype_dirs=[soccer_root / "Playstyles"],
        scheme_dirs=[soccer_root / "SchemeTransitions"],
        trend_dirs=[soccer_root / "StyleTrends"],
        reference_dirs=[soccer_root / "Leagues", soccer_root / "Seasons",
                        soccer_root / "Signals", soccer_root / "Scouting"],
        drop_dirs=[soccer_root / "Matchups", soccer_root / "StyleMatchups"],
    )
    tennis_root = v / "Sports" / "Tennis"
    tennis = SportSpec(
        name="Tennis", is_solo=True, teams_dir=None, team_note_dir=None,
        players_dir=(tennis_root / "Players"
                     if (tennis_root / "Players").is_dir() else None),
        archetype_dirs=[tennis_root / "Playstyles"], scheme_dirs=[],
        trend_dirs=[tennis_root / "StyleTrends"],
        reference_dirs=[tennis_root / "Surfaces", tennis_root / "Tournaments",
                        tennis_root / "Leagues", tennis_root / "Seasons",
                        tennis_root / "Signals", tennis_root / "Scouting"],
        drop_dirs=[tennis_root / "Matchups", tennis_root / "StyleMatchups"],
    )
    return [nba, mlb, soccer, tennis]
