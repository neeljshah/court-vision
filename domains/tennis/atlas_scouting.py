"""domains.tennis.atlas_scouting — Query-time scouting synthesis generator.

Reads EXISTING vault notes (Style_Matchups, Playstyles, Trends) and synthesises
one Scouting brief per archetype pair.  Does NOT recompute from corpus — it parses
and recombines intelligence already written by the other atlas generators.

Public API:
    build_scouting(out_dir, vault_tennis_dir=<repo>/vault/Sports/Tennis) -> list[Path]

Design principles:
  - Read-only on existing vault notes: synthesise, never recompute.
  - Graceful: if a source note is missing the brief still emits with a note.
  - No individual player names anywhere in output.
  - No edge / betting language.
  - All cross-references use [[wikilinks]] back to source notes.

F5-clean: stdlib only (pathlib, re, typing).  No pandas, no numpy.
Rendering delegated to atlas_scouting_render (same package, stdlib-only).
"""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List, Optional, Tuple

from domains.tennis.atlas_scouting_render import render_brief, render_index

# ---------------------------------------------------------------------------
# Repo-relative default vault location
# ---------------------------------------------------------------------------

_DEFAULT_VAULT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Tennis"
)

# Trends ASCII table: header abbreviation → archetype slug
_ABBREV_TO_SLUG: Dict[str, str] = {
    "Clay":   "Clay_Court_Specialist",
    "BigSrv": "Fast_Court_Big_Server",
    "AllCrt": "All_Court_Baseliner",
    "LeftH":  "Left_Handed_Specialist",
    "GSlam":  "Grand_Slam_Performer",
    "Hard":   "Hard_Court_Specialist",
    "Grass":  "Grass_Court_Specialist",
    "Jrny":   "Journeyman",
}

# ---------------------------------------------------------------------------
# Helpers: file I/O and parsing
# ---------------------------------------------------------------------------

def _read(path: pathlib.Path) -> Optional[str]:
    """Return file text or None if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_frontmatter(text: str) -> Dict[str, str]:
    """Return flat {key: value} from the first YAML front-matter block."""
    fm: Dict[str, str] = {}
    in_fm = False
    for line in text.splitlines():
        s = line.strip()
        if s == "---":
            if not in_fm:
                in_fm = True
                continue
            break
        if in_fm and ":" in s:
            k, _, v = s.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _parse_matchup_note(text: str) -> Dict[str, object]:
    """Extract win-rates, meetings, and surface breakdown from a Style_Matchups note."""
    fm = _parse_frontmatter(text)
    surfaces: Dict[str, str] = {}
    surf_re = re.compile(
        r"\*\*(?P<surf>Clay|Grass|Hard):\*\*\s+win-rate of A\s*=\s*(?P<pct>[0-9.]+%)",
        re.IGNORECASE,
    )
    for m in surf_re.finditer(text):
        surfaces[m.group("surf")] = m.group("pct")
    spread_m = re.search(r"Surface spread ([\d.]+\s*pp)", text)
    return {
        "archetype_a": fm.get("archetype_a", ""),
        "archetype_b": fm.get("archetype_b", ""),
        "total_meetings": fm.get("total_meetings", ""),
        "win_rate_a": fm.get("win_rate_a", ""),
        "win_rate_b": fm.get("win_rate_b", ""),
        "surfaces": surfaces,
        "surface_spread": spread_m.group(1).strip() if spread_m else None,
    }


def _parse_playstyle_note(text: str) -> Dict[str, str]:
    """Extract description, surface tendency, and population from a Playstyles note."""
    fm = _parse_frontmatter(text)
    desc_m = re.search(r"## Description\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    tend_m = re.search(r"\*\*Pattern:\*\*\s*(.+)", text)
    return {
        "archetype": fm.get("archetype", ""),
        "player_count": fm.get("player_count", ""),
        "corpus_share_pct": fm.get("corpus_share_pct", ""),
        "description": desc_m.group(1).strip() if desc_m else "",
        "surface_tendency": tend_m.group(1).strip() if tend_m else "",
    }


def _parse_trends_overview(text: str) -> Dict[str, Tuple[float, float, str]]:
    """Return {slug: (first_yr_pct, last_yr_pct, direction)} from _Style_Trends_Overview.md."""
    table_m = re.search(r"```\s*\n(\+[-+]+\+.*?\+)\s*\n```", text, re.DOTALL)
    if not table_m:
        return {}
    lines = [ln for ln in table_m.group(1).splitlines() if ln.startswith("|")]
    if len(lines) < 3:
        return {}
    headers = [h.strip() for h in lines[0].split("|")[1:-1]]
    data_rows = [
        [c.strip() for c in ln.split("|")[1:-1]]
        for ln in lines[1:]
        if ln.startswith("|") and ln.split("|")[1].strip().isdigit()
    ]
    if len(data_rows) < 2:
        return {}

    def _pct(v: str) -> float:
        try:
            return float(v.replace("%", ""))
        except ValueError:
            return 0.0

    result: Dict[str, Tuple[float, float, str]] = {}
    for idx, abbrev in enumerate(headers[1:], start=1):
        slug = _ABBREV_TO_SLUG.get(abbrev)
        if not slug:
            continue
        if idx >= len(data_rows[0]) or idx >= len(data_rows[-1]):
            continue
        fp = _pct(data_rows[0][idx])
        lp = _pct(data_rows[-1][idx])
        direction = "rising" if lp > fp else ("stable" if abs(lp - fp) < 0.5 else "falling")
        result[slug] = (fp, lp, direction)
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_scouting(
    out_dir: pathlib.Path,
    vault_tennis_dir: Optional[pathlib.Path] = None,
) -> List[pathlib.Path]:
    """Synthesise scouting briefs from existing vault notes.

    For each Style_Matchups note, reads the pair note + each archetype's
    Playstyles note + the Trends overview, and emits a synthesised brief
    in out_dir.  Graceful if any source note is missing.

    Parameters
    ----------
    out_dir:
        Destination directory (created if missing).
    vault_tennis_dir:
        vault/Sports/Tennis/ root.  Defaults to the repo-relative location.

    Returns
    -------
    list[Path]
        All written paths (briefs + _Scouting_Index.md).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if vault_tennis_dir is None:
        vault_tennis_dir = _DEFAULT_VAULT
    vault_tennis_dir = pathlib.Path(vault_tennis_dir)

    matchups_dir = vault_tennis_dir / "Style_Matchups"
    playstyles_dir = vault_tennis_dir / "Playstyles"
    trends_file = vault_tennis_dir / "Trends" / "_Style_Trends_Overview.md"

    # Load trend data once (optional)
    trends: Dict[str, Tuple[float, float, str]] = {}
    trends_text = _read(trends_file)
    if trends_text:
        trends = _parse_trends_overview(trends_text)

    # Enumerate Style_Matchups pair notes (skip _index files)
    pair_files: List[pathlib.Path] = []
    if matchups_dir.is_dir():
        pair_files = sorted(
            p for p in matchups_dir.glob("*.md")
            if not p.name.startswith("_")
        )

    written: List[pathlib.Path] = []
    index_entries: List[Tuple[str, str, str, str, str]] = []

    for pair_path in pair_files:
        pair_text = _read(pair_path)
        if not pair_text:
            continue

        matchup = _parse_matchup_note(pair_text)
        arch_a = str(matchup["archetype_a"])
        arch_b = str(matchup["archetype_b"])
        if not arch_a or not arch_b:
            continue

        slug_a = arch_a.replace(" ", "_")
        slug_b = arch_b.replace(" ", "_")

        ps_text_a = _read(playstyles_dir / f"{slug_a}.md")
        playstyle_a = _parse_playstyle_note(ps_text_a) if ps_text_a else None
        if slug_a == slug_b:
            playstyle_b = playstyle_a
        else:
            ps_text_b = _read(playstyles_dir / f"{slug_b}.md")
            playstyle_b = _parse_playstyle_note(ps_text_b) if ps_text_b else None

        brief_body = render_brief(
            pair_filename=pair_path.stem + ".md",
            matchup=matchup,
            playstyle_a=playstyle_a,
            playstyle_b=playstyle_b,
            trends=trends,
        )

        out_path = out_dir / f"{pair_path.stem}.md"
        out_path.write_text(brief_body, encoding="utf-8")
        written.append(out_path)

        wr_a = str(matchup.get("win_rate_a", ""))
        wr_b = str(matchup.get("win_rate_b", ""))
        try:
            wr_a_d = f"{float(wr_a) * 100:.1f}%"
            wr_b_d = f"{float(wr_b) * 100:.1f}%"
        except (ValueError, TypeError):
            wr_a_d, wr_b_d = wr_a, wr_b

        index_entries.append((f"{pair_path.stem}.md", arch_a, arch_b, wr_a_d, wr_b_d))

    written.append(render_index(index_entries, out_dir))
    return written
