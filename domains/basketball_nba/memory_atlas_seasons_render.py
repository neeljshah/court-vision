"""domains.basketball_nba.memory_atlas_seasons_render — Markdown rendering helpers for
the NBA season atlas (memory_atlas_seasons.py).

F5-clean: stdlib + pandas only.  No src.* / kernel.* / edge language.
Idempotent helpers; all state is passed as arguments.
No individual player names are emitted — team-level and league-level data only.

Public API
----------
render_season_note(season, season_df, archetype_mix) -> str
render_index(seasons) -> str
write_note(path, text) -> None
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note

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
    """Render league-wide efficiency context summary (no player names)."""
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

    lines: List[str] = [
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


def render_league_stat_distributions(season_df: pd.DataFrame) -> str:
    """Render league-wide stat distribution summary (median, top-quartile) across teams.

    No individual player names — aggregate distribution only.
    """
    if season_df.empty:
        return ""

    lines: List[str] = [
        "## League Stat Distributions (team-level)",
        "",
    ]

    stat_meta = [
        ("net_rtg",  "Net Rtg",  1),
        ("off_rtg",  "Off Rtg",  1),
        ("def_rtg",  "Def Rtg",  1),
        ("pace",     "Pace",     1),
        ("efg_pct",  "eFG%",     3),
        ("ts_pct",   "TS%",      3),
    ]

    df = season_df.copy()
    if "net_rtg" not in df.columns and "off_rtg" in df.columns and "def_rtg" in df.columns:
        df["net_rtg"] = (df["off_rtg"] - df["def_rtg"]).round(3)

    lines.append("| Stat | Median | Top-Quartile (≥ P75) |")
    lines.append("|------|--------|----------------------|")

    for col, label, decimals in stat_meta:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        median_val = series.median()
        p75_val = series.quantile(0.75)
        lines.append(
            f"| {label} | {_fmt(median_val, decimals)} | {_fmt(p75_val, decimals)} |"
        )

    return "\n".join(lines)


def render_archetype_mix(archetype_mix: Dict[str, int], season: str) -> str:
    """Render counts of players per archetype for this season (no names).

    Parameters
    ----------
    archetype_mix:
        Mapping of archetype label -> player count for this season.
    season:
        Season label used in the header.
    """
    if not archetype_mix:
        return ""

    total = sum(archetype_mix.values())
    if total == 0:
        return ""

    lines: List[str] = [
        "## Archetype Mix (player counts, no names)",
        "",
        "| Archetype | Count | Share |",
        "|-----------|-------|-------|",
    ]
    for label, count in sorted(archetype_mix.items(), key=lambda x: -x[1]):
        share = f"{100 * count / total:.1f}%" if total > 0 else "—"
        lines.append(f"| {label} | {count} | {share} |")

    lines.append(f"\n_Total classified: {total}_")
    return "\n".join(lines)


def render_season_note(
    season: str,
    season_df: pd.DataFrame,
    archetype_mix: Dict[str, int],
) -> str:
    """Return the full Markdown text for a single season note.

    No individual player names are included. Contains:
      - YAML frontmatter
      - League context (averages across teams)
      - Team ratings table (teams OK)
      - League stat distributions (median/top-quartile)
      - Archetype mix (counts only, no names)
    """
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
        f"Data source: `data/team_advanced_stats.parquet`\n"
    )

    sections: List[str] = [
        frontmatter,
        header,
        render_efficiency_context(season_df, season),
        "",
        render_team_table(season_df),
        "",
        render_league_stat_distributions(season_df),
        "",
        render_archetype_mix(archetype_mix, season),
    ]
    return "\n".join(s for s in sections if s is not None)


def render_index(seasons: List[str]) -> str:
    """Return Markdown for the _Seasons_Index hub note."""
    frontmatter = (
        "---\n"
        'title: "NBA Seasons Index"\n'
        "tags:\n"
        "  - sport/nba\n"
        "  - atlas/index\n"
        "---\n"
    )
    lines: List[str] = [
        frontmatter,
        "# NBA Seasons Index\n",
        "[[_Index]]\n",
        "Season notes with league-wide team ratings and stat distributions (no individual names).\n",
        "## Seasons\n",
    ]
    for season in sorted(seasons):
        lines.append(f"- [[Seasons/{season}|{season}]]")
    return "\n".join(lines) + "\n"


# write_note re-exported from obsidian_emit for callers that import it from here
__all__ = [
    "render_efficiency_context", "render_team_table",
    "render_league_stat_distributions", "render_archetype_mix",
    "render_season_note", "render_index", "write_note",
]
