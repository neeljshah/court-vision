"""scripts.platformkit.atlas.world_model — Cross-sport World Model synthesis note.

Emits vault/Sports/_World_Model.md: computed summary of what the platform KNOWS
across all sport domains.  Sections: (a) core empirical thesis — market efficiency
proven across 4 sports/3 market shapes; (b) per-sport breakdown — shape, features,
verdict; (c) universal vs sport-specific — kernel/adapter split; (d) genuine
frontiers — DATA/HUMAN-BLOCKED; (e) graph links.

HONEST DISCIPLINE: markets are EFFICIENT; every tested signal REJECTS.  REJECT is
the honest success criterion.  No durable edge claimed.
PERSON-FREE: teams/leagues/styles only.  Py 3.9.  F5-clean (stdlib only).
"""
from __future__ import annotations

import pathlib
import re
import time
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import frontmatter, write_note

_OUT_FILENAME = "_World_Model.md"

# (sport_id, display, market_shape, base_features, model_family)
_SPORT_DESCRIPTORS: List[Tuple[str, str, str, str, str]] = [
    ("tennis_atp", "Tennis (ATP)", "Head-to-head ML — binary win/loss",
     "elo_diff, surf_diff, best_of, rest_days_a, rest_days_b",
     "Blended Elo → calibrated win probability"),
    ("soccer_fd",  "Soccer (FD)",  "O/U 2.5 goals — binary total",
     "lam_home, lam_away, lam_total, rest_days_home, rest_days_away",
     "Poisson scoring model → P(total > 2.5)"),
    ("mlb_sbro",   "MLB (SBRO)",   "Home/away ML — binary home-win",
     "elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate",
     "Elo with home-field adjustment → calibrated win probability"),
    ("basketball_nba", "Basketball (NBA)", "Player props + game totals",
     "MC sim signals, on-court ratings, usage, pace, defense",
     "Monte Carlo possession sim + 7-engine ensemble"),
]

_SPORT_VERDICTS: Dict[str, str] = {
    "tennis_atp":     "All candidates REJECT — Pinnacle closes price every tested transform",
    "soccer_fd":      "All candidates REJECT — market prices Poisson λ and rest fully",
    "mlb_sbro":       "All candidates REJECT — Elo/H2H residuals priced by sharp closers",
    "basketball_nba": "All pregame features at data ceiling; AST gated (sole exception)",
}

# (frontier_title, one-line description)
_FRONTIERS: List[Tuple[str, str]] = [
    ("SGP / correlation pricing",
     "Real SGP leg-correlation prices unavailable without a live book feed."),
    ("In-game live re-pricing",
     "Requires real-time odds feed + live PBP; corpus with captured prices arrives Oct 2026."),
    ("Freshness / CLV",
     "Openers carry ~58% ATS ceiling; model captures none — uses same-day public info only."),
    ("Richer data substrate",
     "Shot-zone/on-court-5/defender features are next NBA ceiling-raiser; CDN PBP is HUMAN-BLOCKED."),
    ("Additional sport corpora",
     "Fifth sport = ADAPTER-ONLY effort; bottleneck is sourcing a clean time-stamped odds corpus."),
    ("Multi-season joint signals",
     "JOINT signals need ≥2 independent seasonal corpora; single-season results are artifacts."),
]

_TOTAL_NOTES_RE = re.compile(r"Total notes\s*\|\s*\*\*(\d[\d,]*)\*\*")
# graph_report.py writes "Total wikilinks | <n>" (plain, no markup).
# Accept both plain and the legacy [[wikilinks]] form for backward compat.
_TOTAL_LINKS_RE = re.compile(r"Total (?:\[\[)?wikilinks(?:\]\])?\s*\|\s*\*?(\d[\d,]*)\*?")
_REJECT_RE      = re.compile(r"Total REJECT\s*\|\s*(\d+)")
_CANDIDATES_RE  = re.compile(r"Total candidates tested\s*\|\s*\*\*(\d+)\*\*")


def _read(path: pathlib.Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parse_stats(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, pat in (("total_notes", _TOTAL_NOTES_RE), ("total_links", _TOTAL_LINKS_RE)):
        m = pat.search(text)
        if m:
            out[key] = m.group(1)
    return out


def _parse_signals(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, pat in (("total_candidates", _CANDIDATES_RE), ("total_reject", _REJECT_RE)):
        m = pat.search(text)
        if m:
            out[key] = m.group(1)
    return out


def _count_sport_dirs(d: pathlib.Path) -> int:
    try:
        return sum(1 for p in d.iterdir() if p.is_dir() and not p.name.startswith("_"))
    except OSError:
        return len(_SPORT_DESCRIPTORS)


def _section_thesis() -> List[str]:
    return [
        "## (a) Core Empirical Thesis", "",
        "> **The market is efficient.** Across 4 sports and 3 distinct market shapes,",
        "> every leak-free out-of-sample signal candidate REJECTS or DEFERs through",
        "> the REAL gate (`src.loop.gate.evaluate`). No durable pregame edge is claimed.",
        "> REJECT is the honest success criterion — the gate works, the process is clean.", "",
        "**3 market shapes tested — all EFFICIENT:**", "",
        "| Market shape | Sports | Verdict |",
        "|---|---|---|",
        "| Binary ML — Elo win probability | Tennis, MLB | All candidates REJECT |",
        "| Binary O/U — Poisson goal total | Soccer | All candidates REJECT |",
        "| Player props + game total | NBA | Features at data ceiling |",
        "",
        "- Public information (Elo, rest, pace, H2H, totals λ) is **already priced**.",
        "- Single-fold lifts are artifacts — multi-fold walk-forward + independent corpus",
        "  required before any edge claim.",
        "- NBA AST shows a small durable gate (≈+4–5% gated walk-forward) — the sole",
        "  exception, absent in playoffs; cross-sport generalisation unproven.",
        "",
    ]


def _section_per_sport() -> List[str]:
    L: List[str] = [
        "## (b) Per-Sport Breakdown", "",
        "Each sport is an ADAPTER-ONLY extension of the sport-blind kernel.",
        "Leak-freeness proven via truncation-invariance in each domain proof.", "",
        "| Sport | Market Shape | Base Features | Model Family | Honest Verdict |",
        "|---|---|---|---|---|",
    ]
    for sid, display, shape, feats, model in _SPORT_DESCRIPTORS:
        verdict = _SPORT_VERDICTS.get(sid, "REJECT")
        L.append(f"| {display} | {shape} | `{feats}` | {model} | {verdict} |")
    L += [
        "",
        "_All candidates are pure transforms of base columns only — no leakage, no future info._",
        "",
    ]
    return L


def _section_universal() -> List[str]:
    return [
        "## (c) Universal vs Sport-Specific", "",
        "**Universal (the kernel):** gate harness; signal contract (frozen base cols);",
        "calibration standard (Brier vs devigged close); REJECT/DEFER/SHIP taxonomy;",
        "person-free Obsidian graph (playstyles + archetypes + team tactics — no athletes).", "",
        "**Sport-specific (each adapter):** feature extraction; base column contract;",
        "market shape + target variable; playstyle taxonomy; corpus span.", "",
        "**Adding a fifth sport:** adapter-only — zero `kernel/` or `src/` changes.",
        "Pattern proven across 4 sports.  Bottleneck = clean odds corpus, not code.", "",
    ]


def _section_frontiers() -> List[str]:
    L: List[str] = [
        "## (d) What Would Change the Verdict — Genuine Frontiers", "",
        "> All items below are DATA-BLOCKED or HUMAN-BLOCKED, not engineering gaps.", "",
        "| Frontier | Why blocked |",
        "|---|---|",
    ]
    for title, desc in _FRONTIERS:
        L.append(f"| **{title}** | {desc} |")
    L += [
        "",
        "**What will NOT change the verdict:** more model architectures on the same",
        "public features; longer training windows; retuning without a second corpus.", "",
    ]
    return L


def _section_graph(sm: Dict[str, str], sg: Dict[str, str], n: int) -> List[str]:
    return [
        "## (e) Graph Summary", "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Sport domains in graph | {n} |",
        f"| Total notes | {sm.get('total_notes', 'unknown')} |",
        f"| Total wikilinks | {sm.get('total_links', 'unknown')} |",
        f"| Signal candidates evaluated | {sg.get('total_candidates', 'unknown')} |",
        f"| Signal REJECT count | {sg.get('total_reject', 'unknown')} |",
        "| Durable edge claims | 0 (NBA AST gated — not a cross-sport edge) |",
        "",
    ]


def _section_links() -> List[str]:
    return [
        "## Source Notes", "",
        "- [[_Hub]] — multi-sport registry (Up)",
        "- [[_GraphStats]] — memory-graph statistics",
        "- [[_Signals_Hub]] — cross-sport signal-discovery aggregator",
        "- [[_Intelligence_Overview]] — per-sport coverage + tactical dimensions",
        "- [[_Archetype_Taxonomy]] — cross-sport playstyle / archetype themes",
        "",
    ]


def build_world_model(
    vault_sports_dir: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """Write vault/Sports/_World_Model.md; return its path.

    Synthesises what the platform KNOWS across all sport domains.  All meta-note
    sources are optional — computed stats used when available, graceful-skip otherwise.
    No edge claimed; REJECT = honest success criterion.
    """
    if vault_sports_dir is None:
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        vault_sports_dir = repo_root / "vault" / "Sports"
    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    stats_text   = _read(vault_sports_dir / "_GraphStats.md")
    signals_text = _read(vault_sports_dir / "_Signals_Hub.md")
    sm = _parse_stats(stats_text)     if stats_text   else {}
    sg = _parse_signals(signals_text) if signals_text else {}
    n  = _count_sport_dirs(vault_sports_dir)

    fm = frontmatter({
        "tags":      ["world-model", "meta", "cross-sport", "honest"],
        "generated": time.strftime("%Y-%m-%d"),
        "sports":    len(_SPORT_DESCRIPTORS),
    })
    L: List[str] = [
        fm, "",
        "# World Model — Cross-Sport Platform Knowledge Synthesis", "",
        "> **Auto-generated** by `scripts/platformkit/atlas/world_model.py`",
        "> — do not hand-edit.  Re-run `build_world_model()` to refresh.", "",
        "> **Honest framing:** this note summarises what the platform KNOWS.",
        "> The validated finding is that markets are efficient and every tested signal",
        "> REJECTS.  No durable betting edge is claimed.  No edge claimed.", "",
        "Up: [[_Hub]]", "",
        "---", "",
    ]
    L += _section_thesis()
    L += ["---", ""]
    L += _section_per_sport()
    L += ["---", ""]
    L += _section_universal()
    L += ["---", ""]
    L += _section_frontiers()
    L += ["---", ""]
    L += _section_graph(sm, sg, n)
    L += ["---", ""]
    L += _section_links()
    L += [
        "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{len(_SPORT_DESCRIPTORS)} sports · person-free · no edge claimed*", "",
        "_PRIVATE research. No edge claimed. REJECT = honest success._",
    ]
    return write_note(vault_sports_dir / _OUT_FILENAME, "\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    vault_arg = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_world_model(vault_arg)}")
