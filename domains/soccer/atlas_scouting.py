"""domains.soccer.atlas_scouting — Query-time scouting-synthesis generator for soccer schemes.

Reads EXISTING vault notes (Style_Matchups, Playstyles, Trends, Scheme_Transitions)
and synthesises one Scouting brief per scheme pair.  Does NOT recompute from corpus —
it parses and recombines intelligence already written by the other atlas generators.

Public API:
    build_scouting(out_dir, vault_soccer_dir=<repo>/vault/Sports/Soccer) -> list[Path]

Design principles:
  - Read-only on existing vault notes: synthesise, never recompute.
  - Graceful: if a source note is missing the brief still emits with a note.
  - No individual player names anywhere in output.
  - No edge / betting language.
  - All cross-references use bare-stem [[wikilinks]] (no '../', no '.md').

F5-clean: stdlib + in-domain imports only.  No pandas, no numpy.
Rendering delegated to atlas_scouting_render (same package, stdlib-only).
"""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.soccer.atlas_playstyles import _SCHEMES
from domains.soccer.atlas_scouting_render import render_brief, render_index

# ---------------------------------------------------------------------------
# Repo-relative default vault location
# ---------------------------------------------------------------------------

_DEFAULT_VAULT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2]
    / "vault" / "Sports" / "Soccer"
)

# Scheme display label → filesystem key (derived from atlas_playstyles._SCHEMES).
# Used to resolve the label stored in Style_Matchups frontmatter to the Playstyle filename.
_LABEL_TO_KEY: Dict[str, str] = {s.label: s.key for s in _SCHEMES}


# Trends table column header → scheme key (matches atlas_playstyles._SCHEMES keys).
_ABBREV_TO_KEY: Dict[str, str] = {
    "HighScr": "High-Scoring_Attacking",
    "HiVar":   "High-Variance_Entertainers",
    "DefBlk":  "Defensive_Low-Block",
    "DrawPr":  "Draw-Prone_Grinder",
    "Leaky":   "Leaky_High-Risk",
    "StHome":  "Strong-at-Home",
    "Bal":     "Balanced",
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
            fm[k.strip()] = v.strip().strip('"')
    return fm


def _parse_matchup_note(text: str) -> Dict[str, object]:
    """Extract outcome rates and meeting count from a Style_Matchups note."""
    fm = _parse_frontmatter(text)
    return {
        "home_scheme":     fm.get("home_scheme", ""),
        "away_scheme":     fm.get("away_scheme", ""),
        "total_meetings":  fm.get("total_meetings", ""),
        "home_win_rate":   fm.get("home_win_rate", ""),
        "draw_rate":       fm.get("draw_rate", ""),
        "away_win_rate":   fm.get("away_win_rate", ""),
        "over25_rate":     fm.get("over25_rate", ""),
    }


def _parse_playstyle_note(text: str) -> Dict[str, str]:
    """Extract description, stat signature, and team count from a Playstyles note."""
    fm = _parse_frontmatter(text)
    # italic description on the line immediately after the # heading
    desc_m = re.search(r"\n\*(.+?)\*\n", text)
    # Stat Signature rule line
    sig_m = re.search(r"\*\*Classification rule:\*\*\s*(.+)", text)
    return {
        "scheme":        fm.get("scheme", ""),
        "team_count":    fm.get("team_count", ""),
        "description":   desc_m.group(1).strip() if desc_m else "",
        "stat_signature": sig_m.group(1).strip() if sig_m else "",
    }


def _parse_trends_overview(text: str) -> Dict[str, Tuple[float, float, str]]:
    """Return {scheme_key: (first_yr_pct, last_yr_pct, direction)} from trends table."""

    def _pct(v: str) -> float:
        try:
            return float(v.strip().rstrip("%"))
        except ValueError:
            return 0.0

    # Find the data table by locating the header row
    lines = text.splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("| Season") or ln.startswith("| Season "):
            header_idx = i
            break
    if header_idx is None:
        return {}

    headers = [h.strip() for h in lines[header_idx].split("|")[1:-1]]
    data_rows = []
    for ln in lines[header_idx + 2:]:  # skip separator row
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.split("|")[1:-1]]
        if cells and cells[0].isdigit():
            data_rows.append(cells)

    if len(data_rows) < 2:
        return {}

    first_row = data_rows[0]
    last_row = data_rows[-1]

    result: Dict[str, Tuple[float, float, str]] = {}
    for idx, col in enumerate(headers[1:], start=1):
        key = _ABBREV_TO_KEY.get(col)
        if not key:
            continue
        if idx >= len(first_row) or idx >= len(last_row):
            continue
        fp = _pct(first_row[idx])
        lp = _pct(last_row[idx])
        direction = "rising" if lp > fp + 0.5 else ("stable" if abs(lp - fp) <= 0.5 else "falling")
        result[key] = (fp, lp, direction)
    return result


def _parse_stickiness_note(text: str) -> Dict[str, Tuple[int, int, float]]:
    """Return {scheme_key: (stayed, total, rate_pct)} from Scheme_Transitions/Stickiness.md."""
    result: Dict[str, Tuple[int, int, float]] = {}
    # Rows look like:  | [[Playstyles/High-Scoring_Attacking|...]] | 49.2% | 89 | 181 |
    row_re = re.compile(
        r"\[\[Playstyles/(?P<slug>[^\|]+)\|[^\]]+\]\]\s*\|\s*"
        r"(?P<rate>[0-9.]+)%\s*\|\s*(?P<stayed>\d+)\s*\|\s*(?P<total>\d+)"
    )
    for m in row_re.finditer(text):
        slug = m.group("slug").replace(" ", "_").replace("/", "_")
        stayed = int(m.group("stayed"))
        total = int(m.group("total"))
        rate = float(m.group("rate"))
        result[slug] = (stayed, total, rate)
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_scouting(
    out_dir: pathlib.Path,
    vault_soccer_dir: Optional[pathlib.Path] = None,
) -> List[pathlib.Path]:
    """Synthesise scouting briefs from existing vault notes.

    For each Style_Matchups note, reads the pair note + each scheme's Playstyles
    note + the Trends overview + Scheme_Transitions Stickiness, and emits a
    synthesised brief in out_dir.  Graceful if any source note is missing.

    Parameters
    ----------
    out_dir:
        Destination directory (created if missing).
    vault_soccer_dir:
        vault/Sports/Soccer/ root.  Defaults to the repo-relative location.

    Returns
    -------
    list[Path]
        All written paths (briefs + _Scouting_Index.md).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if vault_soccer_dir is None:
        vault_soccer_dir = _DEFAULT_VAULT
    vault_soccer_dir = pathlib.Path(vault_soccer_dir)

    matchups_dir = vault_soccer_dir / "Style_Matchups"
    playstyles_dir = vault_soccer_dir / "Playstyles"
    trends_file = vault_soccer_dir / "Trends" / "_Style_Trends_Overview.md"
    stickiness_file = vault_soccer_dir / "Scheme_Transitions" / "Stickiness.md"

    # Load trends once (optional)
    trends: Dict[str, Tuple[float, float, str]] = {}
    trends_text = _read(trends_file)
    if trends_text:
        trends = _parse_trends_overview(trends_text)

    # Load stickiness once (optional)
    stickiness: Dict[str, Tuple[int, int, float]] = {}
    stick_text = _read(stickiness_file)
    if stick_text:
        stickiness = _parse_stickiness_note(stick_text)

    # Enumerate Style_Matchups pair notes (skip _index / _Index files)
    pair_files: List[pathlib.Path] = []
    if matchups_dir.is_dir():
        pair_files = sorted(
            p for p in matchups_dir.glob("*.md")
            if not p.name.startswith("_")
        )

    written: List[pathlib.Path] = []
    # (filename, scheme_a, scheme_b, hw_pct, draw_pct, aw_pct)
    index_entries: List[Tuple[str, str, str, str, str, str]] = []

    for pair_path in pair_files:
        pair_text = _read(pair_path)
        if not pair_text:
            continue

        matchup = _parse_matchup_note(pair_text)
        scheme_a = str(matchup["home_scheme"])
        scheme_b = str(matchup["away_scheme"])
        if not scheme_a or not scheme_b:
            continue

        # Resolve label → filesystem key; fallback for unknown labels.
        slug_a = _LABEL_TO_KEY.get(scheme_a, scheme_a.replace(" / ", "_").replace(" ", "_"))
        slug_b = _LABEL_TO_KEY.get(scheme_b, scheme_b.replace(" / ", "_").replace(" ", "_"))

        ps_text_a = _read(playstyles_dir / f"{slug_a}.md")
        playstyle_a = _parse_playstyle_note(ps_text_a) if ps_text_a else None
        if slug_a == slug_b:
            playstyle_b = playstyle_a
        else:
            ps_text_b = _read(playstyles_dir / f"{slug_b}.md")
            playstyle_b = _parse_playstyle_note(ps_text_b) if ps_text_b else None

        # Inject resolved slugs so render_brief can build correct wikilinks.
        matchup_with_slugs = dict(matchup)
        matchup_with_slugs["slug_a"] = slug_a
        matchup_with_slugs["slug_b"] = slug_b

        brief_body = render_brief(
            pair_filename=pair_path.name,
            matchup=matchup_with_slugs,
            playstyle_a=playstyle_a,
            playstyle_b=playstyle_b,
            trends=trends,
            stickiness=stickiness,
        )

        out_path = out_dir / pair_path.name
        written.append(write_note(out_path, brief_body))

        def _fmt(v: object) -> str:
            try:
                return f"{float(str(v)) * 100:.1f}%"
            except (ValueError, TypeError):
                return str(v)

        index_entries.append((
            pair_path.name,
            scheme_a, scheme_b,
            _fmt(matchup.get("home_win_rate", "")),
            _fmt(matchup.get("draw_rate", "")),
            _fmt(matchup.get("away_win_rate", "")),
        ))

    written.append(render_index(index_entries, out_dir))
    return written
