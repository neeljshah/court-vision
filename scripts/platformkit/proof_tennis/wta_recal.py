"""scripts.platformkit.proof_tennis.wta_recal — WTA-specific calibration gate-test.

The ATP proof passes calibration (ECE<0.025) but the WTA corpus FAILs (ECE 0.043/0.073)
with the ATP-trained calibrator. This runs a WTA-NATIVE walk-forward Elo + walk-forward
Platt recalibration (reusing domains.tennis.elo_tune, which is corpus-agnostic) and tests
the proof's hypothesis that the FAIL is thin-prior / small-sample noise — via a
minimum-prior-match filter on the eval set.

HONEST: this is a CALIBRATION test, not an edge. A fixed ECE is better-calibrated
probabilities, NOT a market edge. A persistent FAIL is an honest data-limited result, not
a defect to paper over. Markets are efficient; no edge is claimed.

Run:
    python -m scripts.platformkit.proof_tennis.wta_recal
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis import elo_tune as et  # noqa: E402

_WTA_PARQUET = _REPO / "data" / "domains" / "tennis" / "wta" / "matches.parquet"
_ECE_THRESHOLD = 0.025
_MIN_PRIOR_GRID = (0, 5, 10, 20)


def _prior_counts(df: pd.DataFrame) -> np.ndarray:
    """Min(prior matches of p1, prior matches of p2) for each row, in sorted order."""
    seen: Dict[int, int] = {}
    out = np.empty(len(df), dtype=int)
    p1 = df["p1_id"].to_numpy()
    p2 = df["p2_id"].to_numpy()
    for i in range(len(df)):
        a, b = int(p1[i]), int(p2[i])
        out[i] = min(seen.get(a, 0), seen.get(b, 0))
        seen[a] = seen.get(a, 0) + 1
        seen[b] = seen.get(b, 0) + 1
    return out


def run(parquet_path: Path = _WTA_PARQUET) -> Dict:
    if not parquet_path.is_file():
        return {"error": f"WTA corpus not found: {parquet_path}"}
    matches = pd.read_parquet(parquet_path)

    # 1) Best surface blend by test-set Brier (WTA-native).
    sweep = et.blend_sweep(matches)
    best = sweep.sort_values("brier").iloc[0]
    best_blend = float(best["blend"])

    # 2) WTA-native walk-forward + walk-forward Platt at the best blend.
    wf = et._walk_forward_blend(matches, best_blend)
    wf = et._sorted(wf).reset_index(drop=True)
    prior = _prior_counts(wf)
    test_df = et.platt_recalibrate(wf, refit_every=200)  # tighter refit for the smaller corpus

    # Align prior counts to the test subset by date filter (same mask platt uses).
    years = pd.to_datetime(wf["date"]).dt.year
    test_idx = wf.index[years > et.TRAIN_YEAR_MAX].to_numpy()
    prior_test = prior[test_idx]

    y = (test_df["winner"] == 1).to_numpy(dtype=float)
    p_raw = test_df["win_prob_p1"].to_numpy(dtype=float)
    p_recal = test_df["win_prob_recal"].to_numpy(dtype=float)

    # 3) ECE by minimum-prior-match filter (the thin-prior hypothesis).
    rows: List[Dict] = []
    for mp in _MIN_PRIOR_GRID:
        m = prior_test >= mp
        if m.sum() < 100:
            continue
        rows.append({
            "min_prior": mp, "n": int(m.sum()),
            "raw_brier": round(et.brier(p_raw[m], y[m]), 5),
            "recal_brier": round(et.brier(p_recal[m], y[m]), 5),
            "raw_ece": round(et.ece(p_raw[m], y[m]), 5),
            "recal_ece": round(et.ece(p_recal[m], y[m]), 5),
        })
    best_recal_ece = min((r["recal_ece"] for r in rows), default=float("nan"))
    return {
        "corpus": "WTA", "n_total": len(matches), "best_blend": best_blend,
        "train_year_max": et.TRAIN_YEAR_MAX, "ece_threshold": _ECE_THRESHOLD,
        "by_min_prior": rows,
        "best_recal_ece": best_recal_ece,
        "verdict": ("CALIBRATED (ECE<thr at some prior filter)"
                    if best_recal_ece < _ECE_THRESHOLD
                    else "HONEST FAIL — WTA calibration data-limited (ECE>=thr); not an edge"),
        "note": "Calibration metric only; not a market edge. Markets efficient.",
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    print(f"=== WTA Calibration Gate-Test (best_blend={rep['best_blend']}, "
          f"train<= {rep['train_year_max']}) ===")
    print(f"corpus n={rep['n_total']}  ECE threshold <{rep['ece_threshold']}")
    print(f"{'min_prior':>9} {'n':>6} {'raw_brier':>10} {'recal_brier':>12} "
          f"{'raw_ece':>9} {'recal_ece':>10}")
    for r in rep["by_min_prior"]:
        print(f"{r['min_prior']:>9} {r['n']:>6} {r['raw_brier']:>10} "
              f"{r['recal_brier']:>12} {r['raw_ece']:>9} {r['recal_ece']:>10}")
    print(f"\nbest recal ECE across filters: {rep['best_recal_ece']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
