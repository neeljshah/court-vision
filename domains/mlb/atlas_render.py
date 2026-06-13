"""domains.mlb.atlas_render — Obsidian Markdown rendering helpers for MLB atlas.

Pure rendering functions: each takes structured data and returns a string.
No I/O, no pandas reads — the atlas.py orchestrator handles that.

Import contract (F5-clean): stdlib + scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _frontmatter_dict


def _fmt_pct(v: float, decimals: int = 1) -> str:
    """Format a fraction [0,1] as a percentage string."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v * 100:.{decimals}f}%"


def _fmt_f(v: float, decimals: int = 2) -> str:
    """Format a float, handling NaN gracefully."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:.{decimals}f}"


def _wikilink(name: str) -> str:
    """Return an Obsidian [[wikilink]]."""
    return f"[[{name}]]"


def render_league(
    *,
    league: str,
    n_games: int,
    home_win_rate: float,
    avg_runs: float,
    teams: List[str],
    top_teams: List[str],
    seasons: List[int],
) -> str:
    """Render a League note for AL or NL."""
    season_span = f"{min(seasons)}–{max(seasons)}" if seasons else "n/a"
    fm = _frontmatter_dict({
        "league": league,
        "sport": "mlb",
        "corpus_span": season_span,
        "n_games": n_games,
        "tags": [f"sport/mlb", f"league/{league.lower()}"],
    })
    rival_league = "NL" if league == "AL" else "AL"

    top_links = ", ".join(_wikilink(f"Teams/{t}") for t in top_teams)
    all_links = " · ".join(_wikilink(f"Teams/{t}") for t in sorted(teams))

    lines = [
        fm,
        "",
        f"# {league} — American League" if league == "AL" else f"# {league} — National League",
        "",
        f"Part of {_wikilink('_Index')} | Sister league: {_wikilink(f'Leagues/{rival_league}')}",
        "",
        "## Corpus Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Games in corpus | {n_games:,} |",
        f"| Corpus span | {season_span} |",
        f"| Home win rate | {_fmt_pct(home_win_rate)} |",
        f"| Avg runs per game (both teams) | {_fmt_f(avg_runs)} |",
        "",
        "## Top Teams by Win %",
        "",
        top_links,
        "",
        "## All Teams",
        "",
        all_links,
        "",
        f"#sport/mlb #league/{league.lower()}",
    ]
    return "\n".join(lines) + "\n"


def render_team(
    *,
    team: str,
    league: str,
    stats: Any,  # pandas Series / row
    elo: float,
    rivals: List[str],
) -> str:
    """Render a Team note with real corpus stats."""
    seasons = getattr(stats, "seasons_active", None) or []
    if seasons:
        season_span = f"{min(seasons)}–{max(seasons)}"
    else:
        season_span = "n/a"

    fm = _frontmatter_dict({
        "team": team,
        "league": league,
        "sport": "mlb",
        "corpus_span": season_span,
        "elo": f"{elo:.1f}",
        "tags": [f"sport/mlb", f"league/{league.lower()}", f"team/{team.lower()}"],
    })

    games = int(stats["games"]) if not _is_nan(stats["games"]) else 0
    wins = int(stats["wins"]) if not _is_nan(stats["wins"]) else 0
    losses = int(stats["losses"]) if not _is_nan(stats["losses"]) else 0
    win_pct = float(stats["win_pct"]) if not _is_nan(stats["win_pct"]) else float("nan")
    rpg = float(stats["runs_per_game"]) if not _is_nan(stats["runs_per_game"]) else float("nan")
    rapg = float(stats["runs_allowed_per_game"]) if not _is_nan(stats["runs_allowed_per_game"]) else float("nan")
    rdiff = float(stats["run_diff"]) if not _is_nan(stats["run_diff"]) else float("nan")
    hwp = float(stats["home_win_pct"]) if not _is_nan(stats["home_win_pct"]) else float("nan")
    awp = float(stats["away_win_pct"]) if not _is_nan(stats["away_win_pct"]) else float("nan")

    season_win_pct: Dict[int, float] = stats.get("season_win_pct") or {}
    if hasattr(season_win_pct, "items"):
        season_rows = sorted(season_win_pct.items())
    else:
        season_rows = []

    # season trend table (compact)
    trend_lines: List[str] = []
    if season_rows:
        trend_lines += ["", "## Season Win % Trend", ""]
        trend_lines.append("| Season | Win % |")
        trend_lines.append("|--------|-------|")
        for yr, wp in season_rows:
            trend_lines.append(f"| {yr} | {_fmt_pct(wp)} |")

    rival_links = " · ".join(_wikilink(f"Teams/{r}") for r in sorted(rivals[:8]))
    league_link = _wikilink(f"Leagues/{league}")

    rdiff_sign = "+" if rdiff > 0 else ""

    lines = [
        fm,
        "",
        f"# {team}",
        "",
        f"League: {league_link} | {_wikilink('_Index')}",
        "",
        "## Corpus Statistics",
        f"*(2010–2021 archive, {games:,} games)*",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Record (W–L) | {wins}–{losses} |",
        f"| Overall win % | {_fmt_pct(win_pct)} |",
        f"| Home win % | {_fmt_pct(hwp)} |",
        f"| Away win % | {_fmt_pct(awp)} |",
        f"| Runs per game | {_fmt_f(rpg)} |",
        f"| Runs allowed per game | {_fmt_f(rapg)} |",
        f"| Run differential | {rdiff_sign}{_fmt_f(rdiff)} |",
        f"| End-of-corpus Elo | {elo:.1f} |",
        "",
    ] + trend_lines + [
        "",
        "## League Rivals",
        "",
        rival_links if rival_links else "*(none)*",
        "",
        f"#sport/mlb #league/{league.lower()} #team/{team.lower()}",
    ]
    return "\n".join(lines) + "\n"


def render_index(
    *,
    n_games: int,
    seasons: List[int],
    date_min: str,
    date_max: str,
    all_teams: List[str],
    team_stats: Any,  # pandas DataFrame indexed by team
    top_teams: List[str],
    league_stats: Dict[str, Dict[str, Any]],
) -> str:
    """Render the hub _Index note."""
    season_span = f"{min(seasons)}–{max(seasons)}" if seasons else "n/a"
    n_teams = len(all_teams)
    n_al = int((team_stats["league"] == "AL").sum())
    n_nl = int((team_stats["league"] == "NL").sum())

    fm = _frontmatter_dict({
        "sport": "mlb",
        "corpus_span": season_span,
        "n_games": n_games,
        "n_teams": n_teams,
        "tags": ["sport/mlb", "index"],
    })

    # Top teams table
    top_rows: List[str] = []
    for tm in top_teams:
        if tm not in team_stats.index:
            continue
        row = team_stats.loc[tm]
        wp = float(row["win_pct"]) if not _is_nan(row["win_pct"]) else float("nan")
        lg = str(row["league"])
        top_rows.append(
            f"| {_wikilink(f'Teams/{tm}')} | {lg} | {_fmt_pct(wp)} |"
        )

    # League summary
    lg_rows: List[str] = []
    for league in ("AL", "NL"):
        if league not in league_stats:
            continue
        s = league_stats[league]
        lg_rows.append(
            f"| {_wikilink(f'Leagues/{league}')} "
            f"| {s['n_games']:,} "
            f"| {_fmt_pct(s['home_win_rate'])} "
            f"| {_fmt_f(s['avg_runs_per_game'])} |"
        )

    all_team_links = " · ".join(_wikilink(f"Teams/{t}") for t in all_teams)

    lines = [
        fm,
        "",
        "# MLB Intelligence Atlas — Index",
        "",
        "up:: [[_Hub]]",
        "",
        "## Corpus Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total games | {n_games:,} |",
        f"| Seasons | {season_span} |",
        f"| Date range | {date_min} → {date_max} |",
        f"| Unique teams (codes) | {n_teams} |",
        f"| AL teams | {n_al} |",
        f"| NL teams | {n_nl} |",
        "",
        "## Leagues",
        "",
        "| League | Games | Home Win % | Avg Runs/Game |",
        "|--------|-------|------------|---------------|",
    ] + lg_rows + [
        "",
        "## Top 10 Teams by Win %",
        "*(full corpus 2010–2021; min-game franchises included)*",
        "",
        "| Team | League | Win % |",
        "|------|--------|-------|",
    ] + top_rows + [
        "",
        "## All Teams",
        "",
        all_team_links,
        "",
        "#sport/mlb #index",
    ]
    return "\n".join(lines) + "\n"


def _is_nan(v: Any) -> bool:
    """Return True if v is None or float NaN."""
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False
