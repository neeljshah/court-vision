"""domains.mlb.atlas_scouting_render — Markdown rendering for MLB scouting briefs.

Internal module; do not import directly — use atlas_scouting.build_scouting().

F5-clean: stdlib + scripts.platformkit.atlas.obsidian_emit only.
No edge/betting language.  No individual player names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note as _write_note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(raw: object, already_pct: bool = False) -> str:
    """Format a numeric value as a percentage string."""
    try:
        v = float(str(raw).replace("%", ""))
        if not already_pct:
            v *= 100.0
        return f"{v:.1f}%"
    except (ValueError, TypeError):
        return str(raw)


def _ff(raw: object, d: int = 2) -> str:
    try:
        return f"{float(str(raw)):.{d}f}"
    except (ValueError, TypeError):
        return str(raw)


# ---------------------------------------------------------------------------
# Per-pair brief renderer
# ---------------------------------------------------------------------------

def render_brief(
    *,
    pair_filename: str,
    matchup: Dict[str, object],
    playstyle_home: Optional[Dict[str, str]],
    playstyle_away: Optional[Dict[str, str]],
    trends: Dict[str, Tuple[float, float, str]],
    slug_to_name: Dict[str, str],
) -> str:
    """Render one Scouting/<home_slug>__vs__<away_slug>.md brief body.

    Parameters
    ----------
    pair_filename:
        The source Style_Matchups filename (e.g. ``power_run_scoring__vs__balanced_contender.md``).
    matchup:
        Parsed matchup dict with keys: home_slug, away_slug, n, home_win_rate,
        avg_total, high_rate, high_total_thresh, corpus_span.
    playstyle_home / playstyle_away:
        Parsed playstyle dicts (or None if note missing) with keys:
        archetype, team_count, description, signature.
    trends:
        {slug: (first_yr_share, last_yr_share, direction)} from Trends overview.
    slug_to_name:
        {slug: human_name} mapping for display.
    """
    home_slug: str = str(matchup.get("home_slug", ""))
    away_slug: str = str(matchup.get("away_slug", ""))
    home_name: str = slug_to_name.get(home_slug, home_slug.replace("_", " ").title())
    away_name: str = slug_to_name.get(away_slug, away_slug.replace("_", " ").title())
    same: bool = (home_slug == away_slug)

    n = matchup.get("n", "")
    hwr = matchup.get("home_win_rate", "")
    avg_total = matchup.get("avg_total", "")
    high_rate = matchup.get("high_rate", "")
    high_thresh = matchup.get("high_total_thresh", 10.0)
    corpus_span = str(matchup.get("corpus_span", ""))

    # --- front-matter ---
    note_type = "mirror-matchup" if same else "style-matchup"
    fm_tags = f"  - sport/mlb\n  - scouting\n  - {note_type}\n  - home/{home_slug}\n"
    if not same:
        fm_tags += f"  - away/{away_slug}\n"
    fm = (
        "---\n"
        f"home_slug: {home_slug}\naway_slug: {away_slug}\n"
        f"game_count: {n}\n"
        f"home_win_rate: {hwr}\n"
        f"corpus_span: {corpus_span}\n"
        f"tags:\n{fm_tags}"
        "---\n"
    )

    # --- breadcrumb (bare-stem wikilinks) ---
    pair_stem = pair_filename[:-3] if pair_filename.endswith(".md") else pair_filename
    crumb_parts = [
        "[[_Scouting_Index|← Scouting Index]]",
        f"[[{pair_stem}|Style Matchup: {home_name} vs {away_name}]]",
        f"[[{home_slug}|{home_name}]]",
    ]
    if not same:
        crumb_parts.append(f"[[{away_slug}|{away_name}]]")
    breadcrumb = " | ".join(crumb_parts)

    # --- matchup summary ---
    thresh_label = (
        str(int(high_thresh)) if float(high_thresh) == int(float(high_thresh))
        else str(high_thresh)
    )
    hwr_pct = _pct(hwr)
    avg_total_s = _ff(avg_total)
    high_rate_pct = _pct(high_rate)

    summary = [
        "## Matchup Summary", "",
        f"- **Games in corpus:** {n}",
        f"- **Home-win rate:** {hwr_pct}",
        f"- **Avg total runs / game:** {avg_total_s}",
        f"- **High-scoring rate (≥{thresh_label} total runs):** {high_rate_pct}",
    ]
    if same:
        summary.append(
            f"\n> Mirror matchup: both sides carry the {home_name} identity. "
            "Home advantage and within-style variation (roster depth, rotation) "
            "determine outcomes."
        )

    # --- style profiles ---
    def _profile(label: str, slug: str, ps: Optional[Dict[str, str]], side: str) -> List[str]:
        lines: List[str] = [f"### [[{slug}|{label}]] ({side} style)", ""]
        if ps:
            desc = ps.get("description", "")
            if desc:
                lines += [desc, ""]
            sig = ps.get("signature", "")
            if sig:
                lines.append(f"- **Signature:** {sig}")
            tc = ps.get("team_count", "")
            if tc:
                lines.append(f"- **Teams in archetype (corpus):** {tc}")
        else:
            lines.append(f"*Playstyle note not found for {label}.*")
        return lines

    profiles: List[str] = ["", "## Style Profiles", ""]
    profiles.extend(_profile(home_name, home_slug, playstyle_home, "home"))
    if not same:
        profiles += [""] + _profile(away_name, away_slug, playstyle_away, "away")

    # --- run environment note ---
    env_section: List[str] = [
        "", "## Run-Environment Context", "",
        "*(Source: [[_Style_Trends_Overview]])*", "",
    ]
    for slug, label in ([(home_slug, home_name)] if same else [(home_slug, home_name), (away_slug, away_name)]):
        if slug in trends:
            fp, lp, direction = trends[slug]
            env_section.append(
                f"- **{label}:** {direction} — archetype share moved from "
                f"{fp:.1f}% (2010) to {lp:.1f}% (2021) of qualifying franchises."
            )
        else:
            env_section.append(f"- **{label}:** trend data unavailable.")

    # --- sources ---
    sources: List[str] = [
        "", "## Sources", "",
        f"- [[{pair_stem}|Style Matchup note]]",
        f"- [[{home_slug}|{home_name} Playstyle note]]",
    ]
    if not same:
        sources.append(f"- [[{away_slug}|{away_name} Playstyle note]]")
    sources.append("- [[_Style_Trends_Overview|Style Trends Overview]]")
    sources.append("- [[MLB_Home_Environment_Rankings|Home Run-Environment Rankings]]")

    # --- footer ---
    footer_tags = f"#sport/mlb #scouting #{note_type} #home/{home_slug}"
    if not same:
        footer_tags += f" #away/{away_slug}"
    footer = f"\n---\n{footer_tags}\n"

    sections = (
        [fm, f"# Scouting Brief: {home_name} (home) vs {away_name} (away)", "", breadcrumb, ""]
        + summary + profiles + env_section + sources + [footer]
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Index renderer
# ---------------------------------------------------------------------------

def render_index(
    pairs: List[Tuple[str, str, str, str, str, str]],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Write _Scouting_Index.md.

    pairs = [(filename_stem, home_slug, away_slug, home_name, away_name, hwr_pct)]
    """
    rows = "\n".join(
        f"| [[{stem}|{hn} vs {an}]] | {hn} | {an} | {hwr} |"
        for stem, _hs, _as, hn, an, hwr in pairs
    )
    total = len(pairs)
    body = (
        "---\n"
        "type: scouting-index\n"
        "sport: mlb\n"
        "tags:\n"
        "  - sport/mlb\n"
        "  - scouting\n"
        "  - atlas/index\n"
        "---\n\n"
        "# MLB Scouting Briefs — Index\n\n"
        "[[_Index|← MLB Index]] | "
        "[[_Style_Matchups_Index|Style Matchups]] | "
        "[[_Playstyles_Index|Playstyles]] | "
        "[[_Style_Trends_Overview|Trends]]\n\n"
        f"One synthesised scouting brief per style pair with a Style_Matchups note.  "
        f"Total briefs: **{total}**\n\n"
        "| Brief | Home Style | Away Style | Home-Win% |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n"
        "---\n"
        "#sport/mlb #scouting #atlas/index\n"
    )
    path = out_dir / "_Scouting_Index.md"
    _write_note(path, body)
    return path
