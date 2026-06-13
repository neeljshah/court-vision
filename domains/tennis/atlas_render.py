"""domains.tennis.atlas_render — Obsidian note rendering for the tennis atlas.

Companion to atlas.py (LOC split).  Markdown rendering only.
Player-level notes are no longer emitted; the per-player table in _Index has
been replaced by a link to [[Playstyles/_Playstyles_Index]].
F5-clean: stdlib + pandas only.  No edge/betting language.
"""
from __future__ import annotations

import pathlib

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note

PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")


def _opt_pct(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "n/a"
    return f"{float(val):.1f}%"


def _opt_elo(val: object) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "n/a"
    return f"{float(val):.1f}"


# ---------------------------------------------------------------------------
# Surface notes
# ---------------------------------------------------------------------------

def _render_surface(
    surface: str,
    stats: pd.DataFrame,
    matches: pd.DataFrame,
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit Surfaces/<surface>.md and return the path."""
    surf_col = f"{surface.lower()}_matches"
    elo_col = f"{surface.lower()}_elo"

    surf_matches = int(matches[matches["surface"] == surface].shape[0]) if "surface" in matches.columns else 0
    surf_pct = round(surf_matches / len(matches) * 100, 1) if len(matches) > 0 else 0.0

    if not stats.empty and elo_col in stats.columns and surf_col in stats.columns:
        top_surf = stats[stats[surf_col] >= 10].nlargest(20, elo_col, keep="first")
    else:
        top_surf = pd.DataFrame()

    # Aggregate surface stats (no individual names — archetype-level intelligence only)
    n_qualifiers = len(top_surf)
    if not top_surf.empty and elo_col in top_surf.columns:
        median_elo = round(float(top_surf[elo_col].dropna().median()), 1)
        median_wr_col = f"{surface.lower()}_win_pct"
        median_wr = _opt_pct(top_surf[median_wr_col].dropna().median() if median_wr_col in top_surf.columns else None)
    else:
        median_elo = None
        median_wr = "n/a"

    lines = [
"---",
f"surface: {surface}",
f"total_matches: {surf_matches}",
f"corpus_share_pct: {surf_pct}",
"tags:",
"  - sport/tennis",
f"  - surface/{surface.lower()}",
"---",
"",
f"# {surface} — Tennis Surface Profile",
"",
"[[_Index|← Back to Tennis Index]] | [[_Hub|← Hub]]",
"",
"## Corpus Overview",
f"- **Matches on {surface}:** {surf_matches:,} ({surf_pct}% of corpus)",
f"- **Players with ≥10 {surface} matches:** {n_qualifiers}",
f"- **Median {surface} Elo (top qualifiers):** {median_elo if median_elo is not None else 'n/a'}",
f"- **Median {surface} win-rate:** {median_wr}",
"",
"## Player Intelligence",
(
    f"Individual player notes are not emitted.  "
    f"See [[Playstyles/_Playstyles_Index]] for archetype-level {surface} intelligence."
),
"",
f"#sport/tennis #surface/{surface.lower()}",
    ]

    path = out_dir / "Surfaces" / f"{surface}.md"
    return write_note(path, "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Index note
# ---------------------------------------------------------------------------

def _render_index(
    stats: pd.DataFrame,
    matches: pd.DataFrame,
    out_dir: pathlib.Path,
    top_n: int = 20,
) -> pathlib.Path:
    """Emit _Index.md and return the path."""
    n_matches = len(matches)
    date_min = str(matches["date"].min()) if "date" in matches.columns and n_matches > 0 else "n/a"
    date_max = str(matches["date"].max()) if "date" in matches.columns and n_matches > 0 else "n/a"
    n_players = int(stats["player_id"].nunique()) if not stats.empty else 0

    surf_lines: list[str] = []
    if "surface" in matches.columns:
        for surf in PRIMARY_SURFACES:
            cnt = int((matches["surface"] == surf).sum())
            pct = round(cnt / n_matches * 100, 1) if n_matches > 0 else 0.0
            surf_lines.append(f"- [[Surfaces/{surf}|{surf}]]: {cnt:,} matches ({pct}%)")
    surf_section = "\n".join(surf_lines) if surf_lines else "- n/a"

    if not stats.empty and "elo" in stats.columns:
        top_elo = stats.nlargest(top_n, "elo", keep="first")
    else:
        top_elo = pd.DataFrame()

    # Aggregate Elo table (no player names — archetype-level aggregates only)
    n_with_elo = len(top_elo)
    elo_summary = (
        f"Top-{top_n} by Elo: {n_with_elo} players qualify; "
        f"see [[Playstyles/_Playstyles_Index]] for archetype-level breakdowns."
    )

    lines = [
"---",
"corpus: ATP 2015–2025",
f"total_matches: {n_matches}",
f'corpus_span: "{date_min} → {date_max}"',
f"featured_players: {n_players}",
"tags:",
"  - sport/tennis",
"  - atlas/index",
"---",
"",
"# Tennis Intelligence Atlas",
"",
"[[_Hub|← Hub]]",
"",
f"Generated from the ATP corpus ({date_min} → {date_max}).",
"",
"## Corpus Overview",
f"- **Total matches:** {n_matches:,}",
f"- **Players with ≥10 matches:** {n_players}",
f"- **Corpus span:** {date_min} → {date_max}",
"",
"## Surface Breakdown",
surf_section,
"",
"## Player Intelligence",
"Individual player notes are not emitted.  Intelligence is organised by playstyle archetype.",
"",
elo_summary,
"",
"→ **[[Playstyles/_Playstyles_Index|Playstyle Archetypes Index]]**",
"",
"## Surface Notes",
"[[Surfaces/Hard|Hard]] \xb7 [[Surfaces/Clay|Clay]] \xb7 [[Surfaces/Grass|Grass]]",
"",
"---",
"#sport/tennis #atlas/index",
    ]

    path = out_dir / "_Index.md"
    return write_note(path, "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render_all(
    out_dir: pathlib.Path,
    stats: pd.DataFrame,
    matches: pd.DataFrame,
    players: pd.DataFrame,
) -> list[pathlib.Path]:
    """Render all notes; return written paths.

    Player-level notes are intentionally not emitted.  The atlas now links
    to [[Playstyles/_Playstyles_Index]] for per-archetype intelligence.
    """
    written: list[pathlib.Path] = []

    for surf in PRIMARY_SURFACES:
        written.append(_render_surface(surf, stats, matches, out_dir))

    written.append(_render_index(stats, matches, out_dir))
    return written
