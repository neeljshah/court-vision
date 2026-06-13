"""domains.soccer.atlas_seasons_render — Markdown renderers for season-dimension notes.

Separated from atlas_seasons.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas_seasons — never imported across domain boundaries.

All output is descriptive scouting intelligence; no betting/edge language.
"""
from __future__ import annotations

import datetime
from typing import Dict, List

from scripts.platformkit.atlas.obsidian_emit import slug as _slug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _team_link(team: str) -> str:
    """Emit a [[wikilink]] to the Teams/<slug> note."""
    return f"[[Teams/{_slug(team)}|{team}]]"


def _season_link(display: str, season: object) -> str:
    """Emit a [[wikilink]] to a season note.

    The season note filename is ``{_slug(display)} {season}.md`` (slug applied to
    the display name only; the year is appended with a literal space).  The link
    target must therefore be ``"{_slug(display)} {season}"`` — not a fully-slugged
    concatenation of the two, which would replace the space before the year with
    an underscore and dangle.
    """
    target = f"{_slug(display)} {season}"
    return f"[[{target}|{display} {season}]]"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _sign(n: int) -> str:
    if n > 0:
        return f"+{n}"
    return str(n)


# ---------------------------------------------------------------------------
# _Seasons_Index.md
# ---------------------------------------------------------------------------


def render_seasons_index(season_records: List[Dict]) -> str:
    """Render the _Seasons_Index.md hub note."""
    generated = datetime.date.today().isoformat()
    n_seasons = len(season_records)

    # Group by div for the table
    by_div: Dict[str, List[Dict]] = {}
    for rec in season_records:
        by_div.setdefault(rec["div"], []).append(rec)

    lines: List[str] = [
        "---",
        "type: seasons-index",
        "sport: soccer",
        f"season_count: {n_seasons}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - season",
        "---",
        "",
        "# Soccer Seasons Index",
        "",
        "Up: [[_Index]]",
        "",
        f"Season tables available: **{n_seasons}** across {len(by_div)} league(s).",
        "",
    ]

    for div in sorted(by_div):
        records = sorted(by_div[div], key=lambda r: str(r["season"]))
        display = records[0]["display"]
        lines += [
            f"## {display} (`{div}`)",
            "",
            "| Season | Champion | Matches | Partial? |",
            "|--------|----------|---------|----------|",
        ]
        for rec in records:
            champ_link = _team_link(rec["champion"])
            partial = "yes" if rec["is_partial"] else "no"
            season_lnk = _season_link(rec["display"], rec["season"])
            lines.append(
                f"| {season_lnk} | {champ_link} | {rec['n_matches']} | {partial} |"
            )
        lines.append("")

    lines += ["#sport/soccer #season"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# <Div> <Season>.md per season
# ---------------------------------------------------------------------------


def render_season_note(
    *,
    div: str,
    season: object,
    display: str,
    table: List[Dict],
    stats: Dict,
    champion: str,
    is_partial: bool,
) -> str:
    """Render a single (league, season) final-table note."""
    generated = datetime.date.today().isoformat()
    n_teams = len(table)
    relegation_cutoff = max(0, n_teams - 3)  # bottom 3 rows

    team_list = ", ".join(f'"{r["team"]}"' for r in table)

    lines: List[str] = [
        "---",
        f'div: "{div}"',
        f'league: "{display}"',
        f"season: {season}",
        f'champion: "{champion}"',
        f"teams: [{team_list}]",
        f"n_matches: {stats['n_matches']}",
        f"partial_season: {'true' if is_partial else 'false'}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - season",
        "---",
        "",
        f"# {display} — Season {season}",
        "",
        f"Up: [[_Seasons_Index]] · [[Leagues/{_slug(display)}|{display}]]",
        "",
    ]

    if is_partial:
        lines += [
            "> [!WARNING] Partial Season",
            "> This season has fewer matches than a complete round-robin would produce.",
            "> The final table reflects results available in the corpus only.",
            "",
        ]

    # Season overview
    lines += [
        "## Season Overview",
        "",
        "| Stat | Value |",
        "|------|-------|",
        f"| Champion | {_team_link(champion)} |",
        f"| Matches | {stats['n_matches']} |",
        f"| Total Goals | {stats['total_goals']} |",
        f"| Avg Goals/Game | {stats['avg_goals']:.2f} |",
        f"| Over-2.5 Rate | {_pct(stats['over25_rate'])} ({stats['over25']} of {stats['n_matches']}) |",
        "",
    ]

    # Final table
    lines += [
        "## Final Table",
        "",
        "| Rank | Team | P | W | D | L | GF | GA | GD | Pts |",
        "|------|------|---|---|---|---|----|----|-----|-----|",
    ]
    for rank, row in enumerate(table, start=1):
        team_lnk = _team_link(row["team"])
        suffix = ""
        if rank == 1:
            suffix = " [C]"
        elif rank > relegation_cutoff and n_teams >= 4:
            suffix = " ↓"
        lines.append(
            f"| {rank}{suffix} | {team_lnk} | {row['P']} | {row['W']} | {row['D']} "
            f"| {row['L']} | {row['GF']} | {row['GA']} | {_sign(row['GD'])} | **{row['Pts']}** |"
        )

    lines += [
        "",
        "<!-- Rank 1 = Champion · ↓ = Relegation zone (bottom 3) -->",
        "",
    ]

    # Relegation note
    if n_teams >= 4:
        relegation_teams = [_team_link(table[i]["team"]) for i in range(relegation_cutoff, n_teams)]
        lines += [
            "## Notes",
            "",
            f"**Champion:** {_team_link(champion)}",
            "",
            f"**Relegation zone (bottom {n_teams - relegation_cutoff}):** "
            + ", ".join(relegation_teams),
            "",
        ]

    lines.append("#sport/soccer #season")
    return "\n".join(lines) + "\n"
