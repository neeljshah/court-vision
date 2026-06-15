"""scripts.platformkit.proof_soccer.division_calibration — per-division O/U-2.5 calibration.

The soccer O/U-2.5 model pools all 6 divisions and uses a GLOBAL league_mu, so each
division inherits a systematic bias from the shared baseline (high-scoring D1 vs
low-scoring E1). This DIAGNOSES the per-division miscalibration and TESTS whether a
per-division recalibrator (Platt on the logit, fit per division) beats the pooled one —
a CALIBRATION improvement (better ECE/reliability), NOT an edge.

Leak-free: p_over25 comes from the walk-forward leak-free engine (domains.soccer.ratings);
the recalibrators are fit on the EARLIER train split and evaluated on the held-out LATER
split, per division. Mean-offset corrections improve ECE; they are NOT a market edge
(markets efficient). A division that is already well-calibrated needs no correction.

INVARIANTS: never edit src/ or kernel/; reuse domains.soccer; <=300 LOC.

Run:
    python -m scripts.platformkit.proof_soccer.division_calibration
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

from domains.soccer.ratings import walk_forward_goals  # noqa: E402

_MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_EPS = 1e-6
_TEST_FRAC = 0.30
_ECE_BINS = 10


def _ece(p: np.ndarray, y: np.ndarray, bins: int = _ECE_BINS) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += (m.mean()) * abs(p[m].mean() - y[m].mean())
    return float(e)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _cox_slope(p: np.ndarray, y: np.ndarray) -> float:
    """Cox calibration slope: logit(y) ~ a + b*logit(p). b<1 = over-confident."""
    from sklearn.linear_model import LogisticRegression

    lg = np.log(np.clip(p, _EPS, 1 - _EPS) / (1 - np.clip(p, _EPS, 1 - _EPS)))
    if len(np.unique(y)) < 2:
        return float("nan")
    clf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500)
    clf.fit(lg.reshape(-1, 1), y)
    return float(clf.coef_[0, 0])


def _fit_platt(p: np.ndarray, y: np.ndarray):
    """Return a logit->prob recalibrator fit on (p,y); None if degenerate."""
    from sklearn.linear_model import LogisticRegression

    if len(p) < 50 or len(np.unique(y)) < 2:
        return None
    lg = np.log(np.clip(p, _EPS, 1 - _EPS) / (1 - np.clip(p, _EPS, 1 - _EPS)))
    clf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500)
    clf.fit(lg.reshape(-1, 1), y)
    return clf


def _apply(clf, p: np.ndarray) -> np.ndarray:
    if clf is None:
        return p
    lg = np.log(np.clip(p, _EPS, 1 - _EPS) / (1 - np.clip(p, _EPS, 1 - _EPS)))
    return clf.predict_proba(lg.reshape(-1, 1))[:, 1]


def run(matches_path: Path = _MATCHES) -> Dict:
    if not matches_path.is_file():
        return {"error": f"soccer corpus not found: {matches_path}"}
    df = pd.read_parquet(matches_path)
    wf = walk_forward_goals(df).reset_index(drop=True)
    wf = wf.sort_values("date").reset_index(drop=True)
    if "total_goals" in wf:
        y_all = (wf["total_goals"].to_numpy(dtype=float) > 2.5).astype(float)
    else:
        y_all = ((wf["fthg"] + wf["ftag"]).to_numpy(dtype=float) > 2.5).astype(float)
    p_all = wf["p_over25"].to_numpy(dtype=float)
    div_all = wf["div"].to_numpy()

    n = len(wf)
    cut = int(n * (1 - _TEST_FRAC))
    train, test = slice(0, cut), slice(cut, n)

    # Pooled Platt (one recalibrator for all divisions).
    pooled = _fit_platt(p_all[train], y_all[train])
    # Per-division Platt (one recalibrator per division), fit on train rows of that div.
    per_div = {d: _fit_platt(p_all[train][div_all[train] == d], y_all[train][div_all[train] == d])
               for d in np.unique(div_all)}

    rows: List[Dict] = []
    agg = {"raw": ([], []), "pooled": ([], []), "perdiv": ([], [])}
    for d in sorted(np.unique(div_all)):
        m = (div_all == d) & (np.arange(n) >= cut)   # test rows of this division
        if m.sum() < 80:
            continue
        pr, yt = p_all[m], y_all[m]
        p_pool = _apply(pooled, pr)
        p_pd = _apply(per_div.get(d), pr)
        rows.append({
            "div": str(d), "n_test": int(m.sum()),
            "base_over": round(float(yt.mean()), 4),
            "mean_pred_raw": round(float(pr.mean()), 4),
            "bias_raw": round(float(pr.mean() - yt.mean()), 4),
            "ece_raw": round(_ece(pr, yt), 4), "ece_pooled": round(_ece(p_pool, yt), 4),
            "ece_perdiv": round(_ece(p_pd, yt), 4),
            "brier_raw": round(_brier(pr, yt), 4), "brier_perdiv": round(_brier(p_pd, yt), 4),
            "cox_slope_raw": round(_cox_slope(pr, yt), 3),
        })
        for k, arr in (("raw", pr), ("pooled", p_pool), ("perdiv", p_pd)):
            agg[k][0].append(arr); agg[k][1].append(yt)

    overall = {k: round(_ece(np.concatenate(v[0]), np.concatenate(v[1])), 4)
               for k, v in agg.items() if v[0]}
    worst = max(rows, key=lambda r: r["ece_raw"]) if rows else None
    # Honest comparison: does PER-DIVISION recal beat the simpler POOLED recal?
    perdiv_beats_pooled = [r["div"] for r in rows if r["ece_perdiv"] < r["ece_pooled"] - 1e-3]
    o_pool, o_pdiv = overall.get("pooled", 0.0), overall.get("perdiv", 1.0)
    if o_pdiv < o_pool - 1e-4:
        verdict = "per-division recal beats pooled overall (calibration, not edge)"
    else:
        verdict = (f"REFUTED overall: per-division recal does NOT beat pooled (ECE "
                   f"{o_pdiv} vs {o_pool}) — per-division mean-shift is ABSORBED by the "
                   f"pooled recal (NULL pattern). Exception: {perdiv_beats_pooled or 'none'} "
                   f"benefit per-division. The real win is the POOLED recal of the "
                   f"over-confident engine (ECE {overall.get('raw')} -> {o_pool}).")
    return {
        "market": "over_2.5", "n_total": n, "test_frac": _TEST_FRAC,
        "per_division": rows, "overall_ece": overall,
        "worst_raw_division": (worst["div"], worst["ece_raw"]) if worst else None,
        "perdiv_beats_pooled_divisions": perdiv_beats_pooled,
        "verdict": verdict,
        "note": "Calibration metric only; per-division mean-offset is NOT a market edge. Markets efficient.",
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    print(f"=== Soccer per-division O/U-2.5 calibration (n={rep['n_total']}, "
          f"test_frac={rep['test_frac']}) ===")
    print(f"{'div':>4} {'n':>5} {'base':>6} {'pred':>6} {'bias':>7} "
          f"{'ece_raw':>8} {'ece_pool':>9} {'ece_pdiv':>9} {'cox_slope':>10}")
    for r in rep["per_division"]:
        print(f"{r['div']:>4} {r['n_test']:>5} {r['base_over']:>6} {r['mean_pred_raw']:>6} "
              f"{r['bias_raw']:>+7} {r['ece_raw']:>8} {r['ece_pooled']:>9} "
              f"{r['ece_perdiv']:>9} {r['cox_slope_raw']:>10}")
    print(f"\noverall ECE: {rep['overall_ece']}")
    print(f"worst raw division: {rep['worst_raw_division']}  |  "
          f"per-div beats POOLED in: {rep['perdiv_beats_pooled_divisions'] or 'none'}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
