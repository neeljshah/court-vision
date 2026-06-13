"""domains.tennis.atlas_h2h_render — Markdown rendering for aggregate H2H dynamics.

Consumed exclusively by atlas_h2h.build_h2h().  Each public function renders one
name-free aggregate note describing patterns across the whole corpus.

Emitted notes (all in out_dir):
    _Matchups_Index.md      — corpus scope + meeting-count distribution
    _Surface_Dynamics.md    — higher-ranked-player win rate by surface
    _Upset_Patterns.md      — upset rate vs rank gap bin
    _Format_Patterns.md     — best-of-3 vs best-of-5 patterns
    _Rematch_Effects.md     — rematch win-rate shift

F5-clean: stdlib + pathlib only.  No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.  No person names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List

# _frontmatter and _write live in atlas_h2h_render2 (avoids circular import:
# this module imports render_rematch_effects from render2 at the bottom, so
# render2 must not import from here).
from domains.tennis.atlas_h2h_render2 import _frontmatter, _write  # noqa: F401

# Duplicated from atlas_h2h so this module is self-contained (no circular import).
PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render_index(
    corpus_meta: Dict[str, int],
    meeting_dist: Dict[str, int],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit _Matchups_Index.md — corpus overview and meeting-count distribution."""
    out_dir.mkdir(parents=True, exist_ok=True)

    total_matches = corpus_meta["total_matches"]
    total_pairs = corpus_meta["total_pairs"]
    qualified_pairs = corpus_meta["qualified_pairs"]
    min_meetings = corpus_meta["min_meetings"]

    dist_rows = [f"| {bucket} | {count} |" for bucket, count in meeting_dist.items()]
    dist_table = "\n".join(dist_rows) if dist_rows else "| — | — |"

    lines = _frontmatter(["sport/tennis", "matchup", "aggregate"]) + [
        "",
        "# Tennis H2H Dynamics — Matchup Index",
        "",
        "[[_Index|← Tennis Index]]",
        "",
        "Aggregate head-to-head dynamics across the full ATP corpus.  "
        "No individual rivalries are listed here — all figures are corpus-wide patterns.",
        "",
        "## Corpus Scope",
        "",
        f"- **Total matches in corpus:** {total_matches:,}",
        f"- **Unique player pairs with at least one meeting:** {total_pairs:,}",
        f"- **Pairs with {min_meetings}+ meetings (qualified rivalries):** {qualified_pairs:,}",
        "",
        "## Meeting-Count Distribution",
        "",
        "How many times have pairs typically met?",
        "",
        "| Meetings | Pairs |",
        "|---|---|",
        dist_table,
        "",
        "## Aggregate Notes",
        "",
        "| Note | Description |",
        "|---|---|",
        "| [[_Surface_Dynamics|Surface Dynamics]] | Higher-ranked-player win rate by surface |",
        "| [[_Upset_Patterns|Upset Patterns]] | Upset rate vs rank gap |",
        "| [[_Format_Patterns|Format Patterns]] | Best-of-3 vs best-of-5 H2H patterns |",
        "| [[_Rematch_Effects|Rematch Effects]] | Win-rate shift in rematches |",
        "",
        "---",
        "#sport/tennis #matchup #aggregate",
    ]

    return _write(out_dir / "_Matchups_Index.md", lines)


def render_surface_dynamics(
    surface_dyn: Dict[str, Dict[str, float]],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit _Surface_Dynamics.md — higher-ranked-player win rate by surface."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if surface_dyn:
        rows = []
        for surf in PRIMARY_SURFACES:
            if surf not in surface_dyn:
                continue
            d = surface_dyn[surf]
            pct = f"{d['win_rate'] * 100:.1f}%"
            rows.append(f"| [[../Surfaces/{surf}|{surf}]] | {int(d['matches']):,} | {int(d['n_pairs']):,} | {pct} |")
        table_str = "\n".join(rows) if rows else "| — | — | — | — |"
    else:
        table_str = "| — | — | — | — |"

    lines = _frontmatter(["sport/tennis", "matchup", "aggregate", "surface"]) + [
        "",
        "# H2H Surface Dynamics",
        "",
        "[[_Matchups_Index|← Matchups Index]] · [[_Index|← Tennis Index]]",
        "",
        "How often does the higher-ranked player (lower rank number) win head-to-head "
        "encounters on each surface?  Rows exclude matches where both players share the "
        "same ranking or rankings are missing.",
        "",
        "## Higher-Ranked Player Win Rate by Surface",
        "",
        "| Surface | Matches | Pairs | Higher-Rank Win Rate |",
        "|---|---|---|---|",
        table_str,
        "",
        "### Interpretation",
        "",
        "- Win rates above 50% indicate that rankings are predictive on that surface.",
        "- Surfaces closer to 50% exhibit greater parity or ranking-surface mismatch.",
        "- Sample sizes vary across surfaces; grass has the smallest window in the ATP calendar.",
        "",
        "---",
        "#sport/tennis #matchup #aggregate #surface",
    ]

    return _write(out_dir / "_Surface_Dynamics.md", lines)


def render_upset_patterns(
    upset_pats: List[Dict],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit _Upset_Patterns.md — upset rate vs rank-gap bin."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if upset_pats:
        rows = [
            f"| {p['gap_label']} | {p['matches']:,} | {p['upset_rate'] * 100:.1f}% |"
            for p in upset_pats
        ]
        table_str = "\n".join(rows)
    else:
        table_str = "| — | — | — |"

    lines = _frontmatter(["sport/tennis", "matchup", "aggregate", "upset"]) + [
        "",
        "# H2H Upset Patterns",
        "",
        "[[_Matchups_Index|← Matchups Index]] · [[_Index|← Tennis Index]]",
        "",
        "Upset rate (lower-ranked player wins) as a function of rank gap between the two players.  "
        "A rank gap of 1–10 means the players are close in ranking; >100 means a large disparity.",
        "",
        "## Upset Rate vs Rank Gap",
        "",
        "| Rank Gap | Matches | Upset Rate |",
        "|---|---|---|",
        table_str,
        "",
        "### Interpretation",
        "",
        "- Smaller rank gaps naturally produce higher upset rates — players are more evenly matched.",
        "- As the rank gap widens the higher-ranked player wins more reliably.",
        "- Even at large rank gaps there is a non-trivial upset rate, reflecting surface specialisation "
        "and form variance.",
        "",
        "---",
        "#sport/tennis #matchup #aggregate #upset",
    ]

    return _write(out_dir / "_Upset_Patterns.md", lines)


def render_format_patterns(
    fmt_pats: Dict[str, Dict],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit _Format_Patterns.md — best-of-3 vs best-of-5 H2H patterns."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt_pats:
        rows = []
        for label, d in fmt_pats.items():
            pct = f"{d['win_rate'] * 100:.1f}%"
            rows.append(f"| {label} | {d['matches']:,} | {d['n_pairs']:,} | {pct} |")
        table_str = "\n".join(rows)
    else:
        table_str = "| — | — | — | — |"

    lines = _frontmatter(["sport/tennis", "matchup", "aggregate", "format"]) + [
        "",
        "# H2H Format Patterns (Best-of-3 vs Best-of-5)",
        "",
        "[[_Matchups_Index|← Matchups Index]] · [[_Index|← Tennis Index]]",
        "",
        "Does the match format (best-of-3 vs best-of-5 sets) change how often "
        "the higher-ranked player wins head-to-head encounters?",
        "",
        "## Higher-Ranked Player Win Rate by Format",
        "",
        "| Format | Matches | Pairs | Higher-Rank Win Rate |",
        "|---|---|---|---|",
        table_str,
        "",
        "### Interpretation",
        "",
        "- Best-of-5 formats (Grand Slams) often show different dynamics than best-of-3 "
        "(Masters, ATP 250/500) because longer formats reduce variance.",
        "- A higher win rate in best-of-5 would suggest rankings capture endurance advantages.",
        "- A lower win rate would suggest surface specialists or draw luck dominate.",
        "",
        "---",
        "#sport/tennis #matchup #aggregate #format",
    ]

    return _write(out_dir / "_Format_Patterns.md", lines)


# render_rematch_effects lives in atlas_h2h_render2 to keep this file ≤300 LOC.
# Re-exported here so callers (atlas_h2h.py) need not change their import path.
from domains.tennis.atlas_h2h_render2 import render_rematch_effects as render_rematch_effects  # noqa: F401,E501
