"""domains.soccer.atlas_render — Obsidian markdown renderers for the soccer atlas.

Separated from atlas.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas — never imported across domain boundaries.

All output is descriptive scouting intelligence; no betting/edge language.
"""
from __future__ import annotations

import datetime
from typing import Dict, List

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import slug as _slug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _league_link(display: str) -> str:
    return f"[[Leagues/{display.replace(' ', '_')}|{display}]]"


def _team_link(team: str, team_slugs: Dict[str, str]) -> str:
    slug = team_slugs.get(team, _slug(team))
    return f"[[Teams/{slug}|{team}]]"


def _fm(*pairs) -> List[str]:
    """Emit YAML frontmatter lines for key-value pairs."""
    lines = ["---"]
    for k, v in pairs:
        lines.append(f"{k}: {v}")
    return lines + ["---", ""]


# ---------------------------------------------------------------------------
# _Index.md renderer
# ---------------------------------------------------------------------------


def render_index(
    df: pd.DataFrame,
    league_rows: List[Dict],
    top_global_teams: List[Dict],
) -> str:
    """Render the hub _Index.md content."""
    date_min = str(df["date"].min())[:10]
    date_max = str(df["date"].max())[:10]
    n_matches = len(df)
    n_teams = len(set(df["home_team"].tolist()) | set(df["away_team"].tolist()))
    n_seasons = df["season"].nunique()
    generated = datetime.date.today().isoformat()

    lines: List[str] = _fm(
        ("type", "atlas-index"), ("sport", "soccer"),
        ("corpus_matches", n_matches), ("corpus_date_min", date_min),
        ("corpus_date_max", date_max), ("generated", generated),
        ("tags", ""), ("  - sport/soccer", ""), ("  - atlas/index", ""),
    )
    # Fix YAML list indentation (fm helper emits key: value pairs only)
    # Re-emit with proper YAML
    lines = [
        "---", "type: atlas-index", "sport: soccer",
        f"corpus_matches: {n_matches}", f"corpus_date_min: {date_min}",
        f"corpus_date_max: {date_max}", f"generated: {generated}",
        "tags:", "  - sport/soccer", "  - atlas/index", "---", "",
    ]

    lines += [
        "# Soccer Intelligence Atlas", "",
        "Up: [[_Hub]]", "",
        "## Corpus Overview", "",
        "| Field | Value |", "|-------|-------|",
        f"| Matches | {n_matches:,} |",
        f"| Teams | {n_teams} |",
        f"| Seasons | {n_seasons} ({date_min[:4]}–{date_max[:4]}) |",
        f"| Leagues | {len(league_rows)} |", "",
    ]

    lines += [
        "## League Summary", "",
        "| League | Div | Matches | Avg Goals/Game | Over-2.5% | Home Win% |",
        "|--------|-----|---------|----------------|-----------|-----------|",
    ]
    for lr in sorted(league_rows, key=lambda x: x["div"]):
        lines.append(
            f"| {_league_link(lr['display'])} | {lr['div']} | {lr['n_matches']:,} "
            f"| {lr['avg_goals']:.2f} | {_pct(lr['over25_rate'])} "
            f"| {_pct(lr['home_win_pct'])} |"
        )
    lines.append("")

    lines += [
        "## Top Teams by Points per Game (corpus-wide)", "",
        "| Team | PPG | W | D | L | Matches | GF/G | GA/G |",
        "|------|-----|---|---|---|---------|------|------|",
    ]
    for s in top_global_teams:
        link = f"[[Teams/{_slug(s['team'])}|{s['team']}]]"
        lines.append(
            f"| {link} | {s['ppg']:.3f} | {s['wins']} | {s['draws']} "
            f"| {s['losses']} | {s['n_total']} "
            f"| {s['gf_pg']:.2f} | {s['ga_pg']:.2f} |"
        )
    lines.append("")

    lines += ["## Leagues", ""]
    for lr in sorted(league_rows, key=lambda x: x["div"]):
        lines.append(f"- {_league_link(lr['display'])} (`{lr['div']}`)")
    lines += ["", "## See Also", "", "- [[_Hub]]", "", "#sport/soccer #atlas/index"]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Teams/<Team>.md renderer
# ---------------------------------------------------------------------------


def render_team(s: Dict) -> str:
    """Render a single team note."""
    from domains.soccer.config import LEAGUES

    team = s["team"]
    divs_str = ", ".join(s["divs"])
    seasons_str = ", ".join(str(x) for x in s["seasons"])

    lines: List[str] = [
        "---", f'team: "{team}"', f"leagues: [{divs_str}]",
        f"seasons_covered: {len(s['seasons'])}",
        f"corpus_matches: {s['n_total']}",
        "tags:", "  - sport/soccer", "  - atlas/team", "---", "",
        f"# {team}", "", "Up: [[_Index|Soccer Index]]", "",
        "## Corpus Record", "",
        "| Stat | Value |", "|------|-------|",
        f"| Matches | {s['n_total']} |",
        f"| Record (W-D-L) | {s['wins']}-{s['draws']}-{s['losses']} |",
        f"| Points per Game | {s['ppg']:.3f} |",
        f"| Goals For/Game | {s['gf_pg']:.3f} |",
        f"| Goals Against/Game | {s['ga_pg']:.3f} |",
        f"| Over-2.5 Rate | {_pct(s['over25_pct'])} |",
        f"| Clean Sheet % | {_pct(s['cs_pct'])} |",
        f"| BTTS % | {_pct(s['btts_pct'])} |", "",
        "## Home vs Away Splits", "",
        "| Venue | Matches | GF/G | GA/G |",
        "|-------|---------|------|------|",
        f"| Home | {s['n_home']} | {s['gf_home_pg']:.3f} | {s['ga_home_pg']:.3f} |",
        f"| Away | {s['n_away']} | {s['gf_away_pg']:.3f} | {s['ga_away_pg']:.3f} |",
        "",
    ]

    if s["recent_season"] is not None:
        rsn = s["recent_season"]
        lines += [
            f"## Recent Season ({rsn})", "",
            "| Stat | Value |", "|------|-------|",
            f"| Matches | {s['recent_n']} |",
            f"| Record (W-D-L) | {s['recent_wins']}-{s['recent_draws']}-{s['recent_losses']} |",
            f"| Points | {s['recent_pts']} |", "",
        ]

    league_links = [
        _league_link(LEAGUES.get(div, div)) for div in s["divs"]
    ]
    lines += [
        "## Competitions", "",
        f"**Divisions:** {divs_str}", "",
        f"**Seasons:** {seasons_str}", "",
    ]
    if league_links:
        lines += [f"**League Notes:** {' · '.join(league_links)}", ""]

    if s["top_opponents"]:
        lines += ["## Frequent Opponents", ""]
        for opp in s["top_opponents"]:
            lines.append(f"- [[Teams/{_slug(opp)}|{opp}]]")
        lines.append("")

    lines.append("#sport/soccer #atlas/team")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Leagues/<Div>.md renderer
# ---------------------------------------------------------------------------


def render_league(stats: Dict, team_slugs: Dict[str, str]) -> str:
    """Render a single league/division note."""
    display = stats["display"]
    div = stats["div"]
    seasons_str = ", ".join(str(x) for x in stats["seasons"])

    lines: List[str] = [
        "---", f'league: "{display}"', f'div_code: "{div}"',
        f"corpus_matches: {stats['n_matches']}",
        "tags:", "  - sport/soccer", "  - atlas/league", "---", "",
        f"# {display} (`{div}`)", "", "Up: [[_Index|Soccer Index]]", "",
        "## League Statistics (Corpus)", "",
        "| Stat | Value |", "|------|-------|",
        f"| Matches | {stats['n_matches']:,} |",
        f"| Seasons | {seasons_str} |",
        f"| Avg Goals/Game | {stats['avg_goals']:.3f} |",
        f"| Over-2.5 Rate | {_pct(stats['over25_rate'])} |",
        f"| Home Win % | {_pct(stats['home_win_pct'])} |",
        f"| Draw % | {_pct(stats['draw_pct'])} |",
        f"| Away Win % | {_pct(stats['away_win_pct'])} |", "",
    ]

    if stats["top_teams"]:
        lines += [
            f"## Top Teams by PPG (≥10 apps in {div})", "",
            "| Team | PPG |", "|------|-----|",
        ]
        for team_name, ppg in stats["top_teams"]:
            lines.append(f"| {_team_link(team_name, team_slugs)} | {ppg:.3f} |")
        lines.append("")

    lines.append("#sport/soccer #atlas/league")
    return "\n".join(lines) + "\n"
