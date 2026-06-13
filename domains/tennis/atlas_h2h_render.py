"""domains.tennis.atlas_h2h_render — Markdown rendering helpers for atlas_h2h.

Contains _render_matchup_note and _render_index, split out from atlas_h2h.py
to keep each file ≤300 LOC.  Consumed exclusively by atlas_h2h.build_h2h().

F5-clean: stdlib + pathlib only.  No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.
"""
from __future__ import annotations

import pathlib

# Duplicated from atlas_h2h so this module is self-contained (no circular import).
PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")
_LEVEL_MAP: dict[str, str] = {
    "G": "Grand Slam",
    "M": "Masters",
    "F": "Finals",
    "A": "ATP 250/500",
    "D": "Davis Cup",
    "O": "Olympics",
}


def _render_matchup_note(rv: dict, out_dir: pathlib.Path) -> pathlib.Path:
    """Emit <A> vs <B>.md and return the path."""
    a, b = rv["a"], rv["b"]
    total = rv["total"]
    a_wins, b_wins = rv["a_wins"], rv["b_wins"]

    # Frontmatter
    fm_lines = [
        "---",
        f"players: [{a}, {b}]",
        f"total_meetings: {total}",
        f"h2h: {a_wins}-{b_wins} ({a} leads)" if a_wins != b_wins else f"h2h: {a_wins}-{b_wins} (tied)",
        "tags:",
        "  - sport/tennis",
        "  - matchup",
        "---",
    ]

    # Header + player links
    header_lines = [
        "",
        f"# {a} vs {b}",
        "",
        f"[[Players/{a}|{a}]] · [[Players/{b}|{b}]] · [[_Matchups_Index|← Matchups Index]] · [[_Index|← Tennis Index]]",
        "",
    ]

    # H2H summary
    lead_str = f"**{a}** leads" if a_wins > b_wins else (f"**{b}** leads" if b_wins > a_wins else "tied")
    summary_lines = [
        "## Head-to-Head Summary",
        "",
        f"| | {a} | {b} |",
        "|---|---|---|",
        f"| **Overall** | {a_wins} | {b_wins} |",
    ]

    # Surface rows
    for surf in PRIMARY_SURFACES:
        sp = rv["surf_splits"].get(surf)
        if sp:
            summary_lines.append(f"| **{surf}** | {sp['a_wins']} | {sp['b_wins']} |")

    # Grand Slam row
    gs = rv["gs_split"]
    if gs:
        summary_lines.append(f"| **Grand Slams** | {gs['a_wins']} | {gs['b_wins']} |")

    summary_lines += [
        "",
        f"- **Total meetings:** {total}",
        f"- **Overall record:** {lead_str} {max(a_wins, b_wins)}–{min(a_wins, b_wins)}" if a_wins != b_wins else f"- **Overall record:** {lead_str} {a_wins}–{b_wins}",
    ]

    # Surface detail section
    surf_lines = ["", "## By Surface"]
    has_surf = False
    for surf in PRIMARY_SURFACES:
        sp = rv["surf_splits"].get(surf)
        if sp:
            has_surf = True
            a_lead = f"{a} leads" if sp["a_wins"] > sp["b_wins"] else (f"{b} leads" if sp["b_wins"] > sp["a_wins"] else "tied")
            surf_lines.append(f"- **[[../Surfaces/{surf}|{surf}]]** ({sp['total']} meetings): {a} {sp['a_wins']}–{sp['b_wins']} {b} ({a_lead})")
    if not has_surf:
        surf_lines.append("- No Hard/Clay/Grass split data available in this corpus window.")

    # Tournament level detail
    level_lines = ["", "## By Tournament Level"]
    gs = rv["gs_split"]
    ot = rv["other_split"]
    if gs:
        gs_lead = f"{a} leads" if gs["a_wins"] > gs["b_wins"] else (f"{b} leads" if gs["b_wins"] > gs["a_wins"] else "tied")
        level_lines.append(f"- **Grand Slams** ({gs['total']} meetings): {a} {gs['a_wins']}–{gs['b_wins']} {b} ({gs_lead})")
    if ot:
        ot_lead = f"{a} leads" if ot["a_wins"] > ot["b_wins"] else (f"{b} leads" if ot["b_wins"] > ot["a_wins"] else "tied")
        level_lines.append(f"- **Other ATP events** ({ot['total']} meetings): {a} {ot['a_wins']}–{ot['b_wins']} {b} ({ot_lead})")
    if not gs and not ot:
        level_lines.append("- Tournament-level data not available in this corpus window.")

    if gs and ot:
        note = "*(Grand Slam sample is small — interpret splits with caution.)*" if gs["total"] < 3 else ""
        if note:
            level_lines.append(note)

    # Recent meetings
    recent_lines = ["", "## Most Recent Meetings"]
    for m in rv["recent"]:
        winner_name = a if m["first_won"] else b
        lvl_label = _LEVEL_MAP.get(m["tourney_level"], m["tourney_level"]) if m["tourney_level"] else ""
        lvl_str = f" [{lvl_label}]" if lvl_label else ""
        score_str = f" {m['score']}" if m["score"] and m["score"] != "nan" else ""
        recent_lines.append(
            f"- {m['date']} · {m['tourney_name']}{lvl_str} · {m['round']} · **{winner_name}** won{score_str}"
        )

    tail_lines = [
        "",
        "---",
        "#sport/tennis #matchup",
    ]

    content = "\n".join(
        fm_lines + header_lines + summary_lines + surf_lines + level_lines + recent_lines + tail_lines
    ) + "\n"

    matchups_dir = out_dir
    matchups_dir.mkdir(parents=True, exist_ok=True)
    note_name = f"{a} vs {b}.md"
    path = matchups_dir / note_name
    path.write_text(content, encoding="utf-8")
    return path


def _render_index(
    rivalries: dict[tuple[str, str], dict],
    out_dir: pathlib.Path,
    top_n: int,
) -> pathlib.Path:
    """Emit _Matchups_Index.md and return the path."""
    sorted_rv = sorted(rivalries.values(), key=lambda r: r["total"], reverse=True)[:top_n]

    table_rows: list[str] = []
    for rv in sorted_rv:
        a, b = rv["a"], rv["b"]
        total = rv["total"]
        a_wins, b_wins = rv["a_wins"], rv["b_wins"]
        lead = f"{a} {a_wins}–{b_wins}" if a_wins >= b_wins else f"{b} {b_wins}–{a_wins}"
        note_link = f"[[{a} vs {b}|{a} vs {b}]]"
        table_rows.append(f"| {note_link} | {total} | {lead} |")

    table_str = "\n".join(table_rows) if table_rows else "| — | — | — |"

    lines = [
        "---",
        f"top_n: {top_n}",
        "tags:",
        "  - sport/tennis",
        "  - matchup",
        "---",
        "",
        "# Tennis Rivalries — Matchup Index",
        "",
        "[[_Index|← Tennis Index]]",
        "",
        f"Top {len(sorted_rv)} rivalries by total meetings in the ATP corpus.",
        "",
        "| Matchup | Meetings | Leader (record) |",
        "|---|---|---|",
        table_str,
        "",
        "---",
        "#sport/tennis #matchup",
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "_Matchups_Index.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
