"""scripts.platformkit.proof_nba.asof_box_accuracy — does our OWN box data predict better?

The honest north-star test: on games where we have BOTH our (ESPN-ingested) box history AND
the market closing total, is a leak-free as-of model's predicted total a BETTER predictor of
the realized total than the market's closing line? (RMSE/MAE vs realized — lower wins.) And is
the model's O/U probability well-calibrated against the close?

"Beat the best predictions" = beat the closing total on accuracy. The market close is the
predictor to beat. We do NOT claim a $ edge (the book also moved on news we can't see); we
ask whether OUR DATA produces an at-least-as-accurate forecaster. More/own data -> we re-run
this as the corpus grows.

Leak-free: EW points-for/against per team, snapshot-before-update; the closing total is a
realized market datum, used only as the comparison forecaster, never as a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.asof_box_accuracy
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

from scripts.platformkit.proof_nba.totals_calibration import _ece, _phi  # noqa: E402

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_ALPHA = 0.05
_INIT_PF = 113.3
_LINES: Tuple[float, ...] = (215.5, 220.5, 225.5, 230.5, 235.5)
# ESPN emits inconsistent team abbreviations (GS/GSW, NY/NYK, NO/NOP, SA/SAS, UTAH/UTA,
# WSH/WAS) + All-Star junk; canonicalise to the odds-feed convention so the join lands.
_CANON = {"GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}


def _canon(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().replace(_CANON)


def _rmse_mae(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(np.abs(e)))


def _walk_forward_total(df: pd.DataFrame) -> np.ndarray:
    pf: Dict[str, float] = {}
    pa: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float); ap = df["away_pts"].to_numpy(float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            pf.setdefault(t, _INIT_PF); pa.setdefault(t, _INIT_PF)
        pred[i] = 0.5 * (pf[ht] + pa[at]) + 0.5 * (pf[at] + pa[ht])
        pf[ht] += _ALPHA * (hp[i] - pf[ht]); pa[ht] += _ALPHA * (ap[i] - pa[ht])
        pf[at] += _ALPHA * (ap[i] - pf[at]); pa[at] += _ALPHA * (hp[i] - pa[at])
    return pred


def run() -> Dict:
    box_p, odds_p = _NBA / "espn_boxscores.parquet", _NBA / "odds.parquet"
    if not box_p.is_file() or not odds_p.is_file():
        return {"error": "espn_boxscores or odds parquet missing"}
    box = pd.read_parquet(box_p)
    box["date"] = pd.to_datetime(box["date"], format="mixed", errors="coerce")
    box = box.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    box["home_abbr"] = _canon(box["home_abbr"])
    box["away_abbr"] = _canon(box["away_abbr"])
    # Use home_score/away_score (the final score == points, populated for ALL games);
    # home_pts/away_pts come from the box-stats table which the 2026 parse leaves null.
    box["home_pts"] = box["home_score"].astype(float)
    box["away_pts"] = box["away_score"].astype(float)
    box["total"] = box["home_pts"] + box["away_pts"]
    box = box[(box["total"] >= 150) & (box["total"] <= 350)].reset_index(drop=True)
    box["pred_total"] = _walk_forward_total(box)

    od = pd.read_parquet(odds_p).rename(columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    od["date"] = pd.to_datetime(od["date"])
    m = box.merge(od[["date", "home_abbr", "away_abbr", "total"]].rename(columns={"total": "close_total"}),
                  on=["date", "home_abbr", "away_abbr"], how="inner")
    m = m[m["close_total"].notna()].reset_index(drop=True)
    n = len(m)
    if n < 40:
        return {"status": "data_limited", "n_overlap": n,
                "note": "Ingest more 2025-26 games (ESPN reachable) to grow the box-vs-odds overlap."}

    realized = m["total"].to_numpy(float)
    model = m["pred_total"].to_numpy(float)
    close = m["close_total"].to_numpy(float)
    # leak-free affine recal of the model on the FIRST half, scored on the held-out SECOND half
    mid = n // 2
    b, a = np.polyfit(model[:mid], realized[:mid], 1)
    model_c = a + b * model
    sigma = float(np.std(realized[:mid] - model_c[:mid]))
    te = slice(mid, n)
    rm_model, mae_model = _rmse_mae(model_c[te], realized[te])
    rm_close, mae_close = _rmse_mae(close[te], realized[te])

    # model O/U calibration at standard lines on the holdout
    all_p, all_y = [], []
    for ln in _LINES:
        p_over = np.array([1.0 - _phi((ln - pt) / sigma) for pt in model_c[te]])
        y = (realized[te] > ln).astype(float)
        all_p.extend(p_over.tolist()); all_y.extend(y.tolist())
    model_ece = _ece(np.array(all_p), np.array(all_y))
    beats = rm_model < rm_close - 0.1
    matches = rm_model <= rm_close + 1.0
    return {
        "status": "ok", "n_overlap": n, "n_holdout": n - mid, "model_sigma": round(sigma, 2),
        "model_rmse_vs_realized": round(rm_model, 3), "close_rmse_vs_realized": round(rm_close, 3),
        "model_mae_vs_realized": round(mae_model, 3), "close_mae_vs_realized": round(mae_close, 3),
        "model_ou_ece": round(model_ece, 4),
        "verdict": (
            "OUR model BEATS the closing total on RMSE (better predictor)" if beats else
            ("our model MATCHES the close within ~1pt RMSE (competitive)" if matches else
             f"market close is sharper (model RMSE {round(rm_model,2)} vs close {round(rm_close,2)}) "
             f"— expected; need richer/fresher data to close the gap")),
        "note": ("Beat-the-best-predictions test on REAL realized totals + closing lines. "
                 "No $ edge claimed (book sees news we can't). Re-run as the corpus grows."),
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    if rep.get("status") != "ok":
        print(f"{rep['status']}: n_overlap={rep.get('n_overlap')} — {rep.get('note')}"); return 0
    print(f"=== NBA totals: OUR as-of box model vs the market close (n={rep['n_overlap']}, "
          f"holdout={rep['n_holdout']}, sigma={rep['model_sigma']}) ===")
    print(f"  RMSE vs realized:  model={rep['model_rmse_vs_realized']:>7}  "
          f"close={rep['close_rmse_vs_realized']:>7}")
    print(f"  MAE  vs realized:  model={rep['model_mae_vs_realized']:>7}  "
          f"close={rep['close_mae_vs_realized']:>7}")
    print(f"  model O/U ECE={rep['model_ou_ece']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
