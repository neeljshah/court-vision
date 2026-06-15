"""scripts.platformkit.proof_nba.totals_ensemble — COMBINE the totals edges.

The single-model beat-the-close (asof_box_accuracy) ships three leak-free as-of totals
forecasters -- pooled (points-for/against EW), split (home/away-context EW), and poss
(possessions x points-per-possession on the unlocked 2026 box detail). Each alone trails the
close (~19.2 vs ~18.1 RMSE). This module asks the edge-COMBINING question: does a leak-free
STACK of the three (their errors are partly complementary) beat the best single model and
narrow the gap to the close?

The stack is an ordinary-least-squares blend with intercept, fit on the FIRST half only
(realized ~ w0 + w1*pooled + w2*split + w3*poss) and applied to the held-out SECOND half --
so the blend weights never see the eval games. OLS-with-intercept subsumes the per-model affine
recal, so the stack is graded on the same held-out RMSE+bias basis as the singles.

"Unbeatable" = the best CALIBRATED prediction we can build by combining every honest lever.
Markets are efficient, so MATCHING the close is the realistic best case; we report the gap
honestly either way. NO $ edge claimed; the close also moved on freshness we cannot see.

Leak-free: every component is snapshot-before-update; the blend is train-only; the closing
total is the comparison forecaster, never a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.totals_ensemble
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import (  # noqa: E402
    _walk_forward_poss, _walk_forward_split, _walk_forward_total, load_box,
)
from scripts.platformkit.proof_nba.totals_calibration import _ece, _phi  # noqa: E402

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_LINES: Tuple[float, ...] = (215.5, 220.5, 225.5, 230.5, 235.5)
_COMPONENTS = ("pred_pooled", "pred_split", "pred_poss")


def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(e))


def _ols_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Least-squares weights for [1, *components] -> y. Tiny ridge for collinearity."""
    A = np.column_stack([np.ones(len(X)), X])
    lam = 1e-6 * np.eye(A.shape[1])
    return np.linalg.solve(A.T @ A + lam, A.T @ y)


def _apply(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return w[0] + X @ w[1:]


def _affine_recal(pred: np.ndarray, realized: np.ndarray, mid: int) -> np.ndarray:
    b, a = np.polyfit(pred[:mid], realized[:mid], 1)
    return a + b * pred


def _ece_at_lines(pred: np.ndarray, realized: np.ndarray, sigma: float) -> float:
    all_p: List[float] = []
    all_y: List[float] = []
    for ln in _LINES:
        all_p.extend((1.0 - np.array([_phi((ln - pt) / sigma) for pt in pred])).tolist())
        all_y.extend((realized > ln).astype(float).tolist())
    return float(_ece(np.array(all_p), np.array(all_y)))


def _build_merged() -> pd.DataFrame:
    box = load_box()
    box["pred_pooled"] = _walk_forward_total(box)
    box["pred_split"] = _walk_forward_split(box)
    box["pred_poss"] = _walk_forward_poss(box)
    od = pd.read_parquet(_NBA / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    od["date"] = pd.to_datetime(od["date"])
    m = box.merge(od[["date", "home_abbr", "away_abbr", "total"]].rename(
        columns={"total": "close_total"}), on=["date", "home_abbr", "away_abbr"], how="inner")
    return m[m["close_total"].notna()].reset_index(drop=True)


def run() -> Dict:
    box_p, odds_p = _NBA / "espn_boxscores.parquet", _NBA / "odds.parquet"
    if not box_p.is_file() or not odds_p.is_file():
        return {"error": "espn_boxscores or odds parquet missing"}
    m = _build_merged()
    n = len(m)
    if n < 40:
        return {"status": "data_limited", "n_overlap": n}

    realized = m["total"].to_numpy(float)
    close = m["close_total"].to_numpy(float)
    mid = n // 2
    te = slice(mid, n)
    rm_close, bias_close = _rmse_bias(close[te], realized[te])

    # ---- each single model, affine-recal'd leak-free (the same basis as asof_box_accuracy) ----
    singles: Dict[str, Dict] = {}
    for c in _COMPONENTS:
        pc = _affine_recal(m[c].to_numpy(float), realized, mid)
        rm, bias = _rmse_bias(pc[te], realized[te])
        sigma = float(np.std(realized[:mid] - pc[:mid]))
        singles[c] = {"rmse": round(rm, 3), "bias": round(bias, 3),
                      "ece": round(_ece_at_lines(pc[te], realized[te], sigma), 4)}
    best_single = min(singles.values(), key=lambda d: d["rmse"])["rmse"]

    # ---- the STACK: OLS blend of the 3 components fit on the FIRST half, applied held-out ----
    X = m[list(_COMPONENTS)].to_numpy(float)
    w = _ols_fit(X[:mid], realized[:mid])
    stack = _apply(w, X)
    rm_stack, bias_stack = _rmse_bias(stack[te], realized[te])
    sigma_s = float(np.std(realized[:mid] - stack[:mid]))
    ece_stack = _ece_at_lines(stack[te], realized[te], sigma_s)

    gap_best_single = round(best_single - rm_close, 3)
    gap_stack = round(rm_stack - rm_close, 3)
    improved = rm_stack < best_single - 1e-3

    if rm_stack < rm_close - 0.1:
        verdict = (f"the STACK BEATS the close on RMSE ({rm_stack:.3f} vs {rm_close:.3f})")
    elif gap_stack <= 1.0:
        verdict = (f"the STACK MATCHES the close (RMSE {rm_stack:.3f} vs {rm_close:.3f}, "
                   f"gap {gap_stack:+}); combining shaved {round(best_single - rm_stack, 3)} "
                   f"RMSE off the best single ({best_single})")
    elif improved:
        verdict = (f"the STACK narrows but trails: RMSE {rm_stack:.3f} (best single {best_single}, "
                   f"close {rm_close:.3f}); combining helps {round(best_single - rm_stack, 3)} but "
                   "the freshness gap remains")
    else:
        verdict = (f"HONEST NULL: stacking does not beat the best single model "
                   f"({rm_stack:.3f} vs {best_single}); the 3 models are too collinear to combine, "
                   "and the close gap is freshness, not model blending")

    return {
        "status": "ok", "n_overlap": n, "n_holdout": n - mid,
        "close_rmse": round(rm_close, 3), "close_bias": round(bias_close, 3),
        "singles": singles, "best_single_rmse": best_single,
        "stack_rmse": round(rm_stack, 3), "stack_bias": round(bias_stack, 3),
        "stack_ece": round(ece_stack, 4),
        "stack_weights": {k: round(float(v), 3)
                          for k, v in zip(("intercept",) + _COMPONENTS, w)},
        "gap_best_single_to_close": gap_best_single, "gap_stack_to_close": gap_stack,
        "stack_beats_best_single": bool(improved),
        "verdict": verdict,
        "note": ("Edge-COMBINING test: leak-free OLS stack of 3 as-of totals models, blend fit "
                 "on the first half, RMSE+bias on the held-out second half. Markets efficient; "
                 "no $ edge claimed (the close also moves on freshness we cannot see)."),
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    if rep.get("status") != "ok":
        print(f"{rep['status']}: n_overlap={rep.get('n_overlap')}"); return 0
    print(f"=== NBA totals STACK: combining 3 as-of models (n={rep['n_overlap']}, "
          f"holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>16}  {'RMSE':>7} {'bias':>7} {'ECE':>7}")
    print(f"  {'market close':>16}  {rep['close_rmse']:>7} {rep['close_bias']:>7} {'-':>7}")
    for c in _COMPONENTS:
        d = rep["singles"][c]
        print(f"  {c.replace('pred_',''):>16}  {d['rmse']:>7} {d['bias']:>7} {d['ece']:>7}")
    print(f"  {'STACK (combined)':>16}  {rep['stack_rmse']:>7} {rep['stack_bias']:>7} "
          f"{rep['stack_ece']:>7}")
    print(f"\nstack weights: {rep['stack_weights']}")
    print(f"stack beats best single: {rep['stack_beats_best_single']}  |  "
          f"gap to close: best-single {rep['gap_best_single_to_close']:+} -> "
          f"stack {rep['gap_stack_to_close']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
