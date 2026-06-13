"""domains.mlb.atlas_style_trends_render — Markdown rendering for style-trend notes.

Pure rendering functions: accept structured data, return strings.
No I/O, no pandas — the orchestrator (atlas_style_trends.py) handles all that.

Import contract (F5-clean): stdlib + scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def _ff(v: float, d: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _pct(v: float, d: int = 1) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v * 100:.{d}f}%"


def _trend_arrow(series: List[float]) -> str:
    """Return 'up', 'down', or 'flat' based on first-to-last delta."""
    if len(series) < 2:
        return "flat"
    delta = series[-1] - series[0]
    if delta > 0.5:
        return "up"
    if delta < -0.5:
        return "down"
    return "flat"


# ---------------------------------------------------------------------------
# Overview note
# ---------------------------------------------------------------------------


def render_overview(
    *,
    corpus_span: str,
    env_rows: List[Dict[str, Any]],
    dist_rows: List[Dict[str, Any]],
    archetype_slugs: List[str],
    archetype_short: Dict[str, str],
    min_season_games: int,
) -> str:
    """Render _Style_Trends_Overview.md.

    Parameters
    ----------
    corpus_span:       e.g. "2010-2021"
    env_rows:          list of dicts with keys: season, runs_per_game,
                       high_score_rate, home_win_rate, one_run_rate, n_games
    dist_rows:         list of dicts with keys: season, n_teams, <slug>_pct ...
    archetype_slugs:   ordered list of slug strings
    archetype_short:   slug -> short display name
    min_season_games:  minimum games threshold used during classification
    """
    fm = _fm_dict({
        "sport": "mlb",
        "corpus_span": corpus_span,
        "note_type": "style_trends_overview",
        "tags": ["sport/mlb", "trends", "run-environment"],
    })

    # Environment table
    env_hdr = "| Season | RPG | High-Score% | Home-Win% | 1-Run% | Games |"
    env_sep = "|--------|-----|-------------|-----------|--------|-------|"
    e_rows: List[str] = []
    for r in env_rows:
        s = int(r["season"])
        e_rows.append(
            f"| [[Trends/style_trends_{s}]] "
            f"| {_ff(r['runs_per_game'])} "
            f"| {_pct(r['high_score_rate'])} "
            f"| {_pct(r['home_win_rate'])} "
            f"| {_pct(r['one_run_rate'])} "
            f"| {int(r['n_games'])} |"
        )

    # Style distribution table
    hdr_cols = " | ".join(archetype_short[s] for s in archetype_slugs)
    sd_hdr = f"| Season | {hdr_cols} |"
    sep_part = "|".join(["-" * 8] * len(archetype_slugs))
    sd_sep = f"|--------|{sep_part}|"
    sd_rows: List[str] = []
    for r in dist_rows:
        vals = " | ".join(_ff(r[f"{s}_pct"], 1) + "%" for s in archetype_slugs)
        sd_rows.append(f"| {int(r['season'])} | {vals} |")

    # Trend summary (narrative)
    rpg = [r["runs_per_game"] for r in env_rows]
    pw = [r["power_run_scoring_pct"] for r in dist_rows]
    pi = [r["pitching_run_prevention_pct"] for r in dist_rows]
    rpg_min_val = min(rpg)
    rpg_max_val = max(rpg)
    rpg_min_s = env_rows[rpg.index(rpg_min_val)]["season"]
    rpg_max_s = env_rows[rpg.index(rpg_max_val)]["season"]
    pi_max = max(pi)

    key_trends = [
        "## Key Trends",
        "",
        f"- **Run-scoring environment ({_trend_arrow(rpg)}):** "
        f"Runs per game ranged from {_ff(rpg_min_val)} ({rpg_min_s}) "
        f"to {_ff(rpg_max_val)} ({rpg_max_s}). "
        "A sustained scoring trough in 2013-2014 gave way to a "
        "pronounced rise peaking in 2019.",
        "",
        f"- **Power / Run-Scoring style ({_trend_arrow(pw)}):** "
        "Prevalence collapsed to near zero in 2014-2015 then rebounded sharply "
        "to lead all archetypes by 2019.",
        "",
        f"- **Pitching-Led style ({_trend_arrow(pi)}):** "
        f"Peaked during the 2013-2015 scoring suppression era "
        f"({_ff(pi_max, 1)}% of teams) then contracted as offenses surged.",
        "",
        "- **Low-Scoring Grinder:** Common in 2013-2014 "
        "but effectively disappeared by 2016 onward as run totals rose.",
        "",
        "- **Home-field advantage:** "
        "Home teams won between "
        f"{_pct(min(r['home_win_rate'] for r in env_rows))} "
        f"and {_pct(max(r['home_win_rate'] for r in env_rows))} per season — "
        "a consistent but modest structural feature across the corpus.",
    ]

    lines = [
        fm, "",
        "# MLB Style and Run-Scoring Trends — Overview",
        "",
        "up:: [[_Index]] | [[Playstyles/_Playstyles_Index]]",
        "",
        f"Season-by-season league run-scoring environment and team-style "
        f"distribution from the {corpus_span} corpus.  "
        "Metrics are descriptive counts derived from real game results.",
        "",
        "## League Run-Scoring Environment by Season",
        "",
        env_hdr, env_sep,
    ] + e_rows + [
        "",
        "*(RPG = runs per game both teams combined; "
        "High-Score% = share of games with ≥ 10 total runs; "
        "1-Run% = share decided by exactly one run)*",
        "",
        "## Team Style Distribution by Season",
        f"*(% of qualifying franchises per archetype — min {min_season_games} games/season)*",
        "",
        sd_hdr, sd_sep,
    ] + sd_rows + [
        "",
    ] + key_trends + [
        "",
        "#sport/mlb #trends #run-environment",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Per-season note
# ---------------------------------------------------------------------------


def render_season_note(
    *,
    season: int,
    corpus_span: str,
    runs_per_game: float,
    high_score_rate: float,
    home_win_rate: float,
    one_run_rate: float,
    n_games: int,
    style_pcts: Dict[str, float],
    archetype_names: Dict[str, str],
    archetype_slugs: List[str],
    min_season_games: int,
) -> str:
    """Render style_trends_<season>.md."""
    fm = _fm_dict({
        "sport": "mlb",
        "season": season,
        "corpus_span": corpus_span,
        "note_type": "style_trends_season",
        "tags": ["sport/mlb", "trends", f"season/{season}"],
    })

    style_rows = [
        f"| {archetype_names[slug]} | {_ff(style_pcts[slug], 1)}% |"
        for slug in archetype_slugs
    ]

    lines = [
        fm, "",
        f"# MLB {season} — Style and Run-Scoring Profile",
        "",
        "up:: [[Trends/_Style_Trends_Overview]] | [[_Index]]",
        "",
        "## League Run Environment",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Runs per game (both teams) | {_ff(runs_per_game)} |",
        f"| High-scoring game rate (≥ 10 runs) | {_pct(high_score_rate)} |",
        f"| Home-team win rate | {_pct(home_win_rate)} |",
        f"| One-run game rate | {_pct(one_run_rate)} |",
        f"| Games in corpus | {n_games} |",
        "",
        "## Team Style Distribution",
        f"*(% of franchises qualifying for each archetype — min {min_season_games} games)*",
        "",
        "| Style | % of Teams |",
        "|-------|------------|",
    ] + style_rows + [
        "",
        f"#sport/mlb #trends #season/{season}",
    ]
    return "\n".join(lines) + "\n"
