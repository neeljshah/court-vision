"""domains.soccer.atlas_scouting_render — Markdown rendering for soccer scouting briefs.

Internal module; do not import directly — use atlas_scouting.build_scouting().

F5-clean: stdlib only.  No edge/betting language.  No individual player names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note


def _pct(raw: object) -> str:
    """Format a float (0–1) or percent string as 'XX.X%'."""
    try:
        v = float(str(raw).rstrip("%"))
        if v <= 1.0:
            v *= 100
        return f"{v:.1f}%"
    except (ValueError, TypeError):
        return str(raw)


def render_brief(
    pair_filename: str,
    matchup: Dict[str, object],
    playstyle_a: Optional[Dict[str, str]],
    playstyle_b: Optional[Dict[str, str]],
    trends: Dict[str, Tuple[float, float, str]],
    stickiness: Dict[str, Tuple[int, int, float]],
) -> str:
    """Render one Scouting/<A>_vs_<B>.md brief body.

    Parameters
    ----------
    pair_filename:
        Stem+extension of the source Style_Matchups note (e.g. 'Balanced_vs_Defensive_Low-Block.md').
    matchup:
        Output of _parse_matchup_note.
    playstyle_a / playstyle_b:
        Output of _parse_playstyle_note or None if the note was missing.
    trends:
        {scheme_key: (first_yr_pct, last_yr_pct, direction)} from _parse_trends_overview.
    stickiness:
        {scheme_key: (stayed, total, rate)} from _parse_stickiness_note.
    """
    scheme_a: str = str(matchup["home_scheme"])
    scheme_b: str = str(matchup["away_scheme"])
    # Prefer pre-resolved slugs (set by atlas_scouting.build_scouting) so that
    # labels with " / " (e.g. "High-Variance / Entertainers") map to the correct
    # Playstyle filename key (e.g. "High-Variance_Entertainers").
    slug_a = str(matchup.get("slug_a") or scheme_a.replace(" / ", "_").replace(" ", "_"))
    slug_b = str(matchup.get("slug_b") or scheme_b.replace(" / ", "_").replace(" ", "_"))
    same = (slug_a == slug_b)

    total = matchup.get("total_meetings", "")
    hw_pct = _pct(matchup.get("home_win_rate", ""))
    draw_pct = _pct(matchup.get("draw_rate", ""))
    aw_pct = _pct(matchup.get("away_win_rate", ""))
    ov_pct = _pct(matchup.get("over25_rate", ""))

    # --- front-matter ---
    note_type = "mirror-matchup" if same else "scheme-matchup"
    fm_tags = f"  - sport/soccer\n  - scouting\n  - {note_type}\n  - scheme/{slug_a}\n"
    if not same:
        fm_tags += f"  - scheme/{slug_b}\n"
    fm = (
        "---\n"
        f"home_scheme: {scheme_a}\naway_scheme: {scheme_b}\n"
        f"total_meetings: {total}\n"
        f"home_win_rate: {matchup.get('home_win_rate', '')}\n"
        f"draw_rate: {matchup.get('draw_rate', '')}\n"
        f"away_win_rate: {matchup.get('away_win_rate', '')}\n"
        f"over25_rate: {matchup.get('over25_rate', '')}\n"
        f"tags:\n{fm_tags}"
        "---\n"
    )

    # --- breadcrumb (bare-stem wikilinks) ---
    pair_stem = pair_filename[:-3] if pair_filename.endswith(".md") else pair_filename
    crumb_parts = [
        "[[_Scouting_Index|← Scouting Index]]",
        f"[[{pair_stem}|Style Matchup: {scheme_a} vs {scheme_b}]]",
        f"[[{slug_a}|{scheme_a}]]",
    ]
    if not same:
        crumb_parts.append(f"[[{slug_b}|{scheme_b}]]")
    breadcrumb = " | ".join(crumb_parts)

    # --- matchup summary ---
    summary: List[str] = [
        "## Matchup Summary", "",
        f"- **Total scheme-level meetings:** {total}",
        f"- **Home win rate:** {hw_pct}",
        f"- **Draw rate:** {draw_pct}",
        f"- **Away win rate:** {aw_pct}",
        f"- **Over 2.5 goals rate:** {ov_pct}",
    ]
    if same:
        summary.append(
            f"\n> Mirror matchup: both home and away sides are {scheme_a}. "
            "Win-rates reflect that one side wins each encounter; "
            "within-scheme variation (form, home advantage) determines outcomes."
        )

    # --- scheme profiles ---
    def _profile(label: str, slug: str, ps: Optional[Dict[str, str]], role: str) -> List[str]:
        lines = [f"### [[{slug}|{label}]] ({role})", ""]
        if ps:
            desc = ps.get("description", "")
            if desc:
                lines += [desc, ""]
            sig = ps.get("stat_signature", "")
            if sig:
                lines.append(f"- **Stat signature:** {sig}")
            cnt = ps.get("team_count", "")
            if cnt:
                lines.append(f"- **Corpus teams:** {cnt}")
        else:
            lines.append(f"*Playstyle note not found for {label}.*")
        return lines

    profiles: List[str] = ["", "## Scheme Profiles", ""]
    profiles.extend(_profile(scheme_a, slug_a, playstyle_a, "home"))
    if not same:
        profiles += [""] + _profile(scheme_b, slug_b, playstyle_b, "away")

    # --- era trends ---
    trend_section: List[str] = [
        "", "## Era Trends", "",
        "*(Source: [[_Style_Trends_Overview]])*", "",
    ]
    for slug, label in ([(slug_a, scheme_a)] if same else [(slug_a, scheme_a), (slug_b, scheme_b)]):
        if slug in trends:
            fp, lp, direction = trends[slug]
            trend_section.append(
                f"- **{label}:** {direction} — corpus share moved from "
                f"{fp:.1f}% (2015) to {lp:.1f}% (2025)."
            )
        else:
            trend_section.append(f"- **{label}:** trend data unavailable.")

    # --- stickiness ---
    stick_section: List[str] = ["", "## Scheme Stickiness", "",
                                "*(Source: [[Stickiness]])*", ""]
    for slug, label in ([(slug_a, scheme_a)] if same else [(slug_a, scheme_a), (slug_b, scheme_b)]):
        if slug in stickiness:
            stayed, total_trans, rate = stickiness[slug]
            stick_section.append(
                f"- **{label}:** {rate:.1f}% persistence rate "
                f"({stayed} of {total_trans} season-to-season transitions stayed in scheme)."
            )
        else:
            stick_section.append(f"- **{label}:** stickiness data unavailable.")

    # --- sources ---
    sources: List[str] = [
        "", "## Sources", "",
        f"- [[{pair_stem}|Style Matchup note]]",
        f"- [[{slug_a}|{scheme_a} Playstyle note]]",
    ]
    if not same:
        sources.append(f"- [[{slug_b}|{scheme_b} Playstyle note]]")
    sources += [
        "- [[_Style_Trends_Overview|Style Trends Overview]]",
        "- [[Stickiness|Scheme Stickiness]]",
    ]

    # --- footer ---
    footer_tags = f"#sport/soccer #scouting #{note_type} #scheme/{slug_a}"
    if not same:
        footer_tags += f" #scheme/{slug_b}"
    footer = f"\n---\n{footer_tags}\n"

    sections = (
        [fm, f"# Scouting Brief: {scheme_a} (home) vs {scheme_b} (away)", "",
         breadcrumb, ""]
        + summary + profiles + trend_section + stick_section + sources + [footer]
    )
    return "\n".join(sections)


def render_index(
    pairs: List[Tuple[str, str, str, str, str, str]],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Write _Scouting_Index.md.

    pairs = [(filename, scheme_a, scheme_b, hw_pct, draw_pct, aw_pct)]
    """
    rows = "\n".join(
        f"| [[{fn[:-3] if fn.endswith('.md') else fn}|{a} vs {b}]] | {hw} | {dr} | {aw} |"
        for fn, a, b, hw, dr, aw in pairs
    )
    body = (
        "---\n"
        "type: scouting-index\n"
        "tags:\n"
        "  - sport/soccer\n"
        "  - scouting\n"
        "  - atlas/index\n"
        "---\n\n"
        "# Soccer Scouting Briefs — Index\n\n"
        "[[_Index|← Soccer Index]] | "
        "[[_Style_Matchups_Index|Style Matchups]] | "
        "[[_Playstyles_Index|Playstyles]] | "
        "[[_Style_Trends_Overview|Trends]]\n\n"
        f"One synthesised brief per scheme pair with a Style_Matchups note.  "
        f"Total briefs: **{len(pairs)}**\n\n"
        "| Brief | Home-win | Draw | Away-win |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n"
        "---\n"
        "#sport/soccer #scouting #atlas/index\n"
    )
    path = out_dir / "_Scouting_Index.md"
    return write_note(path, body)
