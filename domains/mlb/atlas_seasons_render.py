"""domains.mlb.atlas_seasons_render — Obsidian Markdown renderers for per-season standings.

Pure rendering functions: each takes structured data and returns a Markdown string.
No I/O, no pandas — atlas_seasons.py handles orchestration.

Import contract (F5-clean): stdlib + scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict


# ---------------------------------------------------------------------------
# Formatting helpers (mirrors atlas_render.py conventions)
# ---------------------------------------------------------------------------


def _fmt_pct(v: float, decimals: int = 3) -> str:
    """Format a fraction [0,1] as a percentage string (e.g. 0.5617 → '56.2%')."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v * 100:.{decimals}f}%"


def _fmt_f(v: float, decimals: int = 2) -> str:
    """Format a float, handling NaN gracefully."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:.{decimals}f}"


def _sign(v: float) -> str:
    """Return '+' if v > 0, else ''."""
    return "+" if (v is not None and not math.isnan(v) and v > 0) else ""


def _wikilink(name: str) -> str:
    return f"[[{name}]]"


# ---------------------------------------------------------------------------
# Season note renderer
# ---------------------------------------------------------------------------

# Each standing row: (rank, team, W, L, win_pct, RS, RA, run_diff)
StandingRow = Tuple[int, str, int, int, float, float, float, float]


def render_season(
    *,
    season: int,
    total_games: int,
    nl_rows: List[StandingRow],
    al_rows: List[StandingRow],
    nl_best: str,
    al_best: str,
) -> str:
    """Render one season note with NL + AL standings tables.

    Parameters
    ----------
    season:
        Calendar year (e.g. 2015).
    total_games:
        Total games in corpus for this season.
    nl_rows / al_rows:
        Sorted standings rows — each is
        (rank, team_code, W, L, win_pct, RS_per_game, RA_per_game, run_diff).
    nl_best / al_best:
        Team code with the best regular-season record per league.
    """
    fm = _fm_dict({
        "season": season,
        "sport": "mlb",
        "corpus_games": total_games,
        "tags": ["sport/mlb", "season", f"season/{season}"],
    })

    def _standings_table(rows: List[StandingRow]) -> List[str]:
        lines = [
            "| Rank | Team | W | L | Win% | RS/G | RA/G | RunDiff |",
            "|------|------|---|---|------|------|------|---------|",
        ]
        for rank, team, w, l, wp, rs, ra, rd in rows:
            team_link = _wikilink(f"Teams/{team}")
            sign = _sign(rd)
            lines.append(
                f"| {rank} | {team_link} | {w} | {l} "
                f"| {_fmt_pct(wp)} | {_fmt_f(rs)} | {_fmt_f(ra)} "
                f"| {sign}{_fmt_f(rd)} |"
            )
        return lines

    nl_table = _standings_table(nl_rows)
    al_table = _standings_table(al_rows)

    lines = [
        fm,
        "",
        f"# MLB {season} — Season Standings",
        "",
        f"up:: {_wikilink('_Index')} | {_wikilink('Seasons/_Seasons_Index')}",
        "",
        "> **Corpus note:** These standings are derived from the regular-season game "
        "archive (sportsbookreviewsonline.com, personal research use). "
        "No playoff data is included. Records reflect only games present in the corpus "
        "— totals may differ slightly from official league records due to coverage.",
        "",
        f"**Total corpus games this season:** {total_games:,}",
        "",
        "## National League",
        "",
        f"Best regular-season record in corpus: {_wikilink(f'Teams/{nl_best}')}",
        "",
    ] + nl_table + [
        "",
        "## American League",
        "",
        f"Best regular-season record in corpus: {_wikilink(f'Teams/{al_best}')}",
        "",
    ] + al_table + [
        "",
        "#sport/mlb #season",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Seasons index renderer
# ---------------------------------------------------------------------------


def render_seasons_index(
    *,
    seasons: List[int],
    season_summaries: List[Dict[str, Any]],
) -> str:
    """Render the _Seasons_Index.md hub note.

    Parameters
    ----------
    seasons:
        Sorted list of season years present in the corpus.
    season_summaries:
        One dict per season with keys:
          season (int), total_games (int),
          nl_best (str), nl_best_wp (float),
          al_best (str), al_best_wp (float).
    """
    span = f"{min(seasons)}–{max(seasons)}" if seasons else "n/a"
    fm = _fm_dict({
        "sport": "mlb",
        "corpus_span": span,
        "n_seasons": len(seasons),
        "tags": ["sport/mlb", "season", "index"],
    })

    table_rows: List[str] = []
    for s in season_summaries:
        yr = s["season"]
        nl = s["nl_best"]
        nwp = s["nl_best_wp"]
        al = s["al_best"]
        awp = s["al_best_wp"]
        yr_link = _wikilink(f"Seasons/{yr}")
        nl_link = _wikilink(f"Teams/{nl}") if nl else "n/a"
        al_link = _wikilink(f"Teams/{al}") if al else "n/a"
        table_rows.append(
            f"| {yr_link} | {s['total_games']:,} "
            f"| {nl_link} ({_fmt_pct(nwp)}) "
            f"| {al_link} ({_fmt_pct(awp)}) |"
        )

    lines = [
        fm,
        "",
        "# MLB Seasons Index",
        "",
        f"up:: {_wikilink('_Index')}",
        "",
        "> **Corpus note:** Standings are from the regular-season archive "
        "(2010–2021, sportsbookreviewsonline.com, personal research use). "
        "No playoff data. 'Best record' = highest win% in the corpus for that "
        "season — not necessarily the official league or division leader.",
        "",
        f"**Seasons in corpus:** {span} ({len(seasons)} seasons)",
        "",
        "## Per-Season Summary",
        "",
        "| Season | Games | NL Best Record | AL Best Record |",
        "|--------|-------|----------------|----------------|",
    ] + table_rows + [
        "",
        "## All Seasons",
        "",
        " · ".join(_wikilink(f"Seasons/{yr}") for yr in seasons),
        "",
        "#sport/mlb #season #index",
    ]
    return "\n".join(lines) + "\n"
