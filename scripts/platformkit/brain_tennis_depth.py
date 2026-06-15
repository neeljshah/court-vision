"""brain_tennis_depth.py — serve/return STYLE ARCHETYPE mapping for Tennis.

Pools p1+p2 values from the leak-free as-of parquet
(data/domains/tennis/asof_features.parquet) and maps tertile thresholds
onto four person-free canonical serve/return style archetypes:
  Big Server | First-Strike / All-Court | Counterpuncher / Returner | Grinder / Baseliner

Writes vault/_Organized/Tennis/_Serve_Return_Archetypes.md with per-archetype
stat-signature (actual computed thresholds), mechanism one-liner, corpus share,
and wikilink to the matching Archetypes/ note.

DISTINCT from brain_form_profiles (raw percentile-band distributions): this module
MAPS signatures to style CONCEPTS — the semantic layer above raw bands.

Honest: corpus-distribution constructs, not validated clusters; NOT a per-match
signal and NOT a bet; markets efficient; calibration is not edge.

CLI: ``python -m scripts.platformkit.brain_tennis_depth [<root>] [--json]``
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
    "> **Descriptive intelligence; markets efficient; calibration is not edge; "
    "no edge claimed.** Corpus serve/return distributions mapped to style concepts — "
    "NOT a per-match signal and NOT a bet. Styles are corpus-distribution constructs, "
    "not validated clusters or causal explanations."
)
_NOTE = (
    "descriptive intelligence; markets efficient; calibration is not edge; "
    "no edge claimed; serve/return style archetypes are corpus-distribution constructs, "
    "not validated clusters and not a per-match signal"
)
_PARQUET = "data/domains/tennis/asof_features.parquet"
_SMALL_N = 50

_METRICS: List[Tuple[str, List[str]]] = [
    ("ace_rate", ["p1_ace_rate_asof", "p2_ace_rate_asof"]),
    ("1st_in",   ["p1_1st_in_asof",   "p2_1st_in_asof"]),
    ("1st_win",  ["p1_1st_win_asof",   "p2_1st_win_asof"]),
    ("2nd_win",  ["p1_2nd_win_asof",   "p2_2nd_win_asof"]),
    ("bp_saved", ["p1_bp_saved_asof",  "p2_bp_saved_asof"]),
]

# bands: metric -> ("high"|"low", percentile_as_float)
_STYLE_SPECS = [
    {"name": "Big Server", "wikilink": "Archetypes/Fast_Court_Big_Server",
     "bands": {"ace_rate": ("high", 0.67), "1st_win": ("high", 0.67)},
     "mechanism": ("Dominates points with serve pace and placement; holds at a high clip "
                   "without relying on rally construction.")},
    {"name": "First-Strike / All-Court", "wikilink": "Archetypes/All_Court_Baseliner",
     "bands": {"1st_in": ("high", 0.67), "1st_win": ("high", 0.67)},
     "mechanism": ("Combines first-serve consistency with high first-ball winning rate; "
                   "controls rallies from the opening shot.")},
    {"name": "Counterpuncher / Returner", "wikilink": "Archetypes/Clay_Court_Specialist",
     "bands": {"bp_saved": ("high", 0.67), "2nd_win": ("high", 0.67),
               "ace_rate": ("low", 0.33)},
     "mechanism": ("Wins by forcing opponents to earn every break chance; neutralises "
                   "big serves with patience and second-serve resilience.")},
    {"name": "Grinder / Baseliner", "wikilink": "Archetypes/Hard_Court_Specialist",
     "bands": {"2nd_win": ("high", 0.67), "1st_in": ("high", 0.50),
               "ace_rate": ("low", 0.50)},
     "mechanism": ("Sustains long rallies through second-serve reliability and consistent "
                   "first-serve depth; wins points via attrition rather than outright pace.")},
]


def _pool_metric(df, cols: List[str]):
    """Pool columns into one numeric Series, NaN-dropped (lazy pandas import)."""
    import pandas as pd  # noqa: PLC0415
    parts = [pd.to_numeric(df[c], errors="coerce") for c in cols if c in df.columns]
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, ignore_index=True).dropna()


def _compute_thresholds(df) -> Dict[str, Dict]:
    """Tertile (p33/p50/p67) thresholds per metric, pooled across p1+p2."""
    out: Dict[str, Dict] = {}
    for metric, cols in _METRICS:
        s = _pool_metric(df, cols)
        if len(s) < 2:
            continue
        qs = s.quantile([0.33, 0.50, 0.67])
        out[metric] = {"p33": round(float(qs[0.33]), 5),
                       "p50": round(float(qs[0.50]), 5),
                       "p67": round(float(qs[0.67]), 5),
                       "n":   int(len(s))}
    return out


def _style_share(df, spec: Dict, thresholds: Dict[str, Dict]) -> Optional[float]:
    """Fraction of pooled rows meeting ALL defining band conditions."""
    import pandas as pd  # noqa: PLC0415
    conditions = []
    for metric, (direction, pct) in spec["bands"].items():
        if metric not in thresholds:
            return None
        tkey = f"p{int(round(pct * 100))}"
        thr = thresholds[metric].get(tkey)
        if thr is None:
            return None
        cols = next((c for m, c in _METRICS if m == metric), [])
        parts = [pd.to_numeric(df[c], errors="coerce") for c in cols if c in df.columns]
        if not parts:
            return None
        s = pd.concat(parts, ignore_index=True)
        conditions.append(s >= thr if direction == "high" else s <= thr)
    if not conditions:
        return None
    combined = conditions[0]
    for cond in conditions[1:]:
        n = min(len(combined), len(cond))
        combined = combined.iloc[:n] & cond.iloc[:n]
    total = int(combined.notna().sum())
    return round(float(combined.sum()) / max(total, 1), 4) if total > 0 else None


def _thr_str(metric: str, direction: str, pct: float, thr: Dict[str, Dict]) -> str:
    """One-line threshold expression with actual computed value."""
    if metric not in thr:
        return f"{metric} ({direction} band — threshold unavailable)"
    tkey = f"p{int(round(pct * 100))}"
    val = thr[metric].get(tkey, "?")
    op = ">=" if direction == "high" else "<="
    return f"`{metric}` {op} {val:.4f} (p{int(round(pct*100))} threshold)"


def _render(thresholds: Dict[str, Dict], styles: List[Dict], n_rows: int) -> str:
    small = n_rows < _SMALL_N
    n_note = (f"**n={n_rows} pooled player-match values** — sparse; indicative only."
              if small else f"**n={n_rows} pooled player-match values.**")
    L = ["---",
         "tags: [organized, tennis, intelligence, archetypes, serve-return, person-free]",
         "---", "",
         "# Tennis — Serve/Return Style Archetypes", "",
         _BANNER, "",
         (f"{n_note} Serve/return metrics pooled across p1+p2 sides; tertile thresholds "
          "computed from the full corpus. Styles are person-free constructs — NOT "
          "validated clusters and NOT a per-match pick.\n"),
         "## Corpus Percentile Thresholds (tertiles)", "",
         "| metric | p33 | p50 | p67 | n |",
         "|--------|----:|----:|----:|--:|"]
    for metric, _ in _METRICS:
        if metric not in thresholds:
            continue
        b = thresholds[metric]
        L.append(f"| `{metric}` | {b['p33']:.4f} | {b['p50']:.4f} | {b['p67']:.4f}"
                 f" | {b['n']} |")
    L += ["", "## Canonical Serve/Return Style Archetypes", ""]
    for st in styles:
        wl = f" → [[{st['wikilink']}]]" if st.get("wikilink") else ""
        share_str = f"{st['share']:.1%}" if st.get("share") is not None else "N/A"
        L += [f"### {st['name']}{wl}", "",
              f"**Mechanism:** {st['mechanism']}", "",
              "**Stat-signature (defining bands):**"]
        for metric, (direction, pct) in st["spec"]["bands"].items():
            L.append(f"- {_thr_str(metric, direction, pct, thresholds)}")
        L += ["", f"**Corpus share (all defining bands met):** {share_str}", ""]
    L += ["## Reading this honestly",
          "- **Style concepts, not validated clusters.** Defined by logical "
          "band-combinations; not the result of unsupervised clustering or outcome validation.",
          "- **Corpus share is descriptive.** Frequency count only — NOT a win-rate or edge.",
          "- **Not a per-match signal.** Markets are efficient; calibration is not edge; "
          "no edge claimed.",
          "- **Person-free.** No individual player names; all characterisations at style level.",
          "", "## See also",
          "- [[Archetypes/Fast_Court_Big_Server|Fast Court Big Server]]",
          "- [[Archetypes/All_Court_Baseliner|All Court Baseliner]]",
          "- [[Archetypes/Clay_Court_Specialist|Clay Court Specialist]]",
          "- [[Archetypes/Hard_Court_Specialist|Hard Court Specialist]]",
          "- [[_WhatWins|Tennis What Wins & Why]]",
          "- [[_Index|Tennis Index]]"]
    if small:
        L.append("- **Small sample.** Thresholds are indicative only.")
    return "\n".join(L) + "\n"


def build_tennis_depth(organized_root: Optional[Path] = None,
                       data_root: Optional[Path] = None,
                       write: bool = True,
                       injected=None) -> Dict:
    """Build Tennis _Serve_Return_Archetypes.md from the leak-free as-of parquet.

    ``injected`` accepts a DataFrame for hermetic tests (bypasses disk I/O).
    Skips honestly if the parquet is missing/unreadable. Idempotent.
    Returns dict: thresholds, styles, n_rows, small_n, md, _note.
    """
    root = Path(organized_root) if organized_root else _REPO_ROOT / "vault" / "_Organized"
    droot = Path(data_root) if data_root else _REPO_ROOT
    if injected is not None:
        df = injected
    else:
        pq = droot / _PARQUET
        if not pq.exists():
            return {"skipped": "missing parquet", "_note": _NOTE}
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(pq)
        except Exception as exc:  # noqa: BLE001
            return {"skipped": f"unreadable parquet: {exc}", "_note": _NOTE}
    thresholds = _compute_thresholds(df)
    if not thresholds:
        return {"skipped": "no computable thresholds", "_note": _NOTE}
    styles: List[Dict] = []
    for spec in _STYLE_SPECS:
        styles.append({"name": spec["name"], "wikilink": spec["wikilink"],
                       "mechanism": spec["mechanism"], "spec": spec,
                       "share": _style_share(df, spec, thresholds)})
    n_rows = max((v["n"] for v in thresholds.values()), default=0)
    md = _render(thresholds, styles, n_rows)
    if write:
        tdir = root / "Tennis"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "_Serve_Return_Archetypes.md").write_text(md, encoding="utf-8")
    return {"thresholds": thresholds,
            "styles": [{"name": s["name"], "share": s["share"],
                        "wikilink": s["wikilink"]} for s in styles],
            "n_rows": n_rows, "small_n": n_rows < _SMALL_N, "md": md, "_note": _NOTE}


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__); return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_tennis_depth(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        print(json.dumps({k: v for k, v in rep.items() if k != "md"}, indent=2,
                         default=str)); return 0
    if "skipped" in rep:
        print(f"brain_tennis_depth: SKIPPED ({rep['skipped']})"); return 0
    print(f"brain_tennis_depth: n={rep['n_rows']} pooled rows; "
          f"{len(rep['thresholds'])} metrics; {len(rep['styles'])} styles")
    for st in rep["styles"]:
        share_str = f"{st['share']:.1%}" if st["share"] is not None else "N/A"
        print(f"  [{st['name']:<35}] share={share_str}  link={st['wikilink'] or 'none'}")
    print(f"NOTE: {rep['_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
