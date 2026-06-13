"""domains.basketball_nba.memory_atlas_render — Obsidian note rendering for NBA atlas.

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Optional

import pandas as pd

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")

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
    return _SPACE_RE.sub("_", _SLUG_RE.sub("", name).strip())

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

def _render_section(section_name: str, data: dict) -> str:
    """Render section dict as markdown; skip DEFER notes and _-prefixed keys."""
    lines: list[str] = [f"### {section_name.replace('_', ' ').title()}"]
    for k, v in data.items():
        if k.startswith("_"): continue
        if isinstance(v, dict):
            if "DEFER" in str(v.get("_note", "")): continue
            if v.get("value") is not None: lines.append(f"- **{k}**: {_fmt(v['value'])}")
        elif isinstance(v, (int, float)): lines.append(f"- **{k}**: {_fmt(v)}")
        elif v is not None: lines.append(f"- **{k}**: {v}")
    return "" if len(lines) == 1 else "\n".join(lines) + "\n"

def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

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
    top = players_df.head(top_n)
    lines = [
        "---", "tags:", "  - sport/nba", "  - atlas/index", "---", "",
        "# NBA Intelligence Atlas — Index", "",
        "[[_Hub]] | [[Basketball_NBA]]", "",
        f"**Players indexed:** {len(players_df)}  |  **Teams:** {len(teams)}  |  "
        "**Sources:** player_adv_stats.parquet · player_positions.parquet · "
        "player_pf.parquet · team_advanced_stats.parquet · data/cache/atlas_*.parquet",
        "", "## Top Players by Usage Rate", "",
        "| Player | Team | Usage% | MPG | PIE | Net Rtg On/Off |",
        "|--------|------|--------|-----|-----|----------------|",
    ]
    for _, r in top.iterrows():
        name = r.get("display_name", str(r["player_id"]))
        team = r.get("team", "—")
        lines.append(
            f"| [[Players/{_slug(name)}|{name}]] | [[Teams/{team}|{team}]] | "
            f"{_fmt(r.get('usage_rate'), 3)} | {_fmt(r.get('minutes_pg'))} | "
            f"{_fmt(r.get('pie_mean'), 3)} | {_fmt(r.get('on_off_net_diff'))} |"
        )
    lines += ["", "## Teams", ""]
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
    top_players: list[str],
    team_adv: Optional[pd.Series],
) -> pathlib.Path:
    division = TEAM_DIV.get(tricode, "Unknown")
    conf = TEAM_CONF.get(tricode, "Unknown")
    lines = [
        "---", f"tricode: {tricode}", f'division: "{division}"', f'conference: "{conf}"',
        "tags:", "  - sport/nba", "  - atlas/team", "---", "",
        f"# {tricode}", "", f"[[_Index]] | {conf} · {division}", "",
        "## Roster (Top Players by Usage)", "",
    ]
    lines.extend(f"- [[Players/{_slug(n)}|{n}]]" for n in top_players)
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
    team_roster: dict[str, list[str]],
) -> list[pathlib.Path]:
    """Render all notes and return written paths."""
    written: list[pathlib.Path] = []
    teams = sorted(team_sections.keys())
    written.append(render_index(out_dir, players_df, teams))
    for _, r in players_df.iterrows():
        pid = int(r["player_id"])
        written.append(render_player(
            out_dir, pid, str(r.get("display_name", str(pid))),
            str(r.get("team", "—")), str(r.get("position", "—")),
            adv_by_player.get(pid), player_sections.get(pid, {}),
        ))
    for tricode in teams:
        written.append(render_team(
            out_dir, tricode, team_sections.get(tricode, {}),
            team_roster.get(tricode, []), team_adv_by_tricode.get(tricode),
        ))
    return written
