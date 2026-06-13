"""domains.mlb.atlas_playstyles_render — Markdown rendering helpers for MLB
playstyle-archetype atlas notes.

Pure rendering functions: each accepts structured data and returns a string.
No I/O, no pandas — the orchestrator (atlas_playstyles.py) handles all that.

Import contract (F5-clean): stdlib + scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _pct(v: float, d: int = 1) -> str:
    """Format fraction [0,1] as percentage string."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v * 100:.{d}f}%"


def _ff(v: float, d: int = 2) -> str:
    """Format float; handle NaN gracefully."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _wl(name: str) -> str:
    """Return an Obsidian [[wikilink]]."""
    return f"[[{name}]]"


# ---------------------------------------------------------------------------
# Per-archetype note
# ---------------------------------------------------------------------------

def render_archetype(
    *,
    archetype_slug: str,
    archetype_name: str,
    description: str,
    signature: Dict[str, str],
    teams: List[str],
    team_rows: List[Dict[str, Any]],
    corpus_span: str,
) -> str:
    """Render a single playstyle-archetype note.

    Parameters
    ----------
    archetype_slug:
        Filesystem-safe slug, e.g. ``power_run_scoring``.
    archetype_name:
        Human-readable label, e.g. ``Power / Run-Scoring``.
    description:
        One-paragraph style description (no betting language).
    signature:
        Ordered dict of threshold labels to values, e.g.
        ``{"Runs Scored / G": "> 4.60", ...}``.
    teams:
        Sorted list of team codes that fall into this archetype.
    team_rows:
        List of dicts with keys: team, rs, ra, rd, wp, one_run_rate.
    corpus_span:
        Human label, e.g. ``2010–2021``.
    """
    fm = _fm_dict({
        "archetype": archetype_slug,
        "sport": "mlb",
        "corpus_span": corpus_span,
        "team_count": len(teams),
        "tags": ["sport/mlb", "playstyle", f"archetype/{archetype_slug}"],
    })

    sig_rows = [f"| {k} | {v} |" for k, v in signature.items()]

    # team stat table
    t_header = [
        "| Team | RS/G | RA/G | R-Diff | Win% | 1-Run% |",
        "|------|------|------|--------|------|--------|",
    ]
    t_data: List[str] = []
    for row in sorted(team_rows, key=lambda r: r.get("rd", 0.0), reverse=True):
        tm = row["team"]
        rd_sign = "+" if row.get("rd", 0) > 0 else ""
        t_data.append(
            f"| {_wl(f'Teams/{tm}')} "
            f"| {_ff(row.get('rs', float('nan')))} "
            f"| {_ff(row.get('ra', float('nan')))} "
            f"| {rd_sign}{_ff(row.get('rd', float('nan')))} "
            f"| {_pct(row.get('wp', float('nan')))} "
            f"| {_pct(row.get('one_run_rate', float('nan')))} |"
        )

    team_links = " · ".join(_wl(f"Teams/{t}") for t in sorted(teams))

    lines = [
        fm,
        "",
        f"# Playstyle: {archetype_name}",
        "",
        f"up:: {_wl('Playstyles/_Playstyles_Index')} | {_wl('_Index')}",
        "",
        "## Style Description",
        "",
        description,
        "",
        "## Signature Thresholds",
        f"*(measured over the {corpus_span} corpus)*",
        "",
        "| Metric | Threshold |",
        "|--------|-----------|",
    ] + sig_rows + [
        "",
        f"## Teams in This Archetype  ({len(teams)} total)",
        "",
    ] + t_header + t_data + [
        "",
        "## Team Links",
        "",
        team_links if team_links else "*(none)*",
        "",
        f"#sport/mlb #playstyle #archetype/{archetype_slug}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# _Playstyles_Index note
# ---------------------------------------------------------------------------

def render_playstyles_index(
    *,
    archetypes: List[Dict[str, Any]],
    corpus_span: str,
    n_teams_classified: int,
) -> str:
    """Render the hub _Playstyles_Index note.

    Parameters
    ----------
    archetypes:
        List of dicts with keys: slug, name, team_count, description_short.
    corpus_span:
        Human label, e.g. ``2010–2021``.
    n_teams_classified:
        Total distinct teams assigned to at least one archetype.
    """
    fm = _fm_dict({
        "sport": "mlb",
        "corpus_span": corpus_span,
        "n_archetypes": len(archetypes),
        "tags": ["sport/mlb", "playstyle", "index"],
    })

    arch_rows: List[str] = []
    for a in archetypes:
        arch_rows.append(
            f"| {_wl('Playstyles/' + a['slug'])} | {a['team_count']} | {a['description_short']} |"
        )

    lines = [
        fm,
        "",
        "# MLB Playstyle Archetypes — Index",
        "",
        f"up:: {_wl('_Index')}",
        "",
        "Run-scoring vs. run-prevention identities derived from real corpus "
        f"statistics ({corpus_span}). Each archetype clusters franchise-level "
        "tendencies — not individual seasons — into a style identity.",
        "",
        "## Archetypes",
        "",
        "| Archetype | Teams | Identity |",
        "|-----------|-------|----------|",
    ] + arch_rows + [
        "",
        f"*{n_teams_classified} franchises classified across "
        f"{len(archetypes)} archetypes from the {corpus_span} corpus.*",
        "",
        "#sport/mlb #playstyle #index",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Unclassified stub note
# ---------------------------------------------------------------------------


def render_unclassified_stub(*, corpus_span: str) -> str:
    """Render a stub note for franchises not assigned to any named archetype.

    This provides a valid link target for [[Playstyles/unclassified]] wikilinks
    emitted by style-matchup notes when corpus teams have no primary archetype.
    """
    fm = _fm_dict({
        "archetype": "unclassified",
        "sport": "mlb",
        "corpus_span": corpus_span,
        "tags": ["sport/mlb", "playstyle", "archetype/unclassified"],
    })
    lines = [
        fm,
        "",
        "# Playstyle: Unclassified",
        "",
        f"up:: {_wl('Playstyles/_Playstyles_Index')} | {_wl('_Index')}",
        "",
        "## Style Description",
        "",
        "Franchises that do not meet the threshold criteria for any of the six "
        f"named archetypes in the {corpus_span} corpus. Their run-scoring / "
        "run-prevention profile is transitional or near the boundary of multiple "
        "identities.",
        "",
        "#sport/mlb #playstyle #archetype/unclassified",
    ]
    return "\n".join(lines) + "\n"
