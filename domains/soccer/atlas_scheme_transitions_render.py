"""domains.soccer.atlas_scheme_transitions_render — Markdown renderers for the
scheme-transition matrix atlas.

Separated from atlas_scheme_transitions.py so each file stays within 300 LOC.
Called only by domains.soccer.atlas_scheme_transitions — never imported across domains.

F5 compliance: stdlib + domains.soccer.* only.
No edge/betting language; all stats corpus-derived.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from domains.soccer.atlas_playstyles import _SCHEMES

_SCHEME_KEYS: List[str] = [s.key for s in _SCHEMES]
_SCHEME_LABELS: Dict[str, str] = {s.key: s.label for s in _SCHEMES}
_ABBREVS: Dict[str, str] = {
    "High-Scoring_Attacking": "HighScr",
    "High-Variance_Entertainers": "HiVar",
    "Defensive_Low-Block": "DefBlk",
    "Draw-Prone_Grinder": "DrawPr",
    "Leaky_High-Risk": "Leaky",
    "Strong-at-Home": "StHome",
    "Balanced": "Bal",
}


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _link(key: str) -> str:
    return f"[[Playstyles/{key}|{_SCHEME_LABELS[key]}]]"


def _frontmatter(type_: str, n_transitions: int, generated: str) -> List[str]:
    return [
        "---", f"type: {type_}", "sport: soccer",
        f"n_transitions: {n_transitions}", f"generated: {generated}",
        "tags:", "  - sport/soccer", "  - atlas/scheme-transitions", "---", "",
    ]


def _see_also(*links: str) -> List[str]:
    return ["", "## See Also", ""] + [f"- {lnk}" for lnk in links] + [
        "", "#sport/soccer #atlas/scheme-transitions",
    ]


def _ascii_matrix(
    counts: Dict[str, Dict[str, int]],
    probs: Dict[str, Dict[str, float]],
) -> str:
    """Fixed-width ASCII P(to|from) table; rows=from, cols=to."""
    abbrs = [_ABBREVS[k] for k in _SCHEME_KEYS]
    cw = 8
    header = "FROM\\TO " + " ".join(a.ljust(cw) for a in abbrs) + " | Total"
    sep = "-" * len(header)
    lines = [header, sep]
    for fk in _SCHEME_KEYS:
        cells = [_pct(probs[fk].get(tk, 0.0)).ljust(cw) for tk in _SCHEME_KEYS]
        lines.append(_ABBREVS[fk].ljust(8) + " ".join(cells)
                     + f" | n={sum(counts[fk].values())}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_index(
    sticky: List[Tuple[str, float, int, int]],
    notable: List[Tuple[str, str, int, float]],
    n_corpus: int, n_transitions: int, n_seasons: int,
    seasons: List[int], generated: str,
) -> str:
    s0, s1 = min(seasons), max(seasons)
    lines: List[str] = [
        "---", "type: scheme-transitions-index", "sport: soccer",
        f"corpus_matches: {n_corpus}", f"n_transitions: {n_transitions}",
        f"seasons: {s0}–{s1}", f"generated: {generated}",
        "tags:", "  - sport/soccer", "  - atlas/scheme-transitions", "---", "",
        "# Soccer Scheme Transitions Index", "",
        "Up: [[_Index|Soccer Index]] · [[_Playstyles_Index|Playstyles Index]]", "",
        (f"Consecutive-season scheme transitions for all teams appearing in "
         f"≥10 matches per season across {n_seasons} seasons ({s0}–{s1}) "
         f"from {n_corpus:,} corpus matches. Classification uses the same "
         "priority-waterfall as [[_Playstyles_Index|Playstyles Index]]."),
        "", f"**Total transitions observed:** {n_transitions}", "",
        "## Contents", "",
        "- [[Transition_Matrix|Transition Matrix]] — P(to|from) for all 7×7 scheme pairs",
        "- [[Stickiness|Scheme Stickiness]] — how often each scheme persists season-to-season",
        "- [[Notable_Transitions|Notable Transitions]] — largest off-diagonal flows",
        "", "## Key Findings", "",
    ]
    if sticky:
        st = sticky[0]; ls = sticky[-1]
        lines.append(f"- **Most sticky:** {_link(st[0])} — "
                     f"{_pct(st[1])} persistence (n={st[2]}/{st[3]})")
        if ls[0] != st[0]:
            lines.append(f"- **Least sticky:** {_link(ls[0])} — "
                         f"{_pct(ls[1])} retention (n={ls[2]}/{ls[3]})")
    if notable:
        t = notable[0]
        lines.append(f"- **Top off-diagonal:** {_link(t[0])} → {_link(t[1])} "
                     f"({t[2]} transitions, P={_pct(t[3])})")
    lines += ["", "## Scheme Links", ""]
    for s in _SCHEMES:
        lines.append(f"- {_link(s.key)}")
    lines += ["", "#sport/soccer #atlas/scheme-transitions"]
    return "\n".join(lines) + "\n"


def render_transition_matrix(
    counts: Dict[str, Dict[str, int]],
    probs: Dict[str, Dict[str, float]],
    n_transitions: int, generated: str,
) -> str:
    lines: List[str] = _frontmatter("scheme-transition-matrix", n_transitions, generated) + [
        "# Scheme Transition Matrix", "",
        "Up: [[_Scheme_Transitions_Index|Transitions Index]] · "
        "[[_Playstyles_Index|Playstyles Index]]", "",
        ("Each cell shows **P(column scheme | row scheme)** — the probability that "
         "a team classified into the row scheme in season *t* appears in the column "
         f"scheme in season *t+1*.  Diagonal = stickiness.  Total: {n_transitions}."),
        "", "## P(to|from) Table", "", "```", _ascii_matrix(counts, probs), "```",
        "", "## Raw Counts", "",
        "| From \\ To | " + " | ".join(_ABBREVS[k] for k in _SCHEME_KEYS) + " |",
        "|" + "|".join("---" for _ in range(len(_SCHEME_KEYS) + 1)) + "|",
    ]
    for fk in _SCHEME_KEYS:
        cells = [str(counts[fk].get(tk, 0)) for tk in _SCHEME_KEYS]
        lines.append(f"| {_ABBREVS[fk]} | " + " | ".join(cells) + " |")
    lines += ["", "## Scheme Abbreviations", "", "| Abbrev | Scheme |", "|--------|--------|"]
    for k in _SCHEME_KEYS:
        lines.append(f"| {_ABBREVS[k]} | {_link(k)} |")
    lines += _see_also("[[Stickiness|Stickiness]]", "[[Notable_Transitions|Notable Transitions]]")
    return "\n".join(lines) + "\n"


def render_stickiness(
    sticky: List[Tuple[str, float, int, int]],
    n_transitions: int, generated: str,
) -> str:
    lines: List[str] = _frontmatter("scheme-stickiness", n_transitions, generated) + [
        "# Scheme Stickiness", "",
        "Up: [[_Scheme_Transitions_Index|Transitions Index]] · "
        "[[_Playstyles_Index|Playstyles Index]]", "",
        ("**Stickiness** = fraction of transitions where a team stays in the same "
         "tactical scheme from season *t* to season *t+1*."),
        "", "| Scheme | Stickiness | Stayed | Total |",
        "|--------|-----------|--------|-------|",
    ]
    for key, rate, stays, total in sticky:
        lines.append(f"| {_link(key)} | {_pct(rate)} | {stays} | {total} |")
    if sticky:
        st, ls = sticky[0], sticky[-1]
        lines += [
            "", "## Summary", "",
            f"- Most entrenched: {_link(st[0])} ({_pct(st[1])} persistence rate)",
            f"- Most fluid: {_link(ls[0])} ({_pct(ls[1])} persistence rate)",
        ]
    lines += _see_also("[[Transition_Matrix|Transition Matrix]]",
                       "[[Notable_Transitions|Notable Transitions]]")
    return "\n".join(lines) + "\n"


def render_notable_transitions(
    notable: List[Tuple[str, str, int, float]],
    counts: Dict[str, Dict[str, int]],
    probs: Dict[str, Dict[str, float]],
    generated: str,
) -> str:
    n_total = sum(v for row in counts.values() for v in row.values())
    lines: List[str] = _frontmatter("scheme-notable-transitions", n_total, generated) + [
        "# Notable Scheme Transitions", "",
        "Up: [[_Scheme_Transitions_Index|Transitions Index]] · "
        "[[_Playstyles_Index|Playstyles Index]]", "",
        ("Top off-diagonal transitions by raw count — the most common paths "
         "teams take when changing tactical scheme between consecutive seasons. "
         "All figures are descriptive and corpus-derived."),
        "", "## Top Transitions", "",
        "| From | To | Count | P(to\\|from) |",
        "|------|----|-------|------------|",
    ]
    for fk, tk, cnt, prob in notable:
        lines.append(f"| {_link(fk)} | {_link(tk)} | {cnt} | {_pct(prob)} |")
    if notable:
        t = notable[0]
        lines += [
            "", "## Highlight", "",
            f"The most common scheme change: {_link(t[0])} → {_link(t[1])} "
            f"({t[2]} occurrences, {_pct(t[3])} of teams leaving "
            f"{_SCHEME_LABELS[t[0]]}).",
        ]
    lines += _see_also("[[Transition_Matrix|Transition Matrix]]",
                       "[[Stickiness|Stickiness]]")
    return "\n".join(lines) + "\n"
