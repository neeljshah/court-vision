"""brain_transfer.py — PERSON-FREE cross-sport TRANSFER intelligence node.

Reads each sport's already-built ``_WhatWins.md`` + ``Drivers/<slug>.md`` +
``Mechanisms/<slug>.md`` under ``vault/_Organized/<SPORT>/`` (FILENAMES + HEADINGS
only — no per-game data, no pandas, no network), classifies each driver/mechanism
into a generic SHAPE bucket, and writes ``_Index/_Cross_Sport_Transfer.md``: a dense
table mapping SHAPE -> per-sport instances (resolving ``[[wikilinks]]`` to the real
notes) + a short "what transfers" lesson per shape.

COMPLEMENTARY to ``_Cross_Sport_Digest.md`` (which maps ARCHETYPE analogues): this
node maps DRIVERS/MECHANISMS to generic statistical SHAPES, surfacing which
model-family / calibration / distribution-shape lesson TRANSFERS across sports
(e.g. over-dispersion of counts: MLB negbinom runs ~ NBA shooting-margin variance;
regression of unsustainable finishing: soccer SoT-residual ~ tennis serve-hold).

HONEST: an intelligence MAP; markets efficient; calibration is NOT edge; no edge
claimed.  Transfer is the MODEL-FAMILY / CALIBRATION / DISTRIBUTION-SHAPE lesson
ONLY — never outcomes, prices, ROI, or a market advantage.  Base rates differ per
sport and do NOT transfer.

Idempotent; pure filesystem + string ops.
CLI: ``python -m scripts.platformkit.brain_transfer [<organized_root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = (
    "> **Intelligence map; markets efficient; calibration is not edge; no edge "
    "claimed.**  This maps DRIVERS/MECHANISMS to generic statistical SHAPES to "
    "surface which MODEL-FAMILY / CALIBRATION / DISTRIBUTION-SHAPE lesson transfers "
    "across sports.  Only the modelling reasoning transfers; each sport's base rates "
    "differ and do NOT transfer.  No outcomes, prices, or market advantage."
)

# Generic SHAPE taxonomy.  Each shape: (title, lesson).  The lesson is the
# model-family/calibration/distribution-shape that transfers — NEVER an outcome,
# price, ROI, or market-advantage claim.  All text is person-free, no edge tokens.
_SHAPES: List[Tuple[str, str, str]] = [
    ("distribution_shape_variance", "Over-dispersion / tail of counts",
     "Counts cluster (a few events carry most of the swing), so the realized "
     "distribution is FATTER-TAILED than Poisson.  Transfer: model with a "
     "Negative-Binomial / over-dispersed family and calibrate the TAIL, not the "
     "mean; a mean-shift prior gets absorbed by the rating, the SHAPE fix is what "
     "improves Brier/ECE."),
    ("mean_reversion_regression", "Regression of unsustainable form to expectation",
     "Conversion above/below a quality baseline (finishing, serve-hold) is a "
     "high-variance residual that REGRESSES toward the as-of expectation over a "
     "multi-event sample.  Transfer: shrink the residual toward the quality prior "
     "(finishing->xG, hold->serve-rating); it is an over/under calibration signal, "
     "not a predictive lever."),
    ("dominance_vs_variance", "Quality-gap dominance vs near-coin-flip variance",
     "Outcomes split into clear quality-gap routs (low information about a close "
     "game) and tight high-variance contests.  Transfer: condition the spread/margin "
     "DISTRIBUTION SHAPE on the as-of rating gap (widen for a large gap, compress for "
     "a small one) and down-weight blowouts in close-game calibration."),
    ("situational_leverage", "State-conditional / high-leverage swings",
     "Late-game state (relief leverage, comeback, lead management) re-prices the "
     "outcome conditional on game state.  Transfer: model the swing as a "
     "STATE-CONDITIONAL distribution (leverage-weighted, fatigue-/exposure-aware); "
     "the realized swing is DESCRIPTIVE and must never be fed as a feature."),
    ("structural_rating_baseline", "Base-rate game shape anchoring the rating",
     "The 'routine' game is the closest realization of the rating model "
     "(Elo / strength-to-result) without structural distortion.  Transfer: routine "
     "games CALIBRATE the baseline rating-to-probability conversion; every other "
     "shape is a structural adjustment layered on top of this anchor."),
    ("context_conditioning", "A covariate that must condition (never pool) priors",
     "A context covariate (pace, surface, handedness, total-runs regime) changes "
     "WHICH driver decides and how priors should be weighted.  Transfer: fit priors "
     "PER context stratum and never pool across it; the covariate is a conditioning "
     "variable, not a raw additive feature."),
]
_SHAPE_TITLE = {s: t for s, t, _ in _SHAPES}
_SHAPE_LESSON = {s: l for s, _, l in _SHAPES}
_SHAPE_ORDER = [s for s, _, _ in _SHAPES]

# Classification keywords (matched against slug + H1 heading, lowercased).  First
# matching shape (in _SHAPE_ORDER) wins; unmatched notes fall through unclassified.
_KW: Dict[str, List[str]] = {
    # NOTE: a bare "variance" keyword is deliberately NOT here — it collides with
    # "finishing_variance" (a mean-reversion shape).  Match the dispersion/tail/
    # count-cluster tokens specifically instead.
    "distribution_shape_variance": [
        "big_inning", "negbinom", "over-dispers", "overdisper",
        "margin_structure", "margin", "dispers", "total_runs", "tail"],
    "mean_reversion_regression": [
        "finishing", "regress", "reversion", "serve_hold", "serve-hold",
        "bp_conversion", "break-point", "break_point", "conversion", "unsustain"],
    # NOTE: no bare "rout" keyword — it is a substring of "routine" (a baseline
    # shape).  "blowout"/"dominant"/"mismatch" already cover rout structures.
    "dominance_vs_variance": [
        "blowout", "dominant", "dominance", "surface_mismatch", "level gap",
        "mismatch"],
    "situational_leverage": [
        "bullpen", "comeback", "late", "ht_collapse", "ht_comeback", "ht_flip",
        "red_card", "leverage", "swing", "clutch", "broke_late", "collapse",
        "tiebreak", "three_set", "grind"],
    "structural_rating_baseline": [
        "routine", "baseline", "balanced", "serve_held_throughout", "base-rate",
        "base_rate"],
    "context_conditioning": [
        "pace_x", "surface_x", "sp_hand", "_x_", "territorial", "pace",
        "surface", "handedness", "conditioning"],
}

_SPORTS_ORDER = ["NBA", "MLB", "Soccer", "Tennis"]


def _classify(slug: str, heading: str) -> Optional[str]:
    """Map a driver/mechanism (by slug + H1 heading) to a generic SHAPE.

    First shape in canonical order whose keyword appears wins; ``_x_`` interaction
    slugs are nudged toward context-conditioning unless an earlier shape already
    matched.  Returns None when nothing matches (left unclassified, honestly).
    """
    hay = f"{slug} {heading}".lower().replace("-", "_")
    for shape in _SHAPE_ORDER:
        if any(kw.replace("-", "_") in hay for kw in _KW[shape]):
            return shape
    return None


def _h1(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


def _md_notes(d: Path) -> List[Tuple[str, str]]:
    """Return [(slug, h1_heading)] for non-underscore .md files in *d* (sorted)."""
    if not d.is_dir():
        return []
    out: List[Tuple[str, str]] = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix == ".md" and not p.name.startswith("_"):
            try:
                head = _h1(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                head = ""
            out.append((p.stem, head or p.stem.replace("_", " ")))
    return out


def _scan_sport(sdir: Path) -> List[Dict]:
    """Classified instances for one sport: each {shape, kind, slug, heading, link}."""
    sport = sdir.name
    instances: List[Dict] = []
    for kind, sub in (("Driver", "Drivers"), ("Mechanism", "Mechanisms")):
        for slug, heading in _md_notes(sdir / sub):
            shape = _classify(slug, heading)
            if shape is None:
                continue
            # link resolves FROM _Index/ : ../<SPORT>/<sub>/<slug> is the real note.
            link = f"[[{sport}/{sub}/{slug}\\|{heading}]]"
            instances.append({"shape": shape, "kind": kind, "slug": slug,
                              "heading": heading, "link": link})
    return instances


def _render(by_sport: Dict[str, List[Dict]]) -> Tuple[str, int]:
    """Render _Cross_Sport_Transfer.md.  Returns (markdown, n_links)."""
    sports = [sp for sp in _SPORTS_ORDER if sp in by_sport] + \
             sorted(sp for sp in by_sport if sp not in _SPORTS_ORDER)
    # shape -> sport -> [links]
    grid: Dict[str, Dict[str, List[str]]] = {s: {sp: [] for sp in sports}
                                             for s in _SHAPE_ORDER}
    n_links = 0
    for sp in sports:
        for inst in by_sport[sp]:
            grid[inst["shape"]][sp].append(inst["link"])
            n_links += 1
    active = [s for s in _SHAPE_ORDER if any(grid[s][sp] for sp in sports)]

    ls: List[str] = [
        "---", "tags: [organized, cross-sport, transfer, intelligence, person-free]",
        "---", "",
        "# Cross-Sport Transfer Map (drivers/mechanisms -> generic shapes)", "",
        _BANNER, "",
        "Complementary to [[_Cross_Sport_Digest|Cross-Sport Archetype Digest]] "
        "(archetype analogues): this node maps each sport's **drivers and "
        "mechanisms** to a **generic statistical SHAPE**, surfacing which "
        "model-family / calibration / distribution-shape lesson transfers.", "",
        "## Sport hubs", "",
    ]
    for sp in sports:
        ls.append(f"- **{sp}:** [[{sp}/_WhatWins|{sp} What Wins]] · "
                  f"[[{sp}/_Index|{sp} Index]]")
    ls += [
        "", "## Shape -> per-sport instances (resolving links)", "",
        "Each row is one generic shape; cells link to the REAL driver/mechanism "
        "notes that realize it in each sport.", "",
        "| Shape | " + " | ".join(sports) + " |",
        "|-------|" + "|".join(["---"] * len(sports)) + "|",
    ]
    for s in active:
        cells = []
        for sp in sports:
            links = grid[s][sp]
            cells.append("<br>".join(links) if links else "—")
        ls.append(f"| **{_SHAPE_TITLE[s]}** | " + " | ".join(cells) + " |")
    ls += ["", "## What transfers, per shape", ""]
    for s in active:
        ls += [f"### {_SHAPE_TITLE[s]}", "", _SHAPE_LESSON[s], ""]
    ls += [
        "## Reading this honestly", "",
        "- **The SHAPE transfers, the base rates do NOT.** Each sport's event "
        "frequencies differ; only the modelling reasoning carries over.",
        "- **Descriptive, not predictive.** Drivers/mechanisms summarize REALIZED "
        "games; only the leak-free as-of companion may feed a model.",
        "- **Calibration is not edge.** No edge is claimed; markets are efficient.",
        "",
    ]
    return "\n".join(ls) + "\n", n_links


def build_transfer(organized_root: Optional[Path] = None,
                   write: bool = True) -> Dict:
    """Build the cross-sport transfer map from _Organized/<SPORT>/Drivers+Mechanisms.

    Reads filenames + H1 headings only (no per-game data).  Writes
    ``_Index/_Cross_Sport_Transfer.md`` when ``write`` and >=1 link is found.
    Returns {"n_shapes","n_links","by_shape","sports","path",...}.  Idempotent.
    """
    root = (Path(organized_root) if organized_root
            else _REPO_ROOT / "vault" / "_Organized")
    if not root.is_dir():
        return {"organized_root": str(root), "n_shapes": 0, "n_links": 0,
                "by_shape": {}, "sports": [], "path": None,
                "error": f"not found: {root}"}
    by_sport: Dict[str, List[Dict]] = {}
    for sdir in sorted(root.iterdir()):
        if not sdir.is_dir() or sdir.name.startswith("_"):
            continue
        inst = _scan_sport(sdir)
        if inst:
            by_sport[sdir.name] = inst
    md, n_links = _render(by_sport)
    by_shape: Dict[str, Dict[str, int]] = {}
    for sp, insts in by_sport.items():
        for i in insts:
            by_shape.setdefault(i["shape"], {}).setdefault(sp, 0)
            by_shape[i["shape"]][sp] += 1
    path = root / "_Index" / "_Cross_Sport_Transfer.md"
    if write and n_links > 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
    return {
        "organized_root": str(root),
        "n_shapes": len(by_shape),
        "n_links": n_links,
        "by_shape": by_shape,
        "sports": sorted(by_sport.keys()),
        "path": str(path) if (write and n_links > 0) else None,
        "md": md,
        "note": ("intelligence map; markets efficient; calibration is not edge; "
                 "no edge claimed; SHAPE transfers, base rates do not"),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_transfer(organized_root=Path(root_arg) if root_arg else None,
                         write=True)
    if "--json" in argv:
        print(json.dumps({k: v for k, v in rep.items() if k != "md"},
                         indent=2, default=str))
        return 0
    print(f"organized_root : {rep['organized_root']}")
    if "error" in rep:
        print(f"  ERROR: {rep['error']}")
        return 1
    print(f"sports         : {', '.join(rep['sports'])}")
    print(f"shapes / links : {rep['n_shapes']} / {rep['n_links']}")
    for shape, spc in rep["by_shape"].items():
        print(f"  {_SHAPE_TITLE.get(shape, shape):<40} "
              f"{', '.join(f'{sp}:{n}' for sp, n in spc.items())}")
    print(f"path           : {rep['path']}")
    print(f"note           : {rep['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
