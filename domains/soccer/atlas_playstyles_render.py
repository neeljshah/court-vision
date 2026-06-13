"""domains.soccer.atlas_playstyles_render — Markdown renderers for the playstyle atlas.

Separated from atlas_playstyles.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas_playstyles — never imported across domains.

F5 compliance: stdlib + pandas + domains.soccer.* only.
No edge/betting language; all stats corpus-derived.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from domains.soccer.atlas_playstyles import SchemeSpec, _SCHEMES
from scripts.platformkit.atlas.obsidian_emit import slug as _slug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


# ---------------------------------------------------------------------------
# Scheme-note renderer
# ---------------------------------------------------------------------------


def render_scheme_note(
    spec: SchemeSpec,
    teams: List[str],
    team_stats: pd.DataFrame,
    generated: str,
) -> str:
    """Render one Playstyles/<Scheme>.md note."""
    n_teams = len(teams)
    if n_teams > 0:
        sub = team_stats[team_stats["team"].isin(teams)]
        m_gf = sub["gf_pg"].median()
        m_ga = sub["ga_pg"].median()
        m_ov = sub["over_pct"].median()
        m_cs = sub["cs_pct"].median()
        m_bt = sub["btts_pct"].median()
    else:
        m_gf = m_ga = m_ov = m_cs = m_bt = 0.0

    tag_str = " ".join(spec.tags)
    lines: List[str] = [
        "---",
        f'scheme: "{spec.label}"',
        f"team_count: {n_teams}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - scheme",
    ]
    for t in spec.tags:
        lines.append(f"  - {t.lstrip('#')}")
    lines += ["---", ""]

    lines += [
        f"# {spec.label}",
        "",
        "Up: [[_Playstyles_Index|Playstyles Index]] · [[_Index|Soccer Index]]",
        "",
        f"*{spec.description}*",
        "",
        "## Stat Signature",
        "",
        f"**Classification rule:** {spec.signature}",
        "",
        "| Metric | Scheme Median |",
        "|--------|--------------|",
        f"| GF / game | {m_gf:.2f} |",
        f"| GA / game | {m_ga:.2f} |",
        f"| Over-2.5 rate | {_pct(m_ov)} |",
        f"| Clean-sheet % | {_pct(m_cs)} |",
        f"| BTTS % | {_pct(m_bt)} |",
        "",
        f"## Teams ({n_teams})",
        "",
    ]

    if teams:
        for t in teams:
            lines.append(f"- [[Teams/{_slug(t)}|{t}]]")
    else:
        lines.append("*No teams met this threshold in the current corpus.*")

    lines += [
        "",
        "## See Also",
        "",
        "- [[_Playstyles_Index|Playstyles Index]]",
        "- [[_Index|Soccer Index]]",
        "",
        f"#sport/soccer #scheme {tag_str}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Index renderer
# ---------------------------------------------------------------------------


def render_playstyles_index(
    scheme_map: Dict[str, List[str]],
    n_corpus: int,
    n_teams_total: int,
    generated: str,
) -> str:
    """Render _Playstyles_Index.md."""
    lines: List[str] = [
        "---",
        "type: playstyles-index",
        "sport: soccer",
        f"corpus_matches: {n_corpus}",
        f"teams_classified: {n_teams_total}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - atlas/playstyles",
        "---",
        "",
        "# Soccer Playstyles Index",
        "",
        "Up: [[_Index|Soccer Index]]",
        "",
        (
            "Teams are classified into tactical archetypes using a priority-waterfall "
            "rule applied to corpus-wide statistics (goals for/against per game, "
            "over-2.5 rate, clean-sheet%, BTTS%, draw rate, home scoring advantage). "
            "Each team with ≥30 corpus appearances is assigned to exactly one scheme."
        ),
        "",
        "| Scheme | Teams | Classification Rule |",
        "|--------|-------|---------------------|",
    ]
    for spec in _SCHEMES:
        count = len(scheme_map.get(spec.key, []))
        note_link = f"[[{spec.key}|{spec.label}]]"
        lines.append(f"| {note_link} | {count} | {spec.signature} |")

    lines += ["", "## Schemes", ""]
    for spec in _SCHEMES:
        teams = scheme_map.get(spec.key, [])
        note_link = f"[[{spec.key}|{spec.label}]]"
        lines.append(f"### {note_link}")
        lines.append("")
        lines.append(f"*{spec.description}*")
        lines.append("")
        lines.append(f"**Rule:** {spec.signature}")
        lines.append("")
        lines.append(f"**Teams ({len(teams)}):**")
        for t in teams[:10]:
            lines.append(f"- [[Teams/{_slug(t)}|{t}]]")
        if len(teams) > 10:
            lines.append(
                f"- *(+{len(teams) - 10} more — see [[{spec.key}|full note]])*"
            )
        lines.append("")

    lines += [
        "## See Also",
        "",
        "- [[_Index|Soccer Atlas Index]]",
        "",
        "#sport/soccer #atlas/playstyles",
    ]
    return "\n".join(lines) + "\n"
