"""exp_minutes_projection.py — cheap proof: would a real minutes model fix PTS/REB?

Diagnosis showed OOF error is dominated by minutes surprise. This self-contained
experiment (touches NO production model) tests the ceiling and a realizable model:

  rate decomposition:  stat = (recent per-minute rate) x minutes
    baseline   = r5 x l10_min            (≈ what the model implicitly does)
    ORACLE     = r5 x ACTUAL_min          (perfect minutes -> the ceiling)
    minutes-MLP= r5 x proj_min            (a trained walk-forward minutes model)

Trains the minutes model on games before 2025-10-01, tests on 2025-26, and
compares MAE of each against the production OOF on the SAME (pid, date) rows.
If ORACLE >> OOF, minutes is the lever; if minutes-MLP approaches it, it's realizable.
GPU XGB per project rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import _load_gamelog_combined  # noqa: E402

import xgboost as xgb

OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
CUT = "2025-10-01"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build_rows(pids):
    """Per (pid, game) leak-free feature rows from gamelogs."""
    out = []
    for pid in pids:
        rows = _load_gamelog_combined(pid)  # sorted by date asc
        mins, ptss, rebs, dates = [], [], [], []
        for d, g in rows:
            m = _f(g.get("MIN"))
            if m is None or m < 1:
                # still advances rest clock but no rolling contribution
                dates_prev = dates[-1] if dates else None
                continue
            rest = (d - dates[-1]).days if dates else 3
            feat = None
            if len(mins) >= 3:
                arr_m = np.array(mins); arr_p = np.array(ptss); arr_r = np.array(rebs)
                def roll(a, k):
                    return float(a[-k:].mean())
                ewma = float(pd.Series(mins).ewm(span=5).mean().iloc[-1])
                feat = {
                    "pid": pid, "date": d, "rest": min(rest, 7),
                    "is_b2b": 1 if rest <= 1 else 0,
                    "l3_min": roll(arr_m, 3), "l5_min": roll(arr_m, 5),
                    "l10_min": roll(arr_m, 10), "ewma_min": ewma,
                    "std_min": float(arr_m[-10:].std()),
                    "prev_min": mins[-1], "gp": len(mins),
                    "l5_pts": roll(arr_p, 5), "l5_reb": roll(arr_r, 5),
                    "l5_pts_pm": roll(arr_p, 5) / max(roll(arr_m, 5), 1e-6),
                    "l5_reb_pm": roll(arr_r, 5) / max(roll(arr_m, 5), 1e-6),
                    "actual_min": m,
                    "actual_pts": _f(g.get("PTS")), "actual_reb": _f(g.get("REB")),
                }
            mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)
            rebs.append(_f(g.get("REB")) or 0.0); dates.append(d)
            if feat:
                out.append(feat)
    return pd.DataFrame(out)


def main():
    oof = pd.read_parquet(OOF)
    oof = oof[oof["game_date"].astype(str) >= CUT]
    pids = sorted(oof["player_id"].unique().tolist())
    print(f"building leak-free rows for {len(pids):,} players...")
    df = build_rows(pids)
    df["date"] = pd.to_datetime(df["date"])
    tr = df[df["date"] < CUT].copy()
    te = df[df["date"] >= CUT].copy()
    print(f"minutes-model train={len(tr):,}  test={len(te):,}")

    FEATS = ["rest", "is_b2b", "l3_min", "l5_min", "l10_min", "ewma_min",
             "std_min", "prev_min", "gp", "l5_pts", "l5_reb"]
    dtr = xgb.DMatrix(tr[FEATS], label=tr["actual_min"])
    dte = xgb.DMatrix(te[FEATS])
    params = {"objective": "reg:absoluteerror", "max_depth": 5, "eta": 0.05,
              "subsample": 0.8, "colsample_bytree": 0.8, "device": "cuda",
              "tree_method": "hist"}
    try:
        bst = xgb.train(params, dtr, num_boost_round=400)
    except Exception as exc:
        print(f"[cuda failed: {exc}; cpu]"); params["device"] = "cpu"
        bst = xgb.train(params, dtr, num_boost_round=400)
    te["proj_min"] = bst.predict(dte)

    mae_l10 = (te["l10_min"] - te["actual_min"]).abs().mean()
    mae_proj = (te["proj_min"] - te["actual_min"]).abs().mean()
    print(f"\nMINUTES projection MAE on 2025-26:")
    print(f"  l10_min baseline : {mae_l10:.3f}")
    print(f"  trained model    : {mae_proj:.3f}   ({(mae_l10-mae_proj)/mae_l10*100:+.1f}%)")

    # rate decomposition vs production OOF, joined on (pid, date)
    oof2 = oof.copy()
    oof2["date"] = pd.to_datetime(oof2["game_date"])
    for stat, ratecol, actcol in (("pts", "l5_pts_pm", "actual_pts"),
                                  ("reb", "l5_reb_pm", "actual_reb")):
        os_ = oof2[oof2["stat"] == stat][["player_id", "date", "oof_pred", "actual"]]
        m = te.merge(os_, left_on=["pid", "date"], right_on=["player_id", "date"], how="inner")
        if m.empty:
            print(f"  [{stat}] no join"); continue
        base = (m[ratecol] * m["l10_min"] - m[actcol]).abs().mean()
        oracle = (m[ratecol] * m["actual_min"] - m[actcol]).abs().mean()
        modeled = (m[ratecol] * m["proj_min"] - m[actcol]).abs().mean()
        oof_mae = (m["oof_pred"] - m["actual"]).abs().mean()
        # simple blend: average production OOF with rate*proj_min
        blend = ((m["oof_pred"] + m[ratecol] * m["proj_min"]) / 2 - m[actcol]).abs().mean()
        print(f"\n{stat.upper()} MAE (n={len(m):,}), joined to production OOF:")
        print(f"  production OOF            : {oof_mae:.3f}")
        print(f"  rate x l10_min (baseline) : {base:.3f}")
        print(f"  rate x proj_min (model)   : {modeled:.3f}")
        print(f"  rate x ACTUAL_min (ORACLE): {oracle:.3f}   <- minutes ceiling")
        print(f"  blend(OOF, rate x proj)   : {blend:.3f}   ({(oof_mae-blend)/oof_mae*100:+.1f}% vs OOF)")


if __name__ == "__main__":
    sys.exit(main())
