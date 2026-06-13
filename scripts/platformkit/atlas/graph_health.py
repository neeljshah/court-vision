"""graph_health.py — Wikilink integrity + person-free graph health report.

Scans vault/Sports/**/*.md, writes vault/Sports/_Graph_Health.md with:
  1. Dangling-link audit split into INTENTIONAL vs FIXABLE categories.
  2. Note-type coverage per sport (counts by immediate subfolder).
  3. Conservative person-free check — flags ONLY [[Players/...]] wikilinks,
     player_name:/display_name: frontmatter keys, or ## Players/Roster/Squad
     headers.  No fuzzy surname matching.
  4. GRAPH-INTEGRITY verdict = PASS when fixable dangling == 0.

Usage::

    from scripts.platformkit.atlas.graph_health import build_graph_health
    out = build_graph_health()        # default vault/Sports path
    out = build_graph_health(my_dir)  # custom path
"""
from __future__ import annotations

import pathlib
import re
import time
from collections import Counter
from typing import Dict, FrozenSet, List, Set, Tuple

from scripts.platformkit.atlas.obsidian_emit import write_note
_WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+)")

# High-confidence person-bearing patterns only — no fuzzy surname matching.
_PERSON_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"\[\[Players/"),                                     # [[Players/...
    re.compile(r"^player_name\s*:", re.MULTILINE | re.IGNORECASE),  # frontmatter key
    re.compile(r"^display_name\s*:", re.MULTILINE | re.IGNORECASE), # frontmatter key
    re.compile(r"^##\s+Players\b", re.MULTILINE | re.IGNORECASE),   # section header
    re.compile(r"^##\s+Roster\b",  re.MULTILINE | re.IGNORECASE),   # section header
    re.compile(r"^##\s+Squad\b",   re.MULTILINE | re.IGNORECASE),   # section header
)

_OUT_FILENAME = "_Graph_Health.md"

# Intentional cross-vault allowlist — targets that legitimately live OUTSIDE vault/Sports.
# Add entries here to extend; no logic changes needed.
_INTENTIONAL_EXACT: FrozenSet[str] = frozenset([
    "Home", "MOC-CV", "MOC-Models", "MOC-Betting", "MOC-Strategy",
    "Intelligence/_Scout_Index",
])
_INTENTIONAL_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"^MOC-"),         # any Map-of-Contents note
    re.compile(r"^Intelligence/"), # main-vault Intelligence folder
    # Season-archive notes: Bundesliga_2015, Premier_League_2020, La_Liga_2023, …
    re.compile(r"^(?:Bundesliga|Premier_League|EFL_Championship|Ligue_1|Serie_A|La_Liga)_\d{4}$"),
)


def _is_intentional(target: str) -> bool:
    """Return True if *target* is an intentional cross-vault shortcut."""
    if target in _INTENTIONAL_EXACT:
        return True
    return any(p.search(target) for p in _INTENTIONAL_PATTERNS)


def _read_safe(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_links(text: str) -> List[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _is_person_bearing(text: str) -> bool:
    return any(p.search(text) for p in _PERSON_PATTERNS)


def _resolve_target(target: str, stems: Set[str], rel_paths: Set[str]) -> bool:
    """True if *target* matches a note stem or relative path anywhere in the tree."""
    t = target.strip()
    return t.split("/")[-1] in stems or t in rel_paths


def _scan_vault(vault_dir: pathlib.Path) -> dict:
    """Scan the full vault tree once; return all data needed for the report."""
    # Exclude the output file itself (it contains [[Players/...]] in example text).
    notes = [f for f in vault_dir.rglob("*.md") if f.name != _OUT_FILENAME]
    stems: Set[str] = {f.stem for f in notes}
    rel_paths: Set[str] = {
        f.relative_to(vault_dir).with_suffix("").as_posix() for f in notes
    }

    sport_counts: Dict[str, Dict[str, int]] = {}
    total_links = 0
    dangling_intentional: Counter = Counter()
    dangling_fixable: Counter = Counter()
    person_notes: List[pathlib.Path] = []

    for f in notes:
        parts = f.relative_to(vault_dir).parts
        sport = parts[0] if len(parts) >= 2 else "_root"
        subtype = parts[1] if len(parts) >= 3 else "_root"

        if sport not in sport_counts:
            sport_counts[sport] = {}
        sport_counts[sport][subtype] = sport_counts[sport].get(subtype, 0) + 1

        text = _read_safe(f)

        if _is_person_bearing(text):
            person_notes.append(f)

        links = _extract_links(text)
        total_links += len(links)
        for lk in links:
            if not _resolve_target(lk, stems, rel_paths):
                if _is_intentional(lk):
                    dangling_intentional[lk] += 1
                else:
                    dangling_fixable[lk] += 1

    return {
        "notes": notes,
        "sport_counts": sport_counts,
        "total_links": total_links,
        "dangling_intentional": dangling_intentional,
        "dangling_fixable": dangling_fixable,
        "person_notes": person_notes,
    }


def build_graph_health(
    vault_sports_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Scan vault_sports_dir, write _Graph_Health.md, return its path."""
    if vault_sports_dir is None:
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        vault_sports_dir = repo_root / "vault" / "Sports"

    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    data = _scan_vault(vault_sports_dir)
    notes = data["notes"]
    dangling_intentional: Counter = data["dangling_intentional"]
    dangling_fixable: Counter = data["dangling_fixable"]
    person_notes: List[pathlib.Path] = data["person_notes"]
    sport_counts: Dict[str, Dict[str, int]] = data["sport_counts"]
    total_links: int = data["total_links"]

    total_notes = len(notes)
    n_intentional = sum(dangling_intentional.values())
    n_fixable = sum(dangling_fixable.values())
    total_dangling = n_intentional + n_fixable
    total_resolvable = total_links - total_dangling

    person_count = len(person_notes)
    person_verdict = "PASS" if person_count == 0 else f"FAIL ({person_count} person-bearing notes)"

    graph_integrity_verdict = "PASS" if n_fixable == 0 else f"FAIL ({n_fixable} fixable dangling)"

    all_subtypes = sorted({sub for counts in sport_counts.values() for sub in counts})
    sports_sorted = sorted(k for k in sport_counts if k != "_root") + (
        ["_root"] if "_root" in sport_counts else []
    )
    n_sports = len(sports_sorted) - (1 if "_root" in sport_counts else 0)  # exclude meta pseudo-sport

    L: List[str] = [
        "---", "tags: [graph-health, meta]",
        f"generated: {time.strftime('%Y-%m-%d')}", "---", "",
        "# Memory-Graph Health", "",
        "> Auto-generated by `scripts/platformkit/atlas/graph_health.py` — do not hand-edit.",
        "> Re-run `build_graph_health()` to refresh.", "",
        "Up: [[_Hub]]", "", "---", "",
    ]

    L += [
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total notes | **{total_notes}** |",
        f"| Sports covered | {n_sports} |",
        f"| Total wikilinks | {total_links} |",
        f"| Resolvable links | {total_resolvable} |",
        f"| Dangling links (instances) | {total_dangling} |",
        f"| Dangling — intentional cross-vault | {n_intentional} |",
        f"| Dangling — fixable | {n_fixable} |",
        f"| Dangling targets (unique) | {len(dangling_intentional) + len(dangling_fixable)} |",
        f"| GRAPH-INTEGRITY verdict | **{graph_integrity_verdict}** |",
        f"| PERSON-FREE verdict | **{person_verdict}** |",
        "",
    ]

    L += [
        "## Dangling-Link Audit", "",
        f"A link target is **resolvable** if any note in `vault/Sports/**` has a matching "
        f"stem or relative path.  Out of **{total_links}** wikilinks, "
        f"**{total_resolvable}** resolve and **{total_dangling}** are dangling "
        f"({len(dangling_intentional) + len(dangling_fixable)} unique targets).", "",
        "Dangling links are split into two categories:",
        "- **Intentional** — cross-vault shortcuts that legitimately live outside `vault/Sports`"
        " (e.g. `[[Home]]`, `[[MOC-*]]`, `[[Intelligence/...]]`, season-archive notes).",
        "- **Fixable** — slug mismatches, missing targets, or targets that should exist in"
        " `vault/Sports` but don't.  These are the real integrity issues.", "",
    ]

    # --- Intentional cross-vault ---
    L += [
        "### Intentional Cross-Vault Links", "",
        f"**{n_intentional}** instances across {len(dangling_intentional)} unique targets."
        " These are expected and do not affect graph integrity.", "",
    ]
    if dangling_intentional:
        top_i = sorted(dangling_intentional.items(), key=lambda x: -x[1])[:20]
        L += ["| Target | Instances |", "|--------|-----------|"]
        for tgt, cnt in top_i:
            L.append(f"| `{tgt}` | {cnt} |")
        L.append("")
        if len(dangling_intentional) > 20:
            L.append(
                f"> … and {len(dangling_intentional) - 20} more intentional cross-vault targets."
            )
            L.append("")
    else:
        L += ["> No intentional cross-vault links found.", ""]

    # --- Fixable ---
    L += [
        "### Fixable Dangling Links", "",
        f"**{n_fixable}** instances across {len(dangling_fixable)} unique targets."
        " These represent real integrity gaps to address.", "",
    ]
    if dangling_fixable:
        top_f = sorted(dangling_fixable.items(), key=lambda x: -x[1])[:25]
        L += ["| Target | Instances |", "|--------|-----------|"]
        for tgt, cnt in top_f:
            L.append(f"| `{tgt}` | {cnt} |")
        L.append("")
        if len(dangling_fixable) > 25:
            L.append(
                f"> … and {len(dangling_fixable) - 25} more fixable dangling targets."
            )
            L.append("")
        L += [
            f"> **GRAPH-INTEGRITY: {graph_integrity_verdict}** — "
            f"{n_fixable} fixable dangling link(s) remain.", ""
        ]
    else:
        L += ["> All wikilinks resolve or are intentional — no fixable dangling links.", ""]
        L += ["> **GRAPH-INTEGRITY: PASS**", ""]

    L += [
        "## Note-Type Coverage per Sport", "",
        "Counts by immediate subfolder.  `_root` = notes directly inside the sport folder.", "",
    ]
    cols = ["Sport", "Total"] + all_subtypes
    L.append("| " + " | ".join(cols) + " |")
    L.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for sport in sports_sorted:
        counts = sport_counts[sport]
        total_for_sport = sum(counts.values())
        row = [sport, str(total_for_sport)]
        row += [str(counts.get(sub, 0)) for sub in all_subtypes]
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    L += [
        "## Conservative Person-Free Check", "",
        "A note is flagged **only** when it contains a high-confidence individual-name indicator:",
        "- a `[[Players/...]]` wikilink",
        "- a `player_name:` or `display_name:` frontmatter key",
        "- a `## Players`, `## Roster`, or `## Squad` section header", "",
        "No fuzzy surname matching against free text (that over-flags).", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Person-bearing notes | **{person_count}** |",
        f"| Verdict | **{person_verdict}** |", "",
        "> Target: **0** person-bearing notes.  "
        "The graph models style/pattern/market concepts, not individual athletes.", "",
    ]

    # --- footer ---
    L += [
        "---",
        "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{total_notes} notes · {total_links} wikilinks · "
        f"{total_dangling} dangling ({n_intentional} intentional / {n_fixable} fixable) · "
        f"person-bearing: {person_count} · "
        f"GRAPH-INTEGRITY: {graph_integrity_verdict} · "
        f"PERSON-FREE: {person_verdict}*",
    ]

    out_path = vault_sports_dir / _OUT_FILENAME
    return write_note(out_path, "\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    vault_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_graph_health(vault_dir)}")
