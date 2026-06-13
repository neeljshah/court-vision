"""domains.tennis.atlas_render — Obsidian note rendering for the tennis atlas.

Companion to atlas.py (LOC split).  Markdown rendering only.
Player-level notes are no longer emitted; the per-player table in _Index has
been replaced by a link to [[Playstyles/_Playstyles_Index]].
F5-clean: stdlib + pandas only.  No edge/betting language.
"""
from __future__ import annotations

import pathlib
import re

import pandas as pd

PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")


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

    surf_dir = out_dir / "Surfaces"
    surf_dir.mkdir(parents=True, exist_ok=True)
    path = surf_dir / f"{surface}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Player notes
# ---------------------------------------------------------------------------

def _render_player(row: pd.Series, out_dir: pathlib.Path) -> pathlib.Path:
    """Emit Players/<Name>.md and return the path."""
    name = str(row["name"])
    player_id = int(row["player_id"])
    total = int(row.get("total_matches", 0))
    wins = int(row.get("wins", 0))
    losses = int(row.get("losses", 0))
    win_pct = _opt_pct(row.get("win_pct"))
    elo = _opt_elo(row.get("elo"))
    peak_rank_raw = row.get("peak_rank")
    peak_rank = str(int(peak_rank_raw)) if pd.notna(peak_rank_raw) and peak_rank_raw is not None else "n/a"
    recent_form = str(row.get("recent_form", ""))

    surf_lines: list[str] = []
    for surf in PRIMARY_SURFACES:
        sm = int(row.get(f"{surf.lower()}_matches", 0) or 0)
        sw = _opt_pct(row.get(f"{surf.lower()}_win_pct"))
        se = _opt_elo(row.get(f"{surf.lower()}_elo"))
        if sm > 0:
            surf_lines.append(f"- [[Surfaces/{surf}|{surf}]]: {sm} matches, {sw} win%, Elo {se}")
    surf_section = "\n".join(surf_lines) if surf_lines else "- No surface data in corpus"

    b5t = int(row.get("bo5_matches", 0) or 0)
    bo5_line = (
        f"{_opt_pct(row.get('bo5_win_pct'))} win% over {b5t} best-of-5 matches"
        if b5t > 0
        else "No best-of-5 matches in corpus"
    )

    vs10t = int(row.get("vs_top10_total", 0) or 0)
    vs10_line = (
        f"{_opt_pct(row.get('vs_top10_win_pct'))} win% in {vs10t} matches vs ranked top-10 opponents"
        if vs10t > 0
        else "No vs-top-10 matches with rank data in corpus"
    )

    recent_display = recent_form if recent_form else "n/a"

    lines = [
"---",
f"name: {name}",
f"player_id: {player_id}",
f"current_elo: {elo}",
f"peak_rank: {peak_rank}",
"tour: atp",
"tags:",
"  - sport/tennis",
"  - player",
"---",
"",
f"# {name}",
"",
"[[_Index|← Back to Tennis Index]]",
"",
"## Career Summary (corpus 2015–2025)",
f"- **Total matches:** {total} ({wins}W / {losses}L)",
f"- **Overall win%:** {win_pct}",
f"- **Peak ranking:** {peak_rank}",
f"- **Current Elo:** {elo}",
"",
"## Surface Splits",
surf_section,
"",
"## Best-of-5 Record",
f"- {bo5_line}",
"",
"## vs Top-10 Record",
f"- {vs10_line}",
"",
"## Recent Form (last ≤20 matches, most-recent first)",
f"`{recent_display}`",
"",
"---",
"#sport/tennis #player",
    ]

    players_dir = out_dir / "Players"
    players_dir.mkdir(parents=True, exist_ok=True)
    path = players_dir / f"{name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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
