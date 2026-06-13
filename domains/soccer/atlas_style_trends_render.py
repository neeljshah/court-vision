"""domains.soccer.atlas_style_trends_render — Markdown renderers for the
scheme-season trends atlas.

Separated from atlas_style_trends.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas_style_trends — never imported across domains.

F5 compliance: stdlib + pandas + domains.soccer.* only.
No edge/betting language; all stats corpus-derived.
"""
from __future__ import annotations

from typing import Dict, List

from domains.soccer.atlas_playstyles import _SCHEMES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEME_ABBREVS: Dict[str, str] = {
    "High-Scoring_Attacking": "HighScr",
    "High-Variance_Entertainers": "HiVar",
    "Defensive_Low-Block": "DefBlk",
    "Draw-Prone_Grinder": "DrawPr",
    "Leaky_High-Risk": "Leaky",
    "Strong-at-Home": "StHome",
    "Balanced": "Bal",
}

_SCHEME_KEY_LINES = [
    "| HighScr | High-Scoring Attacking — GF/game ≥ 1.60, Over ≥ 58% |",
    "| HiVar | High-Variance / Entertainers — BTTS ≥ 60%, Over ≥ 58% |",
    "| DefBlk | Defensive Low-Block — GA/game ≤ 1.15, CS% ≥ 31%, Over ≤ 49% |",
    "| DrawPr | Draw-Prone Grinder — Draw rate ≥ 30% |",
    "| Leaky | Leaky / High-Risk — GA/game ≥ 1.80, CS% ≤ 18% |",
    "| StHome | Strong at Home — home GF/game − away GF/game ≥ 0.50 |",
    "| Bal | Balanced — near-median across all dimensions |",
]


def _pct_str(v: float) -> str:
    return f"{v * 100:.1f}%"


def _ascii_trend_table(records: List[Dict]) -> str:
    """Build a fixed-width ASCII table of scheme shares + scoring per season."""
    headers = ["Season", "Matches", "Goals/G", "O2.5%", "HWin%",
               "HighScr", "HiVar", "DefBlk", "DrawPr", "Leaky", "StHome", "Bal"]
    col_w = [7, 8, 7, 6, 6, 7, 6, 7, 7, 6, 7, 5]

    def _row_str(cells: List[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, col_w)) + " |"

    sep = "|-" + "-|-".join("-" * w for w in col_w) + "-|"
    lines = [_row_str(headers), sep]
    for r in records:
        cells = [
            str(r["season"]),
            str(r["n_matches"]),
            f"{r['goals_pg']:.2f}",
            _pct_str(r["over25_rate"]),
            _pct_str(r["home_win_rate"]),
            _pct_str(r["High-Scoring_Attacking"]),
            _pct_str(r["High-Variance_Entertainers"]),
            _pct_str(r["Defensive_Low-Block"]),
            _pct_str(r["Draw-Prone_Grinder"]),
            _pct_str(r["Leaky_High-Risk"]),
            _pct_str(r["Strong-at-Home"]),
            _pct_str(r["Balanced"]),
        ]
        lines.append(_row_str(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_overview(records: List[Dict], generated: str, n_corpus: int) -> str:
    """Render _Style_Trends_Overview.md."""
    seasons = [r["season"] for r in records]
    s_start, s_end = min(seasons), max(seasons)
    first, last = records[0], records[-1]
    delta_over = last["over25_rate"] - first["over25_rate"]
    delta_goals = last["goals_pg"] - first["goals_pg"]
    sign_o = "+" if delta_over >= 0 else ""
    sign_g = "+" if delta_goals >= 0 else ""

    lines: List[str] = [
        "---",
        "type: style-trends-overview",
        "sport: soccer",
        f"corpus_matches: {n_corpus}",
        f"seasons: {s_start}–{s_end}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - atlas/style-trends",
        "---",
        "",
        "# Soccer Scheme-Season Trends",
        "",
        "Up: [[_Index|Soccer Index]] · [[_Playstyles_Index|Playstyles Index]]",
        "",
        (
            f"Tactical-scheme prevalence and scoring patterns across {len(seasons)} seasons "
            f"({s_start}–{s_end}) from {n_corpus:,} matches "
            "(Premier League, Championship, Bundesliga, La Liga, Serie A, Ligue 1). "
            "Schemes assigned per season using the same priority-waterfall as "
            "[[_Playstyles_Index|Playstyles Index]]."
        ),
        "",
        "## Key Findings",
        "",
        f"- **Over-2.5 rate {s_start}→{s_end}:** "
        f"{_pct_str(first['over25_rate'])} → {_pct_str(last['over25_rate'])} "
        f"(Δ {sign_o}{_pct_str(delta_over)})",
        f"- **Goals/game {s_start}→{s_end}:** "
        f"{first['goals_pg']:.2f} → {last['goals_pg']:.2f} "
        f"(Δ {sign_g}{delta_goals:.2f})",
        f"- **Home-win rate range:** "
        f"{_pct_str(min(r['home_win_rate'] for r in records))}–"
        f"{_pct_str(max(r['home_win_rate'] for r in records))}",
        "",
        "## Season Trends Table",
        "",
        "Scheme share = fraction of season-qualifying teams (≥10 matches) "
        "classified into that archetype.",
        "",
        _ascii_trend_table(records),
        "",
        "## Scheme Key",
        "",
        "| Abbrev | Scheme |",
        "|--------|--------|",
        *_SCHEME_KEY_LINES,
        "",
        "## See Also",
        "",
        "- [[_Playstyles_Index|Playstyles Index]] — overall (cross-season) assignments",
        "- [[_Seasons_Index|Seasons Index]] — per-league per-season final standings",
        "",
        "#sport/soccer #atlas/style-trends",
    ]
    return "\n".join(lines) + "\n"


def render_season_snapshot(r: Dict, generated: str) -> str:
    """Render <Season>_scheme_snapshot.md — one note per season."""
    season = r["season"]
    scheme_rows = [
        f"| [[{spec.key}|{spec.label}]] | {_pct_str(r[spec.key])} |"
        for spec in _SCHEMES
    ]
    lines: List[str] = [
        "---",
        "type: style-trends-season",
        f"season: {season}",
        "sport: soccer",
        f"n_matches: {r['n_matches']}",
        f"goals_pg: {r['goals_pg']}",
        f"over25_rate: {r['over25_rate']}",
        f"home_win_rate: {r['home_win_rate']}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - atlas/style-trends",
        f"  - season/{season}",
        "---",
        "",
        f"# Soccer Season Scheme Snapshot — {season}",
        "",
        "Up: [[_Style_Trends_Overview|Style Trends Overview]] · [[_Index|Soccer Index]]",
        "",
        f"**Matches:** {r['n_matches']}  |  "
        f"**Goals/game:** {r['goals_pg']:.2f}  |  "
        f"**Over-2.5:** {_pct_str(r['over25_rate'])}  |  "
        f"**Home-win:** {_pct_str(r['home_win_rate'])}",
        "",
        "## Scheme Distribution",
        "",
        f"{r['n_teams_classified']} teams met the ≥10-match season threshold.",
        "",
        "| Scheme | Share |",
        "|--------|-------|",
        *scheme_rows,
        "",
        "## See Also",
        "",
        "- [[_Style_Trends_Overview|Style Trends Overview]]",
        "- [[_Playstyles_Index|Playstyles Index]]",
        "",
        f"#sport/soccer #atlas/style-trends #season/{season}",
    ]
    return "\n".join(lines) + "\n"
