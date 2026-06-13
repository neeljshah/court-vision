"""domains.tennis.atlas_scouting_render — Markdown rendering for scouting briefs.

Internal module; do not import directly — use atlas_scouting.build_scouting().

F5-clean: stdlib only.  No edge/betting language.  No individual player names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Tuple


def _wr_pct(raw: object) -> str:
    try:
        return f"{float(str(raw)) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(raw)


def render_brief(
    pair_filename: str,
    matchup: Dict[str, object],
    playstyle_a: Optional[Dict[str, str]],
    playstyle_b: Optional[Dict[str, str]],
    trends: Dict[str, Tuple[float, float, str]],
) -> str:
    """Render one Scouting/<A>_vs_<B>.md brief body."""
    arch_a: str = str(matchup["archetype_a"])
    arch_b: str = str(matchup["archetype_b"])
    slug_a = arch_a.replace(" ", "_")
    slug_b = arch_b.replace(" ", "_")
    same = (slug_a == slug_b)

    wr_a_pct = _wr_pct(matchup.get("win_rate_a", ""))
    wr_b_pct = _wr_pct(matchup.get("win_rate_b", ""))
    total = matchup.get("total_meetings", "")

    # --- front-matter ---
    note_type = "mirror-matchup" if same else "style-matchup"
    fm_tags = f"  - sport/tennis\n  - scouting\n  - {note_type}\n  - archetype/{slug_a}\n"
    if not same:
        fm_tags += f"  - archetype/{slug_b}\n"
    fm = (
        "---\n"
        f"archetype_a: {arch_a}\narchetype_b: {arch_b}\n"
        f"total_meetings: {total}\n"
        f"win_rate_a: {matchup.get('win_rate_a', '')}\n"
        f"win_rate_b: {matchup.get('win_rate_b', '')}\n"
        f"tags:\n{fm_tags}"
        "---\n"
    )

    # --- breadcrumb ---
    # Bare-stem wikilinks: strip any leading path component and any .md extension
    # so Obsidian resolves by filename-stem globally (idiomatic, no dangling links).
    pair_stem = pair_filename[:-3] if pair_filename.endswith(".md") else pair_filename
    crumb_parts = [
        f"[[_Scouting_Index|← Scouting Index]]",
        f"[[{pair_stem}|Style Matchup: {arch_a} vs {arch_b}]]",
        f"[[{slug_a}|{arch_a}]]",
    ]
    if not same:
        crumb_parts.append(f"[[{slug_b}|{arch_b}]]")
    breadcrumb = " | ".join(crumb_parts)

    # --- matchup summary ---
    summary = [
        "## Matchup Summary", "",
        f"- **Total archetype-level meetings:** {total}",
        f"- **{arch_a} win-rate:** {wr_a_pct}",
        f"- **{arch_b} win-rate:** {wr_b_pct}",
    ]
    if same:
        summary.append(
            f"\n> Mirror matchup: both sides are {arch_a}. "
            "Win-rates reflect that one side wins each encounter; "
            "within-archetype variation (form, surface) determines outcomes."
        )

    # --- surface context ---
    surf_section: List[str] = []
    surfaces: Dict[str, str] = dict(matchup.get("surfaces", {}))  # type: ignore[arg-type]
    spread_note: Optional[str] = matchup.get("surface_spread")  # type: ignore[assignment]
    if surfaces:
        surf_section = [
            "", "## Surface Context", "",
            f"*(Source: [[{pair_stem}]])*", "",
        ]
        for s in ("Hard", "Clay", "Grass"):
            if s in surfaces:
                surf_section.append(f"- **{s}:** {arch_a} win-rate = {surfaces[s]}")
        if spread_note:
            surf_section.append(
                f"\n*Surface spread {spread_note} — surface context is meaningful.*"
            )

    # --- archetype profiles ---
    def _profile(label: str, slug: str, ps: Optional[Dict[str, str]]) -> List[str]:
        lines = [f"### [[{slug}|{label}]]", ""]
        if ps:
            if ps.get("description"):
                lines += [ps["description"], ""]
            if ps.get("surface_tendency"):
                lines.append(f"- **Surface tendency:** {ps['surface_tendency']}")
            cnt, share = ps.get("player_count", ""), ps.get("corpus_share_pct", "")
            if cnt and share:
                lines.append(
                    f"- **Corpus population:** {cnt} players ({share}% of qualifying corpus)"
                )
        else:
            lines.append(f"*Playstyle note not found for {label}.*")
        return lines

    profiles = ["", "## Archetype Profiles", ""]
    profiles.extend(_profile(arch_a, slug_a, playstyle_a))
    if not same:
        profiles += [""] + _profile(arch_b, slug_b, playstyle_b)

    # --- era trends ---
    trend_section = [
        "", "## Era Trends", "",
        "*(Source: [[_Style_Trends_Overview]])*", "",
    ]
    for slug, label in ([(slug_a, arch_a)] if same else [(slug_a, arch_a), (slug_b, arch_b)]):
        if slug in trends:
            fp, lp, direction = trends[slug]
            trend_section.append(
                f"- **{label}:** {direction} — corpus share moved from "
                f"{fp:.1f}% (first year) to {lp:.1f}% (latest year)."
            )
        else:
            trend_section.append(f"- **{label}:** trend data unavailable.")

    # --- sources ---
    sources = [
        "", "## Sources", "",
        f"- [[{pair_stem}|Style Matchup note]]",
        f"- [[{slug_a}|{arch_a} Playstyle note]]",
    ]
    if not same:
        sources.append(f"- [[{slug_b}|{arch_b} Playstyle note]]")
    sources.append("- [[_Style_Trends_Overview|Style Trends Overview]]")

    # --- footer ---
    footer_tags = f"#sport/tennis #scouting #{note_type} #archetype/{slug_a}"
    if not same:
        footer_tags += f" #archetype/{slug_b}"
    footer = f"\n---\n{footer_tags}\n"

    sections = (
        [fm, f"# Scouting Brief: {arch_a} vs {arch_b}", "", breadcrumb, ""]
        + summary + surf_section + profiles + trend_section + sources + [footer]
    )
    return "\n".join(sections)


def render_index(
    pairs: List[Tuple[str, str, str, str, str]],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Write _Scouting_Index.md.  pairs = [(filename, arch_a, arch_b, wr_a_pct, wr_b_pct)]."""
    rows = "\n".join(
        # bare-stem: strip .md so Obsidian resolves globally
        f"| [[{fn[:-3] if fn.endswith('.md') else fn}|{a} vs {b}]] | {wa} | {wb} |"
        for fn, a, b, wa, wb in pairs
    )
    body = (
        "---\n"
        "type: scouting-index\n"
        "tags:\n"
        "  - sport/tennis\n"
        "  - scouting\n"
        "  - atlas/index\n"
        "---\n\n"
        "# Tennis Scouting Briefs — Index\n\n"
        "[[_Index|← Tennis Index]] | "
        "[[_Style_Matchups_Index|Style Matchups]] | "
        "[[_Playstyles_Index|Playstyles]] | "
        "[[_Style_Trends_Overview|Trends]]\n\n"
        f"One synthesised brief per archetype pair with a Style_Matchups note.  "
        f"Total briefs: **{len(pairs)}**\n\n"
        "| Brief | A win-rate | B win-rate |\n"
        "|---|---|---|\n"
        f"{rows}\n\n"
        "---\n"
        "#sport/tennis #scouting #atlas/index\n"
    )
    path = out_dir / "_Scouting_Index.md"
    path.write_text(body, encoding="utf-8")
    return path
