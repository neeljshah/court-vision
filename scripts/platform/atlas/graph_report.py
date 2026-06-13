"""graph_report.py — Obsidian memory-graph stats meta-generator.

Scans vault/Sports/ and writes vault/Sports/_GraphStats.md with:
  per-sport note counts by subfolder type, link density (wikilinks /
  avg / distinct / dangling), top-tags histogram, and freshness mtime.

Programmatic::

    from scripts.platform.atlas.graph_report import build_graph_report
    out = build_graph_report()          # default repo vault path
    out = build_graph_report(my_dir)    # custom vault/Sports dir
"""

from __future__ import annotations

import pathlib
import re
import time
from collections import Counter
from typing import Dict, List, Tuple

# Subfolder name → display label
_KNOWN_TYPES: Dict[str, str] = {
    "players": "Players", "teams": "Teams", "matchups": "Matchups",
    "leagues": "Leagues", "surfaces": "Surfaces",
    "tournaments": "Tournaments", "seasons": "Seasons", "index": "Index",
}

_WIKILINK_RE    = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_TAG_RE         = re.compile(r"(?m)^  - ([^\n]+)")
_TAGS_BLOCK_RE  = re.compile(r"tags:\s*\n((?:  - [^\n]+\n)+)", re.MULTILINE)
_OUT_FILENAME   = "_GraphStats.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _note_type(dir_parts: Tuple[str, ...]) -> str:
    """Map directory parts (filename already stripped) to a type label."""
    if not dir_parts:
        return "Index"
    return _KNOWN_TYPES.get(dir_parts[0].lower(), dir_parts[0].capitalize())


def _fmt_mtime(ts: float) -> str:
    return "unknown" if ts == 0.0 else time.strftime("%Y-%m-%d", time.localtime(ts))


def _extract_wikilinks(text: str) -> List[str]:
    return [m.group(1).strip() for m in _WIKILINK_RE.finditer(text)]


def _extract_tags(text: str) -> List[str]:
    tags: List[str] = []
    for block in _TAGS_BLOCK_RE.finditer(text):
        tags.extend(m.group(1).strip() for m in _TAG_RE.finditer(block.group(1)))
    return tags


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def _scan_sport(sport_dir: pathlib.Path) -> dict:
    """Return stats dict for one sport directory."""
    type_counts: Counter = Counter()
    all_links: List[str] = []
    all_tags:  List[str] = []
    newest_mtime = 0.0
    note_stems: set = set()

    for md in sorted(sport_dir.rglob("*.md")):
        note_stems.add(md.stem)
        try:
            mt = md.stat().st_mtime
        except OSError:
            mt = 0.0
        if mt > newest_mtime:
            newest_mtime = mt

        dir_parts = md.relative_to(sport_dir).parts[:-1]
        type_counts[_note_type(dir_parts)] += 1

        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        all_links.extend(_extract_wikilinks(text))
        all_tags.extend(_extract_tags(text))

    def _norm(t: str) -> str:
        n = t.split("/")[-1]
        return n[:-3] if n.endswith(".md") else n

    distinct_targets = {_norm(t) for t in all_links}
    return {
        "note_count":       len(note_stems),
        "type_counts":      dict(type_counts),
        "total_links":      len(all_links),
        "distinct_targets": len(distinct_targets),
        "dangling_count":   len(distinct_targets - note_stems),
        "tag_counter":      Counter(all_tags),
        "newest_mtime":     newest_mtime,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_graph_report(
    vault_sports_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Scan vault_sports_dir, write _GraphStats.md, return its path."""
    if vault_sports_dir is None:
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        vault_sports_dir = repo_root / "vault" / "Sports"

    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    sport_dirs = sorted(
        d for d in vault_sports_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )

    sport_stats: Dict[str, dict] = {}
    global_tags: Counter = Counter()
    grand_total = grand_links = grand_dangling = 0

    for sd in sport_dirs:
        stats = _scan_sport(sd)
        sport_stats[sd.name] = stats
        global_tags.update(stats["tag_counter"])
        grand_total   += stats["note_count"]
        grand_links   += stats["total_links"]
        grand_dangling += stats["dangling_count"]

    # Collect distinct type columns across all sports
    all_types = sorted({t for s in sport_stats.values() for t in s["type_counts"]})

    # -----------------------------------------------------------------------
    # Render
    # -----------------------------------------------------------------------
    L: List[str] = []

    L += [
        "---",
        "tags: [memory-graph, stats, meta]",
        f"generated: {time.strftime('%Y-%m-%d')}",
        "---", "",
        "# Memory-Graph Stats", "",
        "> Auto-generated by `scripts/platform/atlas/graph_report.py` — do not hand-edit.",
        "> Re-run `build_graph_report()` to refresh.", "",
        "Up: [[_Hub]]", "", "---", "",
        "## Overview", "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total notes | **{grand_total}** |",
        f"| Sports covered | {len(sport_dirs)} |",
        f"| Total [[wikilinks]] | {grand_links} |",
        f"| Dangling links (total) | {grand_dangling} |", "",
    ]

    # Per-sport note counts
    L.append("## Per-Sport Note Counts")
    L.append("")
    cols = ["Sport", "Total"] + all_types
    L.append("| " + " | ".join(cols) + " |")
    L.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for sport, stats in sport_stats.items():
        row = [sport, str(stats["note_count"])]
        row += [str(stats["type_counts"].get(t, 0)) for t in all_types]
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    # Link density
    L += [
        "## Link Density", "",
        "| Sport | Total Links | Avg Links/Note | Distinct Targets | Dangling |",
        "|-------|-------------|----------------|-----------------|---------|",
    ]
    for sport, stats in sport_stats.items():
        n = stats["note_count"]
        avg = f"{stats['total_links'] / n:.1f}" if n else "0.0"
        L.append(
            f"| {sport} | {stats['total_links']} | {avg}"
            f" | {stats['distinct_targets']} | {stats['dangling_count']} |"
        )
    L.append("")

    # Freshness
    L += ["## Freshness (most-recent note mtime per sport)", "",
          "| Sport | Latest Note Modified |", "|-------|---------------------|"]
    for sport, stats in sport_stats.items():
        L.append(f"| {sport} | {_fmt_mtime(stats['newest_mtime'])} |")
    L.append("")

    # Top tags
    L += ["## Top Tags (across all sports)", "", "| Tag | Count |", "|-----|-------|"]
    for tag, cnt in global_tags.most_common(30):
        L.append(f"| `{tag}` | {cnt} |")
    L.append("")

    L += [
        "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{grand_total} notes · {grand_links} links · {grand_dangling} dangling*",
    ]

    out_path = vault_sports_dir / _OUT_FILENAME
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys
    vault_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_graph_report(vault_dir)}")
