"""domains.soccer.atlas_style_matchups_render — Markdown renderers for the style-matchups atlas.

Separated from atlas_style_matchups.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas_style_matchups — never imported across domains.

F5 compliance: stdlib + pandas + domains.soccer.* only.
No edge/betting language; all stats corpus-derived; no individual player names.
"""
from __future__ import annotations

from typing import List

from domains.soccer.atlas_playstyles import _SCHEMES, SchemeSpec
from domains.soccer.atlas_style_matchups import PairStats, _MIN_PAIR_MEETINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _scheme_label(key: str) -> str:
    for s in _SCHEMES:
        if s.key == key:
            return s.label
    return key


def _scheme_spec(key: str) -> "SchemeSpec | None":
    for s in _SCHEMES:
        if s.key == key:
            return s
    return None


# ---------------------------------------------------------------------------
# Pair-note renderer
# ---------------------------------------------------------------------------


def render_pair_note(ps: PairStats, generated: str) -> str:
    """Render one <SchemeA>_vs_<SchemeB>.md note."""
    hl = _scheme_label(ps.home_scheme)
    al = _scheme_label(ps.away_scheme)
    hs = _scheme_spec(ps.home_scheme)
    as_ = _scheme_spec(ps.away_scheme)
    home_tags = " ".join(hs.tags) if hs else ""
    away_tags = " ".join(as_.tags) if as_ else ""

    lines: List[str] = [
        "---",
        f'home_scheme: "{hl}"',
        f'away_scheme: "{al}"',
        f"total_meetings: {ps.n}",
        f"home_win_rate: {ps.home_win_rate:.3f}",
        f"draw_rate: {ps.draw_rate:.3f}",
        f"away_win_rate: {ps.away_win_rate:.3f}",
        f"over25_rate: {ps.over25_rate:.3f}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - scheme-matchup",
        "---",
        "",
        f"# {hl} (home) vs {al} (away)",
        "",
        "Up: [[_Style_Matchups_Index|Style Matchups Index]] · [[_Index|Soccer Index]]",
        "",
        f"Schemes: [[Playstyles/{ps.home_scheme}|{hl}]] (home) · "
        f"[[Playstyles/{ps.away_scheme}|{al}]] (away)",
        "",
        "## Outcome Rates",
        "",
        "| Result | Count | Rate |",
        "|--------|-------|------|",
        f"| Home Win | {ps.home_wins} | {_pct(ps.home_win_rate)} |",
        f"| Draw | {ps.draws} | {_pct(ps.draw_rate)} |",
        f"| Away Win | {ps.away_wins} | {_pct(ps.away_win_rate)} |",
        f"| Over 2.5 Goals | {ps.over25} | {_pct(ps.over25_rate)} |",
        f"| Total Meetings | {ps.n} | — |",
        "",
        "## Tactical Context",
        "",
    ]
    if hs:
        lines.append(f"**{hl} (home):** {hs.description}")
        lines.append(f"*Rule:* {hs.signature}")
        lines.append("")
    if as_:
        lines.append(f"**{al} (away):** {as_.description}")
        lines.append(f"*Rule:* {as_.signature}")
        lines.append("")

    lines += [
        "## See Also",
        "",
        "- [[_Style_Matchups_Index|Style Matchups Index]]",
        f"- [[Playstyles/{ps.home_scheme}|{hl}]]",
        f"- [[Playstyles/{ps.away_scheme}|{al}]]",
        "- [[_Index|Soccer Index]]",
        "",
        f"#sport/soccer #scheme-matchup {home_tags} {away_tags}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Index renderer
# ---------------------------------------------------------------------------


def render_index(
    noted_pairs: List[PairStats],
    n_corpus: int,
    generated: str,
) -> str:
    """Render _Style_Matchups_Index.md."""
    lines: List[str] = [
        "---",
        "type: style-matchups-index",
        "sport: soccer",
        f"corpus_matches: {n_corpus}",
        f"pairs_with_notes: {len(noted_pairs)}",
        f"generated: {generated}",
        "tags:",
        "  - sport/soccer",
        "  - atlas/style-matchups",
        "---",
        "",
        "# Soccer Style Matchups Index",
        "",
        "Up: [[_Index|Soccer Index]]",
        "",
        (
            "Scheme-vs-scheme matchup matrix derived from the real match corpus. "
            "Each team is classified into a tactical scheme (see [[_Playstyles_Index|Playstyles]]) "
            "then match outcomes are tallied by home-scheme × away-scheme pairing. "
            f"Pair notes are emitted for pairings with ≥{_MIN_PAIR_MEETINGS} corpus meetings."
        ),
        "",
        "| # | Home Scheme | Away Scheme | Meetings | Home W% | Draw% | Away W% | Over-2.5% |",
        "|---|-------------|-------------|----------|---------|-------|---------|-----------|",
    ]
    for i, ps in enumerate(noted_pairs, 1):
        hl = _scheme_label(ps.home_scheme)
        al = _scheme_label(ps.away_scheme)
        stem = f"{ps.home_scheme}_vs_{ps.away_scheme}"
        link = f"[[{stem}|{hl} vs {al}]]"
        lines.append(
            f"| {i} | {link} | — | {ps.n} "
            f"| {_pct(ps.home_win_rate)} | {_pct(ps.draw_rate)} "
            f"| {_pct(ps.away_win_rate)} | {_pct(ps.over25_rate)} |"
        )

    lines += [
        "",
        "## See Also",
        "",
        "- [[_Playstyles_Index|Playstyles Index]]",
        "- [[_Index|Soccer Index]]",
        "",
        "#sport/soccer #atlas/style-matchups",
    ]
    return "\n".join(lines) + "\n"
