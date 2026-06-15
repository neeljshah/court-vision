"""scripts.platformkit.proof_nba.totals_calibration — NBA O/U totals calibration.

The platform scores NBA MONEYLINE Brier only; the total-points line has NEVER been
calibration-tested (NBA_Edge_Map "Total-line and spread calibration are not gate-tested").
This builds a simple LEAK-FREE walk-forward totals model (EW points-for/against per team,
snapshot-before-update) and measures its O/U calibration (ECE/Brier + a Gaussian sigma fit
on the FIRST half, applied to the held-out SECOND half) against realized totals over the
1,299-game postmortem corpus.

HONEST: calibration metric only, NOT an edge; markets efficient. The realized-totals
corpus (postmortem 2024-26) overlaps the closing-total odds (2025-26) on only ~74 games,
so the model-vs-market comparison is reported as a DATA-LIMITED side note, never an edge.

INVARIANTS: never edit src/ or kernel/; reuse domain data only; <=300 LOC.

Run:
    python -m scripts.platformkit.proof_nba.totals_calibration
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_ALPHA = 0.05            # EW update rate
_INIT_PF = 113.3         # half of league mean total (~226.6)
_LINES: Tuple[float, ...] = (205.5, 210.5, 215.5, 220.5, 225.5, 230.5, 235.5, 240.5)
_MIN_TOTAL, _MAX_TOTAL = 150.0, 350.0   # drop corrupt rows (regulation totals are in-range)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(e)


def _load() -> pd.DataFrame:
    pm = pd.read_parquet(_NBA / "postmortem.parquet")
    if "date" in pm.columns:
        pm = pm.drop(columns=[c for c in ("date", "season") if c in pm.columns])
    g = pd.read_parquet(_NBA / "games.parquet")[["game_id", "date"]]
    df = pm.merge(g, on="game_id", how="inner")
    df["date"] = pd.to_datetime(df["date"])
    df["total"] = df["home_pts"].astype(float) + df["away_pts"].astype(float)
    df = df[(df["total"] >= _MIN_TOTAL) & (df["total"] <= _MAX_TOTAL)]
    return df.sort_values("date").reset_index(drop=True)


def _walk_forward(df: pd.DataFrame) -> np.ndarray:
    """Leak-free predicted total per game (snapshot EW PF/PA, then update)."""
    pf: Dict[str, float] = {}
    pa: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_team"].to_numpy()
    a = df["away_team"].to_numpy()
    hp = df["home_pts"].to_numpy(dtype=float)
    ap = df["away_pts"].to_numpy(dtype=float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            pf.setdefault(t, _INIT_PF)
            pa.setdefault(t, _INIT_PF)
        # snapshot BEFORE update: E[home_pts]=avg(home PF, away PA), symmetric for away
        exp_home = 0.5 * (pf[ht] + pa[at])
        exp_away = 0.5 * (pf[at] + pa[ht])
        pred[i] = exp_home + exp_away
        pf[ht] += _ALPHA * (hp[i] - pf[ht]); pa[ht] += _ALPHA * (ap[i] - pa[ht])
        pf[at] += _ALPHA * (ap[i] - pf[at]); pa[at] += _ALPHA * (hp[i] - pa[at])
    return pred


def _odds_overlap(df: pd.DataFrame, pred: np.ndarray) -> Dict:
    p = _NBA / "odds.parquet"
    if not p.is_file():
        return {"status": "no_odds_file"}
    od = pd.read_parquet(p)
    od["date"] = pd.to_datetime(od["date"])
    j = df.assign(pred_total=pred).merge(
        od[["date", "home_team", "away_team", "total"]].rename(columns={"total": "close_total"}),
        on=["date", "home_team", "away_team"], how="inner")
    j = j[j["close_total"].notna()]
    if len(j) < 30:
        return {"status": "data_limited", "n_overlap": int(len(j))}
    y = (j["total"] > j["close_total"]).to_numpy(dtype=float)
    return {
        "status": "ok", "n_overlap": int(len(j)),
        "p_realized_over_close": round(float(y.mean()), 3),  # efficient ~0.5
        "corr_pred_vs_close": round(float(np.corrcoef(j["pred_total"], j["close_total"])[0, 1]), 3),
        "model_mae_vs_close": round(float(np.abs(j["pred_total"] - j["close_total"]).mean()), 2),
    }


def run() -> Dict:
    if not (_NBA / "postmortem.parquet").is_file():
        return {"error": "NBA postmortem corpus not found"}
    df = _load()
    pred = _walk_forward(df)
    total = df["total"].to_numpy(dtype=float)
    resid = total - pred
    n = len(df)
    mid = n // 2
    sigma = float(np.std(resid[:mid]))          # leak-free: fit sigma on first half only
    bias = float(np.mean(resid[:mid]))          # centre the model on the first half too

    # SHAPE FIX (leak-free): the EW point model is UNDER-dispersed (realized~pred slope>1),
    # so predictions cluster near the mean. Fit a linear recalibration total = a + b*pred on
    # the FIRST half and stretch the prediction's dispersion; refit sigma on corrected resid.
    b, a = np.polyfit(pred[:mid], total[:mid], 1)
    pred_corr = a + b * pred
    sigma_corr = float(np.std(total[:mid] - pred_corr[:mid]))

    te = slice(mid, n)                          # held-out second half
    tot_te = total[te]

    def _surface(pt_arr: np.ndarray, sig: float) -> Tuple[float, float, List[Dict]]:
        all_p: List[float] = []
        all_y: List[float] = []
        rows: List[Dict] = []
        for ln in _LINES:
            p_over = np.array([1.0 - _phi((ln - pt) / sig) for pt in pt_arr])
            y = (tot_te > ln).astype(float)
            rows.append({"line": ln, "n": int(len(y)), "base_over": round(float(y.mean()), 3),
                         "ece": round(_ece(p_over, y), 4),
                         "brier": round(float(np.mean((p_over - y) ** 2)), 4)})
            all_p.extend(p_over.tolist()); all_y.extend(y.tolist())
        ap_, ay_ = np.array(all_p), np.array(all_y)
        return _ece(ap_, ay_), float(np.mean((ap_ - ay_) ** 2)), rows

    ece_raw, brier_raw, per_line = _surface(pred[te] + bias, sigma)
    ece_corr, brier_corr, _ = _surface(pred_corr[te], sigma_corr)
    sl = float(np.polyfit(pred[te], tot_te, 1)[0])
    improved = ece_corr < ece_raw - 1e-4
    return {
        "market": "nba_total", "n_games": n, "n_holdout": int(n - mid),
        "resid_sigma": round(sigma, 2), "resid_bias_train": round(bias, 2),
        "pooled_ece": round(ece_raw, 4), "pooled_brier": round(brier_raw, 4),
        "regression_slope_realized_on_pred": round(sl, 3),
        "dispersion_fix": {"slope_b": round(float(b), 3), "sigma_corr": round(sigma_corr, 2),
                           "ece_corrected": round(ece_corr, 4), "brier_corrected": round(brier_corr, 4),
                           "ece_delta": round(ece_corr - ece_raw, 4), "improves": improved},
        "per_line": per_line,
        "odds_overlap": _odds_overlap(df, pred),
        "verdict": (f"SHAPE FIX wins: dispersion-correction improves pooled ECE "
                    f"{round(ece_raw,4)} -> {round(ece_corr,4)} (under-dispersion was the defect)"
                    if improved else
                    f"dispersion-correction does not improve pooled ECE ({round(ece_corr,4)} "
                    f"vs {round(ece_raw,4)}); model already ECE {round(ece_raw,4)}"),
        "note": ("Calibration metric only; NOT a market edge. Realized-totals vs closing-line "
                 "overlap is data-limited (~73 games) so model-vs-market is a side note, not an edge."),
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    print(f"=== NBA Totals O/U Calibration (n={rep['n_games']}, holdout={rep['n_holdout']}, "
          f"sigma={rep['resid_sigma']}, bias={rep['resid_bias_train']}) ===")
    print(f"{'line':>7} {'n':>5} {'base':>6} {'ece':>8} {'brier':>8}")
    for r in rep["per_line"]:
        print(f"{r['line']:>7} {r['n']:>5} {r['base_over']:>6} {r['ece']:>8} {r['brier']:>8}")
    print(f"\npooled ECE={rep['pooled_ece']}  pooled Brier={rep['pooled_brier']}  "
          f"reliability slope={rep['regression_slope_realized_on_pred']} (>1 = under-dispersed)")
    d = rep["dispersion_fix"]
    print(f"dispersion SHAPE fix (b={d['slope_b']}, sigma_corr={d['sigma_corr']}): "
          f"ECE {rep['pooled_ece']} -> {d['ece_corrected']} (delta {d['ece_delta']:+}) "
          f"{'IMPROVES' if d['improves'] else 'no improvement'}")
    print(f"odds overlap: {rep['odds_overlap']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
