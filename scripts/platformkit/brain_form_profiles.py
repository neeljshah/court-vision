"""brain_form_profiles.py — per-sport DISTRIBUTION of leak-free as-of form signals.

Reads the gitignored as-of parquets (built by the per-sport ingest modules), pools
the home/away (or p1/p2) columns for each base metric into a single numeric series,
and writes ``vault/_Organized/<SPORT>/_Form_Profiles.md`` — a dense percentile-band
table (p10/p25/p50/p75/p90) plus person-free one-line stylistic readings of the low
vs high band.

These are LEAK-FREE AS-OF aggregates (snapshot prior to update). The profile is
DESCRIPTIVE distribution knowledge — NOT a bet, NOT a per-game pick, NOT an edge.
Markets are efficient; calibration is not edge; no edge claimed.

CLI: ``python -m scripts.platformkit.brain_form_profiles [<root>] [--json]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_BANNER = ("> **Descriptive intelligence; markets efficient; calibration is not edge; "
           "no edge claimed.** Leak-free as-of form distributions — AGGREGATE knowledge "
           "of signal shape across all observed games. NOT a per-game pick and NOT a bet.")

# Per-sport config: parquet path, list of (base_metric, [side_cols]) to pool,
# and human-readable unit label.
_SPORTS: Dict[str, Dict] = {
    "NBA": {
        "parquet": "data/domains/basketball_nba/asof_features.parquet",
        "metrics": [
            ("pace",     ["home_pace_asof",     "away_pace_asof"]),
            ("ast_rate", ["home_ast_rate_asof",  "away_ast_rate_asof"]),
            ("oreb_pg",  ["home_oreb_pg_asof",   "away_oreb_pg_asof"]),
            ("tov_pg",   ["home_tov_pg_asof",    "away_tov_pg_asof"]),
        ],
        "unit": "per-game as-of prior",
    },
    "MLB": {
        "parquet": "data/domains/mlb/asof_features.parquet",
        "metrics": [
            ("sp_ra",           ["home_sp_ra_asof",          "away_sp_ra_asof"]),
            ("sp_starts_prior", ["home_sp_starts_prior",     "away_sp_starts_prior"]),
        ],
        "unit": "starter as-of prior",
    },
    "Soccer": {
        "parquet": "data/domains/soccer/asof_features.parquet",
        "metrics": [
            ("sot_for",     ["home_sot_for_asof",     "away_sot_for_asof"]),
            ("sot_against", ["home_sot_against_asof", "away_sot_against_asof"]),
            ("shots_for",   ["home_shots_for_asof",   "away_shots_for_asof"]),
        ],
        "unit": "per-match as-of prior",
    },
    "Tennis": {
        "parquet": "data/domains/tennis/asof_features.parquet",
        "metrics": [
            ("ace_rate", ["p1_ace_rate_asof", "p2_ace_rate_asof"]),
            ("1st_in",   ["p1_1st_in_asof",   "p2_1st_in_asof"]),
            ("1st_win",  ["p1_1st_win_asof",   "p2_1st_win_asof"]),
            ("2nd_win",  ["p1_2nd_win_asof",   "p2_2nd_win_asof"]),
            ("bp_saved", ["p1_bp_saved_asof",  "p2_bp_saved_asof"]),
        ],
        "unit": "per-player as-of prior",
    },
}

# Person-free stylistic readings: (low_band_phrase, high_band_phrase).
# Descriptive style-level only — NO outcome/edge claims.
_READINGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "NBA": {
        "pace":     ("grind-it-out half-court style, deliberate possessions",
                     "up-tempo possession-rich style, high transition volume"),
        "ast_rate": ("isolation-heavy, low ball-movement system",
                     "high ball-movement, team-first passing system"),
        "oreb_pg":  ("perimeter-oriented rebounding, quick retreat",
                     "glass-crashing, second-chance offense heavy"),
        "tov_pg":   ("disciplined possession retention, low chaos",
                     "high-turnover style, likely pace-driven or risk-taking offense"),
    },
    "MLB": {
        "sp_ra":           ("elite or locked-in starter, suppressing run environments",
                            "vulnerable starter, elevated run-scoring environment"),
        "sp_starts_prior": ("thin sample — starter profile less stable",
                            "deep sample — starter profile well-established"),
    },
    "Soccer": {
        "sot_for":     ("low-volume attacking threat, possession or counter-oriented",
                        "high-volume attacking threat, pressing or direct style"),
        "sot_against": ("defensively compact, allowing few dangerous attempts",
                        "defensively exposed, conceding high-quality attempts"),
        "shots_for":   ("controlled possession, quality-over-quantity approach",
                        "high-volume attack, wide shot profile"),
    },
    "Tennis": {
        "ace_rate": ("serve-hold-neutral, reliant on placement over pace",
                     "serve-dominant, ace-heavy delivery style"),
        "1st_in":   ("aggressive server, accepting lower first-serve %",
                     "consistent server, high first-serve accuracy"),
        "1st_win":  ("break-vulnerable on first serve, relies on second",
                     "first-serve dominant, holds at high clip"),
        "2nd_win":  ("second serve is a liability, pressure point",
                     "second serve is a weapon, spin or kick heavy"),
        "bp_saved": ("break-point vulnerable, poor tiebreak-pressure handling",
                     "clutch under pressure, strong break-point conversion defense"),
    },
}

_SMALL_N = 50  # below this rows -> "indicative only" caveat


def _pool_metric(df, cols: List[str]):
    """Pool the listed columns from df into one numeric Series, NaN-dropped."""
    import pandas as pd  # noqa: PLC0415
    parts = [pd.to_numeric(df[c], errors="coerce") for c in cols if c in df.columns]
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, ignore_index=True).dropna()


def _percentile_bands(series) -> Optional[Dict]:
    """Compute p10/p25/p50/p75/p90 and n. Returns None if <2 values."""
    if len(series) < 2:
        return None
    qs = series.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "p10": round(float(qs[0.10]), 4),
        "p25": round(float(qs[0.25]), 4),
        "p50": round(float(qs[0.50]), 4),
        "p75": round(float(qs[0.75]), 4),
        "p90": round(float(qs[0.90]), 4),
        "n":   int(len(series)),
    }


def _render(sport: str, bands: Dict[str, Dict], n_rows: int) -> str:
    """Build the Markdown note for one sport."""
    cfg = _SPORTS[sport]
    readings = _READINGS.get(sport, {})
    small = n_rows < _SMALL_N
    n_note = (f"**n={n_rows} pooled values** — sparse; indicative only."
              if small else f"**n={n_rows} pooled values.**")
    hdr = [
        f"---\ntags: [organized, {sport.lower()}, intelligence, form-profiles, "
        f"person-free]\n---",
        f"# {sport} — As-Of Form Signal Distributions\n",
        _BANNER + "\n",
        f"{n_note} Percentile bands of the leak-free as-of prior "
        f"({cfg['unit']}) pooled across home+away (or p1+p2) sides. "
        f"DESCRIPTIVE only — shape of the distribution, not a pick.\n",
        "| metric | p10 | p25 | p50 | p75 | p90 | n |",
        "|--------|----:|----:|----:|----:|----:|--:|",
    ]
    rows = list(hdr)
    for metric, b in bands.items():
        rows.append(f"| `{metric}` | {b['p10']:g} | {b['p25']:g} | {b['p50']:g} "
                    f"| {b['p75']:g} | {b['p90']:g} | {b['n']} |")
    rows += ["", "## Stylistic readings (person-free, distribution-level)"]
    for metric, b in bands.items():
        lo, hi = readings.get(metric, ("low-band style", "high-band style"))
        rows.append(f"- **`{metric}`** — low band (≤p25 ≈{b['p25']:g}): {lo}. "
                    f"High band (≥p75 ≈{b['p75']:g}): {hi}.")
    rows += [
        "", "## Reading this honestly",
        "- **Descriptive, not predictive.** These percentile bands describe the "
        "historical distribution; they are NOT a forecast or a signal magnitude.",
        "- **Leak-free as-of.** Values are snapshotted before each game (prior-only); "
        "the realized post-game stat is NOT used here.",
        "- **No edge claimed.** Markets are efficient; calibration is not edge.",
    ]
    if small:
        rows.append("- **Small sample.** Bands are indicative only; treat with caution.")
    rows += [
        "", "## See also",
        f"- [[_WhatWins|{sport} What Wins & Why]]",
        f"- [[_Index|{sport} Index]]",
    ]
    return "\n".join(rows) + "\n"


def _build_one(sport: str, df, write: bool, root: Path) -> Dict:
    """Compute percentile bands for one sport's as-of parquet (+optional write)."""
    cfg = _SPORTS[sport]
    bands: Dict[str, Dict] = {}
    total_n = 0
    for metric, cols in cfg["metrics"]:
        series = _pool_metric(df, cols)
        b = _percentile_bands(series)
        if b is None:
            continue
        bands[metric] = b
        total_n = max(total_n, b["n"])
    if not bands:
        return {"skipped": "no computable bands"}
    md = _render(sport, bands, total_n)
    if write:
        sdir = root / sport
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "_Form_Profiles.md").write_text(md, encoding="utf-8")
    return {
        "n_rows": total_n,
        "n_metrics": len(bands),
        "bands": bands,
        "small_n": total_n < _SMALL_N,
        "form_profiles_md": md,
    }


def build_form_profiles(
    organized_root: Optional[Path] = None,
    data_root: Optional[Path] = None,
    write: bool = True,
    injected: Optional[Dict] = None,
) -> Dict:
    """Build per-sport FORM-PROFILE notes from leak-free as-of parquets.

    ``injected`` accepts ``{sport: DataFrame}`` for hermetic tests (bypasses I/O).
    Sports with a missing/sparse/unreadable parquet are skipped HONESTLY.
    Returns ``{"n_sports", "by_sport", "_note"}``; idempotent.
    """
    root = Path(organized_root) if organized_root else (_REPO_ROOT / "vault" / "_Organized")
    droot = Path(data_root) if data_root else _REPO_ROOT
    by_sport: Dict[str, Dict] = {}
    n_built = 0
    for sport, cfg in _SPORTS.items():
        if injected is not None:
            if sport not in injected:
                continue
            df = injected[sport]
        else:
            pq = droot / cfg["parquet"]
            if not pq.exists():
                by_sport[sport] = {"skipped": "missing parquet"}
                continue
            try:
                import pandas as pd  # noqa: PLC0415
                df = pd.read_parquet(pq)
            except Exception as exc:  # noqa: BLE001
                by_sport[sport] = {"skipped": f"unreadable parquet: {exc}"}
                continue
        info = _build_one(sport, df, write, root)
        by_sport[sport] = info
        if "skipped" not in info:
            n_built += 1
    return {
        "n_sports": n_built,
        "by_sport": by_sport,
        "_note": ("descriptive intelligence; markets efficient; calibration is not edge; "
                  "no edge claimed; leak-free as-of form distributions, not a per-game signal"),
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    root_arg = next((a for a in argv if not a.startswith("-")), None)
    rep = build_form_profiles(
        organized_root=Path(root_arg) if root_arg else None, write=True
    )
    if "--json" in argv:
        slim = {
            sp: ({k: v for k, v in info.items() if k != "form_profiles_md"}
                 if isinstance(info, dict) else info)
            for sp, info in rep["by_sport"].items()
        }
        print(json.dumps(
            {"n_sports": rep["n_sports"], "by_sport": slim, "_note": rep["_note"]},
            indent=2, default=str,
        ))
        return 0
    print(f"brain_form_profiles: {rep['n_sports']} sport(s) built")
    for sport, info in rep["by_sport"].items():
        if "skipped" in info:
            print(f"  [{sport:<7}] SKIPPED ({info['skipped']})")
        else:
            tag = " (sparse)" if info.get("small_n") else ""
            mets = ", ".join(info["bands"])
            print(f"  [{sport:<7}] {info['n_rows']} pooled rows / "
                  f"{info['n_metrics']} metrics{tag}: {mets}")
    print(f"NOTE: {rep['_note']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
