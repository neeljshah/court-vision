"""domains.basketball_nba.boxdetail_gate -- gate the box-detail as-of family.

Runs the SAME single-corpus walk-forward Diebold-Mariano gate
``asof_ast_rate_eval.gate_feature`` uses for every other as-of reclaim
(``asof_reclaim_gate.py``), pointed at the new
``boxdetail_asof.parquet`` (domains/basketball_nba/boxdetail_asof.py).

Gates the 4 season-to-date diffs judged most plausible a priori: fast-break
points (transition offense), points in the paint (interior scoring), largest
lead (game-control proxy), and combined tech+flagrant foul trouble
(discipline). tov_pts and every *_l10_asof variant are left ungated here --
same family, cheap to add later if these 4 show anything.

HONEST EXPECTATION: box-detail coverage only exists 2026-01-20 onward on this
corpus (~659/1977 games), so this is a THIN single-season slice -- a NULL/
REJECT verdict here is expected and is a SUCCESS, not a failure. The real
value of this module is the family entering the interaction factory's
candidate space (see attribute_registry.py's `family` tag + generator.py's
``nba_boxdetail_self_cross`` template) and in-game conditioning candidacy --
NOT a pregame team-aggregate edge claim.

CANDIDATE-ONLY: reads two parquets additively; touches neither NBAAdapter nor
any live pipeline. No flag flipped. No edge ever claimed.

Output: one verdict JSON per feature under
    data/domains/basketball_nba/boxdetail_gate_<feature>.json
plus a consolidated summary at
    data/domains/basketball_nba/boxdetail_gate_summary.json

F5: NO domains.mlb / domains.tennis / domains.soccer / src.* / kernel.* imports.
PRIVATE: never committed to the public repo.

CLI:  python -m domains.basketball_nba.boxdetail_gate
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from domains.basketball_nba import asof_ast_rate_eval as _eval

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = _REPO_ROOT / "data" / "domains" / "basketball_nba"
_BOXDETAIL_ASOF = _OUT_DIR / "boxdetail_asof.parquet"

# The 4 most plausible season-to-date diffs (see module docstring for why).
GATED_FEATURES: List[str] = [
    "fast_break_pts_diff_asof",
    "paint_pts_diff_asof",
    "largest_lead_diff_asof",
    "foul_trouble_diff_asof",
]

_BANNED_TOKENS = ("roi", "pnl", "p_l", "profit", "dollars")


def _verdict_of(result: Dict) -> str:
    """Honest verdict: REAL must SHIP AND null must REJECT AND trunc must match."""
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


def _train_window_has_coverage(feat_col: str, seed: int = 0) -> bool:
    """True iff the feature has >=1 non-null value inside the gate's own 70%
    TRAIN split. Box-detail coverage only starts 2026-01-20; games.parquet
    spans 2022-10-18..2026-04-12, so the standard walk-forward split's train
    window (first 70% by date) can predate the feature entirely. When it does,
    _gate_once's train-stats standardization (mean/std of an all-NaN column)
    degenerates every test-row feature value to 0 -- the resulting REJECT is
    a no-signal-reached-the-fit artifact, NOT a real evaluated test, and must
    be labelled NOT_TESTABLE rather than reported as an honest REJECT."""
    df = _eval.build_candidate_frame(
        asof=pd.read_parquet(_BOXDETAIL_ASOF), feat_col=feat_col)
    split = int(len(df) * _eval.TRAIN_FRAC)
    return bool(df.iloc[:split][feat_col].notna().any())


def run_sweep(seed: int = 0, out_dir: Path = _OUT_DIR) -> List[Dict]:
    """Gate the 4 declared box-detail diffs; write one verdict JSON per feature + summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict] = []
    for feat_col in GATED_FEATURES:
        res = _eval.gate_feature(feat_col, asof_path=str(_BOXDETAIL_ASOF), seed=seed)
        has_train_signal = _train_window_has_coverage(feat_col, seed=seed)
        verdict = _verdict_of(res) if has_train_signal else "NOT_TESTABLE"
        payload = {
            "component": "boxdetail_gate",
            "sport": "basketball_nba",
            "feature": feat_col,
            "hypothesis": f"{feat_col} (leak-free prior-only trailing diff) beats "
                          "Elo-only base on held-out Brier for NBA home-win probability",
            "verdict": verdict,
            "n_rows": res["n_rows"],
            "cov_total": res["cov_total"],
            "cov_pct": res["cov_pct"],
            "real": res["real"],
            "planted_null": res["planted_null"],
            "truncation": res["truncation"],
            "note": (
                "NOT_TESTABLE: the feature's entire on-disk history (box-detail "
                "starts 2026-01-20) falls after this gate's 70% train cutoff "
                "(2025-03-06), so train-stats standardization sees an all-NaN "
                "column and degenerates every test-row value to 0 -- the "
                "real/null/truncation numbers above are the resulting no-signal "
                "artifact, not an evaluated REJECT. No edge claimed."
                if not has_train_signal else
                "calibration-only; REJECT is an honest success; no edge claimed; "
                "thin single-season slice (box-detail only 2026-01-20 onward)"
            ),
        }
        _assert_no_banned_tokens(payload)
        (out_dir / f"boxdetail_gate_{feat_col}.json").write_text(
            json.dumps(payload, indent=1), encoding="ascii", errors="replace",
        )
        rows.append(payload)

    summary = {
        "component": "boxdetail_gate_summary",
        "sport": "basketball_nba",
        "features_gated": len(rows),
        "verdicts": {r["feature"]: r["verdict"] for r in rows},
        "note": "calibration-only; SHIP requires planted-null REJECT + truncation-"
                "invariant real SHIP; no edge claimed; entering the interaction factory "
                "(family=box_detail_asof) is the real value here, not a pregame verdict",
    }
    _assert_no_banned_tokens(summary)
    (out_dir / "boxdetail_gate_summary.json").write_text(
        json.dumps(summary, indent=1), encoding="ascii", errors="replace",
    )
    return rows


def main() -> int:
    rows = run_sweep()
    print("=" * 72)
    print("NBA box-detail as-of gate -- 4 features vs Elo base (single-corpus WF gate)")
    print("=" * 72)
    for r in rows:
        rl = r["real"]
        print(f"\n{r['feature']:>26s}  verdict={r['verdict']:<7s}  "
              f"cov={r['cov_total']}/{r['n_rows']} ({r['cov_pct']}%)")
        print(f"   REAL  Brier base {rl['brier_base']:.6f}  cand {rl['brier_cand']:.6f}"
              f"  delta {rl['brier_delta']:+.6f}  DM p={rl['dm_p']:.4f}")
        nn = r["planted_null"]
        print(f"   NULL  verdict={nn['verdict']}  (must be REJECT)")
        tr = r["truncation"]
        print(f"   TRUNC verdict={tr['verdict']}  (must match REAL)")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    print(f"\nWrote {len(rows)} per-feature verdict JSONs + boxdetail_gate_summary.json "
          f"under {_OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
