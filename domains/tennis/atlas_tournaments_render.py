"""domains.tennis.atlas_tournaments_render — Markdown rendering for tournament atlas.

Companion to atlas_tournaments.py (LOC split).
F5-clean: stdlib + pandas only.  No edge / betting language.
"""
from __future__ import annotations

import pathlib
import re
from typing import Optional

import pandas as pd

_SLUG_RE = re.compile(r"[^\w\s-]")
_SPACE_RE = re.compile(r"[\s]+")


def _slug(name: str) -> str:
    s = _SLUG_RE.sub("", name).strip()
    return _SPACE_RE.sub("_", s)


def _player_link(name: str) -> str:
    """Return a wikilink resolving to the Players/ note for *name*."""
    return f"[[../Players/{name}|{name}]]"


# ---------------------------------------------------------------------------
# Individual tournament note
# ---------------------------------------------------------------------------

def _render_tournament(info: dict, out_dir: pathlib.Path) -> pathlib.Path:
    """Emit <Tournament Name>.md in *out_dir* and return the path."""
    name: str = info["name"]
    level: str = info["level"]
    level_label: str = info["level_label"]
    surface: str = info["surface"]
    editions: int = info["editions"]
    span: str = info["span"]
    best_of: int = info["best_of"]
    champions_by_year: dict[int, str] = info["champions_by_year"]
    title_counts: dict[str, int] = info["title_counts"]
    recent_finals: list[dict] = info["recent_finals"]
    total_matches: int = info["total_matches"]

    # Champions table: sorted by year descending
    champ_rows: list[str] = []
    for yr in sorted(champions_by_year.keys(), reverse=True):
        player = champions_by_year[yr]
        champ_rows.append(f"| {yr} | {_player_link(player)} |")

    champ_table = (
        "\n".join(champ_rows)
        if champ_rows
        else "| — | No final found in corpus |"
    )

    # Most titles
    titles_lines: list[str] = []
    for player, count in sorted(title_counts.items(), key=lambda kv: -kv[1])[:5]:
        titles_lines.append(f"- {_player_link(player)}: {count} title{'s' if count != 1 else ''}")
    titles_section = (
        "\n".join(titles_lines) if titles_lines else "- No champion data in corpus"
    )

    # Recent finals
    final_lines: list[str] = []
    for f in recent_finals:
        yr = f["year"]
        p1, p2 = f["p1"], f["p2"]
        winner_code = f["winner"]
        score = f.get("score", "")
        if winner_code == "1":
            result = f"{_player_link(p1)} def. {_player_link(p2)}"
        elif winner_code == "2":
            result = f"{_player_link(p2)} def. {_player_link(p1)}"
        else:
            result = f"{_player_link(p1)} vs {_player_link(p2)}"
        score_str = f" ({score})" if score and score != "nan" else ""
        final_lines.append(f"- **{yr}**: {result}{score_str}")
    finals_section = (
        "\n".join(final_lines) if final_lines else "- No finals data in corpus"
    )

    # Honest-data note
    data_note = (
        "Champions listed only where a 'F' (final) round match appears in the corpus. "
        "Years without a recorded final are absent from the table."
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
        "## Champions by Year",
        f"> {data_note}",
        "",
        "| Year | Champion |",
        "|---|---|",
        champ_table,
        "",
        "## Most Titles at This Event",
        "*(corpus window only)*",
        "",
        titles_section,
        "",
        "## Recent Finals",
        "",
        finals_section,
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
    ordered_levels = [l for l in level_order if l in levels_seen]
    # Append any unlisted levels at the end
    ordered_levels += sorted(l for l in levels_seen if l not in ordered_levels)

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
        f"Tournament notes with ≥ 3 editions in the corpus ({total_tournaments} qualifying).",
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
