"""domains.basketball_nba.asof_reclaim_gate -- sweep gate for the untested NBA reclaim dims.

Runs the SAME single-corpus walk-forward Diebold-Mariano gate used by the
``ast_rate_diff_asof`` reclaim (domains.basketball_nba.asof_ast_rate_eval -- ALREADY
gated 2026-06-27 -> HONEST REJECT, excluded here, see asof_reclaim_dims.PREVIOUSLY_REJECTED)
across the six UNTESTED as-of dims named in
docs/research/ceiling/ONDISK_RECLAIM_TARGETS.md row #1:

    pace_diff_asof, oreb_pg_diff_asof, tov_pg_diff_asof   (derived home-away;
                                                            asof_reclaim_dims.add_pair_diffs)
    dreb_diff_asof, fg3m_diff_asof, stl_diff_asof, blk_diff_asof   (already on disk
                                                            in asof_box_extra.parquet)

Each dim gets: REAL single-corpus 70/30 walk-forward DM gate (Elo base vs Elo+feature),
a PLANTED-NULL control (shuffled feature must collapse to REJECT), and a TRUNCATION-
INVARIANCE check (drop last 10% of train rows -> verdict must not flip).  Reuses
asof_ast_rate_eval._gate_once / ._planted_null / .build_candidate_frame verbatim --
this module adds NO new gate math, only feeds it the new dims.

VS-CLOSE NOTE (honesty): the ast_rate_eval template gates vs the Elo BASE only; it
has no vs-close arm because this corpus's closing odds coverage is sparse
(2025-26 only per adapter.py, NaN elsewhere) and build_candidate_frame carries no
`lines`/`closing` field.  This sweep inherits that same honest scope -- vs-Elo-base
only, single-corpus (1299 box-era games), no cross-corpus replication claim.

CANDIDATE-ONLY: reads two parquets additively; touches neither NBAAdapter nor any
live pipeline.  No flags flipped.  A REJECT verdict is a SUCCESS, not a failure.

Output: one verdict JSON per dim under
    data/domains/basketball_nba/reclaim_gate_<dim>.json
plus a consolidated summary at
    data/domains/basketball_nba/reclaim_gate_summary.json

F5: NO domains.mlb / domains.tennis / domains.soccer / src.* / kernel.* imports.
PRIVATE: never committed to the public repo.

CLI:  python -m domains.basketball_nba.asof_reclaim_gate
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from domains.basketball_nba import asof_ast_rate_eval as _eval
from domains.basketball_nba.asof_reclaim_dims import (
    RECLAIM_DIFF_COLS,
    _PAIR_DIFFS,
    _PREBUILT_DIFFS,
    add_pair_diffs,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO_ROOT / "data" / "domains" / "basketball_nba"
_ASOF_BOX_EXTRA = _OUT_DIR / "asof_box_extra.parquet"

# Fields the honesty linter forbids; a defensive re-check on every written verdict.
_BANNED_TOKENS = ("roi", "pnl", "p_l", "profit", "dollars")


def gate_pair_diff(diff_col: str, seed: int = 0) -> Dict:
    """Gate one derived pace/oreb/tov diff column (in-memory, not on disk yet).

    Mirrors asof_ast_rate_eval.gate_feature() exactly but feeds build_candidate_frame
    an in-memory asof_features frame carrying the newly-derived diff column, since
    gate_feature()'s asof_path arg only accepts a file path and these three diffs
    are not materialized in any on-disk parquet.
    """
    asof = add_pair_diffs()  # reads asof_features.parquet, adds the 3 pair diffs
    df = _eval.build_candidate_frame(asof=asof, feat_col=diff_col)
    n = len(df)
    cov_total = int(df["_cov"].sum())
    real = _eval._gate_once(df, feat_col=diff_col)
    null = _eval._planted_null(df, seed=seed, feat_col=diff_col)
    trunc = _eval._gate_once(df, feat_col=diff_col, train_frac=_eval.TRAIN_FRAC * 0.90)
    return {
        "feature": diff_col, "n_rows": n, "cov_total": cov_total,
        "cov_pct": round(100.0 * cov_total / max(n, 1), 1),
        "real": real, "planted_null": null, "truncation": trunc,
    }


def gate_prebuilt_diff(diff_col: str, seed: int = 0) -> Dict:
    """Gate one already-on-disk box-extra diff (dreb/fg3m/stl/blk) via gate_feature."""
    return _eval.gate_feature(diff_col, asof_path=str(_ASOF_BOX_EXTRA), seed=seed)


def _verdict_of(result: Dict) -> str:
    """Honest verdict string: REAL must SHIP AND null must REJECT AND trunc must match."""
    real_v = result["real"]["verdict"]
    null_v = result["planted_null"]["verdict"]
    trunc_v = result["truncation"]["verdict"]
    if null_v != "REJECT":
        return "REJECT"  # planted-null control failed to collapse -> distrust any SHIP
    if real_v == "SHIP" and trunc_v == "SHIP":
        return "SHIP"
    return "REJECT"


def _assert_no_banned_tokens(payload: Dict) -> None:
    blob = json.dumps(payload).lower()
    hit = [t for t in _BANNED_TOKENS if t in blob]
    if hit:
        raise ValueError(f"honesty violation: banned token(s) {hit} in verdict payload")


def run_sweep(seed: int = 0, out_dir: Path = _OUT_DIR) -> List[Dict]:
    """Gate all six untested reclaim dims; write one verdict JSON per dim + summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict] = []
    for diff_col in RECLAIM_DIFF_COLS:
        if diff_col in _PAIR_DIFFS:
            res = gate_pair_diff(diff_col, seed=seed)
        elif diff_col in _PREBUILT_DIFFS:
            res = gate_prebuilt_diff(diff_col, seed=seed)
        else:  # pragma: no cover -- defensive; RECLAIM_DIFF_COLS is the only source
            raise ValueError(f"unknown reclaim dim {diff_col!r}")

        verdict = _verdict_of(res)
        payload = {
            "component": "asof_reclaim_gate",
            "sport": "basketball_nba",
            "dim": diff_col,
            "hypothesis": f"{diff_col} (leak-free prior-only trailing diff) beats "
                          "Elo-only base on held-out Brier for NBA home-win probability",
            "verdict": verdict,
            "n_rows": res["n_rows"],
            "cov_total": res["cov_total"],
            "cov_pct": res["cov_pct"],
            "real": res["real"],
            "planted_null": res["planted_null"],
            "truncation": res["truncation"],
            "note": "calibration-only; REJECT is an honest success; no edge claimed",
        }
        _assert_no_banned_tokens(payload)
        dest = out_dir / f"reclaim_gate_{diff_col}.json"
        dest.write_text(json.dumps(payload, indent=1), encoding="ascii", errors="replace")
        rows.append(payload)

    summary = {
        "component": "asof_reclaim_gate_summary",
        "sport": "basketball_nba",
        "previously_rejected_excluded": ["ast_rate_diff_asof"],
        "dims_gated": len(rows),
        "verdicts": {r["dim"]: r["verdict"] for r in rows},
        "note": "calibration-only; SHIP counts require planted-null REJECT + "
                "truncation-invariant real SHIP; no edge claimed",
    }
    _assert_no_banned_tokens(summary)
    (out_dir / "reclaim_gate_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="ascii", errors="replace",
    )
    return rows


def main() -> int:
    rows = run_sweep()
    print("=" * 72)
    print("NBA as-of RECLAIM sweep -- 6 untested dims vs Elo base (single-corpus WF gate)")
    print("=" * 72)
    for r in rows:
        rl = r["real"]
        print(f"\n{r['dim']:>20s}  verdict={r['verdict']:<7s}  "
              f"cov={r['cov_total']}/{r['n_rows']} ({r['cov_pct']}%)")
        print(f"   REAL  Brier base {rl['brier_base']:.6f}  cand {rl['brier_cand']:.6f}"
              f"  delta {rl['brier_delta']:+.6f}  DM p={rl['dm_p']:.4f}")
        nn = r["planted_null"]
        print(f"   NULL  verdict={nn['verdict']}  (must be REJECT)")
        tr = r["truncation"]
        print(f"   TRUNC verdict={tr['verdict']}  (must match REAL)")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    print(f"\nWrote {len(rows)} per-dim verdict JSONs + reclaim_gate_summary.json under "
          f"{_OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
