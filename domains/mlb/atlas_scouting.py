"""domains.mlb.atlas_scouting — Query-time scouting synthesis for MLB team styles.

Reads EXISTING vault notes (Style_Matchups, Playstyles, Trends) and synthesises
one Scouting brief per style pair.  Does NOT recompute from corpus.

Public API:
    build_scouting(out_dir, vault_mlb_dir=<repo>/vault/Sports/MLB) -> list[Path]

F5-clean: stdlib + scripts.platformkit.atlas.obsidian_emit only.  No pandas, no numpy.
Rendering delegated to atlas_scouting_render (same package, stdlib-only).
"""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List, Optional, Tuple

from domains.mlb.atlas_scouting_render import render_brief, render_index
from scripts.platformkit.atlas.obsidian_emit import write_note

_DEFAULT_VAULT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "vault" / "Sports" / "MLB"
)

_SLUG_TO_NAME: Dict[str, str] = {
    "power_run_scoring":       "Power / Run-Scoring",
    "pitching_run_prevention": "Pitching-Led / Run-Prevention",
    "balanced_contender":      "Balanced Contender",
    "high_variance_offense":   "High-Variance Offense",
    "low_scoring_grinder":     "Low-Scoring Grinder",
    "run_deficit_rebuilding":  "Run-Deficit / Rebuilding",
    "unclassified":            "Unclassified",
}

_HEADER_TO_SLUG: Dict[str, str] = {
    "Power":    "power_run_scoring",
    "Pitching": "pitching_run_prevention",
    "Balanced": "balanced_contender",
    "Hi-Var":   "high_variance_offense",
    "Grinder":  "low_scoring_grinder",
    "Deficit":  "run_deficit_rebuilding",
}


def _read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_frontmatter(text: str) -> Dict[str, str]:
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
    """Extract home/away slugs and outcome stats from a Style_Matchups note."""
    fm = _parse_frontmatter(text)

    def _re_float(pattern: str, pct: bool = False) -> float:
        m = re.search(pattern, text)
        if not m:
            return 0.0
        try:
            v = float(m.group(1).replace("%", ""))
            return v / 100.0 if pct else v
        except ValueError:
            return 0.0

    n_m = re.search(r"Games in corpus\s*\|\s*(\d+)", text)
    n = int(n_m.group(1)) if n_m else int(fm.get("game_count", 0) or 0)
    thresh_m = re.search(r">=\s*([\d.]+)\s*total runs", text)
    return {
        "home_slug":        fm.get("home_style", ""),
        "away_slug":        fm.get("away_style", ""),
        "corpus_span":      fm.get("corpus_span", ""),
        "n":                n,
        "home_win_rate":    _re_float(r"Home-win rate\s*\|\s*([\d.]+%)", pct=True),
        "avg_total":        _re_float(r"Avg total runs / game\s*\|\s*([\d.]+)"),
        "high_rate":        _re_float(r"High-scoring rate[^|]*\|\s*([\d.]+%)", pct=True),
        "high_total_thresh": float(thresh_m.group(1)) if thresh_m else 10.0,
    }


def _parse_playstyle_note(text: str) -> Dict[str, str]:
    """Extract description, signature, and team count from a Playstyles note."""
    fm = _parse_frontmatter(text)
    desc_m = re.search(r"## Style Description\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    description = desc_m.group(1).strip() if desc_m else ""
    sig_rows: List[str] = []
    in_sig = False
    for line in text.splitlines():
        if "## Signature Thresholds" in line:
            in_sig = True
            continue
        if in_sig:
            if line.startswith("##"):
                break
            if "|" in line and "---" not in line and "Metric" not in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if len(cells) >= 2:
                    sig_rows.append(f"{cells[0]}: {cells[1]}")
    return {
        "archetype":   fm.get("archetype", ""),
        "team_count":  fm.get("team_count", ""),
        "description": description,
        "signature":   "; ".join(sig_rows),
    }


def _parse_trends(text: str) -> Dict[str, Tuple[float, float, str]]:
    """Return {slug: (first_yr_share, last_yr_share, direction)} from the trends overview."""
    result: Dict[str, Tuple[float, float, str]] = {}
    rows: List[List[str]] = []
    headers: List[str] = []
    in_table = False
    for line in text.splitlines():
        if "## Team Style Distribution" in line:
            in_table = True
            continue
        if not in_table:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        if "---" in stripped:
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if not cells:
            continue
        if not headers and "Season" in cells[0]:
            headers = cells
            continue
        if headers and cells[0].isdigit():
            rows.append(cells)
    if not headers or len(rows) < 2:
        return result
    first_row, last_row = rows[0], rows[-1]
    for idx, header in enumerate(headers[1:], start=1):
        slug = _HEADER_TO_SLUG.get(header)
        if not slug or idx >= len(first_row) or idx >= len(last_row):
            continue
        try:
            fp = float(first_row[idx].replace("%", ""))
            lp = float(last_row[idx].replace("%", ""))
        except ValueError:
            continue
        diff = lp - fp
        direction = "rising" if diff > 1.0 else ("falling" if diff < -1.0 else "stable")
        result[slug] = (fp, lp, direction)
    return result


def build_scouting(
    out_dir: pathlib.Path,
    vault_mlb_dir: Optional[pathlib.Path] = None,
) -> List[pathlib.Path]:
    """Synthesise MLB scouting briefs from existing vault notes.

    For each Style_Matchups note, reads the pair note + each style's Playstyles
    note + the Trends overview and emits a synthesised brief in out_dir.
    Graceful if any source note is missing.

    Parameters
    ----------
    out_dir:
        Destination directory (created if missing).
    vault_mlb_dir:
        vault/Sports/MLB/ root.  Defaults to the repo-relative location.

    Returns
    -------
    list[Path]
        All written paths (briefs + _Scouting_Index.md).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if vault_mlb_dir is None:
        vault_mlb_dir = _DEFAULT_VAULT
    vault_mlb_dir = pathlib.Path(vault_mlb_dir)

    matchups_dir = vault_mlb_dir / "Style_Matchups"
    playstyles_dir = vault_mlb_dir / "Playstyles"
    trends_file = vault_mlb_dir / "Trends" / "_Style_Trends_Overview.md"

    trends: Dict[str, Tuple[float, float, str]] = {}
    trends_text = _read(trends_file)
    if trends_text:
        trends = _parse_trends(trends_text)

    pair_files: List[pathlib.Path] = (
        sorted(p for p in matchups_dir.glob("*.md") if not p.name.startswith("_"))
        if matchups_dir.is_dir() else []
    )

    written: List[pathlib.Path] = []
    index_entries: List[Tuple[str, str, str, str, str, str]] = []

    for pair_path in pair_files:
        pair_text = _read(pair_path)
        if not pair_text:
            continue
        matchup = _parse_matchup_note(pair_text)
        home_slug = str(matchup.get("home_slug", ""))
        away_slug = str(matchup.get("away_slug", ""))
        if not home_slug or not away_slug:
            continue

        home_name = _SLUG_TO_NAME.get(home_slug, home_slug.replace("_", " ").title())
        away_name = _SLUG_TO_NAME.get(away_slug, away_slug.replace("_", " ").title())

        ps_home = _parse_playstyle_note(t) if (t := _read(playstyles_dir / f"{home_slug}.md")) else None
        ps_away = (
            ps_home if home_slug == away_slug
            else (_parse_playstyle_note(t) if (t := _read(playstyles_dir / f"{away_slug}.md")) else None)
        )

        out_path = out_dir / pair_path.name
        write_note(
            out_path,
            render_brief(
                pair_filename=pair_path.name,
                matchup=matchup,
                playstyle_home=ps_home,
                playstyle_away=ps_away,
                trends=trends,
                slug_to_name=_SLUG_TO_NAME,
            ),
        )
        written.append(out_path)

        try:
            hwr_pct = f"{float(str(matchup.get('home_win_rate', 0))) * 100:.1f}%"
        except (ValueError, TypeError):
            hwr_pct = str(matchup.get("home_win_rate", ""))

        index_entries.append((pair_path.stem, home_slug, away_slug, home_name, away_name, hwr_pct))

    written.append(render_index(index_entries, out_dir))
    return written
