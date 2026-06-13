"""domains.basketball_nba.memory_atlas_scouting — NBA per-archetype scouting synthesis.

Reads EXISTING vault notes (Archetypes/<name>.md + Trends/_Trends_Overview.md) and
synthesises one scouting profile per archetype.  Does NOT recompute from corpus —
it parses and recombines intelligence already written by the archetype/trend generators.

Public API:
    build_scouting(out_dir, vault_nba_dir=<repo>/vault/Sports/Basketball_NBA) -> list[Path]

Design principles:
  - Read-only on existing vault notes: synthesise, never recompute.
  - Graceful: if a source note is missing the profile still emits with a placeholder.
  - No individual player names anywhere in output.
  - No edge / betting language.
  - All cross-references use bare-stem [[wikilinks]] (Obsidian global resolution).
  - F5-clean: stdlib only (pathlib, re, typing).  No pandas, no numpy, no src.*.
  - Rendering delegated to memory_atlas_scouting_render (same package, stdlib-only).
"""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.basketball_nba.memory_atlas_scouting_render import render_profile, render_index

# ---------------------------------------------------------------------------
# Repo-relative default vault location
# ---------------------------------------------------------------------------

_DEFAULT_VAULT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Basketball_NBA"
)

# Mapping: Trends table display label → archetype filesystem slug
# The slug mirrors the filenames in Archetypes/ (spaces and hyphens → _).
_LABEL_TO_SLUG: Dict[str, str] = {
    "High-Usage Creator":  "High_Usage_Creator",
    "Scoring Guard":       "Scoring_Guard",
    "3-and-D Wing":        "3_and_D_Wing",
    "Stretch Big":         "Stretch_Big",
    "Rim-Running Big":     "Rim_Running_Big",
    "Defensive Anchor":    "Defensive_Anchor",
    "Versatile Forward":   "Versatile_Forward",
    "Playmaking Big":      "Playmaking_Big",
    "Bench Contributor":   "Bench_Contributor",
    "Low-Usage Connector": "Low_Usage_Connector",
}

# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _read(path: pathlib.Path) -> Optional[str]:
    """Return file text or None if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _write(path: pathlib.Path, text: str) -> None:
    write_note(path, text)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_archetype_note(text: str) -> Dict[str, object]:
    """Extract style, signature thresholds, and population from an Archetypes/ note."""
    # Style section
    style_m = re.search(r"## STYLE\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    style: str = style_m.group(1).strip() if style_m else ""

    # Signature bullet items (lines starting with "- **key**:")
    sig_section_m = re.search(
        r"## SIGNATURE.*?\n(.*?)(?=\n##|\Z)", text, re.DOTALL
    )
    signature_lines: List[str] = []
    if sig_section_m:
        for ln in sig_section_m.group(1).splitlines():
            s = ln.strip()
            if s.startswith("-"):
                # Strip the leading "- " so render_profile can add it back
                signature_lines.append(s.lstrip("- ").strip())

    # Population
    pop_m = re.search(r"\*\*Players fitting this archetype:\*\*\s*(\d+)", text)
    population: str = pop_m.group(1) if pop_m else "unknown"

    # Typical positions
    pos_m = re.search(r"\*\*Typical position\(s\):\*\*\s*(.+)", text)
    typical_pos: str = pos_m.group(1).strip() if pos_m else "—"

    return {
        "style": style,
        "signature_lines": signature_lines,
        "population": population,
        "typical_pos": typical_pos,
    }


def _parse_trends_overview(text: str) -> Dict[str, Tuple[float, float, str]]:
    """Return {label: (first_pct, last_pct, direction)} from _Trends_Overview.md.

    Reads the '## Archetype Share by Season (%)' markdown table.
    """
    # Find the archetype share table
    table_m = re.search(
        r"## Archetype Share by Season.*?\n((?:\|[^\n]+\n)+)",
        text,
        re.DOTALL,
    )
    if not table_m:
        return {}

    lines = [ln for ln in table_m.group(1).splitlines() if ln.startswith("|")]
    # Expect: header | separator | data rows
    if len(lines) < 3:
        return {}

    # Parse header to find season column positions (ignore first "Archetype" and last "Δ" cols)
    headers = [h.strip() for h in lines[0].split("|")[1:-1]]
    # data rows = rows after separator
    data_lines = [ln for ln in lines[2:] if ln.startswith("|")]

    def _pct(v: str) -> float:
        try:
            return float(v.replace("%", "").strip())
        except ValueError:
            return 0.0

    result: Dict[str, Tuple[float, float, str]] = {}
    for row_ln in data_lines:
        cells = [c.strip() for c in row_ln.split("|")[1:-1]]
        if not cells:
            continue
        label = cells[0]
        # season columns are indices 1..len(headers)-2 (last is "Δ first→last")
        season_cells = cells[1:-1]  # exclude Δ column
        if len(season_cells) < 1:
            continue
        fp = _pct(season_cells[0])
        lp = _pct(season_cells[-1])
        direction = (
            "rising" if lp > fp
            else ("stable" if abs(lp - fp) < 0.5 else "falling")
        )
        result[label] = (fp, lp, direction)

    return result


def _parse_league_eff_note(text: str) -> str:
    """Extract a one-liner about current league efficiency from the overview."""
    # Find the efficiency table and pull the last data row
    eff_m = re.search(
        r"## League Efficiency by Season.*?\n((?:\|[^\n]+\n)+)",
        text,
        re.DOTALL,
    )
    if not eff_m:
        return ""
    eff_lines = [ln for ln in eff_m.group(1).splitlines() if ln.startswith("|")]
    # skip header + separator
    data_rows = [ln for ln in eff_lines[2:] if ln.startswith("|")]
    if not data_rows:
        return ""
    last = [c.strip() for c in data_rows[-1].split("|")[1:-1]]
    # cells: season, off_rtg, def_rtg, net_rtg, pace, efg
    if len(last) < 6:
        return ""
    season, off, dfr, net, pace, efg = last[0], last[1], last[2], last[3], last[4], last[5]
    return (
        f"*(League context {season}: Off Rtg {off} / Def Rtg {dfr} / "
        f"Net Rtg {net} / Pace {pace} / eFG% {efg} — "
        f"source: [[_Trends_Overview]])*"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_scouting(
    out_dir: pathlib.Path,
    vault_nba_dir: Optional[pathlib.Path] = None,
) -> List[pathlib.Path]:
    """Synthesise per-archetype NBA scouting profiles from existing vault notes.

    For each archetype note found in Archetypes/, reads that note + the
    Trends overview and emits a synthesised scouting profile under out_dir/.
    Graceful if any source note is missing — profile still emits with available data.

    Parameters
    ----------
    out_dir:
        Destination directory (created if missing).  Profiles land in out_dir/
        directly; an _Scouting_Index.md is also written.
    vault_nba_dir:
        vault/Sports/Basketball_NBA/ root.  Defaults to the repo-relative location.

    Returns
    -------
    list[Path]
        All written paths (profiles + _Scouting_Index.md).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if vault_nba_dir is None:
        vault_nba_dir = _DEFAULT_VAULT
    vault_nba_dir = pathlib.Path(vault_nba_dir)

    archetypes_dir = vault_nba_dir / "Archetypes"
    trends_file = vault_nba_dir / "Trends" / "_Trends_Overview.md"

    # Load trend data once (optional)
    trends: Dict[str, Tuple[float, float, str]] = {}
    league_eff_note: str = ""
    trends_text = _read(trends_file)
    if trends_text:
        trends = _parse_trends_overview(trends_text)
        league_eff_note = _parse_league_eff_note(trends_text)

    # Enumerate Archetype notes (skip _index files)
    arch_files: List[pathlib.Path] = []
    if archetypes_dir.is_dir():
        arch_files = sorted(
            p for p in archetypes_dir.glob("*.md")
            if not p.name.startswith("_")
        )

    written: List[pathlib.Path] = []
    index_entries: List[Tuple[str, str, Optional[Tuple[float, float, str]]]] = []

    for arch_path in arch_files:
        arch_text = _read(arch_path)
        if not arch_text:
            continue

        parsed = _parse_archetype_note(arch_text)

        # Derive label from the slug → label map (reverse lookup) or from H1
        stem = arch_path.stem  # e.g. "High_Usage_Creator"
        # Try to find the canonical display label
        label: Optional[str] = None
        for lbl, slg in _LABEL_TO_SLUG.items():
            if slg == stem:
                label = lbl
                break
        if label is None:
            # Fallback: reconstruct from stem
            label = stem.replace("_", " ")

        arch_slug = stem  # bare stem for wikilinks

        trend = trends.get(label)

        profile_body = render_profile(
            arch_label=label,
            arch_slug=arch_slug,
            style=str(parsed.get("style", "")),
            signature_lines=list(parsed.get("signature_lines", [])),  # type: ignore[arg-type]
            population=str(parsed.get("population", "unknown")),
            typical_pos=str(parsed.get("typical_pos", "—")),
            trend=trend,
            league_eff_note=league_eff_note,
        )

        out_path = out_dir / f"{arch_slug}.md"
        _write(out_path, profile_body)
        written.append(out_path)
        index_entries.append((arch_slug, label, trend))

    written.append(render_index(index_entries, out_dir))
    return written
