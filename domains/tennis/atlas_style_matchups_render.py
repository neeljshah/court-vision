"""domains.tennis.atlas_style_matchups_render — Rendering helpers for style matchup notes.

Called by atlas_style_matchups.build_style_matchups. Emits Obsidian markdown.
F5-clean: stdlib + domains.tennis.atlas_playstyle_specs only.
No edge / betting language. No individual player names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

from domains.tennis.atlas_playstyle_specs import ArchetypeSpec

PRIMARY_SURFACES: Tuple[str, ...] = ("Hard", "Clay", "Grass")
SURFACE_SPREAD_THRESHOLD: float = 0.03


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _surface_split_lines(tally: Dict, min_n: int = 10) -> List[str]:
    """Emit per-surface win-rate lines when sufficient sample exists."""
    surfs = tally.get("surfaces", {})
    rates: Dict[str, float] = {}
    for surf in PRIMARY_SURFACES:
        sd = surfs.get(surf, {})
        n = sd.get("total", 0)
        wa = sd.get("wins_a", 0)
        if n >= min_n:
            rates[surf] = wa / n
    if not rates:
        return ["*Fewer than 10 meetings on any individual surface — no surface split reported.*"]
    spread = max(rates.values()) - min(rates.values()) if len(rates) > 1 else 0.0
    lines: List[str] = [
        f"- **{surf}:** win-rate of A = {_pct(wr)} ({surfs[surf]['total']} meetings)"
        for surf, wr in sorted(rates.items())
    ]
    note = (
        f"*Surface spread {spread * 100:.1f} pp — pattern holds across surfaces.*"
        if spread < SURFACE_SPREAD_THRESHOLD
        else f"*Surface spread {spread * 100:.1f} pp — surface context is meaningful.*"
    )
    lines.append(""); lines.append(note)
    return lines


def render_pair_note(
    pair: Tuple[str, str],
    tally: Dict,
    out_dir: pathlib.Path,
    slug_map: Dict[str, ArchetypeSpec],
) -> pathlib.Path:
    """Write <SlugA>_vs_<SlugB>.md; return path."""
    slug_a, slug_b = pair
    spec_a, spec_b = slug_map[slug_a], slug_map[slug_b]
    total = tally["total"]
    wins_a = tally["wins_a"]
    wins_b = total - wins_a
    wr_a = wins_a / total if total > 0 else 0.5
    wr_b = wins_b / total if total > 0 else 0.5
    mirror = slug_a == slug_b

    tag_block = (
        f"  - sport/tennis\n  - style-matchup\n  - style-vs-style\n"
        f"  - archetype/{slug_a}"
        + (f"\n  - archetype/{slug_b}" if not mirror else "")
    )
    nav = (
        f"[[_Style_Matchups_Index|← Style Matchups Index]] | "
        f"[[Playstyles/{slug_a}|{spec_a.name}]] | [[Playstyles/{slug_b}|{spec_b.name}]]"
    )

    lines: List[str] = [
        "---",
        f"archetype_a: {spec_a.name}",
        f"archetype_b: {spec_b.name}",
        f"total_meetings: {total}",
        f"win_rate_a: {round(wr_a, 4)}",
        f"win_rate_b: {round(wr_b, 4)}",
        "tags:", tag_block,
        "---", "",
        f"# {spec_a.name} vs {spec_b.name}", "",
        nav, "",
        "## Outcome Summary",
        f"- **Total meetings (archetype level):** {total}",
        f"- **Win-rate — {spec_a.name} (A side):** {_pct(wr_a)} ({wins_a} wins)",
        f"- **Win-rate — {spec_b.name} (B side):** {_pct(wr_b)} ({wins_b} wins)", "",
        "## Surface Breakdown",
    ] + _surface_split_lines(tally) + [
        "",
        "## Archetype Context",
        f"**{spec_a.name}:** {spec_a.description}", "",
        f"**{spec_b.name}:** {spec_b.description}", "",
        "## Tactical Notes",
        (
            f"- Matchup decided by {total} archetype-level encounters in the corpus."
            if not mirror
            else f"- Mirror matchup: both players share the **{spec_a.name}** profile."
        ),
        "- Win-rates reflect the aggregate pattern; individual match quality varies.",
        "- Surface split indicates where the style differential is amplified.", "",
        "---",
        "#sport/tennis #style-matchup #style-vs-style "
        f"#archetype/{slug_a}" + (f" #archetype/{slug_b}" if not mirror else ""),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug_a}_vs_{slug_b}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_index(
    qualified_pairs: List[Tuple[Tuple[str, str], Dict]],
    total_matches: int,
    total_players: int,
    min_pair_meetings: int,
    out_dir: pathlib.Path,
    slug_map: Dict[str, ArchetypeSpec],
) -> pathlib.Path:
    """Write _Style_Matchups_Index.md; return path."""
    rows = []
    for pair, tally in sorted(qualified_pairs, key=lambda x: -x[1]["total"]):
        slug_a, slug_b = pair
        name_a, name_b = slug_map[slug_a].name, slug_map[slug_b].name
        total = tally["total"]
        wr_a = tally["wins_a"] / total if total > 0 else 0.5
        b_label = f"[[Playstyles/{slug_b}|{name_b}]]" + (" *(mirror)*" if slug_a == slug_b else "")
        rows.append(
            f"| [[{slug_a}_vs_{slug_b}|{name_a} vs {name_b}]] "
            f"| [[Playstyles/{slug_a}|{name_a}]] | {b_label} "
            f"| {_pct(wr_a)} | {_pct(1 - wr_a)} | {total} |"
        )
    table = "\n".join(rows) or "| *(no qualified pairs)* | — | — | — | — | — |"
    lines: List[str] = [
        "---", "type: style-matchups-index",
        f"total_corpus_matches: {total_matches}",
        f"qualified_players: {total_players}",
        f"qualified_pairs: {len(qualified_pairs)}",
        f"min_pair_meetings: {min_pair_meetings}",
        "tags:", "  - sport/tennis", "  - style-matchup", "  - atlas/index",
        "---", "",
        "# Tennis Style-vs-Style Matchup Matrix", "",
        "[[_Index|← Tennis Index]] | [[Playstyles/_Playstyles_Index|← Playstyle Index]]", "",
        (
            f"Archetype-level outcome tallies derived from {total_matches:,} corpus matches "
            f"across {total_players} qualifying players. Each player is assigned to one archetype "
            f"using the same thresholds as [[Playstyles/_Playstyles_Index|the playstyle atlas]]. "
            f"Only archetype pairs with ≥ {min_pair_meetings} meetings are reported."
        ),
        "",
        "## Qualified Matchup Pairs", "",
        "| Matchup | Archetype A | Archetype B | Win-Rate A | Win-Rate B | Meetings |",
        "|---|---|---|---|---|---|",
        table, "",
        "## Notes",
        "- Win-rates are archetype-level aggregates, not individual-level predictions.",
        "- Surface splits are reported in each pair note where ≥10 meetings per surface exist.",
        "- No individual player names appear anywhere in this section.",
        "- Archetypes defined in [[Playstyles/_Playstyles_Index]].", "",
        "---", "#sport/tennis #style-matchup #atlas/index",
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "_Style_Matchups_Index.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
