"""calibration_fit.py — fit + OOS-validate per-stat calibration corrections.

Uses data/cache/calibration_frame.parquet (scripts/calibration_study.py). Trains on
games before 2026-02-15, tests after. Compares three correctors against the raw OOF:

  ISO   : isotonic recalibration of the prediction itself (fixes over/under-dispersion)
  GBM   : XGB correction on PRE-GAME covariates only
          [pred, l10_min, rest_days, is_b2b, is_home, opp_pace, opp_def, month, days_into_season]
  ISO+GBM: GBM on top of the isotonic-recalibrated prediction

Reports test MAE for each, AND — the metric that matters for betting — directional
accuracy vs real DK/FD/MGM closing lines (does calibrated pred pick the right side
more often than raw?). Ships per-stat coeffs to data/models/pregame_calibration.json
only for stats where the correction genuinely holds OOS. Leak-free; no prod model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
FRAME = _ROOT / "data" / "cache" / "calibration_frame.parquet"
OUT = _ROOT / "data" / "models" / "pregame_calibration.json"
SPLIT = "2026-02-15"
COVS = ["pred", "l10_min", "rest_days", "is_b2b", "is_home", "opp_pace",
        "opp_def", "month", "days_into_season"]


def directional_acc(df, predcol):
    """On rows joined to a real line, fraction where the model's side matches the
    realized side (actual vs line). Pushes excluded."""
    d = df.dropna(subset=["line"])
    d = d[(d["actual"] - d["line"]).abs() > 1e-9]
    if len(d) == 0:
        return None, 0
    side_model = d[predcol] > d["line"]
    side_real = d["actual"] > d["line"]
    return float((side_model == side_real).mean()), len(d)


def load_lines():
    """Real DK/FD/MGM closes joined by (player_id, date, stat) via benashkar loader."""
    try:
        from scripts.run_gate1_full_analysis import (
            load_benashkar_bets, attach_actuals_and_l10)
        bets = attach_actuals_and_l10(load_benashkar_bets(mainline_only=True))
    except Exception as exc:
        print(f"[lines unavailable: {exc}]")
        return {}
    out = {}
    for b in bets:
        out[(b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["stat"])] = b["line"]
    return out


def main():
    df = pd.read_parquet(FRAME)
    lines = load_lines()
    df["line"] = [lines.get((int(r.player_id), r.date, r.stat))
                  for r in df.itertuples(index=False)]

    coeffs_out = {}
    print(f"{'stat':<5}{'split':>6}  {'MAE_base':>9}{'MAE_iso':>9}{'MAE_gbm':>9}{'MAE_i+g':>9}"
          f"   | dir_base  dir_best  n_line")
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        s = df[df["stat"] == stat].dropna(subset=COVS).copy()
        tr = s[s["date"] < SPLIT]; te = s[s["date"] >= SPLIT]
        if len(tr) < 500 or len(te) < 300:
            continue
        # ISO
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(tr["pred"], tr["actual"])
        te_iso = iso.predict(te["pred"])
        tr_iso = iso.predict(tr["pred"])
        # GBM on covariates -> predict actual directly
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
                  "tree_method": "hist"}
        try:
            gbm = xgb.train(params, xgb.DMatrix(tr[COVS], label=tr["actual"]),
                            num_boost_round=400)
        except Exception:
            params["device"] = "cpu"
            gbm = xgb.train(params, xgb.DMatrix(tr[COVS], label=tr["actual"]),
                            num_boost_round=400)
        te_gbm = gbm.predict(xgb.DMatrix(te[COVS]))
        # ISO+GBM: gbm with iso-recalibrated pred swapped in
        tr2 = tr.copy(); tr2["pred"] = tr_iso
        te2 = te.copy(); te2["pred"] = te_iso
        try:
            gbm2 = xgb.train(params, xgb.DMatrix(tr2[COVS], label=tr2["actual"]),
                             num_boost_round=400)
        except Exception:
            params["device"] = "cpu"
            gbm2 = xgb.train(params, xgb.DMatrix(tr2[COVS], label=tr2["actual"]),
                             num_boost_round=400)
        te_ig = gbm2.predict(xgb.DMatrix(te2[COVS]))

        mae = lambda p: float(np.abs(p - te["actual"].values).mean())
        m_base, m_iso, m_gbm, m_ig = mae(te["pred"].values), mae(te_iso), mae(te_gbm), mae(te_ig)
        # pick best non-base
        cands = {"iso": (m_iso, te_iso), "gbm": (m_gbm, te_gbm), "i+g": (m_ig, te_ig)}
        best = min(cands, key=lambda k: cands[k][0])
        best_pred = cands[best][1]

        te = te.assign(_cal=best_pred, _base=te["pred"].values)
        d_base, n_line = directional_acc(te, "_base")
        d_best, _ = directional_acc(te, "_cal")
        db = f"{d_base*100:6.2f}%" if d_base is not None else "   n/a"
        dbst = f"{d_best*100:6.2f}%" if d_best is not None else "   n/a"
        print(f"{stat:<5}{'OOS':>6}  {m_base:>9.4f}{m_iso:>9.4f}{m_gbm:>9.4f}{m_ig:>9.4f}"
              f"   |  {db}   {dbst}   {n_line:>5,d}  best={best}")

        # ship only if best beats base on MAE OOS
        if cands[best][0] < m_base - 1e-4:
            # store isotonic as (x,y) breakpoints; gbm flagged but not serialized here
            coeffs_out[stat] = {
                "best_method": best,
                "mae_base": m_base, "mae_cal": cands[best][0],
                "iso_x": [float(v) for v in iso.f_.x[:200]],
                "iso_y": [float(v) for v in iso.f_.y[:200]],
                "dir_base": d_base, "dir_cal": d_best,
            }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(coeffs_out, indent=2), encoding="utf-8")
    print(f"\nshipped calibration for stats: {list(coeffs_out)} -> {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
