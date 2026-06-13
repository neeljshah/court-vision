"""domains.mlb.atlas_style_matchups_render — Markdown rendering helpers for
MLB style-vs-style matchup matrix notes.

Pure rendering functions: each accepts structured data and returns a string.
No I/O, no pandas — the orchestrator (atlas_style_matchups.py) handles that.

Import contract (F5-clean): stdlib + scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _pct(v: float, d: int = 1) -> str:
    if math.isnan(v):
        return "n/a"
    return f"{v * 100:.{d}f}%"


def _ff(v: float, d: int = 2) -> str:
    if math.isnan(v):
        return "n/a"
    return f"{v:.{d}f}"


def _wl(name: str) -> str:
    return f"[[{name}]]"


# ---------------------------------------------------------------------------
# Per-pair note renderer
# ---------------------------------------------------------------------------


def render_pair_note(
    *,
    home_slug: str,
    away_slug: str,
    home_name: str,
    away_name: str,
    n: int,
    home_win_rate: float,
    avg_total: float,
    high_rate: float,
    high_total_thresh: float,
    corpus_span: str,
) -> str:
    """Render a single style-vs-style pair note.

    Parameters
    ----------
    home_slug / away_slug:
        Archetype slugs, e.g. ``power_run_scoring``.
    home_name / away_name:
        Human-readable archetype labels.
    n:
        Number of corpus games in this pair.
    home_win_rate:
        Fraction [0,1] of games won by the home team.
    avg_total:
        Average total runs per game in this matchup.
    high_rate:
        Fraction [0,1] of games with total runs >= high_total_thresh.
    high_total_thresh:
        The run-total threshold used for the high-scoring rate.
    corpus_span:
        Human label, e.g. ``2010-2021``.
    """
    title = f"{home_name} (home) vs {away_name} (away)"
    fm = _fm_dict({
        "sport": "mlb",
        "matchup_type": "style_vs_style",
        "home_style": home_slug,
        "away_style": away_slug,
        "corpus_span": corpus_span,
        "game_count": n,
        "tags": [
            "sport/mlb",
            "style-matchup",
            f"home/{home_slug}",
            f"away/{away_slug}",
        ],
    })

    thresh_label = f"{int(high_total_thresh)}" if high_total_thresh == int(high_total_thresh) else f"{high_total_thresh}"

    lines = [
        fm,
        "",
        f"# Style Matchup: {title}",
        "",
        (
            f"up:: {_wl('Style_Matchups/_Style_Matchups_Index')} | "
            f"{_wl('_Index')}"
        ),
        "",
        "## Tactical Context",
        "",
        (
            f"This note covers games where the **home team** plays a "
            f"{_wl(f'Playstyles/{home_slug}')} style and the **away team** "
            f"plays a {_wl(f'Playstyles/{away_slug}')} style, "
            f"measured across the {corpus_span} corpus."
        ),
        "",
        "## Outcome Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Games in corpus | {n} |",
        f"| Home-win rate | {_pct(home_win_rate)} |",
        f"| Avg total runs / game | {_ff(avg_total)} |",
        f"| High-scoring rate (>={thresh_label} total runs) | {_pct(high_rate)} |",
        "",
        "## Style Links",
        "",
        f"- Home style: {_wl(f'Playstyles/{home_slug}')} (*{home_name}*)",
        f"- Away style: {_wl(f'Playstyles/{away_slug}')} (*{away_name}*)",
        "",
        f"#sport/mlb #style-matchup #home/{home_slug} #away/{away_slug}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Index note renderer
# ---------------------------------------------------------------------------


def render_style_matchups_index(
    *,
    pair_rows: List[Dict[str, Any]],
    corpus_span: str,
    n_pairs: int,
    min_games: int,
) -> str:
    """Render the hub _Style_Matchups_Index note.

    Parameters
    ----------
    pair_rows:
        List of dicts with keys: home_slug, away_slug, n, home_win_rate,
        avg_total, high_rate (sorted descending by n before passing in).
    corpus_span:
        Human label, e.g. ``2010-2021``.
    n_pairs:
        Total number of qualifying pairs.
    min_games:
        Minimum game threshold used to qualify a pair.
    """
    fm = _fm_dict({
        "sport": "mlb",
        "matchup_type": "style_vs_style",
        "corpus_span": corpus_span,
        "pair_count": n_pairs,
        "tags": ["sport/mlb", "style-matchup", "index"],
    })

    table_rows = [
        "| Home Style | Away Style | Games | Home-Win% | Avg Total | High-Score% |",
        "|------------|------------|-------|-----------|-----------|-------------|",
    ]
    for pr in pair_rows:
        hs = pr["home_slug"]
        as_ = pr["away_slug"]
        table_rows.append(
            f"| {_wl(f'Playstyles/{hs}')} "
            f"| {_wl(f'Playstyles/{as_}')} "
            f"| {pr['n']} "
            f"| {_pct(pr['home_win_rate'])} "
            f"| {_ff(pr['avg_total'])} "
            f"| {_pct(pr['high_rate'])} |"
        )

    lines = [
        fm,
        "",
        "# MLB Style-vs-Style Matchup Matrix",
        "",
        f"up:: {_wl('_Index')}",
        "",
        (
            "Tactical identity matchup rates derived from the real corpus "
            f"({corpus_span}). Each row covers games where the home team "
            "carries one franchise-level playstyle identity and the away team "
            f"carries another. Only pairs with >= {min_games} corpus games are "
            "listed."
        ),
        "",
        "## Matchup Matrix",
        "",
    ] + table_rows + [
        "",
        f"*{n_pairs} qualifying pairs from the {corpus_span} corpus.*",
        "",
        "#sport/mlb #style-matchup #index",
    ]
    return "\n".join(lines) + "\n"
