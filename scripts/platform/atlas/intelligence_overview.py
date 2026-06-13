"""intelligence_overview.py — Cross-sport intelligence synthesis meta-note.

Reads _Hub.md, _GraphStats.md, _Signals_Hub.md, _Archetype_Taxonomy.md and
per-sport Trends / Playstyles index notes; writes _Intelligence_Overview.md.

Sections: (a) per-sport coverage, (b) cross-sport archetype themes,
(c) edge-search honest readout (markets efficient / all REJECT), (d) 1-line
top style-trend per sport.  All sources are optional — graceful if absent.
No person names; no edge claims beyond the honest verdict tally.  Py 3.9.

    from scripts.platform.atlas.intelligence_overview import build_intelligence_overview
    out = build_intelligence_overview()             # auto-detect vault
    out = build_intelligence_overview(vault_dir)   # explicit path
"""
from __future__ import annotations

import pathlib
import re
import time
from typing import Dict, List, Optional, Tuple

_OUT_FILENAME  = "_Intelligence_Overview.md"
_TABLE_ROW_RE  = re.compile(r"^\s*\|(.+)\|\s*$")
_WIKILINK_RE   = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_HEADING_RE    = re.compile(r"^(#{1,4})\s+(.+)$")
_BOLD_RE       = re.compile(r"\*\*([^*]+)\*\*")


def _read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _collapse_wikilink_pipes(raw: str) -> str:
    """Temporarily replace pipes inside [[target|alias]] so table split is safe."""
    return re.sub(
        r"\[\[([^\]|#]+)\|([^\]]+)\]\]",
        lambda m: f"[[{m.group(1)}|{m.group(2)}]]".replace("|", "\x00"),
        raw,
    )


def _parse_table(text: str) -> List[Dict[str, str]]:
    """Parse markdown table → list of {header: cell} dicts; handles wikilink aliases."""
    rows: List[Dict[str, str]] = []
    headers: List[str] = []
    for raw in text.splitlines():
        safe = _collapse_wikilink_pipes(raw)
        m = _TABLE_ROW_RE.match(safe)
        if not m:
            continue
        cells = [c.strip().replace("\x00", "|") for c in m.group(1).split("|")]
        if all(re.match(r"^[-:\s]+$", c) for c in cells if c):
            continue
        if not headers:
            headers = [c.lower() for c in cells]
            continue
        if len(cells) >= len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def _section_table(text: str, heading_substr: str) -> List[Dict[str, str]]:
    """Extract rows from the first markdown table under *heading_substr* heading."""
    in_sec, buf = False, []
    for raw in text.splitlines():
        h = _HEADING_RE.match(raw)
        if h and heading_substr in h.group(2).lower():
            in_sec = True; continue
        if in_sec:
            if h and h.group(1) == "##": break
            buf.append(raw)
    return _parse_table("\n".join(buf))


def _render_coverage(rows: List[Dict[str, str]]) -> List[str]:
    if not rows:
        return ["_Coverage data unavailable — re-run `build_graph_report()`._", ""]
    dim_keys = [k for k in rows[0] if k != "sport"]
    hdr = "| Sport | " + " | ".join(k.title() for k in dim_keys) + " |"
    sep = "|-------|" + "|".join("-" * max(5, len(k) + 2) for k in dim_keys) + "|"
    lines = [hdr, sep]
    for row in rows:
        lines.append("| " + row.get("sport", "?") + " | "
                     + " | ".join(row.get(k, "0") for k in dim_keys) + " |")
    return lines + [""]


def _parse_taxonomy_themes(text: str) -> List[Tuple[str, int]]:
    """Return (theme_name, link_count) per ## section in _Archetype_Taxonomy.md."""
    themes: List[Tuple[str, int]] = []
    cur, links = None, 0
    for raw in text.splitlines():
        h = _HEADING_RE.match(raw)
        if h and h.group(1) == "##":
            if cur is not None:
                themes.append((cur, links))
            label = h.group(2).strip()
            cur = label if label.lower() not in {"overview", ""} else None
            links = 0
        elif cur:
            links += len(_WIKILINK_RE.findall(raw))
    if cur is not None:
        themes.append((cur, links))
    return themes


def _render_taxonomy(themes: List[Tuple[str, int]], has_file: bool) -> List[str]:
    if not themes:
        return ["_Archetype-theme data unavailable — re-run `build_taxonomy()`._", ""]
    link = "[[_Archetype_Taxonomy]]" if has_file else "_Archetype_Taxonomy"
    lines = [f"Full detail: {link}", "", "| Theme | Archetype Links |",
             "|-------|----------------|"]
    for name, cnt in themes:
        lines.append(f"| {name} | {cnt} |")
    return lines + [""]


def _parse_signals_overview(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for row in _section_table(text, "overview"):
        k = row.get("metric", "").lower().strip()
        v = _BOLD_RE.sub(r"\1", row.get("value", "").strip())
        if k:
            result[k] = v
    return result


def _render_signals(metrics: Dict[str, str], has_file: bool) -> List[str]:
    link = "[[_Signals_Hub]]" if has_file else "_Signals_Hub"
    if not metrics:
        return [f"> No signal data available — re-run `build_signals_hub()`. See {link}.", ""]
    g = metrics.get
    return [
        "> **Honest verdict:** Systematic signal-discovery across all sports via the",
        "> leak-free gate. Markets are efficient. NO edge is claimed.",
        "> REJECT is the honest success criterion.", "",
        f"Full detail: {link}", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Sports with catalogs | {g('sports with catalogs', '?')} |",
        f"| Total candidates tested | {g('total candidates tested', '?')} |",
        f"| REJECT | {g('total reject', '?')} |",
        f"| DEFER | {g('total defer', '?')} |",
        f"| VARIANCE_ONLY | {g('total variance_only', '?')} |",
        f"| SHIP (unverified — not an edge claim) | {g('total ship', '?')} |", "",
    ]


def _sport_trend(sport_id: str, sport_dir: pathlib.Path) -> str:
    """One-line top style-trend for the sport."""
    sid = sport_id.lower()
    if "basketball" in sid or "nba" in sid:
        text = _read(sport_dir / "Trends" / "_Trends_Overview.md")
        if text:
            in_key = False
            for raw in text.splitlines():
                h = _HEADING_RE.match(raw)
                if h and "key trend findings" in h.group(2).lower():
                    in_key = True; continue
                if in_key and h:
                    break
                if in_key and raw.strip().startswith("-"):
                    return _BOLD_RE.sub(r"\1", raw.strip().lstrip("- ").strip())
        return "Trend data unavailable."

    text = _read(sport_dir / "Playstyles" / "_Playstyles_Index.md")
    if not text:
        return "Trend data unavailable."
    rows = _parse_table(text)
    if not rows:
        return "Trend data unavailable."
    sample = rows[0]
    name_key  = next((k for k in sample if k in {"archetype", "scheme"}), None)
    count_key = next((k for k in sample if k in {"teams", "players", "share"}), None)
    if name_key is None or count_key is None:
        return "Trend data unavailable."
    best_name, best_cnt = "", -1
    for row in rows:
        wl = re.search(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]", row.get(name_key, ""))
        name = (wl.group(2) or wl.group(1).split("/")[-1]).replace("_", " ") if wl else row.get(name_key, "?")
        mc = re.match(r"(\d+)", row.get(count_key, "").strip())
        if mc and int(mc.group(1)) > best_cnt:
            best_cnt, best_name = int(mc.group(1)), name
    return f"Largest scheme: {best_name} ({best_cnt} entries)." if best_name else "Trend data unavailable."


def build_intelligence_overview(
    vault_sports_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """Scan vault_sports_dir meta notes and write _Intelligence_Overview.md.

    Source notes (all optional — graceful-skip if absent):
    _Hub.md, _GraphStats.md, _Signals_Hub.md, _Archetype_Taxonomy.md,
    per-sport Trends/_Trends_Overview.md or Playstyles/_Playstyles_Index.md.
    Returns the path of the written file.
    """
    if vault_sports_dir is None:
        vault_sports_dir = pathlib.Path(__file__).resolve().parents[3] / "vault" / "Sports"
    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    stats_path    = vault_sports_dir / "_GraphStats.md"
    signals_path  = vault_sports_dir / "_Signals_Hub.md"
    taxonomy_path = vault_sports_dir / "_Archetype_Taxonomy.md"

    stats_text    = _read(stats_path)
    signals_text  = _read(signals_path)
    taxonomy_text = _read(taxonomy_path)

    sport_dirs = sorted(d for d in vault_sports_dir.iterdir()
                        if d.is_dir() and not d.name.startswith("_"))

    coverage_rows   = _section_table(stats_text, "per-sport note counts") if stats_text else []
    taxonomy_themes = _parse_taxonomy_themes(taxonomy_text) if taxonomy_text else []
    signals_metrics = _parse_signals_overview(signals_text) if signals_text else {}

    total_notes, total_links = "unknown", "unknown"
    if stats_text:
        mn = re.search(r"Total notes\s*\|\s*\*\*(\d[\d,]*)\*\*", stats_text)
        ml = re.search(r"Total \[\[wikilinks\]\]\s*\|\s*(\d[\d,]*)", stats_text)
        if mn: total_notes = mn.group(1)
        if ml: total_links = ml.group(1)

    sport_trends = [(sd.name, _sport_trend(sd.name, sd)) for sd in sport_dirs]
    n = len(sport_dirs)

    L: List[str] = [
        "---", "tags: [intelligence, overview, meta]",
        f"generated: {time.strftime('%Y-%m-%d')}", "---", "",
        "# Intelligence Overview — Multi-Sport Platform Synthesis", "",
        "> Auto-generated by `scripts/platform/atlas/intelligence_overview.py` — do not hand-edit.",
        "> Re-run `build_intelligence_overview()` to refresh.", "",
        "Up: [[_Hub]]", "", "---", "",
        "## At a Glance", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Sports covered | {n} |",
        f"| Total notes | {total_notes} |",
        f"| Total wikilinks | {total_links} |",
        f"| Cross-sport themes | {len(taxonomy_themes)} |", "",
        "---", "", "## (a) Per-Sport Coverage", "",
        "_Note counts by dimension, derived from [[_GraphStats]]._", "",
    ]
    L += _render_coverage(coverage_rows)
    L += [
        "---", "", "## (b) Cross-Sport Archetype Themes", "",
        "_Sport-blind tactical themes from [[_Archetype_Taxonomy]]. No individual entity names._", "",
    ]
    L += _render_taxonomy(taxonomy_themes, taxonomy_path.is_file())
    L += ["---", "", "## (c) Edge-Search Honest Readout", ""]
    L += _render_signals(signals_metrics, signals_path.is_file())
    L += ["---", "", "## (d) Top Style-Trend by Sport", ""]
    if sport_trends:
        L += [f"- **{name}:** {trend}" for name, trend in sport_trends] + [""]
    else:
        L += ["_No per-sport trend data found._", ""]
    L += [
        "---", "", "## Source Notes", "",
        "- [[_Hub]] — multi-sport registry",
        "- [[_GraphStats]] — memory-graph statistics",
        "- [[_Signals_Hub]] — cross-sport signal discovery",
        "- [[_Archetype_Taxonomy]] — cross-sport archetype themes", "",
        "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · {n} sport(s) · {total_notes} notes*",
        "", "_PRIVATE research. No edge claimed._",
    ]

    out_path = vault_sports_dir / _OUT_FILENAME
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys
    vault_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_intelligence_overview(vault_dir)}")
