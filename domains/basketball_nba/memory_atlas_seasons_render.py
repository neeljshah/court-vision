"""domains.basketball_nba.memory_atlas_seasons_render — Markdown rendering helpers for
the NBA season atlas (memory_atlas_seasons.py).

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
Idempotent helpers; all state is passed as arguments.

Public API
----------
render_season_note(season, season_df, players_df) -> str
render_index(seasons) -> str
write_note(path, text) -> None
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Constants (mirrored from memory_atlas_seasons for rendering)
# ---------------------------------------------------------------------------

_MIN_VORP: float = 1.0
_TOP_PLAYERS: int = 8

# ---------------------------------------------------------------------------
# Slug helper (mirrors memory_atlas_render._slug)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")


def _slug(name: str) -> str:
    return _SPACE_RE.sub("_", _SLUG_RE.sub("", name).strip())


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(v: Any, d: int = 1) -> str:
    try:
        return str(round(float(v), d))
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_efficiency_context(season_df: pd.DataFrame, season: str) -> str:
    """Render league-wide efficiency context summary."""
    if season_df.empty:
        return ""

    league_off = season_df["off_rtg"].mean() if "off_rtg" in season_df.columns else None
    league_def = season_df["def_rtg"].mean() if "def_rtg" in season_df.columns else None
    league_pace = season_df["pace"].mean() if "pace" in season_df.columns else None
    league_efg = season_df["efg_pct"].mean() if "efg_pct" in season_df.columns else None

    lines = [
        "## League Context",
        "",
        f"- **League Avg Off Rtg**: {_fmt(league_off, 1)}",
        f"- **League Avg Def Rtg**: {_fmt(league_def, 1)}",
        f"- **League Avg Pace**: {_fmt(league_pace, 1)}",
        f"- **League Avg eFG%**: {_fmt(league_efg, 3)}",
        f"- **Teams in sample**: {len(season_df)}",
    ]
    return "\n".join(lines)


def render_team_table(season_df: pd.DataFrame) -> str:
    """Render a markdown table of all teams sorted by net rating (off - def)."""
    df = season_df.copy()
    if "off_rtg" not in df.columns or "def_rtg" not in df.columns:
        return ""

    df["net_rtg"] = (df["off_rtg"] - df["def_rtg"]).round(1)
    df = df.sort_values("net_rtg", ascending=False).reset_index(drop=True)

    lines: list[str] = [
        "## Team Ratings (season average, sorted by Net Rtg)",
        "",
        "| Rank | Team | Off Rtg | Def Rtg | Net Rtg | Pace | eFG% | TS% |",
        "|------|------|---------|---------|---------|------|------|-----|",
    ]
    for rank, row in df.iterrows():
        tricode = str(row["team_tricode"])
        link = f"[[Teams/{tricode}|{tricode}]]"
        lines.append(
            f"| {rank + 1} | {link} | {_fmt(row.get('off_rtg'), 1)} |"
            f" {_fmt(row.get('def_rtg'), 1)} | {_fmt(row.get('net_rtg'), 1)} |"
            f" {_fmt(row.get('pace'), 1)} | {_fmt(row.get('efg_pct', row.get('efg_pct')), 3)} |"
            f" {_fmt(row.get('ts_pct'), 3)} |"
        )
    return "\n".join(lines)


def render_player_leaders(players_df: pd.DataFrame, season: str) -> str:
    """Render top players by BPM (VORP-filtered) with wikilinks."""
    sub = players_df[players_df["season"] == season].copy()
    if sub.empty:
        return ""

    if "vorp" in sub.columns:
        sub = sub[sub["vorp"] >= _MIN_VORP]

    if sub.empty:
        return ""

    sub = sub.nlargest(_TOP_PLAYERS, "bpm" if "bpm" in sub.columns else sub.columns[0])

    lines: list[str] = [
        "## Player Leaders (BPM, min VORP ≥ 1.0)",
        "",
        "| Rank | Player | Team | BPM | VORP | PER | TS% | USG% |",
        "|------|--------|------|-----|------|-----|-----|------|",
    ]
    for rank, (_, row) in enumerate(sub.iterrows(), 1):
        name = str(row["player_name"])
        slug = _slug(name)
        link = f"[[Players/{slug}|{name}]]"
        team = str(row.get("team", "—"))
        team_link = f"[[Teams/{team}|{team}]]" if team != "—" else "—"
        lines.append(
            f"| {rank} | {link} | {team_link} |"
            f" {_fmt(row.get('bpm'), 1)} | {_fmt(row.get('vorp'), 1)} |"
            f" {_fmt(row.get('per'), 1)} | {_fmt(row.get('ts_pct'), 3)} |"
            f" {_fmt(row.get('usg_pct'), 1)} |"
        )
    return "\n".join(lines)


def render_season_note(
    season: str,
    season_df: pd.DataFrame,
    players_df: pd.DataFrame,
) -> str:
    """Return the full Markdown text for a single season note."""
    frontmatter = (
        "---\n"
        f'season: "{season}"\n'
        "tags:\n"
        "  - sport/nba\n"
        "  - atlas/season\n"
        "---\n"
    )
    header = (
        f"# NBA Season {season}\n\n"
        f"[[_Seasons_Index]] | [[_Index]]\n\n"
        f"Data source: `data/team_advanced_stats.parquet` "
        f"+ `data/cache/bbref_advanced_extended.parquet`\n"
    )

    sections: list[str] = [
        frontmatter,
        header,
        render_efficiency_context(season_df, season),
        "",
        render_team_table(season_df),
        "",
        render_player_leaders(players_df, season),
    ]
    return "\n".join(s for s in sections if s is not None)


def render_index(seasons: list[str]) -> str:
    """Return Markdown for the _Seasons_Index hub note."""
    frontmatter = (
        "---\n"
        'title: "NBA Seasons Index"\n'
        "tags:\n"
        "  - sport/nba\n"
        "  - atlas/index\n"
        "---\n"
    )
    lines: list[str] = [
        frontmatter,
        "# NBA Seasons Index\n",
        "[[_Index]]\n",
        "Season notes with league-wide team ratings and player leaders.\n",
        "## Seasons\n",
    ]
    for season in sorted(seasons):
        lines.append(f"- [[Seasons/{season}|{season}]]")
    return "\n".join(lines) + "\n"


def write_note(path: pathlib.Path, text: str) -> None:
    """Write text to path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
