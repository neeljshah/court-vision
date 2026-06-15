"""brain_mlb_schemes.py — MLB SCHEME taxonomy from leak-free as-of starter + park signals.

Reads ``data/domains/mlb/asof_features.parquet`` and ``data/domains/mlb/asof_park.parquet``,
computes corpus-level percentile bands for sp_ra, sp_starts_prior, and park_factor, then
writes a dense person-free ``vault/_Organized/MLB/_Pitching_Schemes.md``.

Honest banner throughout: DESCRIPTIVE distribution knowledge, markets efficient, calibration
is NOT edge, NOT a per-game signal, NOT a bet.  Skip-on-missing parquets, idempotent, <=300 LOC.

CLI: ``python -m scripts.platformkit.brain_mlb_schemes [<root>] [--json]``
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = (
    "> **Descriptive intelligence; markets efficient; calibration is not edge; no edge claimed.**"
    " Leak-free as-of corpus distributions — NOT a per-game signal and NOT a bet. Each scheme"
    " is a DESCRIPTIVE label for a region of the distribution; it conveys style context, not"
    " an outcome advantage."
)
_FEAT_PQ = "data/domains/mlb/asof_features.parquet"
_PARK_PQ = "data/domains/mlb/asof_park.parquet"
_SMALL_N = 500


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _pool(df, *cols: str):
    import pandas as pd
    parts = [pd.to_numeric(df[c], errors="coerce") for c in cols if c in df.columns]
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, ignore_index=True).dropna()


def _bands(s) -> Optional[Dict]:
    if len(s) < 2:
        return None
    qs = s.quantile([.10, .25, .50, .75, .90])
    return {"p10": round(float(qs[.10]), 3), "p25": round(float(qs[.25]), 3),
            "p50": round(float(qs[.50]), 3), "p75": round(float(qs[.75]), 3),
            "p90": round(float(qs[.90]), 3), "n": int(len(s))}


def _pct(s, lo, hi=None) -> float:
    if len(s) == 0:
        return 0.0
    mask = (s >= lo) if hi is None else ((s >= lo) & (s < hi))
    return round(100.0 * float(mask.sum()) / len(s), 1)


# ---------------------------------------------------------------------------
# Scheme builder
# ---------------------------------------------------------------------------

def _build_schemes(sp_ra, sp_starts, park_factor, rb, sb, pb) -> List[Dict]:
    """Return list of scheme dicts with real threshold numbers and corpus shares."""
    e_ceil  = rb["p25"];  v_floor = rb["p75"]
    ts_ceil = sb["p25"]
    sp_ceil = pb["p25"];  pw_floor = pb["p75"]
    return [
        {"name": "Rotation-Anchored Run Prevention",
         "band": f"sp_ra < {e_ceil:.3f} (≤p25)",
         "share": _pct(sp_ra, 0, e_ceil),
         "mechanism": ("Starter trailing run-rate in bottom corpus quartile; rotation"
                       " suppresses scoring environments on both sides of the ball."),
         "links": ["[[Archetypes/pitching_run_prevention|Pitching-Led / Run-Prevention]]",
                   "[[Archetypes/low_scoring_grinder|Low-Scoring Grinder]]",
                   "[[Drivers/sp_duel|SP Duel driver]]", "[[_WhatWins|MLB What Wins]]"]},
        {"name": "Bullpen-Dependent / Starter-Volatile",
         "band": f"sp_ra ≥ {v_floor:.3f} (≥p75)",
         "share": _pct(sp_ra, v_floor),
         "mechanism": ("Starter run-rate in top corpus quartile; games tilt toward"
                       " bullpen leverage and late-inning relief quality."),
         "links": ["[[Archetypes/high_variance_offense|High-Variance Offense]]",
                   "[[Drivers/bullpen_swing|Bullpen Swing driver]]", "[[_WhatWins|MLB What Wins]]"]},
        {"name": "Thin-Sample / Short-Leash Profile",
         "band": f"sp_starts_prior < {ts_ceil:.0f} (≤p25)",
         "share": _pct(sp_starts, 0, ts_ceil),
         "mechanism": ("Starter has fewer than bottom-quartile starts in the as-of sample;"
                       " run-prevention profile is unstable with high mean variance."),
         "links": ["[[_Form_Profiles|MLB Form Signal Distributions]]", "[[_WhatWins|MLB What Wins]]"]},
        {"name": "Park-Suppressed Environment",
         "band": f"park_factor < {sp_ceil:.3f} (≤p25)",
         "share": _pct(park_factor, 0, sp_ceil),
         "mechanism": ("Park factor in bottom quartile; dimensions/altitude structurally"
                       " suppress run scoring relative to neutral contexts."),
         "links": ["[[Archetypes/low_scoring_grinder|Low-Scoring Grinder]]",
                   "[[Drivers/sp_duel|SP Duel driver]]", "[[_WhatWins|MLB What Wins]]"]},
        {"name": "Power / High-Run-Environment Park",
         "band": f"park_factor ≥ {pw_floor:.3f} (≥p75)",
         "share": _pct(park_factor, pw_floor),
         "mechanism": ("Park factor in top quartile; conditions amplify run production and"
                       " offensive burst archetypes see variance expand."),
         "links": ["[[Archetypes/high_variance_offense|High-Variance Offense]]",
                   "[[Archetypes/power_run_scoring|Power / Run-Scoring]]",
                   "[[Drivers/big_inning|Big Inning driver]]", "[[_WhatWins|MLB What Wins]]"]},
        {"name": "Balanced Staff / Neutral Park",
         "band": (f"sp_ra in [{e_ceil:.3f}, {v_floor:.3f}) AND"
                  f" park_factor in [{sp_ceil:.3f}, {pw_floor:.3f})"),
         "share": _pct(park_factor, sp_ceil, pw_floor),
         "mechanism": ("Neither starter quality nor park context pushes the game toward"
                       " extremes; outcomes most sensitive to lineup sequencing and pen usage."),
         "links": ["[[Archetypes/balanced_contender|Balanced Contender]]",
                   "[[Drivers/routine|Routine driver]]", "[[_WhatWins|MLB What Wins]]"]},
    ]


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _render(schemes, rb, sb, pb, n_games) -> str:
    small = min(rb["n"], pb["n"]) < _SMALL_N
    caveat = " — sparse; indicative only." if small else "."
    lines = [
        "---", "tags: [organized, mlb, intelligence, schemes, pitching, person-free]", "---",
        "# MLB — Pitching Schemes & Run-Environment Taxonomy\n", _BANNER + "\n",
        (f"**n≈{n_games:,} games{caveat}** Each scheme is derived from the ACTUAL corpus"
         f" percentile thresholds computed over {n_games:,} observed games."
         f" Schemes are descriptive run-environment labels — style context, not outcomes.\n"),
        "## Signal Distributions (corpus bands)\n",
        "| signal | p10 | p25 | p50 | p75 | p90 | n (pooled) |",
        "|--------|----:|----:|----:|----:|----:|-----------:|",
        (f"| `sp_ra` (starter trailing RA) | {rb['p10']:g} | {rb['p25']:g}"
         f" | {rb['p50']:g} | {rb['p75']:g} | {rb['p90']:g} | {rb['n']:,} |"),
        (f"| `sp_starts_prior` (sample depth) | {sb['p10']:g} | {sb['p25']:g}"
         f" | {sb['p50']:g} | {sb['p75']:g} | {sb['p90']:g} | {sb['n']:,} |"),
        (f"| `park_factor` (run environment) | {pb['p10']:g} | {pb['p25']:g}"
         f" | {pb['p50']:g} | {pb['p75']:g} | {pb['p90']:g} | {pb['n']:,} |"),
        "\n## Scheme Taxonomy\n",
    ]
    for s in schemes:
        lines += [
            f"### {s['name']}",
            f"**Corpus share:** {s['share']}%  ",
            f"**Defining band:** `{s['band']}`  ",
            f"**Mechanism:** {s['mechanism']}\n",
            "**Cross-links:**",
        ]
        lines += [f"- {lnk}" for lnk in s["links"]]
        lines.append("")
    lines += [
        "## Reading this honestly",
        "- **Descriptive, not predictive.** Scheme labels describe corpus distribution regions; NOT a forecast.",
        "- **Leak-free as-of only.** Signals snapshotted before each game; realized post-game stats NOT used.",
        "- **Markets are efficient; calibration is not edge.** No edge claimed anywhere in this note.",
        "- **Schemes are mutually overlapping.** A game-context may satisfy multiple bands; each share is independent.",
        "", "## See also",
        "- [[_WhatWins|MLB What Wins & Why]]", "- [[_Form_Profiles|MLB Form Signal Distributions]]",
        "- [[_KeyStats|MLB Key Stats]]", "- [[Archetypes/_Computed_Index|Pitcher Archetypes Index]]",
        "- [[_Index|MLB Index]]",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def build_mlb_schemes(organized_root=None, data_root=None, write=True, injected=None) -> Dict:
    """Build the MLB Pitching Schemes note from leak-free as-of parquets.

    ``injected`` accepts ``{"features": DataFrame, "park": DataFrame}`` for hermetic tests.
    Missing / unreadable parquets skipped honestly.  Returns result dict; idempotent.
    """
    import pandas as pd
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    droot = Path(data_root) if data_root else _REPO_ROOT
    if injected is not None:
        df_feat, df_park = injected.get("features"), injected.get("park")
        if df_feat is None or df_park is None:
            return {"skipped": "injected dict missing 'features' or 'park' key"}
    else:
        fp, pp = droot / _FEAT_PQ, droot / _PARK_PQ
        missing = [str(p) for p in (fp, pp) if not p.exists()]
        if missing:
            return {"skipped": f"missing parquets: {missing}"}
        try:
            df_feat, df_park = pd.read_parquet(fp), pd.read_parquet(pp)
        except Exception as exc:
            return {"skipped": f"unreadable parquet: {exc}"}
    sp_ra = _pool(df_feat, "home_sp_ra_asof", "away_sp_ra_asof")
    sp_starts = _pool(df_feat, "home_sp_starts_prior", "away_sp_starts_prior")
    park_factor = _pool(df_park, "park_factor")
    rb, sb, pb = _bands(sp_ra), _bands(sp_starts), _bands(park_factor)
    if rb is None or pb is None:
        return {"skipped": "insufficient data to compute bands"}
    if sb is None:
        sb = {"p10": 0, "p25": 0, "p50": 0, "p75": 0, "p90": 0, "n": 0}
    for band in (rb, sb, pb):
        vals = [band[k] for k in ("p10", "p25", "p50", "p75", "p90")]
        assert vals == sorted(vals), f"Non-monotonic band: {band}"
    n_games = max(len(df_feat), len(df_park))
    schemes = _build_schemes(sp_ra, sp_starts, park_factor, rb, sb, pb)
    md = _render(schemes, rb, sb, pb, n_games)
    if write:
        out = root / "MLB"; out.mkdir(parents=True, exist_ok=True)
        (out / "_Pitching_Schemes.md").write_text(md, encoding="utf-8")
    return {"n_games": n_games, "ra_bands": rb, "starts_bands": sb, "park_bands": pb,
            "schemes": [{"name": s["name"], "share": s["share"], "band": s["band"]} for s in schemes],
            "n_schemes": len(schemes), "small_n": min(rb["n"], pb["n"]) < _SMALL_N,
            "pitching_schemes_md": md,
            "_note": ("descriptive intelligence; markets efficient; calibration is not edge;"
                      " no edge claimed; leak-free as-of corpus distribution, not a per-game signal")}


def _main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__); return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_mlb_schemes(organized_root=Path(root_arg) if root_arg else None, write=True)
    if "--json" in argv:
        print(json.dumps({k: v for k, v in rep.items() if k != "pitching_schemes_md"},
                         indent=2, default=str)); return 0
    if "skipped" in rep:
        print(f"brain_mlb_schemes: SKIPPED ({rep['skipped']})"); return 0
    tag = " (sparse)" if rep.get("small_n") else ""
    print(f"brain_mlb_schemes: {rep['n_games']:,} games / {rep['n_schemes']} schemes{tag}")
    for s in rep["schemes"]:
        print(f"  {s['name']:<45} {s['share']:>5}%  band={s['band'][:55]}")
    print(f"NOTE: {rep['_note']}"); return 0


if __name__ == "__main__":
    sys.exit(_main())
