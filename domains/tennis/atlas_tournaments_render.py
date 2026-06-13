"""domains.tennis.atlas_tournaments_render — Markdown rendering for tournament atlas.

Companion to atlas_tournaments.py (LOC split).
F5-clean: stdlib + pandas only.  No edge / betting language.
No individual player names appear in any rendered output.
Tournament notes are name-free style-profiles (surface, level, archetype
distribution, upset tendency) describing events and venues — not champions.
"""
from __future__ import annotations

import pathlib
from typing import Optional

from scripts.platformkit.atlas.obsidian_emit import slug as _slug  # noqa: F401


def _pct_bar(pct: float, width: int = 10) -> str:
    """Return a simple ASCII bar representing a percentage (0–100)."""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Individual tournament note
# ---------------------------------------------------------------------------

def _render_tournament(info: dict, out_dir: pathlib.Path) -> pathlib.Path:
    """Emit <Tournament Name>.md in *out_dir* and return the path.

    Content is a name-free style-profile: surface, level, corpus statistics,
    winner-archetype distribution, and upset tendency.  No individual player
    names or champion tables appear in the output.
    """
    name: str = info["name"]
    level: str = info["level"]
    level_label: str = info["level_label"]
    surface: str = info["surface"]
    editions: int = info["editions"]
    editions_with_final: int = info["editions_with_final"]
    completion_rate: float = info["completion_rate"]
    span: str = info["span"]
    best_of: int = info["best_of"]
    style_profile: dict = info["style_profile"]
    total_matches: int = info["total_matches"]

    specialist_pct: float = style_profile.get("specialist_pct", 0.0)
    allcourt_pct: float = style_profile.get("allcourt_pct", 0.0)
    unknown_pct: float = style_profile.get("unknown_pct", 100.0)
    n_classified: int = style_profile.get("n_classified", 0)
    upset_rate: Optional[float] = style_profile.get("upset_rate")

    # Archetype distribution section
    if n_classified > 0:
        archetype_lines = [
            "| Archetype | Share | Visual |",
            "|---|---|---|",
            f"| Surface-specialist | {specialist_pct:.0f}% | {_pct_bar(specialist_pct)} |",
            f"| All-court | {allcourt_pct:.0f}% | {_pct_bar(allcourt_pct)} |",
        ]
        if unknown_pct > 0.0:
            archetype_lines.append(
                f"| Unclassified | {unknown_pct:.0f}% | {_pct_bar(unknown_pct)} |"
            )
        archetype_note = (
            f"Based on {n_classified} edition{'s' if n_classified != 1 else ''} "
            f"with an identifiable finalist archetype (corpus window only)."
        )
        archetype_section = "\n".join(archetype_lines) + f"\n\n> {archetype_note}"
    else:
        archetype_section = (
            "*Archetype distribution unavailable — no finals with identifiable "
            "finalists in corpus.*"
        )

    # Upset-tendency section
    if upset_rate is not None:
        upset_pct = round(upset_rate * 100, 1)
        upset_desc = (
            "high" if upset_pct >= 35
            else "moderate" if upset_pct >= 20
            else "low"
        )
        upset_section = (
            f"- **Final upset rate:** {upset_pct:.1f}% ({upset_desc}) — "
            f"fraction of finals won by the lower-ranked finalist (rank at match time)."
        )
    else:
        upset_section = (
            "- **Final upset rate:** not available (rank data absent from corpus)."
        )

    # Completion note
    completion_note = (
        f"Finals recorded for {editions_with_final} of {editions} editions "
        f"({completion_rate:.0f}% completion). "
        "Editions without a recorded 'F' round match are excluded from archetype counts."
    )

    lines = [
        "---",
        f"name: \"{name}\"",
        f"level: {level}",
        f"level_label: {level_label}",
        f"surface: {surface}",
        f"editions: {editions}",
        f"span: \"{span}\"",
        f"best_of: {best_of}",
        "tags:",
        "  - sport/tennis",
        "  - tournament",
        f"  - level/{level.lower()}",
        "---",
        "",
        f"# {name}",
        "",
        "[[_Tournaments_Index|← Tournaments Index]] | [[../_Index|← Tennis Index]]",
        "",
        "## Overview",
        f"- **Level:** {level_label} (`{level}`)",
        f"- **Surface:** {surface}",
        f"- **Editions in corpus:** {editions} ({span})",
        f"- **Typical format:** Best of {best_of}",
        f"- **Total corpus matches:** {total_matches}",
        "",
        "## Winner Archetype Distribution",
        "",
        "> Classification is corpus-internal and name-free: a finalist who reached "
        "finals exclusively on one surface type is labelled *surface-specialist*; "
        "one who reached finals on multiple surfaces is labelled *all-court*.",
        "",
        archetype_section,
        "",
        "## Upset Tendency",
        "",
        upset_section,
        "",
        "## Data Notes",
        "",
        f"> {completion_note}",
        "",
        "---",
        f"#sport/tennis #tournament #level/{level.lower()}",
    ]

    path = out_dir / f"{name}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Index note
# ---------------------------------------------------------------------------

def _render_index(
    tournament_stats: dict[str, dict],
    out_dir: pathlib.Path,
    level_order: list[str],
    level_labels: dict[str, str],
) -> pathlib.Path:
    """Emit _Tournaments_Index.md and return the path."""
    total_tournaments = len(tournament_stats)

    # Group by level, preserve level_order
    by_level: dict[str, list[dict]] = {}
    for info in tournament_stats.values():
        lvl = info["level"]
        by_level.setdefault(lvl, []).append(info)

    # Sort each level's list by editions desc, then name
    for lvl in by_level:
        by_level[lvl].sort(key=lambda d: (-d["editions"], d["name"]))

    section_lines: list[str] = []
    levels_seen = set(by_level.keys())
    ordered_levels = [lv for lv in level_order if lv in levels_seen]
    # Append any unlisted levels at the end
    ordered_levels += sorted(lv for lv in levels_seen if lv not in ordered_levels)

    for lvl in ordered_levels:
        label = level_labels.get(lvl, lvl)
        section_lines.append(f"### {label}")
        section_lines.append("")
        section_lines.append("| Tournament | Surface | Editions | Span |")
        section_lines.append("|---|---|---|---|")
        for info in by_level[lvl]:
            tname = info["name"]
            link = f"[[{tname}|{tname}]]"
            section_lines.append(
                f"| {link} | {info['surface']} | {info['editions']} | {info['span']} |"
            )
        section_lines.append("")

    sections = "\n".join(section_lines) if section_lines else "*(no qualifying tournaments)*"

    lines = [
        "---",
        f"total_tournaments: {total_tournaments}",
        "tags:",
        "  - sport/tennis",
        "  - tournament",
        "  - atlas/index",
        "---",
        "",
        "# Tournaments Index",
        "",
        "[[../_Index|← Tennis Index]]",
        "",
        f"Tournament style-profile notes with ≥ 3 editions in the corpus ({total_tournaments} qualifying).",
        "Notes describe surface, level, and winner-archetype distribution — no individual names.",
        "",
        "## Tournaments by Level",
        "",
        sections,
        "---",
        "#sport/tennis #tournament #atlas/index",
    ]

    path = out_dir / "_Tournaments_Index.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render_all_tournaments(
    out_dir: pathlib.Path,
    tournament_stats: dict[str, dict],
    level_order: list[str],
    level_labels: dict[str, str],
) -> list[pathlib.Path]:
    """Render all tournament notes; return written paths."""
    written: list[pathlib.Path] = []

    # Tournament notes
    for info in tournament_stats.values():
        written.append(_render_tournament(info, out_dir))

    # Index
    written.append(
        _render_index(
            tournament_stats=tournament_stats,
            out_dir=out_dir,
            level_order=level_order,
            level_labels=level_labels,
        )
    )

    return written
