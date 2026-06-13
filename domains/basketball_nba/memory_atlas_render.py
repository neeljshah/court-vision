"""domains.basketball_nba.memory_atlas_render — Obsidian note rendering for NBA atlas.

Team notes use name-free archetype composition (e.g. "2 High-Usage Creators,
3 Low-Usage Connectors") instead of individual player lists.  Player-name keys
are stripped from JSON section data before rendering.

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import slug as _slug_fn, write_note

NBA_DIVISIONS: dict[str, list[str]] = {
    "Atlantic": ["BOS", "BKN", "NYK", "PHI", "TOR"], "Central": ["CHI", "CLE", "DET", "IND", "MIL"],
    "Southeast": ["ATL", "CHA", "MIA", "ORL", "WAS"], "Northwest": ["DEN", "MIN", "OKC", "POR", "UTA"],
    "Pacific": ["GSW", "LAC", "LAL", "PHX", "SAC"], "Southwest": ["DAL", "HOU", "MEM", "NOP", "SAS"],
}
_EAST = ("Atlantic", "Central", "Southeast")
TEAM_CONF: dict[str, str] = {t: ("East" if d in _EAST else "West") for d, ts in NBA_DIVISIONS.items() for t in ts}
TEAM_DIV: dict[str, str] = {t: d for d, ts in NBA_DIVISIONS.items() for t in ts}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    return _slug_fn(name)

def _safe_float(v: Any, d: int = 1) -> Optional[float]:
    try: return round(float(v), d)
    except (TypeError, ValueError): return None

def _fmt(v: Any, d: int = 1) -> str:
    f = _safe_float(v, d); return str(f) if f is not None else "—"

def _stat_line(label: str, v: Any, d: int = 1) -> str:
    return f"- **{label}**: {_fmt(v, d)}"

def _parse_json_col(raw: Any) -> dict:
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        try: return json.loads(raw)
        except (json.JSONDecodeError, TypeError): return {}
    return {}

_NAME_KEYS: frozenset[str] = frozenset({
    # Keys whose values are player display names or name lists
    "player_name", "lineup_names", "display_name", "name", "player_names",
    # Lineup synergy: combo_5man is a list of dicts each containing a "lineup"
    # key whose value is a list of abbreviated player names — drop the whole field
    "combo_5man",
    # Within each lineup-synergy dict the "lineup" key holds abbreviated names
    "lineup",
    # Rotation-patterns: starters/closing_lineup contain lineup_names (already
    # covered above), but belt-and-suspenders in case the key itself is raw
    "lineup_name",
})


def _strip_names(obj: object) -> object:
    """Recursively remove name-bearing keys from dicts/lists.

    Removes any key whose name is in ``_NAME_KEYS`` from dict nodes.
    Passes numeric, boolean, and non-name string values through unchanged.
    """
    if isinstance(obj, dict):
        return {k: _strip_names(v) for k, v in obj.items() if k not in _NAME_KEYS}
    if isinstance(obj, list):
        return [_strip_names(item) for item in obj]
    return obj


def _render_section(section_name: str, data: dict) -> str:
    """Render section dict as markdown; skip DEFER notes and _-prefixed keys.

    Player-name bearing keys are stripped from all nested JSON structures
    before rendering so no individual names appear in team notes.
    """
    lines: list[str] = [f"### {section_name.replace('_', ' ').title()}"]
    for k, v in data.items():
        if k.startswith("_"): continue
        if k in _NAME_KEYS: continue  # skip name-bearing top-level keys
        if isinstance(v, dict):
            v = _strip_names(v)
            if "DEFER" in str(v.get("_note", "")): continue
            if v.get("value") is not None: lines.append(f"- **{k}**: {_fmt(v['value'])}")
        elif isinstance(v, list):
            v = _strip_names(v)
            lines.append(f"- **{k}**: {v}")
        elif isinstance(v, (int, float)): lines.append(f"- **{k}**: {_fmt(v)}")
        elif v is not None: lines.append(f"- **{k}**: {v}")
    return "" if len(lines) == 1 else "\n".join(lines) + "\n"

def _write(path: pathlib.Path, text: str) -> None:
    write_note(path, text)

# ---------------------------------------------------------------------------
# Section renderer (shared player + team)
# ---------------------------------------------------------------------------

def _render_sections(rows: dict[str, pd.Series], skip_key: str) -> list[str]:
    lines: list[str] = []
    for section_name, row in rows.items():
        if row is None: continue
        data: dict = {}
        for col in row.index:
            if col in (skip_key, "_cv_fields", "n", "confidence", "as_of", "value"): continue
            v = row[col]
            parsed = _parse_json_col(v)
            if parsed: data[col] = parsed
            elif v is not None and not (isinstance(v, float) and pd.isna(v)): data[col] = v
        rendered = _render_section(section_name, data)
        if rendered: lines += [rendered, ""]
    return lines

# ---------------------------------------------------------------------------
# Note renderers
# ---------------------------------------------------------------------------

def render_index(out_dir: pathlib.Path, players_df: pd.DataFrame, teams: list[str], top_n: int = 20) -> pathlib.Path:
    lines = [
        "---", "tags:", "  - sport/nba", "  - atlas/index", "---", "",
        "# NBA Intelligence Atlas — Index", "",
        "[[_Hub]]", "",
        f"**Players indexed:** {len(players_df)}  |  **Teams:** {len(teams)}  |  "
        "**Sources:** player_adv_stats.parquet · player_positions.parquet · "
        "player_pf.parquet · team_advanced_stats.parquet · data/cache/atlas_*.parquet",
        "",
        "## Playstyle Archetypes", "",
        "Player intelligence is organised by playstyle archetype rather than individual notes.",
        "See [[Archetypes/_Archetypes_Index]] for the full population breakdown.",
        "",
    ]
    lines += ["## Teams", ""]
    for div, div_teams in NBA_DIVISIONS.items():
        conf = "East" if div in _EAST else "West"
        present = [t for t in div_teams if t in teams]
        if present:
            lines.append(f"- **{div}** ({conf}): " + " · ".join(f"[[Teams/{t}|{t}]]" for t in present))
    path = out_dir / "_Index.md"
    _write(path, "\n".join(lines) + "\n")
    return path


def render_player(
    out_dir: pathlib.Path,
    player_id: int,
    display_name: str,
    team: str,
    position: str,
    adv_row: Optional[pd.Series],
    section_rows: dict[str, pd.Series],
) -> pathlib.Path:
    slug = _slug(display_name)
    lines = [
        "---", f'name: "{display_name}"', f"team: {team}", f'position: "{position}"',
        "tags:", "  - sport/nba", "  - atlas/player", "---", "",
        f"# {display_name}", "", f"[[Teams/{team}|{team}]] | [[_Index]]", "", "## Core Stats", "",
    ]
    if adv_row is not None:
        for label, col in [
            ("Usage%", "usagepercentage"), ("TS%", "trueshootingpercentage"),
            ("eFG%", "effectivefieldgoalpercentage"), ("AST%", "assistpercentage"),
            ("Net Rtg", "netrating"), ("PIE", "pie"), ("MPG (sample)", "minutes"),
            ("Off Rtg", "offensiverating"), ("Def Rtg", "defensiverating"),
        ]:
            lines.append(_stat_line(label, adv_row.get(col)))
    else:
        lines.append("_No advanced stats row found._")
    lines.append("")
    lines.extend(_render_sections(section_rows, "player_id"))
    path = out_dir / "Players" / f"{slug}.md"
    _write(path, "\n".join(lines) + "\n")
    return path


def render_team(
    out_dir: pathlib.Path,
    tricode: str,
    team_section_rows: dict[str, pd.Series],
    team_archetype_composition: list[tuple[int, str]],
    team_adv: Optional[pd.Series],
) -> pathlib.Path:
    """Render one team note.  No individual player names are included.

    Parameters
    ----------
    out_dir:
        Root atlas directory; note is written to out_dir/Teams/<tricode>.md.
    tricode:
        Three-letter team abbreviation.
    team_section_rows:
        Dict of section_name -> parquet row for this team.
    team_archetype_composition:
        List of (count, archetype_label) pairs, sorted descending by count.
        Emitted as a name-free "Archetype Composition" section.
    team_adv:
        Season-average advanced-stats row, or None if unavailable.
    """
    division = TEAM_DIV.get(tricode, "Unknown")
    conf = TEAM_CONF.get(tricode, "Unknown")
    lines = [
        "---", f"tricode: {tricode}", f'division: "{division}"', f'conference: "{conf}"',
        "tags:", "  - sport/nba", "  - atlas/team", "---", "",
        f"# {tricode}", "", f"[[_Index]] | {conf} · {division}", "",
        "## Archetype Composition", "",
    ]
    if team_archetype_composition:
        for count, label in team_archetype_composition:
            lines.append(f"- {count} {label}")
    else:
        lines.append("_No composition data available._")
    lines.append("")
    if team_adv is not None:
        lines += ["## Team Stats (Season Average)", ""]
        for label, col, d in [
            ("Pace", "pace", 1), ("Off Rtg", "off_rtg", 1), ("Def Rtg", "def_rtg", 1),
            ("eFG%", "efg_pct", 3), ("TS%", "ts_pct", 3), ("OREB%", "oreb_pct", 3),
            ("DREB%", "dreb_pct", 3), ("AST%", "ast_pct", 3), ("TOV Ratio", "tov_ratio", 2),
        ]:
            lines.append(_stat_line(label, team_adv.get(col), d))
        lines.append("")
    lines.extend(_render_sections(team_section_rows, "team_tricode"))
    path = out_dir / "Teams" / f"{tricode}.md"
    _write(path, "\n".join(lines) + "\n")
    return path


def render_all(
    out_dir: pathlib.Path,
    players_df: pd.DataFrame,
    adv_by_player: dict[int, pd.Series],
    player_sections: dict[int, dict[str, pd.Series]],
    team_sections: dict[str, dict[str, pd.Series]],
    team_adv_by_tricode: dict[str, pd.Series],
    team_archetype_composition: dict[str, list[tuple[int, str]]],
) -> list[pathlib.Path]:
    """Render all notes and return written paths.

    Player notes are NOT emitted (replaced by archetype notes via
    ``memory_atlas_archetypes.build_archetypes``).  Only _Index.md and
    Teams/<tricode>.md are written here, with no individual player names.
    """
    written: list[pathlib.Path] = []
    teams = sorted(team_sections.keys())
    written.append(render_index(out_dir, players_df, teams))
    # Player notes intentionally omitted — see memory_atlas_archetypes.build_archetypes
    for tricode in teams:
        written.append(render_team(
            out_dir, tricode, team_sections.get(tricode, {}),
            team_archetype_composition.get(tricode, []),
            team_adv_by_tricode.get(tricode),
        ))
    return written
