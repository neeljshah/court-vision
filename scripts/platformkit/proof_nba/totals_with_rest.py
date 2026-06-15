"""scripts.platformkit.proof_nba.totals_with_rest — add REST (the one backtest-able
freshness signal) to the NBA totals model and re-measure vs the market close.

W139 showed richer box data closes 18% of the gap; the rest is the market's FRESHNESS edge.
Rest / back-to-backs (b2b) is the only freshness signal derivable from history (game dates),
so it is the one piece of the freshness gap we can actually backtest. Tired / b2b teams play
at a different pace and efficiency.

Model: multi-feature OLS on (possessions-model base prediction, home/away b2b flags, capped
rest days), fit on the FIRST half, scored on the held-out SECOND half, vs the closing total.
Leak-free: rest is computed from prior game dates only; the base model is leak-free EW.

HONEST: a CALIBRATION/accuracy test. If rest closes more of the gap, our predictions got
better; if not (rest is public + priced), that is an honest null. No $ edge claimed.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.totals_with_rest
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import (  # noqa: E402
    _rmse_mae, _walk_forward_poss, load_box, load_close,
)

_REST_CAP = 4.0   # rest days beyond this stop mattering


def _rest_features(box: pd.DataFrame) -> pd.DataFrame:
    """Per-game home/away rest days (since each team's prior game) + b2b flags. Leak-free."""
    last: Dict[str, pd.Timestamp] = {}
    hr = np.empty(len(box)); ar = np.empty(len(box))
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    dt = box["date"].to_numpy()
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        d = pd.Timestamp(dt[i])
        hr[i] = (d - last[ht]).days if ht in last else 3.0
        ar[i] = (d - last[at]).days if at in last else 3.0
        last[ht] = d; last[at] = d
    out = box.copy()
    out["home_rest"] = np.clip(hr, 0, _REST_CAP)
    out["away_rest"] = np.clip(ar, 0, _REST_CAP)
    out["home_b2b"] = (hr <= 1).astype(float)
    out["away_b2b"] = (ar <= 1).astype(float)
    return out


def _ols_eval(X: np.ndarray, y: np.ndarray, mid: int) -> Tuple[float, float]:
    """Fit OLS on first half, RMSE/MAE on held-out second half."""
    coef, *_ = np.linalg.lstsq(X[:mid], y[:mid], rcond=None)
    pred = X[mid:] @ coef
    return _rmse_mae(pred, y[mid:])


def run() -> Dict:
    if not (_REPO / "data/domains/basketball_nba/espn_boxscores.parquet").is_file():
        return {"error": "espn box parquet missing"}
    box = _rest_features(load_box())
    box["base"] = _walk_forward_poss(box)
    m = box.merge(load_close(), on=["date", "home_abbr", "away_abbr"], how="inner")
    m = m[m["close_total"].notna()].reset_index(drop=True)
    n = len(m)
    if n < 60:
        return {"status": "data_limited", "n_overlap": n,
                "note": "Ingest more 2025-26 games to grow the overlap."}

    y = m["total"].to_numpy(float)
    close = m["close_total"].to_numpy(float)
    mid = n // 2
    ones = np.ones(n)
    base = m["base"].to_numpy(float)
    feats = {k: m[k].to_numpy(float) for k in ("home_rest", "away_rest", "home_b2b", "away_b2b")}

    rm_close, mae_close = _rmse_mae(close[mid:], y[mid:])
    rm_base, mae_base = _ols_eval(np.column_stack([ones, base]), y, mid)
    X_rest = np.column_stack([ones, base, feats["home_b2b"], feats["away_b2b"],
                              feats["home_rest"], feats["away_rest"]])
    rm_rest, mae_rest = _ols_eval(X_rest, y, mid)

    # coefficient on b2b (fit on full data, for direction/size reporting only)
    coef, *_ = np.linalg.lstsq(X_rest, y, rcond=None)
    helps = rm_rest < rm_base - 0.05
    gap_base = round(rm_base - rm_close, 3)
    gap_rest = round(rm_rest - rm_close, 3)
    return {
        "status": "ok", "n_overlap": n, "n_holdout": n - mid,
        "close_rmse": round(rm_close, 3),
        "base_rmse": round(rm_base, 3), "rest_rmse": round(rm_rest, 3),
        "base_mae": round(mae_base, 3), "rest_mae": round(mae_rest, 3),
        "rest_rmse_gain": round(rm_base - rm_rest, 3),
        "gap_to_close_base": gap_base, "gap_to_close_rest": gap_rest,
        "b2b_coef_home": round(float(coef[2]), 2), "b2b_coef_away": round(float(coef[3]), 2),
        "rest_helps": helps,
        "verdict": (
            f"REST closes more of the gap: RMSE {round(rm_base,2)} -> {round(rm_rest,2)} "
            f"(gap to close {gap_base:+} -> {gap_rest:+})" if helps else
            f"REST does NOT help (RMSE {round(rm_base,2)} -> {round(rm_rest,2)}); fatigue is "
            f"public + priced, an honest null — the residual gap is injuries/lineups"),
        "note": "Calibration/accuracy test on real totals + closing lines. No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    if rep.get("status") != "ok":
        print(f"{rep['status']}: n={rep.get('n_overlap')}"); return 0
    print(f"=== NBA totals + REST vs the close (n={rep['n_overlap']}, holdout={rep['n_holdout']}) ===")
    print(f"  market close RMSE = {rep['close_rmse']}")
    print(f"  base (possessions)      RMSE={rep['base_rmse']}  MAE={rep['base_mae']}  "
          f"gap_to_close={rep['gap_to_close_base']:+}")
    print(f"  base + REST/b2b         RMSE={rep['rest_rmse']}  MAE={rep['rest_mae']}  "
          f"gap_to_close={rep['gap_to_close_rest']:+}")
    print(f"  b2b coefficient: home={rep['b2b_coef_home']}  away={rep['b2b_coef_away']} pts")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
