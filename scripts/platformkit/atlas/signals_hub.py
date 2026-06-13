"""signals_hub.py — Cross-sport signal-discovery hub aggregator.

Scans vault/Sports/<Sport>/Signals/_Catalog.md (base candidates) AND
_Catalog_Joint.md (joint/interaction candidates) per sport, parses each
verdict table, and writes vault/Sports/_Signals_Hub.md.  Sports missing
a catalog are silently skipped (graceful-skip for in-flight sibling agents).

    from scripts.platformkit.atlas.signals_hub import build_signals_hub
    out = build_signals_hub()       # default repo vault/Sports path
    out = build_signals_hub(path)   # custom vault/Sports dir
"""

from __future__ import annotations

import pathlib
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from scripts.platformkit.atlas.obsidian_emit import write_note

_CATALOG_REL       = pathlib.Path("Signals") / "_Catalog.md"
_CATALOG_JOINT_REL = pathlib.Path("Signals") / "_Catalog_Joint.md"
_OUT_FILENAME      = "_Signals_Hub.md"
_TABLE_ROW_RE      = re.compile(r"^\s*\|(.+)\|\s*$")


@dataclass
class SportSignalStats:
    sport: str
    catalog_path: pathlib.Path
    candidates: int = 0
    base_candidates: int = 0
    joint_candidates: int = 0
    reject: int = 0
    defer: int = 0
    variance_only: int = 0
    ship: int = 0
    signals: List[Dict[str, str]] = field(default_factory=list)


def _parse_catalog(catalog_path: pathlib.Path) -> Optional[SportSignalStats]:
    """Parse a single _Catalog.md or _Catalog_Joint.md verdict table.
    Returns None on unrecoverable error or if no rows found."""
    try:
        text = catalog_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    sport = catalog_path.parts[-3]  # …/<Sport>/Signals/_Catalog*.md
    stats = SportSignalStats(sport=sport, catalog_path=catalog_path)
    in_section = saw_header = False
    signal_col_idx = actual_col_idx = -1

    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^#+\s+Verdict table", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^#+\s", line):
            in_section = False
            continue
        if not in_section:
            continue
        m = _TABLE_ROW_RE.match(raw)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if all(re.match(r"^[-:\s]+$", c) for c in cells if c):
            continue  # separator row
        if not saw_header:
            hdr = [c.lower() for c in cells]
            signal_col_idx = hdr.index("signal") if "signal" in hdr else 0
            if "actual" in hdr:
                actual_col_idx = hdr.index("actual")
            elif "verdict" in hdr:
                actual_col_idx = hdr.index("verdict")
            else:
                actual_col_idx = 2
            saw_header = True
            continue
        if len(cells) <= max(signal_col_idx, actual_col_idx):
            continue
        sig = cells[signal_col_idx]
        verdict = cells[actual_col_idx].upper()
        if not sig:
            continue
        stats.candidates += 1
        stats.signals.append({"signal": sig, "actual": verdict})
        if "REJECT" in verdict:
            stats.reject += 1
        elif "DEFER" in verdict:
            stats.defer += 1
        elif "VARIANCE_ONLY" in verdict:
            stats.variance_only += 1
        elif "SHIP" in verdict:
            stats.ship += 1

    return stats if stats.candidates > 0 or saw_header else None


def _parse_sport(sport_dir: pathlib.Path) -> Optional[SportSignalStats]:
    """Parse both _Catalog.md and _Catalog_Joint.md for a sport dir.

    Returns a merged SportSignalStats if at least one catalog file exists and
    contains rows.  Gracefully skips whichever file is absent.
    """
    base_path  = sport_dir / _CATALOG_REL
    joint_path = sport_dir / _CATALOG_JOINT_REL

    base_stats  = _parse_catalog(base_path)  if base_path.is_file()  else None
    joint_stats = _parse_catalog(joint_path) if joint_path.is_file() else None

    if base_stats is None and joint_stats is None:
        return None

    sport = sport_dir.name
    merged = SportSignalStats(
        sport=sport,
        catalog_path=base_path if base_path.is_file() else joint_path,
    )
    if base_stats is not None:
        merged.base_candidates = base_stats.candidates
        merged.candidates      += base_stats.candidates
        merged.reject          += base_stats.reject
        merged.defer           += base_stats.defer
        merged.variance_only   += base_stats.variance_only
        merged.ship            += base_stats.ship
        merged.signals         += base_stats.signals
    if joint_stats is not None:
        merged.joint_candidates = joint_stats.candidates
        merged.candidates       += joint_stats.candidates
        merged.reject           += joint_stats.reject
        merged.defer            += joint_stats.defer
        merged.variance_only    += joint_stats.variance_only
        merged.ship             += joint_stats.ship
        merged.signals          += joint_stats.signals

    return merged if merged.candidates > 0 else None


def build_signals_hub(
    vault_sports_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """Scan vault_sports_dir for per-sport signal catalogs and write
    vault/Sports/_Signals_Hub.md.  Returns the path of the written file.

    Both _Catalog.md (base signals) and _Catalog_Joint.md (joint/interaction
    signals) are scanned per sport and aggregated.  Sports missing both files
    are silently skipped (graceful-skip).
    """
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
    sport_stats: List[SportSignalStats] = []
    ships_present = False
    for sd in sport_dirs:
        parsed = _parse_sport(sd)
        if parsed is None:
            continue
        sport_stats.append(parsed)
        if parsed.ship > 0:
            ships_present = True

    grand_candidates    = sum(s.candidates     for s in sport_stats)
    grand_base          = sum(s.base_candidates  for s in sport_stats)
    grand_joint         = sum(s.joint_candidates for s in sport_stats)
    grand_reject        = sum(s.reject           for s in sport_stats)
    grand_defer         = sum(s.defer            for s in sport_stats)
    grand_variance_only = sum(s.variance_only    for s in sport_stats)
    grand_ship          = sum(s.ship             for s in sport_stats)

    L: List[str] = []
    L += [
        "---",
        "tags: [signals, edge-discovery, meta, honest]",
        f"generated: {time.strftime('%Y-%m-%d')}",
        "---",
        "",
    ]

    L += [
        "# Signals Hub — Cross-Sport Signal Discovery Summary",
        "",
        "> **Honest framing:** Systematic signal-discovery across all sports via the REAL",
        "> leak-free gate. Candidate signals are pure transforms of proof-validated leak-free",
        "> features (base signals) and ≥2-column algebraic interactions (joint signals).",
        "> EXPECTED and OBSERVED verdicts are REJECT/DEFER — markets are efficient.",
        "> NO edge is claimed; the REJECT is the honest success criterion.",
        "",
        "> Auto-generated by `scripts/platformkit/atlas/signals_hub.py` — do not hand-edit.",
        "> Re-run `build_signals_hub()` to refresh.",
        "",
        "Up: [[_Hub]]",
        "",
        "---",
        "",
    ]

    if ships_present:
        L += [
            "## ⚠ Unverified Candidate Warning",
            "",
            "One or more sports report a SHIP verdict. **A SHIP at this stage is an",
            "unverified candidate, not a claimed edge.** Single-fold lifts are artifacts",
            "(see feedback file `feedback_single_fold_lifts_are_artifacts.md`). The signal",
            "requires: multi-fold walk-forward, independent corpus, CLV grading, and",
            "cross-season hold-out BEFORE any edge claim is permitted.",
            "",
            "---",
            "",
        ]

    L += [
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Sports with catalogs | **{len(sport_stats)}** |",
        f"| Total candidates tested | **{grand_candidates}** |",
        f"| — Base (single-feature) | {grand_base} |",
        f"| — Joint (interaction) | {grand_joint} |",
        f"| Total REJECT | {grand_reject} |",
        f"| Total DEFER | {grand_defer} |",
        f"| Total VARIANCE_ONLY | {grand_variance_only} |",
        f"| Total SHIP | {grand_ship} |",
        "",
    ]

    L += [
        "## Per-Sport Signal Counts",
        "",
        "| Sport | #Base | #Joint | #Total | #REJECT | #DEFER | #VARIANCE_ONLY | #SHIP | Catalog |",
        "|-------|-------|--------|--------|---------|--------|----------------|-------|---------|",
    ]

    def _ship_cell(n: int) -> str:
        return f"**{n} — ARTIFACT-HUNT REQUIRED**" if n > 0 else str(n)

    for s in sport_stats:
        L.append(
            f"| {s.sport} | {s.base_candidates} | {s.joint_candidates}"
            f" | {s.candidates} | {s.reject} | {s.defer}"
            f" | {s.variance_only} | {_ship_cell(s.ship)}"
            f" | [[{s.sport}/Signals/_Catalog]] |"
        )
    L += [
        f"| **TOTAL** | **{grand_base}** | **{grand_joint}**"
        f" | **{grand_candidates}** | **{grand_reject}** | **{grand_defer}**"
        f" | **{grand_variance_only}** | {_ship_cell(grand_ship)} | — |",
        "",
    ]

    if not sport_stats:
        L += [
            "> No per-sport signal catalogs found yet. Re-run after sibling agents",
            "> write their `vault/Sports/<Sport>/Signals/_Catalog.md`.",
            "",
        ]

    L += ["---", "", "## Catalog Links", ""]
    if sport_stats:
        for s in sport_stats:
            L.append(f"- [[{s.sport}/Signals/_Catalog]] — {s.sport} base signal catalog")
            if s.joint_candidates > 0:
                L.append(f"- [[{s.sport}/Signals/_Catalog_Joint]] — {s.sport} joint/interaction signal catalog")
    else:
        L.append("_No catalogs present yet._")

    L += [
        "",
        "---",
        "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{len(sport_stats)} sport(s) · {grand_candidates} candidate(s) "
        f"({grand_base} base + {grand_joint} joint)*",
        "",
        "_PRIVATE research. No edge claimed. REJECT = honest success._",
    ]

    out_path = vault_sports_dir / _OUT_FILENAME
    return write_note(out_path, "\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    vault_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_signals_hub(vault_dir)}")
